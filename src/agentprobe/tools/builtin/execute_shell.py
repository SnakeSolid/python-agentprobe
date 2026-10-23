"""Mock shell execution (honours `tool_vars`), same shape as command_execute."""

from __future__ import annotations

import json
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from agentprobe.tools.vars import get_tool_vars


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="execute_shell",
        description=(
            "Mock shell command execution (no real process). Returns a response configured "
            "via `tool_vars.execute_shell.responses`, an ERROR for matching `fail_on` "
            "substrings, or a fixed mock success."
        ),
    )
    async def execute_shell(
        command: Annotated[str, Field(
            description="Shell command to execute (mock).", min_length=1, max_length=8000,
        )],
    ) -> str:
        tv = get_tool_vars().get("execute_shell", {})
        responses: dict[str, str] = tv.get("responses", {})
        fail_on: list[str] = tv.get("fail_on", [])

        if command in responses:
            return responses[command]
        if any(sub in command for sub in fail_on):
            return f"ERROR: forbidden: {command}"
        return json.dumps({"ok": True, "output": "(mock) command accepted"})
