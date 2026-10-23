from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentprobe.errors import ReplayError
from agentprobe.llm.types import AssistantMessage, ToolCall, Usage


class Fixture:
    """One fixture per scenario. JSONL: one line per LLM response."""

    def __init__(self, path: Path, mode: str):  # mode: "record" | "replay"
        self.path = path
        self.mode = mode
        self._lines: list[dict[str, Any]] = []
        self._fp = None
        if mode == "replay":
            if not path.exists():
                raise ReplayError(f"fixture not found: {path}")
            self._lines = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        else:  # record
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._fp = self.path.open("w", encoding="utf-8")

    async def next_response(self, seq: int) -> AssistantMessage:
        if self.mode == "replay":
            if seq > len(self._lines):
                raise ReplayError(f"fixture exhausted at seq={seq}: {self.path}")
            line = self._lines[seq - 1]
            resp = line["response"]
            return AssistantMessage(
                content=resp.get("content"),
                tool_calls=[
                    ToolCall(id=tc["id"], name=tc["name"], arguments=tc["arguments"])
                    for tc in resp.get("tool_calls", [])
                ],
                usage=Usage(**resp["usage"]) if resp.get("usage") else None,
            )
        raise RuntimeError("record mode does not call next_response")

    def record(
        self,
        seq: int,
        turn: int | None,
        msg: AssistantMessage,
        request_meta: dict[str, Any],
    ) -> None:
        if self._fp is None:
            return
        payload = {
            "seq": seq,
            "turn": turn,
            "request_meta": request_meta,
            "response": {
                "content": msg.content,
                "tool_calls": [
                    {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                    for tc in msg.tool_calls
                ],
                "usage": (msg.usage.as_dict() if msg.usage else None),
            },
        }
        self._fp.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self._fp.flush()

    def close(self) -> None:
        if self._fp is not None:
            self._fp.close()
