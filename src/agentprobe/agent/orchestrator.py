from __future__ import annotations

import asyncio
import time

from agentprobe.agent.observer import Observer, SessionCtx
from agentprobe.agent.subagent import SubagentSpawner
from agentprobe.agent.ui import Ui, error_label
from agentprobe.config import Limits
from agentprobe.errors import LimitExceeded, ScenarioAbort
from agentprobe.llm.client import LLMClient
from agentprobe.llm.types import Message, ToolCall, ToolResult
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
        ui: Ui,
        spawner: SubagentSpawner | None = None,
        is_repl: bool = False,
        enabled_tools: list[str] | None = None,
    ):
        self.llm = llm
        self.tools = tools
        self.observer = observer
        self.logger = logger
        self.limits = limits
        self.ui = ui
        self.spawner = spawner
        self.is_repl = is_repl
        self.enabled_tools = enabled_tools

    async def turn(
        self,
        messages: list[Message],
        user_input: str,
        ctx: SessionCtx,
    ) -> str | None:
        """Run one full turn. Returns final assistant text, or None if aborted."""
        ctx.turn += 1
        self._current_turn = ctx.turn
        turn_start = time.monotonic()
        messages.append(Message(role="user", content=user_input))
        self.logger.log("user_message", turn=ctx.turn, text=user_input)

        tools_schema = await self.tools.schemas(enabled=self.enabled_tools)
        if self.spawner is not None and (
            self.enabled_tools is None or "spawn_agent" in self.enabled_tools
        ):
            tools_schema.append(self.spawner.tool_schema())
        self.ui.turn_start(
            ctx, tools_count=len(tools_schema), messages_count=len(messages)
        )

        completed = False
        try:
            while True:
                self.logger.log(
                    "llm_request",
                    turn=ctx.turn,
                    messages_count=len(messages),
                    tools_count=len(tools_schema),
                )
                self.ui.segment_start()
                try:
                    response = await self.llm.chat(
                        [m.to_openai() for m in messages],
                        tools_schema,
                        turn=ctx.turn,
                        on_chunk=self.ui.chunk,
                    )
                finally:
                    self.ui.segment_end()
                self.logger.log(
                    "llm_response",
                    turn=ctx.turn,
                    content=response.content,
                    tool_calls=[
                        {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                        for tc in response.tool_calls
                    ],
                    usage=response.usage.as_dict() if response.usage else None,
                    ttft_ms=response.ttft_ms,
                    latency_ms=response.latency_ms,
                )
                await self.observer.on_assistant_message(response, ctx)
                if response.usage is not None:
                    ctx.tokens_in += response.usage.prompt_tokens
                    ctx.tokens_out += response.usage.completion_tokens
                    ctx.tokens_total += response.usage.total_tokens

                messages.append(
                    Message(
                        role="assistant",
                        content=response.content,
                        tool_calls=response.tool_calls or None,
                    )
                )

                if not response.tool_calls:
                    await self.observer.on_turn_end(ctx)
                    self.logger.log(
                        "turn_end",
                        turn=ctx.turn,
                        duration_ms=(time.monotonic() - turn_start) * 1000,
                        usage=response.usage.as_dict() if response.usage else None,
                        tools=dict(ctx.tools_histogram),
                    )
                    self.ui.turn_end(ctx, (time.monotonic() - turn_start) * 1000)
                    completed = True
                    return response.content

                # Pre-check all pending calls (may abort before any execution)
                for tc in response.tool_calls:
                    await self.observer.on_tool_call_pending(tc, ctx)

                results = await self._execute_tools(response.tool_calls)
                # Results are appended in original tool-call order
                for call, res in zip(response.tool_calls, results):
                    self.ui.tool(
                        call.name,
                        call.arguments,
                        res.duration_ms,
                        error_label(res),
                    )
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
        except ScenarioAbort:  # noqa: TRY203 - propagate to runner/CLI
            raise
        except LimitExceeded:  # noqa: TRY203 - propagate to runner/CLI
            raise
        finally:
            if not completed:
                self.ui.turn_end(
                    ctx, (time.monotonic() - turn_start) * 1000, partial=True
                )

    async def _execute_tools(self, calls: list[ToolCall]) -> list[ToolResult]:
        for c in calls:
            self.logger.log(
                "tool_call",
                turn=self._current_turn,
                call_id=c.id,
                name=c.name,
                arguments=c.arguments,
            )
        if all(c.name in PARALLEL_SAFE for c in calls):
            return list(await asyncio.gather(*(self._execute_one(c) for c in calls)))
        out: list[ToolResult] = []
        for c in calls:
            out.append(await self._execute_one(c))
        return out

    async def _execute_one(self, call: ToolCall) -> ToolResult:
        t0 = time.monotonic()
        if call.name == "spawn_agent" and self.spawner is not None:
            res = await self.spawner.call(call.arguments)
        else:
            res = await self.tools.call_tool(call.name, call.arguments)
        res.duration_ms = (time.monotonic() - t0) * 1000
        res.call_id = call.id
        return res

    def _check_limits(self, ctx: SessionCtx, turn_start: float) -> None:
        if ctx.turn > self.limits.max_turns:
            raise LimitExceeded("max_turns", self.limits.max_turns, ctx.turn)
        if ctx.tools_count > self.limits.max_tool_calls:
            raise LimitExceeded("max_tool_calls", self.limits.max_tool_calls, ctx.tools_count)
        elapsed = time.monotonic() - turn_start
        if elapsed > self.limits.max_duration_secs:
            raise LimitExceeded("max_duration_secs", self.limits.max_duration_secs, int(elapsed))
