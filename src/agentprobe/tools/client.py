"""MCP tool client used by the orchestrator.

Supports both ``in_memory`` (same process) and ``stdio`` (subprocess) transports.
Tools are filtered by ``tools.enabled`` and errors are mapped to
:class:`ToolResult` with ``is_error=True``.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import TextContent

from agentprobe.config import Config
from agentprobe.llm.types import ToolResult
from agentprobe.tools.server import build_server

_PROTECTED_ENV_VARS = [
    "AGENTPROBE_WORKSPACE",
    "AGENTPROBE_DOCS_DIR",
    "AGENTPROBE_SKILLS_DIR",
    "AGENTPROBE_TOOL_VARS",
]

_env_lock = asyncio.Lock()


class MCPToolClient:
    # Transport lifecycle handles. For in_memory this references the
    # async-generator context manager used to create the session; for stdio it
    # references the ClientSession plus the stdio context manager. Typed as Any
    # because the concrete type differs per transport.
    _session_cm: Any = None
    _stdio_cm: Any = None

    def __init__(
        self,
        session: ClientSession,
        enabled: set[str],
        restore_env: dict[str, str | None],
    ):
        self._session = session
        self._enabled = enabled
        self._restore_env = restore_env

    @classmethod
    async def start(
        cls,
        cfg: Config,
        config_path: Path,
        tool_vars: dict[str, dict[str, Any]],
        workspace: Path,
    ) -> MCPToolClient:
        enabled = set(cfg.tools.enabled)
        env_vars = {
            "AGENTPROBE_WORKSPACE": str(workspace),
            "AGENTPROBE_DOCS_DIR": str(cfg.app.docs_dir),
            "AGENTPROBE_SKILLS_DIR": str(cfg.app.skills_dir),
            "AGENTPROBE_TOOL_VARS": json.dumps(tool_vars),
        }

        if cfg.app.tool_transport == "in_memory":
            async with _env_lock:
                restore = _set_env(env_vars)
                server = build_server(include_user=True)
            session_cm = create_connected_server_and_client_session(server)
            session = await session_cm.__aenter__()
            client = cls(session, enabled, restore)
            client._session_cm = session_cm
            return client

        # stdio transport
        sub_env = dict(os.environ)
        sub_env.update(env_vars)
        sub_env["AGENTPROBE_CONFIG"] = str(config_path)
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "agentprobe.tools.server"],
            env=sub_env,
        )
        stdio_cm = stdio_client(params)
        read, write = await stdio_cm.__aenter__()
        session = ClientSession(read, write)
        await session.__aenter__()
        await session.initialize()
        client = cls(session, enabled, {})
        client._session_cm = session
        client._stdio_cm = stdio_cm
        return client

    async def schemas(self) -> list[dict[str, Any]]:
        result = await self._session.list_tools()
        out: list[dict[str, Any]] = []
        for t in result.tools:
            if t.name not in self._enabled:
                continue
            out.append(
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.inputSchema,
                    },
                }
            )
        return out

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        result = await self._session.call_tool(name, arguments)
        text = _extract_text(result.content)
        is_error = bool(result.isError)
        if not is_error and text.startswith("ERROR:"):
            is_error = True
        return ToolResult(call_id="", name=name, content=text, is_error=is_error)

    async def close(self) -> None:
        try:
            if self._stdio_cm is not None:
                # stdio transport: close the ClientSession then the stdio context.
                try:
                    await self._session.__aexit__(None, None, None)
                finally:
                    await self._stdio_cm.__aexit__(None, None, None)
            elif self._session_cm is not None:
                # in-memory transport: keeping the context manager alive as an
                # attribute prevents the async generator being re-finalized a
                # second time by GC (which triggered the cross-task cancel-scope
                # error), so we can close it once via __aexit__.
                await self._session_cm.__aexit__(None, None, None)
        finally:
            async with _env_lock:
                for key, value in self._restore_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value


def _extract_text(content: list[Any]) -> str:
    parts: list[str] = []
    for item in content:
        if isinstance(item, TextContent):
            parts.append(item.text)
        else:
            text = getattr(item, "text", None)
            if text is not None:
                parts.append(str(text))
    return "\n".join(parts)


def _set_env(values: dict[str, str]) -> dict[str, str | None]:
    """Set the given env vars, returning the previous values for restore."""
    restore: dict[str, str | None] = {}
    for key in _PROTECTED_ENV_VARS:
        restore[key] = os.environ.get(key)
    for key, value in values.items():
        os.environ[key] = value
    return restore
