"""Exercise the MCP ``stdio`` tool transport (subprocess tool server)."""

import yaml

from agentprobe.config import load_config
from agentprobe.tools.client import MCPToolClient


async def _stdio_client(project, tmp_path):
    # Re-dump the project config on disk with the stdio transport enabled so the
    # subprocess tool server can locate the config via AGENTPROBE_CONFIG.
    data = project.model_dump(mode="json")
    data["app"]["tool_transport"] = "stdio"
    cfg_path = tmp_path / "stdio_config.yaml"
    cfg_path.write_text(yaml.safe_dump(data))
    cfg = load_config(cfg_path)
    return await MCPToolClient.start(
        cfg=cfg, config_path=cfg_path, tool_vars={}, workspace=cfg.app.workspace
    )


async def test_stdio_list_tools(project, tmp_path):
    c = await _stdio_client(project, tmp_path)
    try:
        schemas = await c.schemas()
        names = {s["function"]["name"] for s in schemas}
        assert "read_doc" in names
        assert "write" in names
    finally:
        await c.close()


async def test_stdio_read_doc_and_errors(project, tmp_path):
    c = await _stdio_client(project, tmp_path)
    try:
        res = await c.call_tool("read_doc", {"name": "vrp_basic"})
        assert not res.is_error
        assert "stub" in res.content

        res2 = await c.call_tool("read_doc", {"name": "missing"})
        assert res2.is_error

        res3 = await c.call_tool("read", {"path": "../../etc/passwd"})
        assert res3.is_error
    finally:
        await c.close()


async def test_stdio_write_and_read(project, tmp_path):
    c = await _stdio_client(project, tmp_path)
    try:
        res = await c.call_tool("write", {"path": "ok.txt", "content": "hello"})
        assert not res.is_error
        res2 = await c.call_tool("read", {"path": "ok.txt"})
        assert not res2.is_error
        assert "hello" in res2.content
    finally:
        await c.close()
