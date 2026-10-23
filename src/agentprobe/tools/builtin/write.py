"""Create a new text file inside the workspace."""

from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from agentprobe.tools.sandbox import Sandbox


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="write",
        description=(
            "Create a NEW text file inside the workspace. Fails if it already exists. "
            "Parent directories are not created. Not parallel-safe."
        ),
    )
    async def write(
        path: Annotated[str, Field(
            description="Relative path in the workspace.", min_length=1, max_length=4096,
        )],
        content: Annotated[str, Field(
            description="File content (UTF-8).", max_length=1_000_000,
        )],
    ) -> str:
        try:
            sb = Sandbox.from_env()
            target = sb.resolve(path)
            if target.exists():
                return f"ERROR: exists: {path}"
            if not target.parent.exists():
                return f"ERROR: missing_parent: {target.parent}"
            target.write_text(content, encoding="utf-8")
            return f"OK: wrote {len(content)} chars to {path}"
        except Exception as e:
            return f"ERROR: io_error: {e}"
