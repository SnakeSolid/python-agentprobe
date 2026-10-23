from __future__ import annotations

import logging
from typing import Any

from rich.console import Console as RichConsole
from rich.markup import escape


def configure_logging() -> None:
    """Silence noisy third-party loggers (MCP, openai, httpx)."""
    for name in ("mcp", "openai", "httpx", "httpcore", "anyio", "urllib3"):
        logging.getLogger(name).setLevel(logging.WARNING)
        logging.getLogger(name).propagate = False


class Console:
    """Thin wrapper over rich console honouring `logging.console_level` / `color`."""

    def __init__(self, level: str = "info", color: str = "auto", truncate: int = 400):
        self.level = level
        self.truncate = truncate
        force_terminal = None
        if color == "always":
            force_terminal = True
        elif color == "never":
            force_terminal = False
        self._console = RichConsole(force_terminal=force_terminal)

    def _fmt_args(self, args: dict[str, Any]) -> str:
        parts = []
        for k, v in args.items():
            s = str(v)
            if len(s) > self.truncate:
                s = s[: self.truncate] + "\u2026"
            parts.append(f"{k}={s}")
        return ", ".join(parts)

    def user(self, text: str) -> None:
        if self.level == "quiet":
            return
        self._console.print(f"[cyan][user][/cyan] {escape(text)}")

    def assistant(self, text: str) -> None:
        self._console.print(f"[green][assistant][/green] {escape(text)}")

    def stream_begin(self, prefix: str = "[assistant]") -> None:
        self._console.print(f"[green]{escape(prefix)}[/green] ", end="")

    def stream_write(self, text: str) -> None:
        self._console.print(text, end="")
        self._console.file.flush()

    def stream_end(self) -> None:
        self._console.print()

    def tool(self, name: str, args: dict[str, Any], duration_ms: float | None = None) -> None:
        if self.level == "quiet":
            return
        suffix = f" [{duration_ms:.0f}ms]" if duration_ms is not None else ""
        self._console.print(f"[yellow]\u2192 {name}({escape(self._fmt_args(args))}){suffix}[/yellow]")

    def error(self, text: str) -> None:
        self._console.print(f"[red][error][/red] {escape(text)}")

    def warning(self, text: str) -> None:
        self._console.print(f"[yellow][warning][/yellow] {escape(text)}")

    def info(self, text: str) -> None:
        if self.level == "quiet":
            return
        self._console.print(f"[dim][info][/dim] {escape(text)}")

    def interrupt(self, text: str) -> None:
        self._console.print(f"[red][interrupt][/red] {escape(text)}")

    def tokens(self, line: str) -> None:
        if self.level == "quiet":
            return
        self._console.print(f"[dim]tokens: {escape(line)}[/dim]")

    def run(self, run_id: str, text: str) -> None:
        if self.level == "quiet":
            return
        self._console.print(f"[run {run_id}] {text}", style="dim", markup=False)

    def scenario(self, name: str, text: str) -> None:
        if self.level == "quiet":
            return
        self._console.print(f"[scenario {name}] {text}", style="dim", markup=False)

    def status(self, status: str, text: str) -> None:
        color = {"PASS": "green", "FAIL": "red", "LIMIT": "red", "ERROR": "red", "SKIP": "dim"}.get(status, "")
        styled = f"[{color}]{status}[/{color}]" if color else status
        self._console.print(f"{styled} {escape(text)}")

    def plain(self, text: str = "") -> None:
        if text:
            self._console.print(escape(text), markup=False)
        else:
            self._console.print()
