from __future__ import annotations

from typing import Any, Protocol

from agentprobe.agent.observer import SessionCtx
from agentprobe.logging.console import Console


def error_label(res: Any) -> str | None:
    """Short error label for a failed tool result, or ``None`` if it succeeded.

    Tool error content is typically already prefixed with ``ERROR:``; strip it
    so the facade adds the prefix exactly once.
    """
    if not getattr(res, "is_error", False):
        return None
    content = getattr(res, "content", "") or ""
    first = content.splitlines()[0][:200] if content else "error"
    if first.upper().startswith("ERROR:"):
        first = first[len("ERROR:") :].lstrip()
    return first


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
        msg: int | None = None,
    ) -> None: ...

    def tool_start(self, name: str, args: dict[str, Any]) -> None: ...

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
        msg: int | None = None,
    ) -> None: ...

    def tool_start(self, name: str, args: dict[str, Any]) -> None: ...

    def turn_start(self, ctx: SessionCtx, *, tools_count: int, messages_count: int) -> None: ...

    def turn_end(self, ctx: SessionCtx, latency_ms: float, *, partial: bool = False) -> None: ...


class ConsoleUi:
    """Renders loop events to STDOUT honouring mode + verbosity.

    - ``mode="repl"``: assistant text is streamed per chunk; user input is not
      echoed (the ``>>> `` prompt already echoes it); tool lines have no prefix.
    - ``mode="headless"``: assistant segments are buffered and only surfaced at
      ``verbose``; tool lines are prefixed with ``[scenario <name>]`` and carry
      the agent-message number that issued them.
    """

    def __init__(self, console: Console, *, mode: str, scenario: str | None = None):
        if mode not in ("repl", "headless"):
            raise ValueError(f"unsupported ui mode: {mode}")
        self.console = console
        self.mode = mode
        self.scenario = scenario
        self._buf: list[str] = []
        self._written = 0
        self._started = False

    def segment_start(self) -> None:
        self._buf = []
        self._written = 0
        self._started = False

    def chunk(self, text: str) -> None:
        self._buf.append(text)
        # In repl mode stream incrementally, but hold back any trailing
        # whitespace so a segment that ends before a tool call does not emit
        # blank lines (matches headless `.rstrip()` behaviour).
        if self.mode == "repl":
            self._flush_repl()

    def _flush_repl(self) -> None:
        full = "".join(self._buf)
        n = len(full)
        while n > 0 and full[n - 1].isspace():
            n -= 1
        if n > self._written:
            to_write = full[self._written:n]
            if not self._started:
                self._started = True
                self.console.stream_begin()
            self.console.stream_write(to_write)
            self._written = n

    def segment_end(self) -> None:
        if self.mode == "repl":
            self._flush_repl()  # flush any remaining non-whitespace content
            if self._started:
                self.console.stream_end()
            self._buf = []
            self._written = 0
            self._started = False
        else:
            text = "".join(self._buf).rstrip()
            if self.console.level == "verbose" and text:
                self.console.assistant(text)
            self._buf = []

    def tool_start(self, name: str, args: dict[str, Any]) -> None:
        """Print a tool header (name + arguments) before it runs.

        Used by ``spawn_agent`` so the subagent's own activity is framed by the
        spawn call; the matching result line is emitted by :meth:`tool`.
        """
        if self.console.level == "quiet":
            return
        if self.scenario is not None:
            self.console.scenario(self.scenario, f"  {self.console.tool_line(name, args)}")
        else:
            self.console.tool(name, args)

    def tool(
        self,
        name: str,
        args: dict[str, Any],
        duration_ms: float | None = None,
        error: str | None = None,
        msg: int | None = None,
    ) -> None:
        if self.console.level == "quiet":
            return
        if name == "spawn_agent":
            # Header already printed by tool_start(); emit result + duration only.
            line = self.console.tool_footer_line(name, duration_ms, error)
            if self.scenario is not None:
                self.console.scenario(self.scenario, f"  {line}")
            else:
                self.console.tool_footer(name, duration_ms, error)
            return
        if self.scenario is not None:
            line = self.console.tool_line(name, args, duration_ms, error)
            self.console.scenario(self.scenario, f"  {line}" + (f"  (msg {msg})" if msg else ""))
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


class SubagentUi(Ui):
    """Surfaces a subagent's own activity on STDOUT at ``verbose`` level.

    Each line is tagged with the sub-session id (e.g. ``repl_.../sub-1``) so it
    is clearly attributed to the subagent rather than the parent. Below
    ``verbose`` it stays silent, matching the spec default where subagent
    internals are hidden and surface only via the parent's summary.
    """

    def __init__(self, console: Console, session_id: str):
        self.console = console
        self.session_id = session_id
        self._buf: list[str] = []

    def segment_start(self) -> None:
        self._buf = []

    def chunk(self, text: str) -> None:
        self._buf.append(text)

    def segment_end(self) -> None:
        text = "".join(self._buf).rstrip()
        if self.console.level == "verbose" and text:
            self._sub(f"[assistant] {text}")
        self._buf = []

    def tool_start(self, name: str, args: dict[str, Any]) -> None:
        # Subagents never spawn further subagents; nothing to emit.
        pass

    def tool(
        self,
        name: str,
        args: dict[str, Any],
        duration_ms: float | None = None,
        error: str | None = None,
        msg: int | None = None,
    ) -> None:
        if self.console.level != "verbose":
            return
        line = self.console.tool_line(name, args, duration_ms, error)
        self._sub(line + (f"  (msg {msg})" if msg else ""))

    def turn_start(self, ctx: SessionCtx, *, tools_count: int, messages_count: int) -> None:
        if self.console.level != "verbose":
            return
        self._sub(
            f"turn {ctx.turn} | messages={messages_count} tools={tools_count} "
            f"| context\u2248{ctx.tokens_in + ctx.tokens_out} tokens"
        )

    def turn_end(self, ctx: SessionCtx, latency_ms: float, *, partial: bool = False) -> None:
        if self.console.level != "verbose":
            return
        sfx = " (partial)" if partial else ""
        self._sub(
            f"turn_end {ctx.turn} | latency={latency_ms:.0f}ms | "
            f"tokens in={ctx.tokens_in} out={ctx.tokens_out}{sfx}"
        )

    def _sub(self, text: str) -> None:
        self.console.subagent(self.session_id, text)
