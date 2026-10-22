# Appendix: Code Snippets and Examples

## G. Tool implementations (selected)

### G.1. `read`

```python
# src/agentprobe/tools/builtin/read.py
from typing import Annotated, Literal
from pydantic import Field
from mcp.server.fastmcp import FastMCP

from agentprobe.tools.sandbox import Sandbox


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="read",
        description=(
            "Read a text file inside the workspace. Truncates to `limit` chars "
            "and appends a marker when truncated. Fails on paths escaping the workspace."
        ),
    )
    async def read(
        path: Annotated[str, Field(
            description="Path to a text file, relative to the workspace root. "
                        "Absolute paths are rejected unless inside the workspace.",
            min_length=1, max_length=4096,
        )],
        offset: Annotated[int, Field(
            description="Byte offset to start reading from (0-based).", ge=0,
        )] = 0,
        limit: Annotated[int, Field(
            description="Maximum number of characters to return.", ge=1, le=1_000_000,
        )] = 100_000,
        encoding: Annotated[Literal["utf-8", "utf-8-sig", "latin-1"], Field(
            description="Text encoding used to decode the file.",
        )] = "utf-8",
    ) -> str:
        try:
            sb = Sandbox.from_env()
            target = sb.resolve(path)
            text = target.read_bytes().decode(encoding, errors="replace")
        except Exception as e:
            return f"ERROR: io_error: {e}"
        chunk = text[offset: offset + limit]
        if offset + limit < len(text):
            chunk += f"\n… [truncated {len(text) - offset - limit} chars]"
        return chunk
```

### G.2. `write`

```python
# src/agentprobe/tools/builtin/write.py
from typing import Annotated
from pydantic import Field
from mcp.server.fastmcp import FastMCP

from agentprobe.tools.sandbox import Sandbox


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="write",
        description="Create a NEW text file inside the workspace. Fails if it already "
                    "exists. Parent directories are not created.",
    )
    async def write(
        path: Annotated[str, Field(description="Relative path in the workspace.",
                                   min_length=1, max_length=4096)],
        content: Annotated[str, Field(description="File content (UTF-8).",
                                       max_length=1_000_000)],
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
```

### G.3. `command_execute` (mock with `tool_vars`)

```python
# src/agentprobe/tools/builtin/command_execute.py
import json
from typing import Annotated
from pydantic import Field
from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="command_execute",
        description="Mock command execution. Returns a fixed success, or a response "
                    "configured via scenario `tool_vars.command_execute.responses`.",
    )
    async def command_execute(
        command: Annotated[str, Field(description="VRP command to execute (mock).",
                                       min_length=1, max_length=8000)],
    ) -> str:
        from agentprobe.tools.vars import get_tool_vars
        tv = get_tool_vars().get("command_execute", {})
        responses: dict[str, str] = tv.get("responses", {})
        fail_on: list[str] = tv.get("fail_on", [])

        if command in responses:
            return responses[command]
        if any(sub in command for sub in fail_on):
            return f"ERROR: forbidden: {command}"
        return json.dumps({"ok": True, "output": "(mock) command accepted"})
```

### G.4. `syntax_check`

```python
# src/agentprobe/tools/builtin/syntax_check.py
import json
from typing import Annotated
from pydantic import Field
from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="syntax_check",
        description="Basic VRP syntax validation. Rejects '?' and 'commit' tokens. "
                    "Returns JSON {ok, errors}. This is a result, not an error.",
    )
    async def syntax_check(
        commands: Annotated[str, Field(description="Multi-line VRP script.",
                                        max_length=100_000)],
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
```

### G.5. `read_skill`

```python
# src/agentprobe/tools/builtin/read_skill.py
from pathlib import Path
from typing import Annotated
import os
from pydantic import Field
from mcp.server.fastmcp import FastMCP
import yaml

from agentprobe.tools.sandbox import Sandbox


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="read_skill",
        description="Load the body of a skill (SKILL.md). Frontmatter is stripped.",
    )
    async def read_skill(
        name: Annotated[str, Field(description="Skill folder name.",
                                    min_length=1, max_length=128)],
    ) -> str:
        try:
            skills_root = Sandbox(Path(os.environ["AGENTPROBE_SKILLS_DIR"]))
            target = skills_root.resolve(f"{name}/SKILL.md")
            text = target.read_text(encoding="utf-8")
            # strip frontmatter
            if text.startswith("---"):
                parts = text.split("---", 2)
                if len(parts) >= 3:
                    return parts[2].lstrip("\n")
            return text
        except Exception as e:
            return f"ERROR: skill_not_found: {e}"
```

### G.6. `spawn_agent` (registered conditionally)

```python
# src/agentprobe/tools/builtin/spawn_agent.py
# This tool is special: it is NOT a plain MCP tool. It's registered by the
# orchestrator because it needs access to the parent's config, session,
# observer, and LLM client. In the MCP server, it appears as a regular tool,
# but its implementation delegates to the parent process via a callback
# mechanism (see orchestrator snippet H).

# See §7.2 / §8 for full behavior. The parameters:
#   task: str [1..8000]
#   context: str [0..32000]
# Returns JSON: {answer, usage, turns, tools, is_error, error}
```

**Note:** `spawn_agent` is implemented **in-process** (not as an MCP round-trip), because it needs to launch a nested LLM loop with its own session. The orchestrator registers its schema alongside MCP tools but intercepts calls to it before dispatching to MCP.

---

