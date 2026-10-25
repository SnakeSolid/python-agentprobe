import pytest

from agentprobe.errors import ReplayError
from agentprobe.llm.fixture import Fixture
from agentprobe.llm.types import AssistantMessage, ToolCall, Usage


async def test_roundtrip(tmp_path):
    path = tmp_path / "fixture.jsonl"
    rec = Fixture(path, "record")
    msg = AssistantMessage(
        content="hello",
        tool_calls=[ToolCall(id="1", name="read", arguments={"path": "a.txt"})],
        usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )
    rec.record(1, 1, msg, {"model": "m", "tools_count": 2})
    rec.close()

    replay = Fixture(path, "replay")
    out = await replay.next_response(1)
    assert out.content == "hello"
    assert out.tool_calls[0].id == "1"
    assert out.tool_calls[0].name == "read"
    assert out.tool_calls[0].arguments == {"path": "a.txt"}
    assert out.usage is not None
    assert out.usage.total_tokens == 15
    replay.close()


async def test_roundtrip_no_usage(tmp_path):
    path = tmp_path / "f.jsonl"
    rec = Fixture(path, "record")
    rec.record(1, 1, AssistantMessage(content="only text"), {})
    rec.close()
    replay = Fixture(path, "replay")
    out = await replay.next_response(1)
    assert out.content == "only text"
    assert out.usage is None
    replay.close()


def test_replay_missing_file_raises(tmp_path):
    with pytest.raises(ReplayError, match="fixture not found"):
        Fixture(tmp_path / "nope.jsonl", "replay")


async def test_replay_exhausted_raises(tmp_path):
    path = tmp_path / "one.jsonl"
    rec = Fixture(path, "record")
    rec.record(1, 1, AssistantMessage(content="x"), {})
    rec.close()
    replay = Fixture(path, "replay")
    await replay.next_response(1)
    with pytest.raises(ReplayError, match="fixture exhausted"):
        await replay.next_response(2)


async def test_replay_identity_matches(tmp_path):
    path = tmp_path / "matching.jsonl"
    rec = Fixture(path, "record")
    rec.record(1, 1, AssistantMessage(content="hello"), {"model": "m", "tools_count": 2})
    rec.close()
    replay = Fixture(path, "replay")
    out = await replay.next_response(1, {"model": "m", "tools_count": 2})
    assert out.content == "hello"


async def test_replay_identity_mismatch_tools_count(tmp_path):
    path = tmp_path / "mismatch.jsonl"
    rec = Fixture(path, "record")
    rec.record(1, 1, AssistantMessage(content="hello"), {"model": "m", "tools_count": 2})
    rec.close()
    replay = Fixture(path, "replay")
    with pytest.raises(ReplayError, match="replay identity mismatch.*tools_count recorded=2 actual=3"):
        await replay.next_response(1, {"model": "m", "tools_count": 3})


async def test_replay_identity_mismatch_model(tmp_path):
    path = tmp_path / "mismatch_model.jsonl"
    rec = Fixture(path, "record")
    rec.record(1, 1, AssistantMessage(content="hello"), {"model": "a", "tools_count": 2})
    rec.close()
    replay = Fixture(path, "replay")
    with pytest.raises(ReplayError, match="replay identity mismatch.*model recorded='a' actual='b'"):
        await replay.next_response(1, {"model": "b", "tools_count": 2})


async def test_replay_identity_skipped_when_no_recorded_meta(tmp_path):
    # Older fixtures without request_meta still replay without validating.
    path = tmp_path / "legacy.jsonl"
    path.write_text(
        '{"seq":1,"response":{"content":"old","tool_calls":[],"usage":null}}\n',
        encoding="utf-8",
    )
    replay = Fixture(path, "replay")
    out = await replay.next_response(1, {"model": "m", "tools_count": 9})
    assert out.content == "old"


async def test_replay_identity_skipped_when_no_incoming_meta(tmp_path):
    path = tmp_path / "no_incoming.jsonl"
    rec = Fixture(path, "record")
    rec.record(1, 1, AssistantMessage(content="x"), {"model": "m", "tools_count": 2})
    rec.close()
    replay = Fixture(path, "replay")
    out = await replay.next_response(1)
    assert out.content == "x"
