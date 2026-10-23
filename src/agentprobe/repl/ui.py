from __future__ import annotations

from agentprobe.logging.console import Console


class StreamPrinter:
    """Streams assistant content incrementally with a one-time prefix per segment."""

    def __init__(self, console: Console):
        self.console = console
        self._started = False

    def begin_segment(self) -> None:
        self._started = False

    def on_chunk(self, chunk: str) -> None:
        if not self._started:
            self._started = True
            self.console.stream_begin()
        self.console.stream_write(chunk)

    def end_segment(self) -> None:
        if self._started:
            self.console.stream_end()
            self._started = False
