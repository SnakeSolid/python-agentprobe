
from agentprobe.llm.fixture import Fixture
from agentprobe.llm.types import AssistantMessage, ToolCall, Usage


async def test_fixture_round_trip(tmp_path):
    path = tmp_path / "sub" / "scenario.jsonl"
    f = Fixture(path, mode="record")
    f.record(
        turn=1,
        msg=AssistantMessage(
            content="hi",
            tool_calls=[ToolCall(id="1", name="read", arguments={"path": "a"})],
            usage=Usage(10, 20, 30),
        ),
        request_meta={"model": "m", "tools_count": 3},
    )
    f.close()

    r = Fixture(path, mode="replay")
    msg = await r.next_response()
    assert msg.content == "hi"
    assert msg.tool_calls[0].name == "read"
    assert msg.tool_calls[0].arguments == {"path": "a"}
    assert msg.usage.prompt_tokens == 10
    assert msg.usage.total_tokens == 30


async def test_fixture_missing_file(tmp_path):
    from agentprobe.errors import ReplayError

    try:
        Fixture(tmp_path / "nope" / "x.jsonl", mode="replay")
        raise AssertionError("expected ReplayError")
    except ReplayError:
        pass


async def test_fixture_exhausted(tmp_path):
    import json

    path = tmp_path / "x.jsonl"
    path.write_text(json.dumps({"response": {"content": "a", "tool_calls": [], "usage": None}}))
    from agentprobe.errors import ReplayError

    r = Fixture(path, mode="replay")
    await r.next_response()
    try:
        await r.next_response()
        raise AssertionError("expected ReplayError")
    except ReplayError:
        pass
