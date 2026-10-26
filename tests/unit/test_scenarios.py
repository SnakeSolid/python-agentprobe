from pathlib import Path

import pytest

from agentprobe.scenario.schema import load_scenario

SCENARIOS = Path(__file__).resolve().parents[2] / "scenarios"


@pytest.mark.parametrize(
    "name",
    ["firewall_permit_tcp.yaml", "vsys_create_with_subagent.yaml", "interface_status_filtered.yaml"],
)
def test_scenarios_load_and_validate(name):
    s = load_scenario(SCENARIOS / name)
    assert s.name
    assert s.initial_message
    assert isinstance(s.checks.required_tools, list)


def test_scenario_templating_from_params(tmp_path):
    p = tmp_path / "s.yaml"
    p.write_text(
        "name: t\n"
        "initial_message: 'config ${target}'\n"
        "tool_vars:\n"
        "  command_execute:\n"
        "    responses:\n"
        "      'display ${target}': 'output for ${target}'\n"
    )
    s = load_scenario(p, params={"target": "vsys"})
    assert s.initial_message == "config vsys"
    assert s.tool_vars["command_execute"]["responses"]["display vsys"] == "output for vsys"


def test_scenario_variables_default_and_override(tmp_path):
    p = tmp_path / "s.yaml"
    p.write_text(
        "name: t\n"
        "variables:\n"
        "  target: default\n"
        "  extra: x\n"
        "initial_message: 'do ${target} ${extra}'\n"
    )
    s = load_scenario(p, params={"target": "override"})
    assert s.initial_message == "do override x"


def test_scenario_unmatched_placeholder_left_untouched(tmp_path):
    p = tmp_path / "s.yaml"
    p.write_text("name: t\ninitial_message: 'keep ${missing}'\n")
    s = load_scenario(p)
    assert s.initial_message == "keep ${missing}"


def test_vsys_scenario_requires_skill_and_subagent():
    s = load_scenario(SCENARIOS / "vsys_create_with_subagent.yaml")
    assert "read_skill" in s.checks.required_tools
    assert "spawn_agent" in s.checks.required_tools
    assert "vsys" in s.checks.final_include
    assert "system-view" in s.checks.final_include
    assert s.checks.max_agent_messages is not None
    assert s.checks.max_agent_messages >= 10  # enough turns for skill + subagent
    assert s.timeouts.turn_secs is not None


def test_interface_status_scenario_uses_new_filters():
    s = load_scenario(SCENARIOS / "interface_status_filtered.yaml")
    assert "Interface\\s+Physical" in s.checks.tool_output_include
    assert "GE1/0/1\\s+up\\s+up" in s.checks.tool_output_include
    assert "ERROR:" in s.checks.tool_output_exclude
    assert s.checks.min_tool_calls == 1
    assert s.checks.max_tool_calls == 4
    assert s.checks.min_tool_call == {"command_execute": 1}
    assert s.checks.max_tool_call == {"command_execute": 2}
    # Regex lists validated at load time (invalid patterns would raise).
    assert "command_execute" in s.checks.required_tools
