from pathlib import Path

import pytest

from agentprobe.config import Config


def _minimal_raw():
    return {
        "app": {
            "workspace": "./workspace",
            "docs_dir": "./docs",
            "skills_dir": "./skills",
            "prompt_file": "./prompts/system.md",
            "memory_file": "./workspace/MEMORY.md",
            "log_dir": "./logs",
        },
        "models": {"main": {"endpoint": "http://x", "api_key": "k", "model": "m"}},
        "limits": {},
        "tools": {},
    }


def test_env_substitution(monkeypatch):
    monkeypatch.setenv("MY_WS", "/tmp/agentprobe-ws")
    raw = _minimal_raw()
    raw["app"]["workspace"] = "${MY_WS}"
    cfg = Config.model_validate(raw)
    assert cfg.app.workspace == Path("/tmp/agentprobe-ws")


def test_env_substitution_nested(monkeypatch):
    monkeypatch.setenv("ENDPOINT_URL", "http://127.0.0.1:9999")
    raw = _minimal_raw()
    raw["models"]["main"]["endpoint"] = "${ENDPOINT_URL}/v2"
    cfg = Config.model_validate(raw)
    assert cfg.models.main.endpoint == "http://127.0.0.1:9999/v2"


def test_missing_env_var_raises(monkeypatch):
    monkeypatch.delenv("DOES_NOT_EXIST_123", raising=False)
    raw = _minimal_raw()
    raw["models"]["main"]["endpoint"] = "${DOES_NOT_EXIST_123}"
    with pytest.raises(Exception) as ei:
        Config.model_validate(raw)
    assert "missing env var" in str(ei.value)


def test_path_validation_missing_dir(tmp_path):
    cfg = Config.model_validate(_minimal_raw())
    cfg.app.workspace = tmp_path / "definitely-missing"
    with pytest.raises(ValueError, match="path does not exist"):
        cfg.validate_paths()


def test_path_validation_ok(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    cfg = Config.model_validate(_minimal_raw())
    cfg.app.workspace = ws
    cfg.app.docs_dir = tmp_path
    cfg.app.skills_dir = tmp_path
    cfg.app.prompt_file = tmp_path / "system.md"
    cfg.app.log_dir = tmp_path / "logs"
    cfg.validate_paths()  # should not raise
