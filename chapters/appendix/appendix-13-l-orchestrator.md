# Appendix: Code Snippets and Examples

## L. Orchestrator

### L.1. `src/agentprobe/agent/orchestrator.py` (simplified, single session)

```python
from __future__ import annotations
import asyncio, json, time
from typing import Any

from agentprobe.agent.observer import Observer, SessionCtx
from agentprobe.agent.subagent import SubagentSpawner
from agentprobe.errors import LimitExceeded, ScenarioAbort
from agentprobe.llm.client import LLMClient
from agentprobe.llm.types import AssistantMessage, Message, ToolCall, ToolResult
from agentprobe.logging.yaml_logger import YamlLogger
from agentprobe.tools.client import MCPToolClient


class Orchestrator:
    def __init__(
        self,
        llm: LLMClient,
        tools: MCPToolClient,
        observer: Observer,
        logger: YamlLogger,
        limits,
        spawner: SubagentSpawner | None = None,
        is_repl: bool = False,
    ):
        self.llm = llm
        self.tools = tools
        self.observer = observer
        self.logger = logger
        self.limits = limits
        self.spawner = spawner
        self.is_repl = is_repl

    async def turn(self, messages: list[Message], user_input: str,
                   ctx: SessionCtx) -> str | None:
        """Run one full turn. Returns final assistant text, or None if aborted."""
        ctx.turn += 1
        turn_start = time.monotonic()
        messages.append(Message(role="user", content=user_input))
        self.logger.log("user_message", turn=ctx.turn, text=user_input)

        tools_schema = await self.tools.schemas()
        if self.spawner is not None:
            tools_schema.append(self.spawner.tool_schema())

        try:
            while True:
                self.logger.log("llm_request", turn=ctx.turn,
                                messages_count=len(messages),
                                tools_count=len(tools_schema))
                response = await self.llm.chat(
                    [m.to_openai() for m in messages], tools_schema
                )
                self.logger.log(
                    "llm_response", turn=ctx.turn,
                    content=response.content,
                    tool_calls=[
                        {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                        for tc in response.tool_calls
                    ],
                    usage=response.usage.__dict__ if response.usage else None,
                    ttft_ms=response.ttft_ms,
                    latency_ms=response.latency_ms,
                )
                await self.observer.on_assistant_message(response, ctx)

                messages.append(Message(
                    role="assistant",
                    content=response.content,
                    tool_calls=response.tool_calls or None,
                ))

                if not response.tool_calls:
                    await self.observer.on_turn_end(ctx)
                    return response.content

                # Pre-check all pending calls
                for tc in response.tool_calls:
                    await self.observer.on_tool_call_pending(tc, ctx)

                # Execute
                results = await self._execute_tools(response.tool_calls)
                for res in results:
                    await self.observer.on_tool_result(res, ctx)
                    self.logger.log("tool_result", turn=ctx.turn,
                                    call_id=res.call_id, name=res.name,
                                    is_error=res.is_error,
                                    duration_ms=res.duration_ms,
                                    content=res.content,
                                    artifacts=res.artifacts)
                    messages.append(Message(
                        role="tool",
                        content=res.content,
                        tool_call_id=res.call_id,
                        name=res.name,
                    ))

                # Between-iteration limits
                if not self.is_repl:
                    self._check_limits(ctx, turn_start)
        except ScenarioAbort:
            raise
        except LimitExceeded:
            raise

    async def _execute_tools(self, calls: list[ToolCall]) -> list[ToolResult]:
        # Parallel only if ALL calls are parallel-safe.
        if all(c.name in PARALLEL_SAFE for c in calls):
            return await asyncio.gather(*(self._execute_one(c) for c in calls))
        out = []
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
            raise LimitExceeded("max_duration_secs",
                                self.limits.max_duration_secs, int(elapsed))


PARALLEL_SAFE = {
    "read", "read_doc", "read_skill",
    "command_execute", "execute_shell", "syntax_check",
}
```

### L.2. `src/agentprobe/agent/subagent.py` (sketch)

```python
from __future__ import annotations
from typing import Any

from agentprobe.llm.types import ToolResult


class SubagentSpawner:
    def __init__(self, cfg, limits, llm_factory, tools_factory, prompt, observer_factory):
        self.cfg = cfg
        self.limits = limits
        self._llm_factory = llm_factory
        self._tools_factory = tools_factory
        self._prompt = prompt
        self._observer_factory = observer_factory

    def tool_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "spawn_agent",
                "description": "Delegate an isolated subtask to a subagent. "
                               "The subagent does not see the main dialogue history.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task": {"type": "string", "minLength": 1, "maxLength": 8000},
                        "context": {"type": "string", "maxLength": 32000},
                    },
                    "required": ["task"],
                },
            },
        }

    async def call(self, args: dict[str, Any]) -> ToolResult:
        from agentprobe.agent.orchestrator import Orchestrator
        from agentprobe.agent.observer import SessionCtx, NoOpObserver
        # Build an isolated session (no spawn_agent in the subagent tool list).
        # ... (see §8 for full behavior; return ToolResult with JSON payload)
        return ToolResult(call_id="", name="spawn_agent", content='{"answer": "TODO"}')
```

The subagent loop mirrors the main loop with its own `Session`, `Messages`, and `Limits`. On any error, return `ToolResult(is_error=True, content="subagent aborted: ...")` to the parent.

---

