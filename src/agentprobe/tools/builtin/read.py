"""Read a text file inside the workspace."""

from __future__ import annotations

from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from agentprobe.tools.sandbox import Sandbox


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="read",
        description=(
            "Read a text file inside the workspace. Truncates to `limit` chars "
            "and appends a marker when truncated. Fails on paths escaping the workspace."
        ),
    )
    async def read(
        path: Annotated[str, Field(
            description="Path to a text file, relative to the workspace root. "
                        "Absolute paths are rejected unless inside the workspace.",
            min_length=1, max_length=4096,
        )],
        offset: Annotated[int, Field(
            description="Byte offset to start reading from (0-based).", ge=0,
        )] = 0,
        limit: Annotated[int, Field(
            description="Maximum number of characters to return.", ge=1, le=1_000_000,
        )] = 100_000,
        encoding: Annotated[Literal["utf-8", "utf-8-sig", "latin-1"], Field(
            description="Text encoding used to decode the file.",
        )] = "utf-8",
    ) -> str:
        try:
            sb = Sandbox.from_env()
            target = sb.resolve(path)
            text = target.read_bytes().decode(encoding, errors="replace")
        except Exception as e:
            return f"ERROR: io_error: {e}"
        chunk = text[offset : offset + limit]
        if offset + limit < len(text):
            chunk += f"\n… [truncated {len(text) - offset - limit} chars]"
        return chunk
