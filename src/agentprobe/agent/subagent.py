from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentprobe.agent.observer import NoOpObserver, SessionCtx
from agentprobe.agent.ui import NoOpUi
from agentprobe.config import Config
from agentprobe.errors import LimitExceeded, LLMError, ReplayError, ScenarioAbort
from agentprobe.llm.client import LLMClient
from agentprobe.llm.types import Message, ToolResult
from agentprobe.logging.yaml_logger import Logger, YamlLogger
from agentprobe.tools.client import MCPToolClient


class SubLogger:
    """Logs subagent events to the parent's file with a sub-session id."""

    def __init__(self, parent_path: Path, sub_session_id: str, parent_session_id: str):
        self._inner = YamlLogger(parent_path, session_id=sub_session_id)
        self.path = parent_path
        self.session_id = sub_session_id
        self._parent = parent_session_id

    def log(self, event: str, **kwargs: Any) -> None:
        self._inner.log(event, parent_session_id=self._parent, **kwargs)

    def close(self) -> None:
        self._inner.close()


class SubagentSpawner:
    def __init__(
        self,
        *,
        cfg: Config,
        parent_session_id: str,
        system_text: str,
        tools_client: MCPToolClient,
        logger: Logger,  # parent logger (provides path)
        enabled_tools: list[str],
    ):
        self.cfg = cfg
        self.parent_session_id = parent_session_id
        self.system_text = system_text
        self.tools = tools_client
        self.logger = logger
        self.enabled_tools = enabled_tools
        self._seq = 0

    def tool_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "spawn_agent",
                "description": (
                    "Delegate an isolated subtask to a subagent. "
                    "The subagent does not see the main dialogue history."
                ),
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

        self._seq += 1
        sub_session = f"{self.parent_session_id}/sub-{self._seq}"
        task = str(args.get("task", ""))
        context = args.get("context")

        user_input = f"Context:\n{context}\n\nTask:\n{task}" if context else task
        messages = [Message(role="system", content=self.system_text)]
        sub_ctx = SessionCtx()
        sub_logger = SubLogger(self.logger.path, sub_session, self.parent_session_id)
        assert self.cfg.models.subagent is not None
        sub_llm = LLMClient(self.cfg.models.subagent)
        sub_tools = self.tools
        sub_tools_enabled = [t for t in self.enabled_tools if t != "spawn_agent"]

        orchestrator = Orchestrator(
            llm=sub_llm,
            tools=sub_tools,
            observer=NoOpObserver(),
            logger=sub_logger,
            limits=self.cfg.limits.subagent,
            ui=NoOpUi(),
            spawner=None,
            is_repl=False,
            enabled_tools=sub_tools_enabled,
        )

        is_error = False
        error: str | None = None
        answer: str | None = None
        try:
            answer = await orchestrator.turn(messages, user_input, sub_ctx)
        except ScenarioAbort as e:
            is_error, error = True, f"subagent aborted: {e.reason}"
        except LimitExceeded as e:
            is_error, error = True, f"subagent aborted: {e.reason}"
        except (LLMError, ReplayError) as e:
            is_error, error = True, f"subagent aborted: {e}"
        finally:
            await sub_llm.aclose()
            sub_logger.close()

        if is_error:
            return ToolResult(
                call_id="",
                name="spawn_agent",
                content=json.dumps(
                    {
                        "answer": answer,
                        "usage": {"tokens_in": None, "tokens_out": None},
                        "turns": sub_ctx.turn,
                        "tools": sub_ctx.tools_histogram,
                        "is_error": True,
                        "error": error,
                    },
                    ensure_ascii=False,
                ),
                is_error=True,
                artifacts={"session_id": sub_session},
            )

        payload = {
            "answer": answer,
            "usage": {
                "tokens_in": sub_ctx.tokens_in if sub_ctx.tokens_total else None,
                "tokens_out": sub_ctx.tokens_out if sub_ctx.tokens_total else None,
            },
            "turns": sub_ctx.turn,
            "tools": sub_ctx.tools_histogram,
            "is_error": False,
            "error": None,
        }
        return ToolResult(
            call_id="",
            name="spawn_agent",
            content=json.dumps(payload, ensure_ascii=False),
            is_error=False,
            artifacts={"session_id": sub_session},
        )
