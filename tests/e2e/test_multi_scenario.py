"""E2E: multi-scenario runs via --scenario-dir (criteria 9 and 10)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.e2e.helpers import (
    build_config,
    fixture_line,
    run_cli,
    write_fixture,
    write_scenario,
)


@pytest.fixture
def config(tmp_path: Path) -> Path:
    return build_config(tmp_path)


def _write_pass_pair(tmp_path: Path) -> tuple[Path, Path]:
    """Write two passing scenarios and their replay fixtures; return (scen_dir, replay)."""
    scen_dir = tmp_path / "scenarios"
    replay = tmp_path / "replay"
    write_scenario(
        scen_dir / "a.yaml",
        "multi-a",
        initial_message="hi a",
        checks={"final_include": ["ok"]},
    )
    write_scenario(
        scen_dir / "b.yaml",
        "multi-b",
        initial_message="hi b",
        checks={"final_include": ["fine"]},
    )
    write_fixture(replay, "multi-a", [fixture_line("ok")])
    write_fixture(replay, "multi-b", [fixture_line("fine")])
    return scen_dir, replay


def test_multi_scenario_summary(tmp_path: Path, config: Path) -> None:
    """Criterion 9: two valid scenarios via --scenario-dir exit 0 with a 2-row summary."""
    scen_dir, replay = _write_pass_pair(tmp_path)
    summary = tmp_path / "summary.yaml"
    r = run_cli(
        "run",
        "--scenario-dir",
        str(scen_dir),
        "--replay",
        str(replay),
        "--summary",
        "--summary-file",
        str(summary),
        config=config,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "multi-a" in r.stdout
    assert "multi-b" in r.stdout
    data = yaml.safe_load(summary.read_text(encoding="utf-8"))
    assert set(data) == {"run", "scenarios", "totals"}
    assert len(data["scenarios"]) == 2
    assert data["totals"]["passed"] == 2
    assert data["run"]["scenarios_total"] == 2


def test_scenario_typo_exits_2_no_runs(tmp_path: Path, config: Path) -> None:
    """Criterion 10: a YAML typo in one of two scenarios -> exit 2 and no scenario runs."""
    scen_dir = tmp_path / "scenarios"
    write_scenario(
        scen_dir / "good.yaml",
        "good-scenario",
        initial_message="hi",
        checks={"final_include": ["ok"]},
    )
    # A typo: missing the required initial_message field -> validation error.
    write_scenario(scen_dir / "bad.yaml", "bad-scenario", description="typo")
    logs = tmp_path / "logs"
    r = run_cli("run", "--scenario-dir", str(scen_dir), config=config)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "validation error" in (r.stdout + r.stderr).lower()
    # No scenario ran: no per-scenario event log was produced for the good one.
    assert list(logs.glob("*/good-scenario.yaml")) == []
