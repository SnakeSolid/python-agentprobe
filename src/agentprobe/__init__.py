"""agentprobe — an asynchronous LLM agent for E2E testing.

The CLI entry point is exposed via the ``agentprobe`` console script
(see ``pyproject.toml``). ``pyproject.toml`` is the single source of truth
for the version; we read it via installed distribution metadata so the two
cannot drift.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("agentprobe")
except PackageNotFoundError:  # pragma: no cover - running from an uninstalled source tree
    __version__ = "0.1.0"
