from __future__ import annotations

import asyncio
import json
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

import anyio
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.server.fastmcp import FastMCP

from agentprobe.config import load_config
from agentprobe.errors import ConfigError
from agentprobe.llm.types import ToolResult
from agentprobe.tools.server import build_server

# Env vars injected for tool modules.
ENV_WORKSPACE = "AGENTPROBE_WORKSPACE"
ENV_TOOL_VARS = "AGENTPROBE_TOOL_VARS"
ENV_DOCS_DIR = "AGENTPROBE_DOCS_DIR"
ENV_SKILLS_DIR = "AGENTPROBE_SKILLS_DIR"
ENV_CONFIG = "AGENTPROBE_CONFIG"


class MCPToolClient:
    """Client-side wrapper over an MCP server (in-memory or stdio)."""

    def __init__(self) -> None:
        self.transport: str | None = None
        self._stack = AsyncExitStack()
        self._session: ClientSession | None = None
        self._mcp: FastMCP | None = None
        self._server_task: asyncio.Task[None] | None = None
        self._closed = False

    @classmethod
    async def start(
        cls,
        *,
        transport: str,
        config_path: Path,
        tool_vars: dict[str, dict[str, Any]],
        workspace: Path,
        docs_dir: Path,
        skills_dir: Path,
    ) -> MCPToolClient:
        self = cls()
        self.transport = transport

        env = os.environ.copy()
        env[ENV_WORKSPACE] = str(workspace)
        env[ENV_TOOL_VARS] = json.dumps(tool_vars)
        env[ENV_DOCS_DIR] = str(docs_dir)
        env[ENV_SKILLS_DIR] = str(skills_dir)
        env[ENV_CONFIG] = str(config_path)
        os.environ.update(env)

        try:
            if transport == "in_memory":
                await self._start_in_memory(config_path, env)
            elif transport == "stdio":
                await self._start_stdio(config_path, env)
            else:
                raise ConfigError(f"unknown tool_transport: {transport}")
        except Exception:
            await self.close()
            raise
        return self

    async def _start_in_memory(self, config_path: Path, env: dict[str, str]) -> None:
        cfg = load_config(config_path)
        dirs: list[Path] = [Path(__file__).parent / "builtin"]
        if cfg.app.user_tools_dir:
            dirs.append(cfg.app.user_tools_dir)
        self._mcp = build_server(*dirs)

        send1, recv1 = anyio.create_memory_object_stream[Any](256)
        send2, recv2 = anyio.create_memory_object_stream[Any](256)
        # Server reads from recv1 (client writes via send1); server writes via send2 -> client reads recv2.
        server_read, client_write = recv1, send1
        client_read, server_write = recv2, send2

        opts = self._mcp._mcp_server.create_initialization_options()

        async def _run_server() -> None:
            await self._mcp._mcp_server.run(  # type: ignore[union-attr]
                server_read, server_write, opts
            )

        self._server_task = asyncio.create_task(_run_server())
        try:
            session = await self._stack.enter_async_context(
                ClientSession(client_read, client_write)
            )
            await session.initialize()
            self._session = session
        except Exception:
            if self._server_task is not None:
                self._server_task.cancel()
            raise

    async def _start_stdio(self, config_path: Path, env: dict[str, str]) -> None:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "agentprobe.tools.server"],
            env=env,
            cwd=str(Path.cwd()),
        )
        read, write = await self._stack.enter_async_context(stdio_client(params))
        session = await self._stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        self._session = session

    async def schemas(self, enabled: list[str] | None = None) -> list[dict[str, Any]]:
        assert self._session is not None
        result = await self._session.list_tools()
        out: list[dict[str, Any]] = []
        for t in result.tools:
            if enabled is not None and t.name not in enabled:
                continue
            out.append(
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description or "",
                        "parameters": t.inputSchema or {"type": "object", "properties": {}},
                    },
                }
            )
        return out

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        assert self._session is not None
        try:
            result = await self._session.call_tool(name, arguments or {})
        except Exception as e:
            return ToolResult(
                call_id="", name=name, content=f"ERROR: rpc_error: {e}", is_error=True
            )
        text = self._extract_text(result)
        is_error = bool(getattr(result, "isError", False)) or text.startswith("ERROR:")
        return ToolResult(call_id="", name=name, content=text, is_error=is_error)

    @staticmethod
    def _extract_text(result: Any) -> str:
        parts: list[str] = []
        for block in getattr(result, "content", None) or []:
            if hasattr(block, "text"):
                parts.append(block.text)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._server_task is not None:
            self._server_task.cancel()
            try:
                await self._server_task
            except (asyncio.CancelledError, Exception):  # noqa: S110
                pass
        try:
            await self._stack.aclose()
        except Exception:  # noqa: S110
            pass
