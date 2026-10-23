import os

import pytest
import yaml

from agentprobe.config import load_config


def _write_cfg(tmp_path, **overrides):
    ws = tmp_path / "workspace"
    docs = tmp_path / "docs"
    skills = tmp_path / "skills"
    prompts = tmp_path / "prompts"
    logs = tmp_path / "logs"
    for d in (ws, docs, skills, prompts, logs):
        d.mkdir()
    (prompts / "system.md").write_text("x")
    base = {
        "app": {
            "workspace": str(ws), "docs_dir": str(docs), "skills_dir": str(skills),
            "prompt_file": str(prompts / "system.md"), "subagent_prompt_file": None,
            "memory_file": str(ws / "MEMORY.md"), "user_tools_dir": None,
            "log_dir": str(logs), "tool_transport": "in_memory",
        },
        "models": {"main": {"endpoint": "e", "api_key": "k", "model": "m"}, "subagent": None},
        "limits": {"main": {}, "subagent": {}},
        "tools": {"enabled": ["read_doc", "read", "write", "edit", "execute_shell", "command_execute", "read_skill", "syntax_check"]},
        "logging": {},
    }
    base.update(overrides)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(base))
    return path


def test_env_substitution(tmp_path, monkeypatch):
    monkeypatch.setenv("MY_KEY", "secret123")
    path = _write_cfg(tmp_path)
    # api_key is static; test via a dynamic value in a harmless field
    text = path.read_text()
    text = text.replace("model: m", "model: ${MY_KEY}")
    path.write_text(text)
    cfg = load_config(path)
    assert cfg.models.main.model == "secret123"


def test_missing_env_var_is_error(tmp_path):
    os.environ.pop("DOES_NOT_EXIST", None)
    path = _write_cfg(tmp_path)
    text = path.read_text().replace("model: m", "model: ${DOES_NOT_EXIST}")
    path.write_text(text)
    with pytest.raises(ValueError):
        load_config(path)


def test_unknown_tool_is_error(tmp_path):
    path = _write_cfg(tmp_path)
    path.write_text(path.read_text().replace("- syntax_check", "- bogus_tool"))
    with pytest.raises(ValueError):
        load_config(path)


def test_subagent_null_disables(tmp_path):
    cfg = load_config(_write_cfg(tmp_path))
    assert cfg.models.subagent is None
