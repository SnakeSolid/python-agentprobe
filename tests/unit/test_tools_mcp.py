import json
from pathlib import Path

from agentprobe.tools.client import MCPToolClient


async def _client(project):
    return await MCPToolClient.start(
        cfg=project, config_path=Path("unused"), tool_vars={},
        workspace=project.app.workspace,
    )


async def test_write_creates_file(project):
    c = await _client(project)
    try:
        res = await c.call_tool("write", {"path": "new.txt", "content": "hello"})
        assert not res.is_error
        assert (project.app.workspace / "new.txt").read_text() == "hello"
    finally:
        await c.close()


async def test_write_existing_fails(project):
    (project.app.workspace / "ex.txt").write_text("x")
    c = await _client(project)
    try:
        res = await c.call_tool("write", {"path": "ex.txt", "content": "y"})
        assert res.is_error
        assert "exists" in res.content
    finally:
        await c.close()


async def test_write_escape_workspace(project):
    c = await _client(project)
    try:
        res = await c.call_tool("write", {"path": "../../evil.txt", "content": "pwn"})
        assert res.is_error
        assert not (project.app.workspace.parent / "evil.txt").exists()
    finally:
        await c.close()


async def test_read_escape_workspace(project):
    c = await _client(project)
    try:
        res = await c.call_tool("read", {"path": "../../etc/passwd"})
        assert res.is_error
        assert "sandbox" in res.content or "ERROR" in res.content
    finally:
        await c.close()


async def test_edit_unique(project):
    (project.app.workspace / "f.txt").write_text("a b a")
    c = await _client(project)
    try:
        res = await c.call_tool("edit", {"path": "f.txt", "old_string": " b ", "new_string": " X "})
        assert not res.is_error
        assert (project.app.workspace / "f.txt").read_text() == "a X a"
    finally:
        await c.close()


async def test_edit_not_unique(project):
    (project.app.workspace / "f.txt").write_text("aa aa")
    c = await _client(project)
    try:
        res = await c.call_tool("edit", {"path": "f.txt", "old_string": "aa", "new_string": "z"})
        assert res.is_error
        assert "not_unique" in res.content
    finally:
        await c.close()


async def test_edit_replace_all(project):
    (project.app.workspace / "f.txt").write_text("aa aa")
    c = await _client(project)
    try:
        res = await c.call_tool(
            "edit", {"path": "f.txt", "old_string": "aa", "new_string": "z", "replace_all": True}
        )
        assert not res.is_error
        assert (project.app.workspace / "f.txt").read_text() == "z z"
    finally:
        await c.close()


async def test_syntax_check(project):
    c = await _client(project)
    try:
        res = await c.call_tool(
            "syntax_check", {"commands": "# comment\n\nsystem-view\n? help\n commit\n"}
        )
        data = json.loads(res.content)
        assert data["ok"] is False
        assert len(data["errors"]) == 2
    finally:
        await c.close()


async def test_syntax_check_ok(project):
    c = await _client(project)
    try:
        res = await c.call_tool("syntax_check", {"commands": "system-view\n# ok\n"})
        data = json.loads(res.content)
        assert data["ok"] is True
        assert data["errors"] == []
    finally:
        await c.close()


async def test_read_doc_stub(project):
    c = await _client(project)
    try:
        res = await c.call_tool("read_doc", {"name": "vrp_basic"})
        assert not res.is_error
        assert "stub" in res.content
        res2 = await c.call_tool("read_doc", {"name": "missing"})
        assert res2.is_error
    finally:
        await c.close()


async def test_validation_error_is_error(project):
    c = await _client(project)
    try:
        res = await c.call_tool("read", {"path": "a.txt", "limit": 2_000_000})
        assert res.is_error
    finally:
        await c.close()
