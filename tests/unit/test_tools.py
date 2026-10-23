import pytest
import yaml

from agentprobe.tools.client import MCPToolClient


@pytest.fixture
async def client(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text("# Guide\nThis is the guidance.")
    skills_dir = tmp_path / "skills"
    (skills_dir / "s1").mkdir(parents=True)
    (skills_dir / "s1" / "SKILL.md").write_text(
        "---\nname: s1\ndescription: demo skill\n---\nskill body line"
    )
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "system.md").write_text("base")
    logs = tmp_path / "logs"
    logs.mkdir()
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        yaml.safe_dump(
            {
                "app": {
                    "workspace": str(ws),
                    "docs_dir": str(docs),
                    "skills_dir": str(skills_dir),
                    "prompt_file": str(prompts / "system.md"),
                    "memory_file": str(ws / "MEMORY.md"),
                    "log_dir": str(logs),
                },
                "models": {"main": {"endpoint": "http://x", "api_key": "k", "model": "m"}},
                "limits": {},
                "tools": {},
            }
        )
    )
    tool_vars = {
        "command_execute": {"responses": {"display current-configuration": "interface GigabitEthernet0/0/0"}}
    }
    c = await MCPToolClient.start(
        transport="in_memory",
        config_path=cfg_path,
        tool_vars=tool_vars,
        workspace=ws,
        docs_dir=docs,
        skills_dir=skills_dir,
    )
    try:
        yield c
    finally:
        await c.close()


async def test_write_and_read(client):
    res = await client.call_tool("write", {"path": "cfg.txt", "content": "hello world"})
    assert res.is_error is False
    assert "OK" in res.content
    res2 = await client.call_tool("read", {"path": "cfg.txt"})
    assert "hello world" in res2.content


async def test_write_exists_error(client):
    await client.call_tool("write", {"path": "a.txt", "content": "x"})
    res = await client.call_tool("write", {"path": "a.txt", "content": "y"})
    assert res.is_error is True
    assert "exists" in res.content


async def test_write_missing_parent_error(client):
    res = await client.call_tool("write", {"path": "nested/b.txt", "content": "x"})
    assert res.is_error is True
    assert "missing_parent" in res.content


async def test_edit_ok(client):
    await client.call_tool("write", {"path": "f.txt", "content": "one two one"})
    res = await client.call_tool(
        "edit", {"path": "f.txt", "old_string": "two", "new_string": "TWO"}
    )
    assert res.is_error is False
    assert "OK" in res.content
    out = await client.call_tool("read", {"path": "f.txt"})
    assert out.content == "one TWO one"


async def test_edit_multiple_matches_error(client):
    await client.call_tool("write", {"path": "f.txt", "content": "one one"})
    res = await client.call_tool(
        "edit", {"path": "f.txt", "old_string": "one", "new_string": "x"}
    )
    assert res.is_error is True
    assert "multiple_matches" in res.content


async def test_edit_missing_file_error(client):
    res = await client.call_tool(
        "edit", {"path": "nope.txt", "old_string": "a", "new_string": "b"}
    )
    assert res.is_error is True
    assert "not_found" in res.content


async def test_read_doc_ok(client):
    res = await client.call_tool("read_doc", {"name": "guide"})
    assert res.is_error is False
    assert "guidance" in res.content


async def test_read_doc_missing(client):
    res = await client.call_tool("read_doc", {"name": "nope"})
    assert res.is_error is True
    assert "doc_not_found" in res.content


async def test_read_skill_ok(client):
    res = await client.call_tool("read_skill", {"name": "s1"})
    assert res.is_error is False
    assert "skill body line" in res.content
    # frontmatter stripped
    assert "name: s1" not in res.content


async def test_read_skill_missing(client):
    res = await client.call_tool("read_skill", {"name": "nope"})
    assert res.is_error is True
    assert "skill_not_found" in res.content


async def test_syntax_check_errors(client):
    res = await client.call_tool("syntax_check", {"commands": "show ?\ncommit"})
    assert res.is_error is False  # returns a result, not an error
    assert "errors" in res.content
    assert "'?' not allowed" in res.content
    assert "'commit' not allowed" in res.content


async def test_syntax_check_clean(client):
    res = await client.call_tool("syntax_check", {"commands": "display version"})
    assert res.is_error is False
    assert "\"ok\": true" in res.content


async def test_command_execute_with_tool_vars(client):
    res = await client.call_tool("command_execute", {"command": "display current-configuration"})
    assert res.is_error is False
    assert "GigabitEthernet0/0/0" in res.content


async def test_traversal_rejected_in_write(client):
    res = await client.call_tool("write", {"path": "../evil.txt", "content": "x"})
    assert res.is_error is True
    assert "ERROR" in res.content
