"""LLM client over the OpenAI-compatible API (streaming).

Retries on transient errors, honours ``trust_env=False`` so environment proxies
are ignored unless explicitly configured, and supports `--record` / `--replay`
via an optional :class:`Fixture`.
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from typing import Any

import httpx
from openai import APIConnectionError, APITimeoutError, AsyncOpenAI, RateLimitError

from agentprobe.config import ModelConfig
from agentprobe.errors import LLMError
from agentprobe.llm.fixture import Fixture
from agentprobe.llm.types import AssistantMessage, ToolCall, Usage


class LLMClient:
    def __init__(
        self,
        cfg: ModelConfig,
        fixture: Fixture | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.cfg = cfg
        self.fixture = fixture
        self._http = httpx.AsyncClient(
            proxy=cfg.proxy,
            trust_env=False,
            timeout=httpx.Timeout(cfg.request_timeout_secs),
            transport=transport,
        )
        self._client = AsyncOpenAI(
            base_url=cfg.endpoint,
            api_key=cfg.api_key,
            http_client=self._http,
            max_retries=0,  # we retry manually to control fixture replay
        )
        self.last_usage: Usage | None = None

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        turn: int = 0,
    ) -> AssistantMessage:
        if self.fixture is not None and self.fixture.mode == "replay":
            return await self.fixture.next_response()

        last_exc: Exception | None = None
        for attempt in range(max(1, self.cfg.max_retries)):
            try:
                msg = await self._stream(messages, tools)
                if self.fixture is not None and self.fixture.mode == "record":
                    self.fixture.record(
                        turn=turn,
                        msg=msg,
                        request_meta={"model": self.cfg.model, "tools_count": len(tools)},
                    )
                self.last_usage = msg.usage
                return msg
            except (
                RateLimitError,
                APIConnectionError,
                APITimeoutError,
                httpx.TimeoutException,
                httpx.ConnectError,
            ) as e:
                last_exc = e
                if attempt + 1 >= max(1, self.cfg.max_retries):
                    break
                delay = (2**attempt) + random.random()
                await asyncio.sleep(delay)
            except Exception as e:  # non-retriable
                raise LLMError(f"{type(e).__name__}: {e}") from e
        raise LLMError(
            f"LLM failed after {self.cfg.max_retries} retries: {last_exc!r}"
        )

    async def _stream(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> AssistantMessage:
        t0 = time.monotonic()
        ttft: float | None = None
        content_parts: list[str] = []
        tool_calls_acc: dict[int, dict[str, Any]] = {}
        usage: Usage | None = None

        # openai 1.x types messages/tools as its own Param types; our plain dicts
        # don't structurally match, so narrow the overload check on this call.
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
            if delta and delta.tool_calls:
                for tc in delta.tool_calls:
                    acc = tool_calls_acc.setdefault(
                        tc.index, {"id": "", "name": "", "arguments": ""}
                    )
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
            ToolCall(
                id=v["id"], name=v["name"], arguments=json.loads(v["arguments"] or "{}")
            )
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
