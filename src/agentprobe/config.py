from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator

_ENV_PATTERN = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


def _substitute_env(value: Any) -> Any:
    if isinstance(value, str):
        def repl(m: re.Match[str]) -> str:
            name = m.group(1)
            if name not in os.environ:
                raise ValueError(f"missing env var: {name}")
            return os.environ[name]
        return _ENV_PATTERN.sub(repl, value)
    if isinstance(value, dict):
        return {k: _substitute_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_env(v) for v in value]
    return value


class ScenarioDefaults(BaseModel):
    turn_timeout_secs: float = 120
    max_agent_messages: int = 30
    max_context_tokens: int = 200_000
    max_duration_secs: float = 300


class AppSection(BaseModel):
    workspace: Path
    docs_dir: Path
    skills_dir: Path
    prompt_file: Path
    subagent_prompt_file: Path | None = None
    memory_file: Path
    user_tools_dir: Path | None = None
    log_dir: Path
    tool_transport: Literal["in_memory", "stdio"] = "in_memory"
    scenario_defaults: ScenarioDefaults = ScenarioDefaults()
    tool_vars: dict[str, dict[str, Any]] = Field(default_factory=dict)


class ModelConfig(BaseModel):
    endpoint: str
    api_key: str
    model: str
    temperature: float = 0.6
    request_timeout_secs: float = 120
    max_retries: int = 3
    proxy: str | None = None


class ModelsSection(BaseModel):
    main: ModelConfig
    subagent: ModelConfig | None = None  # None -> spawn_agent unavailable


class Limits(BaseModel):
    max_turns: int = 35
    max_tool_calls: int = 100
    max_duration_secs: float = 600
    max_context_tokens: int = 1_000_000

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump()


class LimitsSection(BaseModel):
    main: Limits = Limits()
    subagent: Limits = Limits(
        max_turns=20, max_tool_calls=50, max_duration_secs=300, max_context_tokens=200_000
    )


class ToolsSection(BaseModel):
    enabled: list[str] = Field(default_factory=list)


class LoggingSection(BaseModel):
    console_level: Literal["quiet", "info", "verbose"] = "info"
    console_truncate_chars: int = 400
    color: Literal["auto", "always", "never"] = "auto"


class Config(BaseModel):
    app: AppSection
    models: ModelsSection
    limits: LimitsSection
    tools: ToolsSection
    logging: LoggingSection = LoggingSection()

    @field_validator("*", mode="before")
    @classmethod
    def _env(cls, v: Any) -> Any:
        return _substitute_env(v)

    def validate_paths(self) -> None:
        for p in (
            self.app.workspace,
            self.app.docs_dir,
            self.app.skills_dir,
            self.app.prompt_file.parent,
            self.app.log_dir.parent if not self.app.log_dir.exists() else self.app.log_dir,
        ):
            if not p.exists():
                raise ValueError(f"path does not exist: {p}")
        # log_dir itself may not exist yet; create parent-bearing check
        if not self.app.log_dir.exists() and not self.app.log_dir.parent.exists():
            raise ValueError(f"log_dir parent does not exist: {self.app.log_dir}")


def load_config(path: Path) -> Config:
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    cfg = Config.model_validate(raw)
    cfg.validate_paths()
    return cfg
