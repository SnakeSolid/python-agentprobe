import pytest

from agentprobe.agent.observer import ScenarioObserver, SessionCtx
from agentprobe.errors import ScenarioAbort
from agentprobe.llm.types import AssistantMessage, ToolCall, Usage
from agentprobe.scenario.schema import Checks


def _checks(**kw):
    return Checks(**kw)


async def test_max_agent_messages():
    obs = ScenarioObserver(_checks(max_agent_messages=1))
    ctx = SessionCtx()
    await obs.on_assistant_message(AssistantMessage(content="a", usage=Usage(1, 1, 2)), ctx)
    with pytest.raises(ScenarioAbort) as e:
        await obs.on_assistant_message(AssistantMessage(content="b", usage=Usage(1, 1, 2)), ctx)
    assert e.value.reason == "max_agent_messages"
    assert e.value.exit_code == 1


async def test_max_agent_messages_not_added_to_context():
    obs = ScenarioObserver(_checks(max_agent_messages=1))
    ctx = SessionCtx()
    await obs.on_assistant_message(AssistantMessage(content="a", usage=Usage(1, 1, 2)), ctx)
    with pytest.raises(ScenarioAbort):
        await obs.on_assistant_message(AssistantMessage(content="b", usage=Usage(1, 1, 2)), ctx)
    assert ctx.agent_messages == 2


async def test_max_context_tokens():
    obs = ScenarioObserver(_checks(max_context_tokens=10))
    ctx = SessionCtx()
    with pytest.raises(ScenarioAbort) as e:
        await obs.on_assistant_message(
            AssistantMessage(content="a", usage=Usage(100, 0, 100)), ctx
        )
    assert e.value.reason == "max_context_tokens"
    assert e.value.exit_code == 1
    assert ctx.context_tokens_max == 100


async def test_usage_null_skips_check():
    obs = ScenarioObserver(_checks(max_context_tokens=10))
    ctx = SessionCtx()
    await obs.on_assistant_message(AssistantMessage(content="a", usage=None), ctx)
    assert ctx.agent_messages == 1
    assert ctx.context_tokens_max == 0


async def test_forbidden_tool_aborts_before_call():
    obs = ScenarioObserver(_checks(forbidden_tools=["execute_shell"]))
    ctx = SessionCtx()
    with pytest.raises(ScenarioAbort) as e:
        await obs.on_tool_call_pending(ToolCall(id="1", name="execute_shell", arguments={}), ctx)
    assert e.value.reason == "forbidden_tool:execute_shell"
    assert e.value.exit_code == 1
    assert ctx.tools_count == 0


async def test_max_tool_calls_general():
    obs = ScenarioObserver(_checks(), max_tool_calls=2)
    ctx = SessionCtx()
    ctx.tools_count = 2
    with pytest.raises(ScenarioAbort) as e:
        await obs.on_tool_call_pending(ToolCall(id="1", name="read", arguments={}), ctx)
    assert e.value.reason == "max_tool_calls"
    assert e.value.exit_code == 3


async def test_final_checks():
    obs = ScenarioObserver(
        _checks(
            final_include=["tcp"],
            required_tools=["read_doc"],
            forbidden_tools=["execute_shell"],
        )
    )
    ctx = SessionCtx()
    ctx.final_text_for_checks = "allows tcp traffic"
    ctx.tools_histogram = {"read": 1}  # read_doc not called -> failure
    failures = obs.final_checks(ctx)
    assert any("required_tools" in f for f in failures)
    assert not any("final_include" in f for f in failures)
