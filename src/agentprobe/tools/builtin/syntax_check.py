from __future__ import annotations

import json
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="syntax_check",
        description=(
            "Basic VRP syntax validation. Rejects '?' and the token 'commit'. "
            "Returns JSON {ok, errors}. This is a result, not an error. Parallel-safe."
        ),
    )
    async def syntax_check(
        commands: Annotated[str, Field(description="Multi-line VRP script.", max_length=100_000)],
    ) -> str:
        errors: list[str] = []
        for i, raw in enumerate(commands.splitlines(), start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "?" in line:
                errors.append(f"line {i}: '?' not allowed")
            if "commit" in line.split():
                errors.append(f"line {i}: 'commit' not allowed")
        return json.dumps({"ok": not errors, "errors": errors})
