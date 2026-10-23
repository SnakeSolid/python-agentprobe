"""A minimal OpenAI-compatible streaming server for the ``--record`` round-trip.

The CLI talks to this endpoint instead of a real LLM, so ``--record`` can write a
real JSONL fixture without network access or a real model. It serves one assistant
message whose content is ``TEXT``.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Self

TEXT = "hello world"


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        nl = chr(10)
        d1 = {
            "choices": [{"index": 0, "delta": {"role": "assistant", "content": TEXT}}]
        }
        d2 = {
            "choices": [],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        for d in (d1, d2):
            self.wfile.write(("data: " + json.dumps(d) + nl + nl).encode())
            self.wfile.flush()

    def log_message(self, *args: object) -> None:
        pass


class FakeLLMServer:
    """Runs the fake LLM in a background thread; use as a context manager."""

    def __init__(self, text: str = "hello world"):
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def __enter__(self) -> Self:
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._httpd = None
        self._thread = None

    @property
    def endpoint(self) -> str:
        assert self._httpd is not None
        host, port = self._httpd.server_address
        return f"http://{host}:{port}/v1"
