from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from agentprobe.tools.sandbox import Sandbox


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="edit",
        description=(
            "Replace text in an existing file inside the workspace. When replace_all is "
            "false, old_string must occur exactly once. Not parallel-safe."
        ),
    )
    async def edit(
        path: Annotated[str, Field(description="Relative path in the workspace.", min_length=1, max_length=4096)],
        old_string: Annotated[str, Field(description="Text to search for.", min_length=1, max_length=100_000)],
        new_string: Annotated[str, Field(description="Replacement text.", max_length=100_000)],
        replace_all: Annotated[bool, Field(description="Replace all occurrences.")] = False,
    ) -> str:
        try:
            sb = Sandbox.from_env()
            target = sb.resolve(path)
            if not target.exists():
                return f"ERROR: not_found: {path}"
            text = target.read_text(encoding="utf-8")
            if replace_all:
                if old_string not in text:
                    return f"ERROR: old_string_not_found: {old_string[:80]!r}"
                new_text = text.replace(old_string, new_string)
            else:
                count = text.count(old_string)
                if count == 0:
                    return f"ERROR: old_string_not_found: {old_string[:80]!r}"
                if count > 1:
                    return f"ERROR: multiple_matches: {count} occurrences; use replace_all=True"
                new_text = text.replace(old_string, new_string, 1)
            target.write_text(new_text, encoding="utf-8")
            return f"OK: edited {path} ({len(old_string)} -> {len(new_string)} chars)"
        except Exception as e:
            return f"ERROR: io_error: {e}"
