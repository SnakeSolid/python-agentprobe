# Technical Specification: `agentprobe` — Asynchronous LLM Agent for E2E Testing

## 9. Tools (MCP)

### 9.1. MCP Server

- `tools/server.py` creates `FastMCP("agentprobe-tools")` and imports every module in `tools/builtin/*.py` and (if configured) `user_tools_dir/*.py`; each module exposes `register(mcp)` on the shared instance.
- Duplicate names → startup error.
- Filtering by `tools.enabled` occurs when assembling the `tools` array for the LLM (the MCP server may hold more, but only the filtered set is sent).

### 9.2. MCP Client

- `tool_transport: in_memory` (default): `mcp.client.session.ClientSession` over an in-memory transport; the MCP server lives in the same process.
- `tool_transport: stdio`: `ClientSession` over `stdio_client` (subprocess `python -m agentprobe.tools.server`); the subprocess environment includes `AGENTPROBE_TOOL_VARS=<json>` (see §9.5).
- In both modes, tools access `tool_vars` via `get_tool_vars()`.

### 9.3. Tool Module Contract

Every tool module:
1. Lives in **its own file** under `tools/builtin/` (or `user_tools_dir/`).
2. Exposes `register(mcp)`.
3. Declares arguments with a **Pydantic model**; **every field** has a `description`, constraints (`min_length`, `max_length`, `ge`, `le`, `pattern`, `Literal`/`Enum`), and a `default` when optional.
4. The `@mcp.tool(description=...)` documents the tool briefly, including constraints (e.g. "workspace only", "mock").
5. Business-logic errors are returned as strings prefixed with `ERROR: <code>: <msg>`; the client maps this to `ToolResult(is_error=True, ...)`.
6. Return type is `str` (or `dict`, which the client serializes to JSON for the `role:"tool"` message).

**Reference example with descriptions and constraints:**

```python
# tools/builtin/read.py
from pydantic import BaseModel, Field
from typing import Literal
from mcp.server.fastmcp import FastMCP
from agentprobe.tools.sandbox import Sandbox
from agentprobe.tools.vars import get_tool_vars

class ReadArgs(BaseModel):
    path: str = Field(
        description="Path to a text file, relative to the workspace root. "
                    "Absolute paths are rejected unless inside the workspace.",
        min_length=1,
        max_length=4096,
    )
    offset: int = Field(
        default=0,
        description="Byte offset to start reading from (0-based).",
        ge=0,
    )
    limit: int = Field(
        default=100_000,
        description="Maximum number of characters to return.",
        ge=1,
        le=1_000_000,
    )
    encoding: Literal["utf-8", "utf-8-sig", "latin-1"] = Field(
        default="utf-8",
        description="Text encoding used to decode the file.",
    )

def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="read",
        description="Read a text file inside the workspace. Truncates to `limit` chars "
                    "and appends a marker when truncated. Fails on paths escaping the workspace.",
    )
    async def read(args: ReadArgs) -> str:
        sandbox = Sandbox.from_env()
        path = sandbox.resolve(args.path)
        data = path.read_bytes()
        text = data.decode(args.encoding, errors="replace")
        chunk = text[args.offset: args.offset + args.limit]
        if args.offset + args.limit < len(text):
            chunk += f"\n… [truncated {len(text) - args.offset - args.limit} chars]"
        return chunk
```

### 9.4. Default Tool Set

| Tool | Arguments (with constraints) | Behavior |
|---|---|---|
| `read` | `path: str [1..4096]`; `offset: int [>=0]=0`; `limit: int [1..1_000_000]=100000`; `encoding: Literal["utf-8","utf-8-sig","latin-1"]="utf-8"` | Reads a file in `workspace`, truncates; appends `… [truncated N chars]`. |
| `write` | `path: str [1..4096]`; `content: str [0..1_000_000]` | Creates a **new** file; error if it exists; does not create parent dirs. `parallel_safe=False`. |
| `edit` | `path: str [1..4096]`; `old_string: str [1..100000]`; `new_string: str [0..100000]`; `replace_all: bool=False` | File must exist; `old_string` must occur exactly once when `replace_all=False`. `parallel_safe=False`. |
| `read_doc` | `name: str [1..256]` (basename without `.md`) | Reads `<docs_dir>/<name>.md`; traversal-protected; error if absent. |
| `read_skill` | `name: str [1..128]` | Reads `<skills_dir>/<name>/SKILL.md`; returns body; frontmatter goes to `artifacts`. |
| `command_execute` | `command: str [1..8000]` | **Mock**: `{"ok": true, "output": "(mock) command accepted"}`. Honors `tool_vars` (§9.5). |
| `execute_shell` | `command: str [1..8000]` | **Mock**: same shape as `command_execute`; honors `tool_vars`. |
| `syntax_check` | `commands: str [0..100000]` | For each non-empty line without `#`: rejects `?` and substring `commit`. Returns JSON `{"ok": bool, "errors": [str]}`. |
| `spawn_agent` | `task: str [1..8000]`; `context: str [0..32000]` (optional) | See §8. |

### 9.5. `tool_vars` (Tool Parameterization in a Scenario)

- Scenario section `tool_vars: { <tool_name>: <object> }`.
- **Headless**: `tool_vars` are installed on the MCP server before the session starts (fresh subprocess for `stdio`, reset state for `in_memory`).
- **REPL**: `tool_vars = {}` (or from `config.app.tool_vars`, if present; optional).
- Tools decide whether to consume `tool_vars`; unknown keys are ignored.

**`command_execute` / `execute_shell` — final format (unchanged):**

```yaml
tool_vars:
  command_execute:
    responses:
      "display version": "Huawei VRP V8 ..."
    fail_on: ["reboot", "reset"]
```

Tool behavior:
1. If `command in responses` → return `responses[command]`.
2. Else if `any(sub in command for sub in fail_on)` → return `ERROR: forbidden: <command>`.
3. Else → return `{"ok": true, "output": "(mock) command accepted"}`.

**Example of a user tool (`read_config`) using `tool_vars`:**

```yaml
tool_vars:
  read_config:
    source: ./fixtures/device_before.txt
```

The tool reads `get_tool_vars().get("read_config", {}).get("source")` and returns the file contents.

### 9.6. Sandbox

- `Sandbox.resolve(path) -> Path`: `workspace / path` → `realpath` → assert `commonpath([workspace_real, target]) == workspace_real`. Symlinks are resolved; escapes → `ERROR: sandbox_violation: <path>`.
- `read_doc` / `read_skill` use separate roots (`docs_dir`, `skills_dir`) with the same guard.
- Tools obtain the sandbox via `Sandbox.from_env()` (workspace is passed via `AGENTPROBE_WORKSPACE`).

### 9.7. Bundled Docs Stubs

Shipped with exactly two files:

```
docs/
  vrp_basic.md
  security_policy.md
```

- Content: brief stubs (a few lines: "stub, will be replaced"), so `read_doc` and acceptance tests pass.
- Additional docs are added manually by the owner; the directory is scanned dynamically per `read_doc` call (no config change required).
- `--dry-run` prints the actual list of files in `docs_dir`.

---

