"""Mock VRP command execution (honours `tool_vars`)."""

from __future__ import annotations

import json
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from agentprobe.tools.vars import get_tool_vars


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="command_execute",
        description=(
            "Mock command execution (no real device). Returns a response configured via "
            "scenario `tool_vars.command_execute.responses`, or an ERROR for commands "
            "matching `fail_on` substrings, else a fixed mock success."
        ),
    )
    async def command_execute(
        command: Annotated[str, Field(
            description="VRP command to execute (mock).", min_length=1, max_length=8000,
        )],
    ) -> str:
        tv = get_tool_vars().get("command_execute", {})
        responses: dict[str, str] = tv.get("responses", {})
        fail_on: list[str] = tv.get("fail_on", [])

        if command in responses:
            return responses[command]
        if any(sub in command for sub in fail_on):
            return f"ERROR: forbidden: {command}"
        return json.dumps({"ok": True, "output": "(mock) command accepted"})
