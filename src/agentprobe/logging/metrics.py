from __future__ import annotations

from typing import Any

from agentprobe.llm.types import Usage


class Metrics:
    """Per-session aggregate metrics."""

    def __init__(self) -> None:
        self.turns = 0
        self.agent_messages = 0
        self.tools: dict[str, int] = {}
        self.context_tokens_max: int = 0
        self.prompt_tokens: int | None = None
        self.completion_tokens: int | None = None
        self.total_tokens: int | None = None
        self.errors = 0

    def add_usage(self, usage: Usage | None) -> None:
        if usage is None:
            return
        self.prompt_tokens = (self.prompt_tokens or 0) + usage.prompt_tokens
        self.completion_tokens = (self.completion_tokens or 0) + usage.completion_tokens
        self.total_tokens = (self.total_tokens or 0) + usage.total_tokens
        self.context_tokens_max = max(self.context_tokens_max, usage.total_tokens)

    def add_tool(self, name: str) -> None:
        self.tools[name] = self.tools.get(name, 0) + 1

    def usage_dict(self) -> dict[str, int]:
        return {
            "tokens_in": self.prompt_tokens or 0,
            "tokens_out": self.completion_tokens or 0,
            "tokens_total": self.total_tokens or 0,
        }

    def as_dict(self) -> dict[str, Any]:
        return self.usage_dict()
