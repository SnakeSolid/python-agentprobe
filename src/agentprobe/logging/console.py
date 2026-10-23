"""Compact console output with optional ANSI colors."""

from __future__ import annotations

import sys
from typing import Any

_RESET = "\x1b[0m"
_CYAN = "\x1b[36m"
_GREEN = "\x1b[32m"
_YELLOW = "\x1b[33m"
_RED = "\x1b[31m"
_DIM = "\x1b[2m"


class Console:
    def __init__(
        self,
        level: str = "info",
        color: str = "auto",
        truncate: int = 400,
    ):
        self.level = level
        self.truncate = truncate
        self.color = self._resolve_color(color)

    @staticmethod
    def _resolve_color(mode: str) -> bool:
        if mode == "always":
            return True
        if mode == "never":
            return False
        return sys.stdout.isatty()

    def _paint(self, color: str, text: str) -> str:
        if not self.color:
            return text
        return f"{color}{text}{_RESET}"

    def _truncate(self, text: str) -> str:
        if self.truncate and len(text) > self.truncate:
            return text[: self.truncate] + "…"
        return text

    def user(self, text: str) -> None:
        if self.level == "quiet":
            return
        print(self._paint(_CYAN, f"[user] {self._truncate(text)}"))

    def assistant(self, text: str) -> None:
        if self.level == "quiet":
            return
        print(self._paint(_GREEN, f"[assistant] {self._truncate(text)}"))

    def tool(self, name: str, args: dict[str, Any], ms: float) -> None:
        if self.level == "quiet":
            return
        args_str = ", ".join(f"{k}={v}" for k, v in args.items())
        line = f"→ {name}({args_str}) [{ms:.0f}ms]"
        print(self._paint(_YELLOW, line))

    def error(self, text: str) -> None:
        print(self._paint(_RED, text), file=sys.stderr)

    def warn(self, text: str) -> None:
        print(self._paint(_YELLOW, f"warning: {text}"))

    def tokens_line(
        self,
        token_in: int | None,
        token_out: int | None,
        turn_ms: float,
        total_ms: float,
    ) -> None:
        if self.level == "quiet":
            return
        in_s = "-" if token_in is None else str(token_in)
        out_s = "-" if token_out is None else str(token_out)
        line = (
            f"tokens: in={in_s} out={out_s} | turn {turn_ms:.0f}ms | total {total_ms / 1000:.1f}s"
        )
        print(self._paint(_DIM, line))

    def info(self, text: str) -> None:
        if self.level == "quiet":
            return
        print(text)
