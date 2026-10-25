from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from typing import Any

import httpx
from openai import APIConnectionError, APITimeoutError, AsyncOpenAI, RateLimitError

from agentprobe.config import ModelConfig
from agentprobe.errors import LLMError
from agentprobe.llm.fixture import Fixture
from agentprobe.llm.types import AssistantMessage, ToolCall, Usage

OnChunk = Callable[[str], None]

_RETRYABLE = (
    RateLimitError,
    APIConnectionError,
    APITimeoutError,
    httpx.TimeoutException,
    httpx.ConnectError,
)


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

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        turn: int | None = None,
        on_chunk: OnChunk | None = None,
    ) -> AssistantMessage:
        if self.fixture is not None and self.fixture.mode == "replay":
            self._seq += 1
            return await self.fixture.next_response(self._seq, self._request_meta(tools))

        last_exc: Exception | None = None
        for attempt in range(self.cfg.max_retries):
            try:
                msg = await self._stream(messages, tools, on_chunk=on_chunk)
                break
            except _RETRYABLE as e:
                last_exc = e
                await asyncio.sleep(2**attempt + 0.1)
            except Exception as e:
                # Non-retriable
                raise LLMError(f"{type(e).__name__}: {e}") from e
        else:
            raise LLMError(
                f"LLM failed after {self.cfg.max_retries} retries: {last_exc}"
            )

        if self.fixture is not None and self.fixture.mode == "record":
            self._seq += 1
            self.fixture.record(self._seq, turn, msg, self._request_meta(tools))
        return msg

    def _request_meta(self, tools: list[dict[str, Any]]) -> dict[str, Any]:
        return {"model": self.cfg.model, "tools_count": len(tools)}

    async def _stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        on_chunk: OnChunk | None = None,
    ) -> AssistantMessage:
        t0 = time.monotonic()
        ttft: float | None = None
        content_parts: list[str] = []
        tool_calls_acc: dict[int, dict[str, Any]] = {}
        usage: Usage | None = None

        stream = await self._client.chat.completions.create(  # type: ignore[call-overload]
            model=self.cfg.model,
            messages=messages,
            tools=tools,
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
                if on_chunk is not None:
                    on_chunk(delta.content)
            if delta and delta.tool_calls:
                for tc in delta.tool_calls:
                    acc = tool_calls_acc.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
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
        calls = [
            ToolCall(id=v["id"], name=v["name"], arguments=json.loads(v["arguments"] or "{}"))
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
