
import httpx
import pytest

from agentprobe.config import ModelConfig
from agentprobe.llm.client import LLMClient
from agentprobe.llm.fixture import Fixture
from agentprobe.llm.types import AssistantMessage


def _cfg(**overrides):
    data = {
        "endpoint": "https://example.com/v1",
        "api_key": "k",
        "model": "m",
        "temperature": 0.5,
        "request_timeout_secs": 10,
        "max_retries": 3,
        "proxy": None,
    }
    data.update(overrides)
    return ModelConfig(**data)


def _sse_bytes(chunks):
    out = []
    for c in chunks:
        out.append(f"data: {c}\n\n")
    return "".join(out).encode()


async def test_replay_no_network(project, tmp_path):
    path = tmp_path / "r.jsonl"
    f = Fixture(path, mode="record")
    f.record(turn=1, msg=AssistantMessage(content="replayed", tool_calls=[], usage=None), request_meta={})
    f.close()
    client = LLMClient(_cfg(), fixture=Fixture(path, mode="replay"))
    try:
        msg = await client.chat([{"role": "user", "content": "hi"}], [])
        assert msg.content == "replayed"
    finally:
        await client.aclose()


async def test_stream_parsing_tool_calls_and_usage():
    chunks = [
        '{"id":"x","object":"chat.completion.chunk","created":0,"model":"m","choices":[{"index":0,"delta":{"role":"assistant","content":"Hello"},"finish_reason":null}]}',
        '{"id":"x","object":"chat.completion.chunk","created":0,"model":"m","choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"id":"call_1","type":"function","function":{"name":"read","arguments":"{\\"path\\":\\"a\\"}"}}]},"finish_reason":null}]}',
        '{"id":"x","object":"chat.completion.chunk","created":0,"model":"m","choices":[{"index":0,"delta":{},"finish_reason":"tool_calls"}]}',
        '{"id":"x","object":"chat.completion.chunk","created":0,"model":"m","choices":[],"usage":{"prompt_tokens":5,"completion_tokens":3,"total_tokens":8}}',
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=_sse_bytes(chunks)
        )

    transport = httpx.MockTransport(handler)
    client = LLMClient(_cfg(), transport=transport)
    try:
        msg = await client.chat([{"role": "user", "content": "hi"}], [{"type": "function", "function": {"name": "read"}}])
        assert msg.content == "Hello"
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0].name == "read"
        assert msg.tool_calls[0].arguments == {"path": "a"}
        assert msg.usage.prompt_tokens == 5
        assert msg.usage.completion_tokens == 3
        assert msg.usage.total_tokens == 8
        assert msg.ttft_ms is not None
        assert msg.latency_ms is not None
    finally:
        await client.aclose()


async def test_retry_on_429():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"error": {"message": "rate"}})
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=_sse_bytes([
                '{"id":"x","object":"chat.completion.chunk","created":0,"model":"m","choices":[{"index":0,"delta":{"role":"assistant","content":"ok"},"finish_reason":null}]}',
                '{"id":"x","object":"chat.completion.chunk","created":0,"model":"m","choices":[],"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}',
            ])
        )

    transport = httpx.MockTransport(handler)
    client = LLMClient(_cfg(), transport=transport)
    try:
        msg = await client.chat([{"role": "user", "content": "hi"}], [])
        assert msg.content == "ok"
        assert calls["n"] == 2
    finally:
        await client.aclose()


async def test_context_error_raises():
    from agentprobe.errors import LLMError

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "bad"}})

    transport = httpx.MockTransport(handler)
    client = LLMClient(_cfg(max_retries=3), transport=transport)
    try:
        with pytest.raises(LLMError):
            await client.chat([{"role": "user", "content": "hi"}], [])
    finally:
        await client.aclose()
