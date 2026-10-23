from __future__ import annotations

import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import yaml


class Logger(Protocol):
    """Structural interface shared by YamlLogger (parent) and SubLogger (subagents)."""

    path: Path
    session_id: str

    def log(self, event: str, **kwargs: Any) -> None: ...

    def close(self) -> None: ...


class YamlLogger:
    def __init__(self, path: Path, session_id: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.session_id = session_id
        self._fp = path.open("a", encoding="utf-8")

    def log(self, event: str, **kwargs: Any) -> None:
        payload = {
            "event": event,
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "session_id": self.session_id,
            **kwargs,
        }
        self._fp.write("---\n")
        self._fp.write(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True))
        self._fp.flush()

    def close(self) -> None:
        if self._fp is not None and not self._fp.closed:
            self._fp.close()


def new_session_id(mode: str) -> str:
    return f"{mode}_{datetime.now(UTC):%Y%m%d_%H%M%S}_{secrets.token_hex(2)}"


def new_run_id() -> str:
    return f"{datetime.now(UTC):%Y%m%d_%H%M%S}_{secrets.token_hex(2)}"
