import pytest

from agentprobe.agent.observer import ScenarioObserver, SessionCtx
from agentprobe.errors import ScenarioAbort
from agentprobe.llm.types import AssistantMessage, ToolCall, ToolResult, Usage
from agentprobe.scenario.schema import Checks


def _msg(content: str = "hello", usage: Usage | None = None, tool_calls=None):
    return AssistantMessage(content=content, tool_calls=tool_calls or [], usage=usage)


async def test_forbidden_tool_aborts():
    ob = ScenarioObserver(Checks(forbidden_tools=["rm"]))
    ctx = SessionCtx()
    with pytest.raises(ScenarioAbort) as ei:
        await ob.on_tool_call_pending(ToolCall(id="1", name="rm", arguments={}), ctx)
    assert ei.value.reason == "forbidden_tool:rm"
    assert ei.value.exit_code == 1


async def test_max_agent_messages_aborts():
    ob = ScenarioObserver(Checks(max_agent_messages=1))
    ctx = SessionCtx()
    await ob.on_assistant_message(_msg(), ctx)
    with pytest.raises(ScenarioAbort) as ei:
        await ob.on_assistant_message(_msg(), ctx)
    assert ei.value.reason == "max_agent_messages"
    assert ei.value.exit_code == 1


async def test_usage_none_skips_context_check():
    ob = ScenarioObserver(Checks(max_context_tokens=10))
    ctx = SessionCtx()
    # No usage -> context check skipped, no abort despite small limit.
    await ob.on_assistant_message(_msg(usage=None), ctx)
    assert ctx.context_tokens_max == 0


async def test_context_tokens_aborts():
    ob = ScenarioObserver(Checks(max_context_tokens=10))
    ctx = SessionCtx()
    usage = Usage(prompt_tokens=8, completion_tokens=8, total_tokens=16)
    with pytest.raises(ScenarioAbort) as ei:
        await ob.on_assistant_message(_msg(usage=usage), ctx)
    assert ei.value.reason == "max_context_tokens"
    assert ei.value.exit_code == 1


async def test_tool_result_tracks_histogram():
    ob = ScenarioObserver(Checks())
    ctx = SessionCtx()
    await ob.on_tool_result(ToolResult(call_id="1", name="read", content=""), ctx)
    await ob.on_tool_result(ToolResult(call_id="2", name="read", content=""), ctx)
    assert ctx.tools_histogram == {"read": 2}
    assert ctx.tools_count == 2


def test_final_checks():
    ob = ScenarioObserver(
        Checks(
            final_include=["tcp", r"10\.0\.0\.0/24"],
            final_exclude=["forbidden"],
            required_tools=["syntax_check"],
        )
    )
    ctx = SessionCtx()
    ctx.final_text_for_checks = "permit tcp 10.0.0.0/24"
    ctx.tools_histogram = {"write": 1}
    failures = ob.final_checks(ctx)
    assert failures == ["required_tools: syntax_check not called"]


def test_final_checks_pass():
    ob = ScenarioObserver(
        Checks(
            final_include=["tcp"],
            final_exclude=["forbidden"],
            required_tools=["syntax_check"],
        )
    )
    ctx = SessionCtx()
    ctx.final_text_for_checks = "permit tcp ok"
    ctx.tools_histogram = {"syntax_check": 1}
    assert ob.final_checks(ctx) == []


async def test_tool_output_transcript_built_from_results():
    ob = ScenarioObserver(Checks())
    ctx = SessionCtx()
    await ob.on_tool_result(
        ToolResult(call_id="1", name="command_execute", content="display vsys\nvsys dmz id=2"),
        ctx,
    )
    assert ctx.tool_outputs == ["command_execute:\ndisplay vsys\nvsys dmz id=2"]
    assert "vsys dmz" in ctx.tool_output_transcript


async def test_tool_output_content_matchers():
    ob = ScenarioObserver(
        Checks(
            tool_output_include=[r"command_execute:\n.*display vsys[\s\S]*vsys dmz"],
            tool_output_exclude=["reboot"],
        )
    )
    ctx = SessionCtx()
    await ob.on_tool_result(
        ToolResult(
            call_id="1",
            name="command_execute",
            content="display vsys\nvsys default id=1\nvsys dmz id=2",
        ),
        ctx,
    )
    assert ob.final_checks(ctx) == []


async def test_tool_output_content_matchers_fail():
    ob = ScenarioObserver(Checks(tool_output_include=["never-present"]))
    ctx = SessionCtx()
    await ob.on_tool_result(
        ToolResult(call_id="1", name="cmd", content="some output"), ctx
    )
    assert any("tool_output_include" in f for f in ob.final_checks(ctx))


async def test_count_matchers():
    ob = ScenarioObserver(
        Checks(
            min_tool_calls=3,
            max_tool_calls=3,
            min_tool_call={"read": 1},
            max_tool_call={"write": 2},
        )
    )
    ctx = SessionCtx()
    ctx.tools_count = 3
    ctx.tools_histogram = {"read": 1, "write": 2}
    assert ob.final_checks(ctx) == []


async def test_count_matchers_fail():
    ob = ScenarioObserver(Checks(min_tool_calls=5, max_tool_call={"write": 1}))
    ctx = SessionCtx()
    ctx.tools_count = 3
    ctx.tools_histogram = {"write": 2}
    failures = ob.final_checks(ctx)
    assert any("min_tool_calls" in f for f in failures)
    assert any("max_tool_call" in f for f in failures)
