# Appendix: Code Snippets and Examples

## I. LLM client

### I.1. `src/agentprobe/llm/client.py`

```python
from __future__ import annotations
import asyncio, time
from typing import Any
import httpx
from openai import AsyncOpenAI
from openai import APIConnectionError, APITimeoutError, RateLimitError

from agentprobe.config import ModelConfig
from agentprobe.errors import LLMError
from agentprobe.llm.types import AssistantMessage, ToolCall, Usage
from agentprobe.llm.fixture import Fixture


class LLMClient:
    def __init__(self, cfg: ModelConfig, fixture: Fixture | None = None):
        self.cfg = cfg
        self.fixture = fixture
        self._http = httpx.AsyncClient(
            proxy=cfg.proxy,
            trust_env=False,
            timeout=httpx.Timeout(cfg.request_timeout_secs),
        )
        self._client = AsyncOpenAI(
            base_url=cfg.endpoint,
            api_key=cfg.api_key,
            http_client=self._http,
            max_retries=0,  # we retry manually to control fixture replay
        )
        self._seq = 0  # fixture sequencing

    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
                   ) -> AssistantMessage:
        if self.fixture is not None:
            self._seq += 1
            return await self.fixture.next_response(self._seq)

        last_exc: Exception | None = None
        for attempt in range(self.cfg.max_retries):
            try:
                return await self._stream(messages, tools)
            except (RateLimitError, APIConnectionError, APITimeoutError) as e:
                last_exc = e
                await asyncio.sleep(2 ** attempt + 0.1)
            except Exception as e:
                # Non-retriable
                raise LLMError(f"{type(e).__name__}: {e}") from e
        raise LLMError(f"LLM failed after {self.cfg.max_retries} retries: {last_exc}")

    async def _stream(self, messages, tools) -> AssistantMessage:
        t0 = time.monotonic()
        ttft: float | None = None
        content_parts: list[str] = []
        tool_calls_acc: dict[int, dict[str, Any]] = {}
        usage: Usage | None = None

        stream = await self._client.chat.completions.create(
            model=self.cfg.model,
            messages=messages,  # type: ignore[arg-type]
            tools=tools,        # type: ignore[arg-type]
            tool_choice="auto" if tools else "none",
            temperature=self.cfg.temperature,
            stream=True,
            stream_options={"include_usage": True},
        )

        async for chunk in stream:
            if ttft is None:
                ttft = (time.monotonic() - t0) * 1000
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                content_parts.append(delta.content)
            if delta and delta.tool_calls:
                for tc in delta.tool_calls:
                    acc = tool_calls_acc.setdefault(tc.index, {
                        "id": "", "name": "", "arguments": "",
                    })
                    if tc.id:
                        acc["id"] = tc.id
                    if tc.function and tc.function.name:
                        acc["name"] += tc.function.name
                    if tc.function and tc.function.arguments:
                        acc["arguments"] += tc.function.arguments
            if chunk.usage is not None:
                usage = Usage(
                    prompt_tokens=chunk.usage.prompt_tokens,
                    completion_tokens=chunk.usage.completion_tokens,
                    total_tokens=chunk.usage.total_tokens,
                )

        latency = (time.monotonic() - t0) * 1000
        import json as _json
        calls = [
            ToolCall(id=v["id"], name=v["name"], arguments=_json.loads(v["arguments"] or "{}"))
            for v in tool_calls_acc.values()
        ]
        return AssistantMessage(
            content="".join(content_parts) or None,
            tool_calls=calls,
            usage=usage,
            ttft_ms=ttft,
            latency_ms=latency,
        )

    async def aclose(self) -> None:
        await self._http.aclose()
```

### I.2. `src/agentprobe/llm/fixture.py`

```python
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
                for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
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

    def record(self, seq: int, turn: int, msg: AssistantMessage,
               request_meta: dict[str, Any]) -> None:
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
                "usage": (
                    {
                        "prompt_tokens": msg.usage.prompt_tokens,
                        "completion_tokens": msg.usage.completion_tokens,
                        "total_tokens": msg.usage.total_tokens,
                    } if msg.usage else None
                ),
            },
        }
        self._fp.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self._fp.flush()

    def close(self) -> None:
        if self._fp is not None:
            self._fp.close()
```

**Wiring:** in `LLMClient._stream`, after a successful response in record mode, call `self.fixture.record(seq, turn, msg, request_meta)`. In replay mode, `next_response` is invoked by `chat`. The `seq` counter increments on every LLM call, not every turn.

---

