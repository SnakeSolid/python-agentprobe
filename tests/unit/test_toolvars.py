import json
from pathlib import Path

from agentprobe.tools.client import MCPToolClient


def _vars():
    return {
        "command_execute": {
            "responses": {"display version": "Huawei VRP V8 ..."},
            "fail_on": ["reboot", "reset"],
        }
    }


async def test_command_execute_response(project):
    c = await MCPToolClient.start(
        cfg=project, config_path=Path("unused"),
        tool_vars=_vars(), workspace=project.app.workspace,
    )
    try:
        res = await c.call_tool("command_execute", {"command": "display version"})
        assert not res.is_error
        assert "VRP V8" in res.content
    finally:
        await c.close()


async def test_command_execute_fail_on(project):
    c = await MCPToolClient.start(
        cfg=project, config_path=Path("unused"),
        tool_vars=_vars(), workspace=project.app.workspace,
    )
    try:
        res = await c.call_tool("command_execute", {"command": "reboot now"})
        assert res.is_error
        assert "forbidden" in res.content
    finally:
        await c.close()


async def test_command_execute_default_mock(project):
    c = await MCPToolClient.start(
        cfg=project, config_path=Path("unused"),
        tool_vars=_vars(), workspace=project.app.workspace,
    )
    try:
        res = await c.call_tool("command_execute", {"command": "show version"})
        assert not res.is_error
        data = json.loads(res.content)
        assert data["ok"] is True
    finally:
        await c.close()


async def test_no_tool_vars_empty(project):
    c = await MCPToolClient.start(
        cfg=project, config_path=Path("unused"),
        tool_vars={}, workspace=project.app.workspace,
    )
    try:
        res = await c.call_tool("command_execute", {"command": "display version"})
        assert not res.is_error
        data = json.loads(res.content)
        assert data["ok"] is True
    finally:
        await c.close()
