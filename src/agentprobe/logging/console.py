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
            # `verbose` shows full arguments; otherwise truncate long values.
            if self.level != "verbose" and len(s) > self.truncate:
                s = s[: self.truncate] + "\u2026"
            parts.append(f"{k}={s}")
        return ", ".join(parts)

    def user(self, text: str) -> None:
        if self.level == "quiet":
            return
        self._console.print(f"[cyan]{escape('[user]')}[/cyan] {escape(text)}")

    def assistant(self, text: str) -> None:
        self._console.print(f"[green]{escape('[assistant]')}[/green] {escape(text)}")

    def stream_begin(self, prefix: str = "[assistant]") -> None:
        self._console.print(f"[green]{escape(prefix)}[/green] ", end="", soft_wrap=True)

    def stream_write(self, text: str) -> None:
        self._console.print(text, end="", markup=False, soft_wrap=True)
        self._console.file.flush()

    def stream_end(self) -> None:
        self._console.print()

    def tool_line(
        self,
        name: str,
        args: dict[str, Any],
        duration_ms: float | None = None,
        error: str | None = None,
    ) -> str:
        suffix = f" [{duration_ms:.0f}ms]" if duration_ms is not None else ""
        err = f" ERROR: {error}" if error else ""
        return f"\u2192 {name}({self._fmt_args(args)}){suffix}{err}"

    def tool(
        self,
        name: str,
        args: dict[str, Any],
        duration_ms: float | None = None,
        error: str | None = None,
    ) -> None:
        if self.level == "quiet":
            return
        line = self.tool_line(name, args, duration_ms, error)
        self._console.print(f"[yellow]{escape(line)}[/yellow]", soft_wrap=True)

    def error(self, text: str) -> None:
        self._console.print(f"[red]{escape('[error]')}[/red] {escape(text)}")

    def warning(self, text: str) -> None:
        self._console.print(f"[yellow]{escape('[warning]')}[/yellow] {escape(text)}")

    def info(self, text: str) -> None:
        if self.level == "quiet":
            return
        self._console.print(f"[dim]{escape('[info]')}[/dim] {escape(text)}")

    def interrupt(self, text: str) -> None:
        self._console.print(f"[red]{escape('[interrupt]')}[/red] {escape(text)}")

    def tokens(self, line: str) -> None:
        if self.level == "quiet":
            return
        self._console.print(f"[dim]tokens: {escape(line)}[/dim]", soft_wrap=True)

    def run(self, run_id: str, text: str) -> None:
        if self.level == "quiet":
            return
        self._console.print(f"[run {run_id}] {text}", style="dim", markup=False, soft_wrap=True)

    def scenario(self, name: str, text: str) -> None:
        if self.level == "quiet":
            return
        self._console.print(
            f"[scenario {name}] {text}", style="dim", markup=False, soft_wrap=True
        )

    def status(self, status: str, text: str) -> None:
        color = {"PASS": "green", "FAIL": "red", "LIMIT": "red", "ERROR": "red", "SKIP": "dim"}.get(status, "")
        styled = f"[{color}]{status}[/{color}]" if color else status
        self._console.print(f"{styled} {escape(text)}", soft_wrap=True)

    def plain(self, text: str = "") -> None:
        if text:
            self._console.print(escape(text), markup=False, soft_wrap=True)
        else:
            self._console.print()
