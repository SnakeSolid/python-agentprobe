from __future__ import annotations

from typing import Any, Protocol

from agentprobe.agent.observer import SessionCtx
from agentprobe.logging.console import Console


def error_label(res: Any) -> str | None:
    """Short error label for a failed tool result, or ``None`` if it succeeded."""
    if not getattr(res, "is_error", False):
        return None
    content = getattr(res, "content", "") or ""
    return content.splitlines()[0][:200] if content else "error"


class Ui(Protocol):
    """Logging facade for the agent loop.

    The loop reports *what* happened (an assistant segment is streaming, a tool
    ran, a turn began/ended); the facade decides *how* to render it on STDOUT
    according to ``mode`` (repl vs headless) and verbosity (quiet/info/verbose).
    The same facade is the natural place to also sink session data (YAML) and
    scenario recording later.
    """

    def segment_start(self) -> None: ...

    def chunk(self, text: str) -> None: ...

    def segment_end(self) -> None: ...

    def tool(
        self,
        name: str,
        args: dict[str, Any],
        duration_ms: float | None = None,
        error: str | None = None,
    ) -> None: ...

    def turn_start(self, ctx: SessionCtx, *, tools_count: int, messages_count: int) -> None: ...

    def turn_end(self, ctx: SessionCtx, latency_ms: float, *, partial: bool = False) -> None: ...


class NoOpUi:
    """Discards all events (used for invisible subagents)."""

    def segment_start(self) -> None: ...

    def chunk(self, text: str) -> None: ...

    def segment_end(self) -> None: ...

    def tool(
        self,
        name: str,
        args: dict[str, Any],
        duration_ms: float | None = None,
        error: str | None = None,
    ) -> None: ...

    def turn_start(self, ctx: SessionCtx, *, tools_count: int, messages_count: int) -> None: ...

    def turn_end(self, ctx: SessionCtx, latency_ms: float, *, partial: bool = False) -> None: ...


class ConsoleUi:
    """Renders loop events to STDOUT honouring mode + verbosity.

    - ``mode="repl"``: assistant text is streamed per chunk; user input is not
      echoed (the ``>>> `` prompt already echoes it); tool lines have no prefix.
    - ``mode="headless"``: assistant segments are buffered and only surfaced at
      ``verbose``; tool lines are prefixed with ``[scenario <name>]``.
    """

    def __init__(self, console: Console, *, mode: str, scenario: str | None = None):
        if mode not in ("repl", "headless"):
            raise ValueError(f"unsupported ui mode: {mode}")
        self.console = console
        self.mode = mode
        self.scenario = scenario
        self._buf: list[str] = []
        self._streaming = False

    def segment_start(self) -> None:
        self._buf = []
        if self.mode == "repl":
            self._streaming = True
            self.console.stream_begin()

    def chunk(self, text: str) -> None:
        if self.mode == "repl":
            if self._streaming:
                self.console.stream_write(text)
        else:
            self._buf.append(text)

    def segment_end(self) -> None:
        if self.mode == "repl":
            if self._streaming:
                self.console.stream_end()
                self._streaming = False
        else:
            if self.console.level == "verbose" and self._buf:
                self.console.assistant("".join(self._buf))
            self._buf = []

    def tool(
        self,
        name: str,
        args: dict[str, Any],
        duration_ms: float | None = None,
        error: str | None = None,
    ) -> None:
        if self.console.level == "quiet":
            return
        if self.scenario is not None:
            line = self.console.tool_line(name, args, duration_ms, error)
            self.console.scenario(self.scenario, f"  {line}")
        else:
            self.console.tool(name, args, duration_ms, error)

    def turn_start(self, ctx: SessionCtx, *, tools_count: int, messages_count: int) -> None:
        if self.console.level != "verbose":
            return
        context = ctx.tokens_in + ctx.tokens_out
        self.console.info(
            f"turn {ctx.turn} | messages={messages_count} tools={tools_count} "
            f"| context\u2248{context} tokens"
        )

    def turn_end(self, ctx: SessionCtx, latency_ms: float, *, partial: bool = False) -> None:
        if self.console.level != "verbose":
            return
        sfx = " (partial)" if partial else ""
        self.console.info(
            f"turn_end {ctx.turn} | latency={latency_ms:.0f}ms | "
            f"tokens in={ctx.tokens_in} out={ctx.tokens_out}{sfx}"
        )
