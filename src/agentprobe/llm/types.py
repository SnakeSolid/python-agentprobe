"""Core message and response types shared across the agent."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["system", "user", "assistant", "tool"]


@dataclass
class Usage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class AssistantMessage:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage | None = None
    ttft_ms: float | None = None
    latency_ms: float | None = None
    raw: dict[str, Any] | None = None  # original response for record


@dataclass
class ToolResult:
    call_id: str
    name: str
    content: str
    is_error: bool = False
    duration_ms: float = 0.0
    artifacts: dict[str, Any] = field(default_factory=dict)


@dataclass
class Message:
    role: Role
    content: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    name: str | None = None

    def to_openai(self) -> dict[str, Any]:
        out: dict[str, Any] = {"role": self.role}
        if self.content is not None:
            out["content"] = self.content
        if self.tool_calls:
            out["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                }
                for tc in self.tool_calls
            ]
        if self.tool_call_id is not None:
            out["tool_call_id"] = self.tool_call_id
        if self.name is not None:
            out["name"] = self.name
        return out
