"""Subagent support (`spawn_agent`).

Subagents run an isolated, depth-1 agent loop with their own session, model,
limits and tools (the parent's enabled set, without ``spawn_agent``). Their
context is independent of the main dialogue history.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentprobe.agent.observer import NoOpObserver, SessionCtx
from agentprobe.agent.orchestrator import Orchestrator
from agentprobe.config import Config
from agentprobe.errors import LimitExceeded, LLMError, ScenarioAbort
from agentprobe.llm.client import LLMClient
from agentprobe.llm.fixture import Fixture
from agentprobe.llm.types import Message, ToolResult
from agentprobe.logging.yaml_logger import YamlLogger
from agentprobe.prompt.builder import PromptBuilder
from agentprobe.skills.loader import SkillLoader
from agentprobe.tools.client import MCPToolClient


def _abort_result(reason: str) -> ToolResult:
    payload = {
        "answer": "",
        "usage": {"tokens_in": None, "tokens_out": None},
        "turns": 0,
        "tools": {},
        "is_error": True,
        "error": f"subagent aborted: {reason}",
    }
    return ToolResult(
        call_id="", name="spawn_agent", content=json.dumps(payload), is_error=True
    )


class SubagentSpawner:
    def __init__(
        self,
        cfg: Config,
        config_path: Path,
        parent_logger: YamlLogger,
        parent_session_id: str,
        parent_tools: MCPToolClient,
        fixture: Fixture | None,
    ):
        self.cfg = cfg
        self._config_path = config_path
        self._parent_logger = parent_logger
        self._parent_session_id = parent_session_id
        self._parent_tools = parent_tools
        self._fixture = fixture
        self._index = 0

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
        self._index += 1
        sub_session_id = f"{self._parent_session_id}/sub-{self._index}"
        logger = _SubLogger(
            self._parent_logger, sub_session_id, self._parent_session_id
        )
        task = args.get("task", "")
        context = args.get("context") or ""
        llm: LLMClient | None = None
        try:
            # The spawner is only constructed when a subagent model is configured.
            assert self.cfg.models.subagent is not None
            llm = LLMClient(self.cfg.models.subagent, fixture=self._fixture)
            skills = SkillLoader(self.cfg.app.skills_dir)
            sub_prompt_file = self.cfg.app.subagent_prompt_file or self.cfg.app.prompt_file
            builder = PromptBuilder(sub_prompt_file, self.cfg.app.memory_file, skills)
            system_text = self._build_system(builder)

            messages = [Message(role="system", content=system_text)]
            if context:
                messages.append(Message(role="user", content=context))
            messages.append(Message(role="user", content=task))

            orchestrator = Orchestrator(
                llm=llm,
                tools=self._parent_tools,
                observer=NoOpObserver(),
                logger=logger,
                limits=self.cfg.limits.subagent,
                spawner=None,
                is_repl=False,
                console=None,
            )

            ctx = SessionCtx()
            answer = await orchestrator.turn(messages, task, ctx)

            usage: dict[str, int | None] = {
                "tokens_in": None,
                "tokens_out": None,
            }
            if llm.last_usage is not None:
                usage = {
                    "tokens_in": llm.last_usage.prompt_tokens,
                    "tokens_out": llm.last_usage.completion_tokens,
                }
            payload = {
                "answer": answer or "",
                "usage": usage,
                "turns": ctx.turn,
                "tools": dict(ctx.tools_histogram),
                "is_error": False,
                "error": None,
            }
            return ToolResult(
                call_id="", name="spawn_agent", content=json.dumps(payload)
            )
        except (LimitExceeded, LLMError, ScenarioAbort) as e:
            logger.log("subagent_aborted", reason=str(e))
            return _abort_result(str(e))
        finally:
            if llm is not None:
                await llm.aclose()

    @staticmethod
    def _build_system(builder: PromptBuilder) -> str:
        parts = [builder.static.rstrip()]
        skills = builder.skills.available_skills_block()
        parts.append("# AVAILABLE SKILLS")
        parts.append(skills or "(none)")
        return "\n\n".join(parts)


class _SubLogger:
    """Writes subagent events into the parent's YAML stream with its own session id."""

    def __init__(self, parent_logger: YamlLogger, session_id: str, parent_session_id: str):
        self.parent = parent_logger
        self.session_id = session_id
        self.parent_session_id = parent_session_id

    def log(self, event: str, **kwargs: Any) -> None:
        self.parent.log(event, parent_session_id=self.parent_session_id, **kwargs)

    def close(self) -> None:
        pass
