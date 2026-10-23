from pathlib import Path

import pytest

from agentprobe.scenario.schema import load_scenario

SCENARIOS = Path(__file__).resolve().parents[2] / "scenarios"


@pytest.mark.parametrize(
    "name",
    ["firewall_permit_tcp.yaml", "vsys_create_with_subagent.yaml"],
)
def test_scenarios_load_and_validate(name):
    s = load_scenario(SCENARIOS / name)
    assert s.name
    assert s.initial_message
    assert isinstance(s.checks.required_tools, list)


def test_vsys_scenario_requires_skill_and_subagent():
    s = load_scenario(SCENARIOS / "vsys_create_with_subagent.yaml")
    assert "read_skill" in s.checks.required_tools
    assert "spawn_agent" in s.checks.required_tools
    assert "vsys" in s.checks.final_include
    assert "system-view" in s.checks.final_include
    assert s.checks.max_agent_messages is not None
    assert s.checks.max_agent_messages >= 10  # enough turns for skill + subagent
    assert s.timeouts.turn_secs is not None
