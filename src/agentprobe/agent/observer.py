from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

from agentprobe.errors import ScenarioAbort
from agentprobe.llm.types import AssistantMessage, ToolCall, ToolResult
from agentprobe.scenario.schema import Checks


@dataclass
class SessionCtx:
    turn: int = 0
    agent_messages: int = 0
    tools_count: int = 0
    tools_histogram: dict[str, int] = field(default_factory=dict)
    context_tokens_max: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_total: int = 0
    last_assistant_text: str = ""
    final_text_for_checks: str = ""


class Observer(Protocol):
    async def on_assistant_message(self, msg: AssistantMessage, ctx: SessionCtx) -> None: ...
    async def on_tool_call_pending(self, call: ToolCall, ctx: SessionCtx) -> None: ...
    async def on_tool_result(self, res: ToolResult, ctx: SessionCtx) -> None: ...
    async def on_turn_end(self, ctx: SessionCtx) -> None: ...


class NoOpObserver:
    async def on_assistant_message(self, msg: AssistantMessage, ctx: SessionCtx) -> None: ...
    async def on_tool_call_pending(self, call: ToolCall, ctx: SessionCtx) -> None: ...
    async def on_tool_result(self, res: ToolResult, ctx: SessionCtx) -> None: ...
    async def on_turn_end(self, ctx: SessionCtx) -> None: ...


class ScenarioObserver:
    def __init__(self, checks: Checks):
        self.checks = checks

    async def on_assistant_message(self, msg: AssistantMessage, ctx: SessionCtx) -> None:
        ctx.agent_messages += 1
        if self.checks.max_agent_messages is not None and ctx.agent_messages > self.checks.max_agent_messages:
            raise ScenarioAbort("max_agent_messages", exit_code=1)

        if msg.usage is not None:
            used = msg.usage.prompt_tokens + msg.usage.completion_tokens
            ctx.context_tokens_max = max(ctx.context_tokens_max, used)
            if self.checks.max_context_tokens is not None and used > self.checks.max_context_tokens:
                raise ScenarioAbort("max_context_tokens", exit_code=1)

        if msg.content:
            ctx.last_assistant_text = msg.content
            if not msg.tool_calls:
                ctx.final_text_for_checks = msg.content

    async def on_tool_call_pending(self, call: ToolCall, ctx: SessionCtx) -> None:
        if call.name in self.checks.forbidden_tools:
            raise ScenarioAbort(f"forbidden_tool:{call.name}", exit_code=1)

    async def on_tool_result(self, res: ToolResult, ctx: SessionCtx) -> None:
        ctx.tools_count += 1
        ctx.tools_histogram[res.name] = ctx.tools_histogram.get(res.name, 0) + 1

    async def on_turn_end(self, ctx: SessionCtx) -> None:
        pass

    def final_checks(self, ctx: SessionCtx) -> list[str]:
        failures: list[str] = []
        text = ctx.final_text_for_checks
        for pat in self.checks.final_include:
            if not re.search(pat, text, re.MULTILINE):
                failures.append(f'final_include: missing "{pat}"')
        for pat in self.checks.final_exclude:
            if re.search(pat, text, re.MULTILINE):
                failures.append(f'final_exclude: matched "{pat}"')
        for required in self.checks.required_tools:
            if required not in ctx.tools_histogram:
                failures.append(f"required_tools: {required} not called")
        return failures
