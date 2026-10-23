import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]  # repo root: tests/e2e -> project


def _run(args):
    return subprocess.run(
        [sys.executable, "-m", "agentprobe"] + args,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        check=False,
    )


def test_firewall_replay(tmp_path):
    fixture_dir = ROOT / "tests/fixtures"
    summary = tmp_path / "summary.yaml"
    result = _run(
        [
            "run",
            "--config",
            "config/config.yaml",
            "--scenario",
            "scenarios/firewall_permit_tcp.yaml",
            "--replay",
            str(fixture_dir),
            "--summary",
            "--summary-file",
            str(summary),
        ]
    )
    assert result.returncode == 0, result.stderr + result.stdout
    data = yaml.safe_load(summary.read_text())
    assert data["scenarios"][0]["checks"]["passed"] is True
    assert "tcp" in result.stdout.lower()


def test_dry_run_no_model(tmp_path):
    result = _run(["dry-run", "--config", "config/config.yaml"])
    assert result.returncode == 0, result.stderr
    assert "=== SYSTEM PROMPT ===" in result.stdout
    assert "huawei_vsys" in result.stdout
