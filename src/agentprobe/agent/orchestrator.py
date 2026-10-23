"""The main agent turn loop."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from agentprobe.agent.observer import Observer, SessionCtx
from agentprobe.errors import LimitExceeded

if TYPE_CHECKING:
    from agentprobe.agent.subagent import SubagentSpawner
    from agentprobe.config import Limits
from agentprobe.llm.client import LLMClient
from agentprobe.llm.types import Message, ToolCall, ToolResult
from agentprobe.logging.console import Console
from agentprobe.logging.yaml_logger import Logger
from agentprobe.tools.client import MCPToolClient

PARALLEL_SAFE = {
    "read",
    "read_doc",
    "read_skill",
    "command_execute",
    "execute_shell",
    "syntax_check",
}


class Orchestrator:
    def __init__(
        self,
        llm: LLMClient,
        tools: MCPToolClient,
        observer: Observer,
        logger: Logger,
        limits: Limits,
        spawner: SubagentSpawner | None = None,
        is_repl: bool = False,
        console: Console | None = None,
        system_refresh: Callable[[], str] | None = None,
    ):
        self.llm = llm
        self.tools = tools
        self.observer = observer
        self.logger = logger
        self.limits = limits
        self.spawner = spawner
        self.is_repl = is_repl
        self.console = console
        self.system_refresh = system_refresh

    async def turn(
        self, messages: list[Message], user_input: str, ctx: SessionCtx
    ) -> str | None:
        """Run one full turn. Returns the final assistant text, or None if aborted."""
        ctx.turn += 1
        turn_start = time.monotonic()
        messages.append(Message(role="user", content=user_input))
        self.logger.log("user_message", turn=ctx.turn, text=user_input)
        if self.console:
            self.console.user(user_input)

        if self.system_refresh:
            messages[0].content = self.system_refresh()

        tools_schema = await self.tools.schemas()
        if self.spawner is not None:
            tools_schema.append(self.spawner.tool_schema())

        while True:
            self.logger.log(
                "llm_request",
                turn=ctx.turn,
                messages_count=len(messages),
                tools_count=len(tools_schema),
            )
            response = await self.llm.chat(
                [m.to_openai() for m in messages], tools_schema, turn=ctx.turn
            )
            if response.usage is not None:
                ctx.usage_total["tokens_in"] += response.usage.prompt_tokens
                ctx.usage_total["tokens_out"] += response.usage.completion_tokens
                ctx.usage_total["tokens_total"] += response.usage.total_tokens
            self.logger.log(
                "llm_response",
                turn=ctx.turn,
                content=response.content,
                tool_calls=[
                    {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                    for tc in response.tool_calls
                ],
                usage=response.usage.__dict__ if response.usage else None,
                ttft_ms=response.ttft_ms,
                latency_ms=response.latency_ms,
            )
            if response.content and self.console:
                self.console.assistant(response.content)

            await self.observer.on_assistant_message(response, ctx)

            messages.append(
                Message(
                    role="assistant",
                    content=response.content,
                    tool_calls=response.tool_calls or None,
                )
            )

            if not response.tool_calls:
                await self.observer.on_turn_end(ctx)
                if self.console:
                    turn_ms = (time.monotonic() - turn_start) * 1000
                    self.console.tokens_line(
                        response.usage.prompt_tokens if response.usage else None,
                        response.usage.completion_tokens if response.usage else None,
                        turn_ms,
                        turn_ms,
                    )
                return response.content

            for tc in response.tool_calls:
                await self.observer.on_tool_call_pending(tc, ctx)

            for tc in response.tool_calls:
                self.logger.log(
                    "tool_call",
                    turn=ctx.turn,
                    call_id=tc.id,
                    name=tc.name,
                    arguments=tc.arguments,
                )

            results = await self._execute_tools(response.tool_calls)
            for res in results:
                await self.observer.on_tool_result(res, ctx)
                self.logger.log(
                    "tool_result",
                    turn=ctx.turn,
                    call_id=res.call_id,
                    name=res.name,
                    is_error=res.is_error,
                    duration_ms=res.duration_ms,
                    content=res.content,
                    artifacts=res.artifacts,
                )
                if self.console:
                    self.console.tool(res.name, {}, res.duration_ms)
                messages.append(
                    Message(
                        role="tool",
                        content=res.content,
                        tool_call_id=res.call_id,
                        name=res.name,
                    )
                )

            if not self.is_repl:
                self._check_limits(ctx, turn_start)

        return None

    async def _execute_tools(self, calls: list[ToolCall]) -> list[ToolResult]:
        if calls and all(c.name in PARALLEL_SAFE for c in calls):
            return list(await asyncio.gather(*(self._execute_one(c) for c in calls)))
        out: list[ToolResult] = []
        for c in calls:
            out.append(await self._execute_one(c))
        return out

    async def _execute_one(self, call: ToolCall) -> ToolResult:
        t0 = time.monotonic()
        try:
            if call.name == "spawn_agent" and self.spawner is not None:
                res = await self.spawner.call(call.arguments)
            else:
                res = await self.tools.call_tool(call.name, call.arguments)
        except Exception as e:  # transport/parse errors become error results
            res = ToolResult(
                call_id=call.id, name=call.name, content=str(e), is_error=True
            )
        res.duration_ms = (time.monotonic() - t0) * 1000
        res.call_id = call.id
        return res

    def _check_limits(self, ctx: SessionCtx, turn_start: float) -> None:
        if ctx.turn > self.limits.max_turns:
            raise LimitExceeded("max_turns", self.limits.max_turns, ctx.turn)
        if ctx.tools_count > self.limits.max_tool_calls:
            raise LimitExceeded(
                "max_tool_calls", self.limits.max_tool_calls, ctx.tools_count
            )
        elapsed = time.monotonic() - turn_start
        if elapsed > self.limits.max_duration_secs:
            raise LimitExceeded(
                "max_duration_secs", self.limits.max_duration_secs, int(elapsed)
            )
