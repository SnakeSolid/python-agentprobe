"""Edit an existing text file by replacing a unique old string."""

from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from agentprobe.tools.sandbox import Sandbox


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="edit",
        description=(
            "Edit an existing file inside the workspace by replacing `old_string` with "
            "`new_string`. The file must exist and `old_string` must occur exactly once "
            "unless `replace_all` is set. Not parallel-safe."
        ),
    )
    async def edit(
        path: Annotated[str, Field(
            description="Relative path in the workspace.", min_length=1, max_length=4096,
        )],
        old_string: Annotated[str, Field(
            description="Exact text to replace.", min_length=1, max_length=100_000,
        )],
        new_string: Annotated[str, Field(
            description="Replacement text.", max_length=100_000,
        )] = "",
        replace_all: Annotated[bool, Field(
            description="Replace every occurrence instead of requiring uniqueness.",
        )] = False,
    ) -> str:
        try:
            sb = Sandbox.from_env()
            target = sb.resolve(path)
            if not target.exists():
                return f"ERROR: not_found: {path}"
            text = target.read_text(encoding="utf-8")
            count = text.count(old_string)
            if count == 0:
                return f"ERROR: old_string_not_found: {path}"
            if count > 1 and not replace_all:
                return f"ERROR: old_string_not_unique: {count} occurrences in {path}"
            new_text = text.replace(old_string, new_string)
            target.write_text(new_text, encoding="utf-8")
            return f"OK: replaced {count} occurrence(s) in {path}"
        except Exception as e:
            return f"ERROR: io_error: {e}"
