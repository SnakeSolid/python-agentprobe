"""JSONL fixtures for `--record` / `--replay`.

The fixture format is the sole exception to the "YAML only" rule for
spec-defined artifacts: it must be replayable line-by-line.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentprobe.errors import ReplayError
from agentprobe.llm.types import AssistantMessage, ToolCall, Usage


class Fixture:
    """One fixture per scenario. JSONL: one JSON object per LLM response line."""

    def __init__(self, path: Path, mode: str):  # mode: "record" | "replay"
        self.path = path
        self.mode = mode
        self._lines: list[dict[str, Any]] = []
        self._fp: Any = None
        self._seq = 0  # owned by the fixture so parent+subagents stay in lock-step
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

    async def next_response(self) -> AssistantMessage:
        if self.mode == "replay":
            self._seq += 1
            if not self._lines or self._seq > len(self._lines):
                raise ReplayError(f"fixture exhausted at seq={self._seq}: {self.path}")
            line = self._lines[self._seq - 1]
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
        turn: int,
        msg: AssistantMessage,
        request_meta: dict[str, Any],
    ) -> None:
        if self._fp is None:
            return
        self._seq += 1
        payload = {
            "seq": self._seq,
            "turn": turn,
            "request_meta": request_meta,
            "response": {
                "content": msg.content,
                "tool_calls": [
                    {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                    for tc in msg.tool_calls
                ],
                "usage": (
                    {
                        "prompt_tokens": msg.usage.prompt_tokens,
                        "completion_tokens": msg.usage.completion_tokens,
                        "total_tokens": msg.usage.total_tokens,
                    }
                    if msg.usage
                    else None
                ),
            },
        }
        self._fp.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self._fp.flush()

    def close(self) -> None:
        if self._fp is not None:
            self._fp.close()
            self._fp = None
