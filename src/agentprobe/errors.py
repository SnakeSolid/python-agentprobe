"""Application error hierarchy.

Each error family maps to a CLI exit code (see the tech spec §15.5).
"""

from __future__ import annotations


class AgentProbeError(Exception):
    """Base class for all application errors."""


class ConfigError(AgentProbeError):
    """Configuration or scenario validation failure. Exit code 2."""


class SandboxViolation(AgentProbeError):
    """A path escapes the allowed filesystem root."""


class LimitExceeded(AgentProbeError):
    """General limits (turns/tool_calls/duration) exceeded. Exit code 3."""

    def __init__(self, reason: str, limit: float, actual: float):
        super().__init__(reason)
        self.reason = reason
        self.limit = limit
        self.actual = actual


class LLMError(AgentProbeError):
    """LLM request failed after retries. Exit code 4."""


class ReplayError(LLMError):
    """Replay fixture missing or exhausted. Exit code 4."""


class ScenarioAbort(Exception):
    """Raised by ``ScenarioObserver`` to abort a scenario immediately."""

    def __init__(self, reason: str, exit_code: int):
        super().__init__(reason)
        self.reason = reason
        self.exit_code = exit_code
