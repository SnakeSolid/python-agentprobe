"""Shared helpers for the replay-based E2E acceptance tests.

These tests exercise the real CLI as a subprocess (``python -m agentprobe``)
against ``--record`` / ``--replay`` JSONL fixtures, with no real LLM. Each test
builds its own scenario YAML, fixture JSONL and config inside ``tmp_path`` so
the suite is self-contained and never touches the repo's ``logs/``, ``scenarios/``
or ``workspace/`` directories.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

# e2e helpers

REPO_ROOT = Path(__file__).resolve().parents[2]

# Real tool set from config/config.yaml (includes execute_shell and spawn_agent).
DEFAULT_TOOLS = [
    "read_doc",
    "read",
    "write",
    "edit",
    "execute_shell",
    "command_execute",
    "read_skill",
    "syntax_check",
    "spawn_agent",
]

SCENARIO_DEFAULTS = {
    "turn_timeout_secs": 120,
    "max_agent_messages": 30,
    "max_context_tokens": 200000,
    "max_duration_secs": 300,
}


def _as_abs(root: Path, value: str) -> str:
    p = Path(value)
    return str(p if p.is_absolute() else root / p)


def build_config(
    tmp_path: Path,
    *,
    endpoint: str = "https://example.invalid/v1",
    api_key: str = "test-key",
    tools_enabled: list[str] | None = None,
    log_dir: Path | None = None,
    extra_tools: list[str] | None = None,
) -> Path:
    """Write a self-contained config into tmp_path and return its path.

    Points all app resource dirs at the real repo ones (absolute), but redirects
    ``log_dir`` into ``tmp_path`` so scenario logs don't pollute the repo.
    """
    root = REPO_ROOT
    ws = tmp_path / "workspace"
    logs = log_dir or (tmp_path / "logs")
    ws.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    (ws / "MEMORY.md").write_text("test memory", encoding="utf-8")

    enabled = list(tools_enabled) if tools_enabled is not None else list(DEFAULT_TOOLS)
    if extra_tools:
        enabled = enabled + list(extra_tools)

    cfg = {
        "app": {
            "workspace": str(ws),
            "docs_dir": _as_abs(root, "./docs"),
            "skills_dir": _as_abs(root, "./skills"),
            "prompt_file": _as_abs(root, "./prompts/system.md"),
            "subagent_prompt_file": None,
            "memory_file": _as_abs(root, "./workspace/MEMORY.md"),
            "user_tools_dir": None,
            "log_dir": str(logs),
            "tool_transport": "in_memory",
            "scenario_defaults": SCENARIO_DEFAULTS,
        },
        "models": {
            "main": {
                "endpoint": endpoint,
                "api_key": api_key,
                "model": "e2e-fake-model",
                "temperature": 0.0,
                "request_timeout_secs": 30,
                "max_retries": 0,
                "proxy": None,
            },
            "subagent": None,
        },
        "limits": {
            "main": {
                "max_turns": 35,
                "max_tool_calls": 100,
                "max_duration_secs": 600,
                "max_context_tokens": 1000000,
            },
            "subagent": {
                "max_turns": 20,
                "max_tool_calls": 50,
                "max_duration_secs": 300,
                "max_context_tokens": 200000,
            },
        },
        "tools": {"enabled": enabled},
        "logging": {
            "console_level": "info",
            "console_truncate_chars": 400,
            "color": "never",
        },
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    return path


def run_cli(
    *args: str,
    config: str | Path,
    cwd: Path = REPO_ROOT,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run ``python -m agentprobe <args>`` as a subprocess and return the result."""
    cmd = [sys.executable, "-m", "agentprobe", *args, "--config", str(config)]
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=check,
    )


def write_scenario(path: Path, name: str, **fields: object) -> Path:
    """Write a scenario YAML file and return its path."""
    data: dict[str, object] = {"name": name, **fields}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def write_fixture(replay_dir: Path, name: str, lines: list[dict]) -> Path:
    """Write a replay fixture ``<name>.jsonl`` and return its path."""
    replay_dir.mkdir(parents=True, exist_ok=True)
    path = replay_dir / f"{name}.jsonl"
    text = "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines)
    path.write_text(text, encoding="utf-8")
    return path


def fixture_line(
    content: str,
    *,
    tool_calls: list[dict] | None = None,
    turn: int = 1,
    prompt_tokens: int = 100,
    completion_tokens: int = 20,
) -> dict:
    """Build a single JSONL fixture line in the app's record format."""
    return {
        "seq": 1,
        "turn": turn,
        "request_meta": {"model": "e2e-fake-model", "tools_count": 0},
        "response": {
            "content": content,
            "tool_calls": tool_calls or [],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        },
    }


def read_events(log_dir: Path, name: str) -> list[dict]:
    """Parse the per-scenario YAML event log into a list of event dicts."""
    logs = sorted(log_dir.glob(f"*/{name}.yaml"))
    if not logs:
        return []
    events: list[dict] = []
    for doc in yaml.safe_load_all(logs[-1].read_text(encoding="utf-8")):
        if doc:
            events.append(doc)
    return events


def event_names(events: list[dict]) -> list[str]:
    return [e.get("event") for e in events]


def find_events(events: list[dict], event: str) -> list[dict]:
    return [e for e in events if e.get("event") == event]
