"""Pytest fixtures for the e2e acceptance suite."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.e2e.helpers import REPO_ROOT, build_config, read_events, run_cli


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    """A self-contained config with logs redirected into tmp_path."""
    return build_config(tmp_path)


@pytest.fixture
def run(repo_root: Path):
    """Return a bound runner that passes a config and repo_root cwd."""

    def _run(*args: str, config: str | Path) -> object:
        return run_cli(*args, config=config, cwd=repo_root)

    return _run


@pytest.fixture
def events(config_path: Path, tmp_path: Path):
    """Read the per-scenario event log for a given scenario name/glob."""

    def _events(name: str, log_dir: Path | None = None) -> list[dict]:
        logs = log_dir or (tmp_path / "logs")
        return read_events(logs, name)

    return _events
