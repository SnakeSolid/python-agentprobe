from __future__ import annotations

from agentprobe.agent.observer import SessionCtx
from agentprobe.llm.types import Message


class Session:
    """Holds the message history and per-session context counters."""

    def __init__(self, system_text: str):
        self.messages: list[Message] = [Message(role="system", content=system_text)]
        self.ctx = SessionCtx()

    @property
    def system_message(self) -> Message:
        return self.messages[0]

    def append(self, msg: Message) -> None:
        self.messages.append(msg)
