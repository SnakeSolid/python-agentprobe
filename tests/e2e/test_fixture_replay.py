"""E2E: fixture replay acceptance (criteria 1, 4, 5)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.e2e.fake_llm import FakeLLMServer
from tests.e2e.helpers import (
    build_config,
    find_events,
    fixture_line,
    read_events,
    run_cli,
    write_fixture,
    write_scenario,
)

FIREWALL_SCENARIO = (
    Path(__file__).resolve().parents[2] / "scenarios" / "firewall_permit_tcp.yaml"
)


@pytest.fixture
def config(tmp_path: Path) -> Path:
    return build_config(tmp_path)


def _firewall_fixture() -> list[dict]:
    return [
        fixture_line(
            "Let me check the docs first.",
            turn=1,
            tool_calls=[
                {"id": "call_1", "name": "read_doc", "arguments": {"name": "vrp_basic"}}
            ],
        ),
        fixture_line("I found the security-policy section. Should I confirm?", turn=1),
        fixture_line(
            "Writing the policy to a file now.",
            turn=2,
            tool_calls=[
                {
                    "id": "call_2",
                    "name": "write",
                    "arguments": {
                        "path": "policy.txt",
                        "content": "security-policy\n permit tcp to 10.0.0.0/24\n",
                    },
                }
            ],
        ),
        fixture_line("The rule was written to policy.txt. Verify it?", turn=2),
        fixture_line("The rule in policy.txt permits all tcp traffic to 10.0.0.0/24.", turn=3),
    ]


def test_firewall_replay_passes(tmp_path: Path, config: Path) -> None:
    """Criterion 1: replaying a fixture for the firewall scenario exits 0 with checks passed."""
    fixture_dir = tmp_path / "replay"
    write_fixture(fixture_dir, "firewall-permit-tcp", _firewall_fixture())
    summary = tmp_path / "summary.yaml"
    r = run_cli(
        "run",
        "--scenario",
        str(FIREWALL_SCENARIO),
        "--replay",
        str(fixture_dir),
        "--summary-file",
        str(summary),
        config=config,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    data = yaml.safe_load(summary.read_text(encoding="utf-8"))
    assert data["scenarios"][0]["status"] == "PASS"
    assert data["scenarios"][0]["checks"]["passed"] is True
    assert data["totals"]["passed"] == 1


def test_missing_fixture_exits_4(tmp_path: Path, config: Path) -> None:
    """Criterion 4: a replay dir with no fixture file for the scenario exits 4."""
    empty = tmp_path / "empty_replay"
    empty.mkdir()
    r = run_cli(
        "run",
        "--scenario",
        str(FIREWALL_SCENARIO),
        "--replay",
        str(empty),
        config=config,
    )
    assert r.returncode == 4, r.stdout + r.stderr
    # The "fixture not found" reason lands in the per-scenario event log, not stdout.
    events = read_events(tmp_path / "logs", "firewall-permit-tcp")
    abort = find_events(events, "scenario_abort")
    assert abort, "expected a scenario_abort event"
    assert "fixture not found" in abort[-1]["reason"]
    assert abort[-1]["exit_code"] == 4


def test_record_then_replay_roundtrip(tmp_path: Path) -> None:
    """Criterion 5: --record writes a fixture (exit 0), then --replay reproduces it."""
    scen = write_scenario(
        tmp_path / "roundtrip.yaml",
        "roundtrip",
        initial_message="hello",
        checks={"final_include": ["hello world"]},
    )
    rec = tmp_path / "rec"
    with FakeLLMServer(text="hello world") as srv:
        rec_config = build_config(tmp_path, endpoint=srv.endpoint)
        r1 = run_cli("run", "--scenario", str(scen), "--record", str(rec), config=rec_config)
        assert r1.returncode == 0, r1.stdout + r1.stderr

    fixture = rec / "roundtrip.jsonl"
    assert fixture.exists()
    assert fixture.read_text(encoding="utf-8").strip()

    # Replay does not need a live endpoint; use a separate config to prove reproducibility.
    replay_config = build_config(tmp_path / ("cfg2"))
    r2 = run_cli("run", "--scenario", str(scen), "--replay", str(rec), config=replay_config)
    assert r2.returncode == 0, r2.stdout + r2.stderr
