"""E2E: scenario aborts (criteria 2 and 3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e.helpers import (
    build_config,
    event_names,
    find_events,
    fixture_line,
    read_events,
    run_cli,
    write_fixture,
    write_scenario,
)


@pytest.fixture
def config(tmp_path: Path) -> Path:
    return build_config(tmp_path)


@pytest.fixture
def logs(tmp_path: Path) -> Path:
    return tmp_path / "logs"


def test_forbidden_tool_aborts(tmp_path: Path, config: Path, logs: Path) -> None:
    """Criterion 2: forbidden execute_shell call aborts with exit 1 and no tool_call event."""
    name = "forbidden-tool"
    scen = write_scenario(
        tmp_path / "forbid.yaml",
        name,
        initial_message="run it",
        checks={"forbidden_tools": ["execute_shell"]},
    )
    fixture_dir = tmp_path / "replay"
    write_fixture(
        fixture_dir,
        name,
        [
            fixture_line(
                "Running the command.",
                tool_calls=[{"id": "c1", "name": "execute_shell", "arguments": {"command": "ls"}}],
            )
        ],
    )
    r = run_cli(
        "run", "--scenario", str(scen), "--replay", str(fixture_dir), "--summary", config=config
    )
    assert r.returncode == 1, r.stdout + r.stderr
    events = read_events(logs, name)
    abort = find_events(events, "scenario_abort")
    assert abort, "expected a scenario_abort event"
    assert abort[-1]["reason"] == "forbidden_tool:execute_shell"
    assert abort[-1]["exit_code"] == 1
    assert "tool_call" not in event_names(events)


def test_max_agent_messages_aborts(tmp_path: Path, config: Path, logs: Path) -> None:
    """Criterion 3: emitting more assistant messages than max_agent_messages aborts (exit 1)."""
    name = "max-messages"
    scen = write_scenario(
        tmp_path / "max.yaml",
        name,
        initial_message="start",
        transitions=[
            {"message": "continue-one", "include": ["one"]},
            {"message": "continue-two", "include": ["two"]},
        ],
        checks={"max_agent_messages": 2},
    )
    fixture_dir = tmp_path / "replay"
    write_fixture(
        fixture_dir,
        name,
        [
            fixture_line("one", turn=1),
            fixture_line("two", turn=2),
            fixture_line("three", turn=3),
        ],
    )
    r = run_cli(
        "run", "--scenario", str(scen), "--replay", str(fixture_dir), "--summary", config=config
    )
    assert r.returncode == 1, r.stdout + r.stderr
    events = read_events(logs, name)
    abort = find_events(events, "scenario_abort")
    assert abort and abort[-1]["reason"] == "max_agent_messages"
    assert abort[-1]["agent_messages"] == 3
    # Exactly three LLM requests were made (the third message triggered the abort,
    # so there is no subsequent llm_request event).
    assert event_names(events).count("llm_request") == 3
