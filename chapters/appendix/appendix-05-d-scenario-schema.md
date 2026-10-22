# Appendix: Code Snippets and Examples

## D. Scenario schema

### D.1. `src/agentprobe/scenario/schema.py`

```python
from __future__ import annotations
import re
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field, field_validator

from agentprobe.config import ScenarioDefaults


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
    max_agent_messages: int | None = None
    max_context_tokens: int | None = None
    max_duration_secs: float | None = None

    @field_validator("final_include", "final_exclude")
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
            max_agent_messages=self.checks.max_agent_messages or d.max_agent_messages,
            max_context_tokens=self.checks.max_context_tokens or d.max_context_tokens,
            max_duration_secs=self.checks.max_duration_secs or d.max_duration_secs,
        )


def load_scenario(path: Path) -> Scenario:
    import yaml
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return Scenario.model_validate(raw)
```

---

