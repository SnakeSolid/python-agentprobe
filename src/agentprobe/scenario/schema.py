from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

from agentprobe.config import ScenarioDefaults

_SIMPLE = re.compile(r"\$\{([A-Za-z0-9_.]+)\}")


def _substitute(obj: Any, vars: Mapping[str, Any]) -> Any:
    """Recursively substitute ``${key}`` in all strings (keys and values) of ``obj``."""

    def walk(o: Any) -> Any:
        if isinstance(o, str):
            return _SIMPLE.sub(lambda m: str(vars.get(m.group(1), m.group(0))), o)
        if isinstance(o, list):
            return [walk(i) for i in o]
        if isinstance(o, dict):
            return {walk(k) if isinstance(k, str) else k: walk(v) for k, v in o.items()}
        return o

    return walk(obj)


class Transition(BaseModel):
    message: str
    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    once: bool = False

    @field_validator("include", "exclude")
    @classmethod
    def _compile_check(cls, pats: list[str]) -> list[str]:
        for p in pats:
            re.compile(p)  # raises if invalid
        return pats


class Checks(BaseModel):
    tags: list[str] = Field(default_factory=list)
    final_include: list[str] = Field(default_factory=list)
    final_exclude: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    # Tool *output content* matchers (regex, matched against the concatenated
    # transcript of every tool result's output).
    tool_output_include: list[str] = Field(default_factory=list)
    tool_output_exclude: list[str] = Field(default_factory=list)
    # Count matchers.
    min_tool_calls: int | None = None
    max_tool_calls: int | None = None
    min_tool_call: dict[str, int] = Field(default_factory=dict)
    max_tool_call: dict[str, int] = Field(default_factory=dict)
    max_agent_messages: int | None = None
    max_context_tokens: int | None = None
    max_duration_secs: float | None = None

    @field_validator(
        "final_include", "final_exclude", "tool_output_include", "tool_output_exclude"
    )
    @classmethod
    def _compile_check(cls, pats: list[str]) -> list[str]:
        for p in pats:
            re.compile(p)
        return pats


class Timeouts(BaseModel):
    turn_secs: float | None = None


class Scenario(BaseModel):
    name: str
    description: str | None = None
    initial_message: str
    # Optional per-scenario template defaults (overridden by --param).
    variables: dict[str, Any] = Field(default_factory=dict)
    tool_vars: dict[str, dict[str, Any]] = Field(default_factory=dict)
    transitions: list[Transition] = Field(default_factory=list)
    checks: Checks = Checks()
    timeouts: Timeouts = Timeouts()

    def effective_defaults(self, d: ScenarioDefaults) -> Checks:
        """Fill None values in checks from scenario defaults."""
        return Checks(
            tags=self.checks.tags,
            final_include=self.checks.final_include,
            final_exclude=self.checks.final_exclude,
            required_tools=self.checks.required_tools,
            forbidden_tools=self.checks.forbidden_tools,
            tool_output_include=self.checks.tool_output_include,
            tool_output_exclude=self.checks.tool_output_exclude,
            min_tool_calls=self.checks.min_tool_calls,
            max_tool_calls=self.checks.max_tool_calls,
            min_tool_call=self.checks.min_tool_call,
            max_tool_call=self.checks.max_tool_call,
            max_agent_messages=self.checks.max_agent_messages or d.max_agent_messages,
            max_context_tokens=self.checks.max_context_tokens or d.max_context_tokens,
            max_duration_secs=self.checks.max_duration_secs or d.max_duration_secs,
        )


def load_scenario(path: Path, params: Mapping[str, Any] | None = None) -> Scenario:
    """Load a scenario, applying ``${key}`` templating.

    Per-scenario ``variables:`` provide defaults; ``params`` (e.g. from the CLI
    ``--param key=value`` flag) override them. Unmatched placeholders are left
    untouched.
    """
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise TypeError(f"scenario {path} must be a YAML mapping")
    raw_vars = raw.get("variables") or {}
    if not isinstance(raw_vars, dict):
        raise TypeError(f"scenario {path} 'variables' must be a mapping")
    merged: dict[str, Any] = dict(raw_vars)
    if params:
        merged.update(params)
    if merged:
        raw = _substitute(raw, merged)
    return Scenario.model_validate(raw)
