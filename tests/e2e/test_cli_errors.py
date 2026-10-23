"""E2E: CLI/config error exit codes (criteria 6, 7, 8)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e.helpers import REPO_ROOT, build_config, run_cli


@pytest.fixture
def config(tmp_path: Path) -> Path:
    return build_config(tmp_path)


FIREWALL = REPO_ROOT / "scenarios" / "firewall_permit_tcp.yaml"


def test_unknown_tool_in_config_exits_2(tmp_path: Path) -> None:
    """Criterion 6: an unknown tool in tools.enabled is a config error (exit 2)."""
    cfg = build_config(tmp_path, extra_tools=["no_such_tool"])
    r = run_cli("run", "--scenario", str(FIREWALL), config=cfg)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "unknown tool" in (r.stdout + r.stderr)


def test_repl_summary_not_supported(tmp_path: Path, config: Path) -> None:
    """Criterion 7: --summary in repl mode exits 2."""
    r = run_cli("repl", "--summary", config=config)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "not supported in repl" in (r.stdout + r.stderr)


def test_record_and_replay_together_exits_2(tmp_path: Path, config: Path) -> None:
    """Criterion 8a: --record and --replay simultaneously exits 2."""
    d = tmp_path / "d"
    d.mkdir()
    r = run_cli(
        "run",
        "--scenario",
        str(FIREWALL),
        "--record",
        str(d),
        "--replay",
        str(d),
        config=config,
    )
    assert r.returncode == 2, r.stdout + r.stderr


def test_record_without_path_exits_2(tmp_path: Path, config: Path) -> None:
    """Criterion 8b: --record without a path is a CLI usage error (exit 2)."""
    r = run_cli("run", "--scenario", str(FIREWALL), "--record", config=config)
    assert r.returncode == 2, r.stdout + r.stderr
