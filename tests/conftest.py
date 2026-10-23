import sys
from pathlib import Path

import pytest
import yaml

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))


@pytest.fixture
def project(tmp_path):
    """Create a minimal project layout with config, and return cfg."""
    ws = tmp_path / "workspace"
    docs = tmp_path / "docs"
    skills = tmp_path / "skills"
    prompts = tmp_path / "prompts"
    logs = tmp_path / "logs"
    for d in (ws, docs, skills, prompts, logs):
        d.mkdir()
    (ws / "MEMORY.md").write_text("note")
    (docs / "vrp_basic.md").write_text("stub vrp")
    (docs / "security_policy.md").write_text("stub sp")
    (prompts / "system.md").write_text("# AGENTS\nstatic\n")
    (prompts / "subagent.md").write_text("sub")
    skill_dir = skills / "skill_a"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: skill_a\ndescription: the skill\n---\n\nbody\n"
    )

    cfg_data = {
        "app": {
            "workspace": str(ws),
            "docs_dir": str(docs),
            "skills_dir": str(skills),
            "prompt_file": str(prompts / "system.md"),
            "subagent_prompt_file": None,
            "memory_file": str(ws / "MEMORY.md"),
            "user_tools_dir": None,
            "log_dir": str(logs),
            "tool_transport": "in_memory",
            "scenario_defaults": {
                "turn_timeout_secs": 120,
                "max_agent_messages": 30,
                "max_context_tokens": 200000,
                "max_duration_secs": 300,
            },
        },
        "models": {
            "main": {
                "endpoint": "https://example.com/v1",
                "api_key": "k",
                "model": "m",
            },
            "subagent": None,
        },
        "limits": {
            "main": {"max_turns": 35, "max_tool_calls": 100, "max_duration_secs": 600, "max_context_tokens": 1000000},
            "subagent": {"max_turns": 20, "max_tool_calls": 50, "max_duration_secs": 300, "max_context_tokens": 200000},
        },
        "tools": {
            "enabled": [
                "read_doc", "read", "write", "edit",
                "execute_shell", "command_execute", "read_skill", "syntax_check",
            ]
        },
        "logging": {"console_level": "info", "console_truncate_chars": 400, "color": "never"},
    }
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg_data))
    from agentprobe.config import load_config

    return load_config(cfg_path)
