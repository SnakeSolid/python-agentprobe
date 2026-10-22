# Technical Specification: `agentprobe` — Asynchronous LLM Agent for E2E Testing

## Table of Contents

1. Purpose and Scope
2. Glossary
3. Architecture
4. Configuration
5. System Prompt
6. LLM Client
7. Agent Loop (Orchestrator)
8. Subagents (`spawn_agent`)
9. Tools (MCP)
10. Skills
11. Memory
12. REPL Mode
13. Headless Mode (Scenarios)
14. Logging and Metrics
15. CLI
16. Security
17. Testing
18. Non-Functional Requirements
19. Accepted Assumptions
20. Appendix: Complete Examples

---

## 1. Purpose and Scope

### 1.1. Goal

`agentprobe` is a Python application that reproduces the behavior of a reverse-engineered Huawei Security Expert agent: it dialogues with an LLM, invokes tools, supports subagents, and lazily loads skills — while allowing **automated scenario execution** (headless) for E2E verification of model behavior.

The primary use case is **writing end-to-end tests** for LLM-based agents whose prompt, tool set, and subagent behavior must be validated against real or recorded model outputs.

### 1.2. In Scope

- Main agent with an OpenAI-compatible LLM backend (streaming).
- Subagents per Zed's model: `spawn_agent`, depth 1, isolated context, parallel execution.
- Tools implemented as an **MCP server** (one file per tool).
- Default tool set: `read_doc`, `read`, `write`, `edit`, `execute_shell`, `read_skill`, `command_execute`, `syntax_check`, `spawn_agent` (dynamically).
- Lazy skill loading via `read_skill`; skills advertised in the system prompt.
- `MEMORY.md`: a file editable by the agent, re-read and injected before every turn.
- Two mutually exclusive run modes: **REPL** and **headless scenario** (YAML).
- Compact console output; complete YAML log file.
- Metrics: tokens (from model `usage` only), latency, tool calls, turns, duration.
- Filesystem sandbox within `workspace` (and separate roots for `docs_dir`, `skills_dir`).
- `tool_vars` section in scenario for parameterizing tool behavior.
- Multi-scenario runs: `--scenario`, `--scenario-dir`, `--scenario-glob`, filters, `--parallel`, `--fail-fast`, `--workspace-mode`.
- `--record` / `--replay` for LLM response fixtures (explicit paths only).
- `--dry-run`, `--summary`, `--summary-file` (explicit path), `/reload` in REPL.

### 1.3. Out of Scope (current version)

- Real execution of commands on the device (`command_execute`, `execute_shell` are mocks).
- Approval mechanisms for dangerous commands (only textual warnings in the prompt).
- Prompt caching (e.g., Anthropic-style `cache_control`).
- Multi-user mode, web UI, database.
- Full VRP parser for `syntax_check` (only basic validation).
- Non-YAML output formats (JUnit XML, JSON summaries, etc.).
- `--summary` in REPL mode.

---

## 2. Glossary

| Term | Meaning |
|---|---|
| **Main agent** | Dialogue orchestrator; has all tools and `spawn_agent`. |
| **Subagent** | Isolated agent at depth 1; has no `spawn_agent`. |
| **Tool** | An MCP tool exposed to the model via `tools` in Chat Completions. |
| **MCP server** | In-process or subprocess `mcp.server.fastmcp.FastMCP` instance registering tools. |
| **Skill** | `skills/<name>/SKILL.md` with YAML frontmatter; loaded lazily via `read_skill`. |
| **Session** | One dialogue: messages, counters, log file, `session_id`. |
| **Turn** | One cycle of `LLM → (optional) tool_calls → tool results → LLM` until an assistant message with no `tool_calls`. |
| **Scenario** | YAML file with `initial_message`, `transitions`, `checks`, `tool_vars`. |
| **Mock** | A tool returning a fixed successful result. |
| **`tool_vars`** | Scenario section parameterizing behavior of specific tools. |
| **Observer** | A hook in the orchestrator invoked on every event (message, tool_call); the scenario runner uses it for checks. |
| **Run** | A single `agentprobe run` invocation, potentially covering multiple scenarios. |
| **`run_id`** | Identifier of a run: `<YYYYMMDD_HHMMSS>_<rand4>`. |

---

## 3. Architecture

### 3.1. Layers

```
CLI (typer)
 ├── REPL ──┐
 └── Headless ────┤
                  ▼
            Orchestrator
             ├── LLMClient (openai SDK + httpx, trust_env=False, streaming)
             ├── MCPToolClient (mcp, in-memory or stdio)
             │     └── MCPToolServer (FastMCP; builtin + user tools, one file per tool)
             ├── SubagentSpawner (depth=1, isolation)
             ├── SkillLoader
             ├── PromptBuilder
             ├── Sandbox
             ├── Session
             │     ├── ConsoleFormatter
             │     ├── YamlLogger
             │     └── MetricsCollector
             └── Observer (runtime checks: ScenarioObserver / NoOpObserver)
```

### 3.2. Project Structure

```
agentprobe/
  pyproject.toml
  README.md
  config/
    config.yaml
  prompts/
    system.md
    subagent.md
  skills/
    huawei_vsys/
      SKILL.md
  docs/
    vrp_basic.md          # stub
    security_policy.md    # stub
  workspace/
    MEMORY.md
  scenarios/
    firewall_permit_tcp.yaml
  tests/
    unit/
    e2e/
    fixtures/
      llm_responses/
        <recorded_run_id>/
          <scenario_name>.jsonl
  src/agentprobe/
    __init__.py
    __main__.py
    cli.py
    config.py
    errors.py
    llm/
      client.py
      types.py
      fixture.py            # --record / --replay
    agent/
      orchestrator.py
      observer.py           # Protocol + NoOpObserver + ScenarioObserver
      subagent.py
      session.py
      limits.py
    tools/
      server.py             # FastMCP app, register builtins
      client.py             # MCPToolClient (in-memory / stdio)
      sandbox.py
      vars.py               # get_tool_vars()
      builtin/
        read_doc.py
        read.py
        write.py
        edit.py
        execute_shell.py
        command_execute.py
        read_skill.py
        syntax_check.py
    skills/
      loader.py
    prompt/
      builder.py
      memory.py
    repl/
      app.py
      commands.py
      ui.py
    scenario/
      schema.py
      runner.py
    logging/
      yaml_logger.py
      console.py
      metrics.py
```

### 3.3. Dependencies

- Python **3.11+** (uses `asyncio.TaskGroup`).
- `openai>=1.40` — SDK; internally receives our own `httpx.AsyncClient`.
- `httpx[http2]` — transport for `openai.AsyncOpenAI(http_client=...)`.
- `mcp>=1.0` — MCP server/client (`FastMCP`, `ClientSession`, stdio/in-memory transports).
- `pydantic>=2` — config, tool schemas, scenario schema.
- `pyyaml` — config, log, scenarios.
- `rich` — colors/levels in console (ANSI fallback).
- Dev: `pytest`, `pytest-asyncio`, `ruff`, `mypy`.

### 3.4. Token Accounting

- **Only from model `usage`** (`prompt_tokens`, `completion_tokens`, `total_tokens`).
- If `usage` is absent: `tokens_in/tokens_out/tokens_total = null`; the `max_context_tokens` check is **skipped**, `warning: usage_missing` is logged; the turn completes normally. Aggregates count non-null values only; if all values are null, aggregates are `null` (not `0`).

---

## 4. Configuration (`config/config.yaml`)

### 4.1. Schema

```yaml
app:
  workspace: ./workspace              # sandbox root for read/write/edit
  docs_dir: ./docs                    # for read_doc
  skills_dir: ./skills                # for read_skill / AVAILABLE SKILLS
  prompt_file: ./prompts/system.md
  subagent_prompt_file: null          # null → use prompt_file
  memory_file: ./workspace/MEMORY.md
  user_tools_dir: ./tools             # optional
  log_dir: ./logs
  tool_transport: in_memory           # in_memory | stdio
  scenario_defaults:
    turn_timeout_secs: 120
    max_agent_messages: 30
    max_context_tokens: 200000
    max_duration_secs: 300

models:
  main:
    endpoint: https://api.example.com/v1
    api_key: ${MAIN_API_KEY}          # env substitution
    model: qwen3.6-27b
    temperature: 0.6
    request_timeout_secs: 120
    max_retries: 3
    proxy: null                       # e.g. http://127.0.0.1:8080
  subagent:                           # absent/empty → spawn_agent unavailable
    endpoint: https://api.example.com/v1
    api_key: ${SUB_API_KEY}
    model: qwen3.6-27b
    temperature: 0.4
    request_timeout_secs: 120
    max_retries: 3
    proxy: null

limits:
  main:
    max_turns: 35
    max_tool_calls: 100
    max_duration_secs: 600
    max_context_tokens: 1000000
  subagent:
    max_turns: 20
    max_tool_calls: 50
    max_duration_secs: 300
    max_context_tokens: 200000

tools:
  enabled:
    - read_doc
    - read
    - write
    - edit
    - execute_shell
    - command_execute
    - read_skill
    - syntax_check

logging:
  console_level: info                 # quiet | info | verbose
  console_truncate_chars: 400
  color: auto                         # auto | always | never
```

### 4.2. Rules

- **Pydantic validation**: any validation error → `exit 2` with a human-readable message and the field path.
- **`${VAR}` substitution**: string values may contain `${VAR}`, substituted from the environment; a missing variable is a configuration error.
- **`models.subagent` absent** → `spawn_agent` is **not registered** and is not offered in `tools`.
- **`tools.enabled`** filters the final tool set; an unknown name is a configuration error (typo protection).
- **`subagent_prompt_file: null`** → the subagent uses `prompt_file`.
- **`proxy`** in `models.*` → `httpx.AsyncClient(proxy=proxy, trust_env=False)`. When `proxy: null`, `trust_env=False` is still applied (env vars like `HTTP_PROXY`/`HTTPS_PROXY` are ignored).
- **`tool_transport`**: `in_memory` runs the MCP server in the same process; `stdio` spawns `python -m agentprobe.tools.server` as a subprocess (env includes `AGENTPROBE_TOOL_VARS`, see 9.5).

---

## 5. System Prompt

### 5.1. `prompts/system.md`

A single static file assembled by hand from the original `AGENTS.md + IDENTITY.md + SOUL.md + TOOLS.md + USER.md`. Section order:

```
# AGENTS
# IDENTITY
# SOUL
# TOOLS
# USER
# MEMORY               ← dynamic (re-read before every turn)
# AVAILABLE SKILLS     ← dynamic (at session start and on /reload)
```

- Remove duplicate rules (verification/evidence-based parts repeat in the source); merge CLI-formatting MUSTs.
- The YAML frontmatter of `IDENTITY.md` belongs in `config.yaml`, not in the prompt.

### 5.2. Dynamic Sections

- **`# MEMORY`** — re-read `memory_file` before every turn. If the file is missing, the section is empty.
- **`# AVAILABLE SKILLS`** — at session start and on `/reload`, scan `skills_dir`, parse frontmatter, produce:
  ```
  - name: huawei_vsys
    description: How to create and configure a virtual system (vsys) on VRPv8.
  ```
  Full body is delivered only via `read_skill`.

### 5.3. Caching

Not required (out of scope).

---

## 6. LLM Client

### 6.1. SDK and Transport

- `openai.AsyncOpenAI(base_url=endpoint, api_key=api_key, http_client=httpx.AsyncClient(proxy=proxy, trust_env=False, timeout=...))`.
- Request: `client.chat.completions.create(model=..., messages=..., tools=..., tool_choice="auto", temperature=..., stream=True, stream_options={"include_usage": True})`.
- `stream_options={"include_usage": True}` is **mandatory** to receive `usage` in the final chunk (for providers supporting the OpenAI protocol).

### 6.2. Streaming

- Incrementally accumulate `content` and `tool_calls` (keyed by `index`).
- In REPL, print `content` as it arrives.
- Accumulate `usage` from the chunk with `finish_reason` or from the last chunk where `usage != null`.

### 6.3. Response Metrics

`ttft_ms`, `latency_ms`, `tokens_in`, `tokens_out`, `tokens_total` — all derived from `usage` (or `null`, see §3.4).

### 6.4. Retries and Timeouts

- 3 attempts, exponential backoff: 1s / 2s / 4s + jitter.
- Retry on: `429`, `5xx`, `httpx.TimeoutException`, `httpx.ConnectError`, `openai.APITimeoutError`, `openai.APIConnectionError`.
- Do not retry other `4xx`.
- Total per-request timeout — `request_timeout_secs`.

### 6.5. `--record` / `--replay`

**Both flags require an explicit path.** No defaults. Missing path → `exit 2`.

- **`--record PATH`**:
  - If `PATH` is a **directory** → writes `<PATH>/<scenario_name>.jsonl` for each scenario. The directory is created if absent; its parent must exist (else `exit 2`).
  - If `PATH` is a **file** → allowed only with a single `--scenario <file>` (otherwise `exit 2`).
  - One line per turn: `{"turn": int, "response": <OpenAI-compatible assistant message + usage>, "request_meta": {"model": ..., "tools_count": ...}}`.
- **`--replay PATH`**: no LLM calls; reads saved responses in order. Missing per-scenario file → that scenario ends with `exit 4`, remaining scenarios continue.
- `--record` and `--replay` are mutually exclusive (`exit 2` if both given).
- **Only YAML artifacts are allowed for spec-defined outputs; the fixture format is JSONL** (one JSON object per line) — this is the sole exception because it must be replayable line-by-line, and it is explicitly part of the `--record`/`--replay` contract, not a general output format. The rule "YAML only" (§1.3, §8 of the delta) applies to configs, logs, and summaries.

---

## 7. Agent Loop (Orchestrator)

### 7.1. Main Turn Loop

```
messages += [user_message]
loop:
  response = LLMClient.chat(messages, tools=mcp_client.schemas())
  observer.on_assistant_message(response)        # may abort
  messages.append(assistant_message)
  if not response.tool_calls: break
  for call in tool_calls:
      observer.on_tool_call_pending(call)        # may abort BEFORE execution
      result = await execute_tool(call)
      observer.on_tool_result(result)
      messages.append(tool_result_message)
  check_limits()                                 # turns / tool_calls / duration
finish_turn()
```

### 7.2. Observer Protocol

```python
class Observer(Protocol):
    async def on_assistant_message(self, msg: AssistantMessage, ctx: SessionCtx) -> None: ...
    async def on_tool_call_pending(self, call: ToolCall, ctx: SessionCtx) -> None: ...
    async def on_tool_result(self, res: ToolResult, ctx: SessionCtx) -> None: ...
    async def on_turn_end(self, stats: TurnStats, ctx: SessionCtx) -> None: ...
```

- `NoOpObserver` — used in REPL.
- `ScenarioObserver` — used in headless; on a failed check, raises `ScenarioAbort(reason, exit_code)`.
- The orchestrator catches `ScenarioAbort` → writes `scenario_abort` to the log → `session_end` → propagates upward (CLI returns the exit code).

### 7.3. Parallel Tool Calls

- `parallel_safe=True`: `read`, `read_doc`, `read_skill`, `command_execute`, `execute_shell`, `syntax_check`.
- `parallel_safe=False`: `write`, `edit`, `spawn_agent`.
- If **all** calls in the batch are `parallel_safe=True` → run via `asyncio.gather`; otherwise — sequential in the order received.
- Results are appended to `messages` in the original order.
- **`on_tool_call_pending`** is called for **every** call **before** any parallel batch starts; if it aborts, the batch does not run.

### 7.4. General Limits (`limits.*`)

Checked between loop iterations: `max_turns` (session turns), `max_tool_calls` (cumulative), `max_duration_secs` (wall-clock), `max_context_tokens` (`tokens_in + tokens_out` of the last response; skipped when `null`).

- **REPL**: not applied; a warning is shown as the model approaches `max_context_tokens`.
- **Headless**: exceeded → `limit_exceeded` in log → `exit 3`.
- **Subagent**: exceeded → subagent session aborted with an error; parent receives `tool_result(is_error=True, content="subagent aborted: <reason>")`; the parent continues. The parent's own scenario checks apply independently.

---

## 8. Subagents (`spawn_agent`)

### 8.1. Availability

The tool is registered **only** when `models.subagent` is present and `spawn_agent` is not filtered out by `tools.enabled`.

### 8.2. Tool Contract

```
name: spawn_agent
description: "Delegate an isolated subtask to a subagent. The subagent does not see the main dialogue history."
parameters:
  task:    string, required, 1..8000 chars
  context: string, optional, 0..32000 chars
returns: JSON-string
  {"answer": string,
   "usage": {"tokens_in": int|null, "tokens_out": int|null},
   "turns": int,
   "tools": {name: count},
   "is_error": bool,
   "error": string|null}
```

### 8.3. Isolation and Limits

- New `Session`; `system` — `subagent_prompt_file` (or `prompt_file`).
- Model — `models.subagent`; limits — `limits.subagent`.
- Subagent tool set = `tools.enabled` **without** `spawn_agent`.
- `MEMORY.md` is accessible via `read`/`edit` (same `workspace`), but **not injected** into the subagent's system prompt (avoids conflicting edits).
- Subagent `session_id`: `<parent_session_id>/sub-<n>`; `parent_session_id` is logged on every event.
- `parallel_safe=False` for `spawn_agent` (sequential, to simplify limits and logging).

### 8.4. Errors

- Internal LLM error, limit exceeded, or any non-recoverable error → `tool_result(is_error=True, ...)` returned to the parent.

---

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

## 10. Skills

- Format: `skills/<name>/SKILL.md` with YAML frontmatter (`name`, `description` required; `name` must equal the folder name, else warning + skip).
- At session start and on `/reload`, scan; the `# AVAILABLE SKILLS` section lists only `name` + `description`.
- `read_skill(name)` returns the body (without frontmatter); `artifacts.metadata` carries the frontmatter.

Example `SKILL.md`:

```markdown
---
name: huawei_vsys
description: How to create and configure a virtual system (vsys) on VRPv8.
---

# Body
...instructions for the model...
```

---

## 11. Memory

- Path: `app.memory_file` (default `workspace/MEMORY.md`).
- The agent edits it via `write`/`edit`; the application does **not** impose a format.
- Before every turn, `PromptBuilder` re-reads the file and injects its contents under `# MEMORY` in the system message. If the file is absent, the section is empty.
- `MEMORY.md` is **not** injected into the subagent's system prompt.

---

## 12. REPL Mode

### 12.1. Launch

```
agentprobe repl --config config/config.yaml
```

### 12.2. Behavior

- Prompt `>>> `; multi-line input via trailing `\`.
- Streams the assistant response; prints tools line-by-line; prints a tokens line per turn.
- Ctrl-C — interrupt the current turn (cancels the LLM request and parallel tools); returns to prompt; history up to the interrupt is preserved.
- Ctrl-D — exit.
- **Limits are not applied** in REPL; a warning is shown as the model approaches `max_context_tokens`.
- `--summary` is not supported in REPL (`exit 2` if passed).

### 12.3. Commands

| Command | Action |
|---|---|
| `/help` | Show commands. |
| `/exit`, `/quit` | Exit. |
| `/reset` | New `Session` (history cleared; `MEMORY.md` untouched); new log. |
| `/reload` | Re-read `config.yaml`, `prompts/*`, `skills/*`; rebuild system message in `messages[0]`; re-register MCP server and tools. History preserved. On config error — report and keep the old config. |
| `/tools` | List tools with brief descriptions. |
| `/stats` | Session statistics. |
| `/log` | Path to the log. |
| `/model` | Models (main / subagent). |
| `/memory` | Contents of `MEMORY.md`. |

---

## 13. Headless Mode (Scenarios)

### 13.1. Launch (single scenario)

```
agentprobe run --config config/config.yaml --scenario scenarios/firewall_permit_tcp.yaml
agentprobe run ... --record tests/fixtures/llm_responses/20261022_101500_ab12/
agentprobe run ... --replay tests/fixtures/llm_responses/20261022_101500_ab12/
```

### 13.2. Multi-Scenario Launch

```
--scenario PATH          # repeatable
--scenario-dir DIR       # all *.yaml/*.yml in DIR (non-recursive)
--scenario-glob PATTERN  # e.g. 'scenarios/*.yaml'
--filter TAG             # filter by checks.tags
--filter-name REGEX      # filter by name
```

- All flags may be combined; the resulting list is the union, then `--filter*` are applied.
- Duplicate paths (by `realpath`) are removed.
- Empty list → `exit 2`.
- **All scenarios are validated before any run starts.** Any validation error → `exit 2`; no scenario is executed (fail-fast on config).

Scenario schema adds:

```yaml
checks:
  tags: ["firewall", "smoke"]   # for --filter
```

### 13.3. Isolation Per Scenario

Each scenario is a fully independent run:

| Resource | Isolation |
|---|---|
| `Session` | New; messages, counters, `session_id` independent |
| MCP server | New; `in_memory` — state reset + own `tool_vars`; `stdio` — new subprocess |
| `tool_vars` | Only from the current scenario |
| Workspace | **Fresh copy** of `workspace/` template (see §13.4) |
| `MEMORY.md` | From template copy (changes do not leak between scenarios) |
| LLM fixture | `<dir>/<scenario_name>.jsonl` (see §13.6) |
| Log | `logs/<run_id>/<scenario_name>.yaml` |
| `Observer` | New `ScenarioObserver` with the current scenario's `checks` |

### 13.4. Workspace Modes

`--workspace-mode {copy,shared,fresh}` (default `copy`):

- **`copy`** (default): for each scenario, create `logs/<run_id>/<scenario_name>/workspace/` — full copy of `app.workspace`. The agent works in the copy. On success — deleted; on failure — **kept** (for debugging). `--keep-workspace` forces keep always.
- **`shared`**: all scenarios use the original `app.workspace`. Fast, but scenarios may affect each other (files, `MEMORY.md`). A warning is logged and printed at start.
- **`fresh`**: empty directory (with `MEMORY.md` copied from the template if present). Useful for clean tests.

Config paths (`workspace`, `memory_file`) are resolved before copying; under `copy`/`fresh`, relative `workspace`/`memory_file` paths are rewritten to the run directory. `docs_dir`/`skills_dir` are shared (logically read-only).

### 13.5. Execution Order

- **Default: sequential** — `--scenario` (in flag order), then `--scenario-dir`/`--scenario-glob` (alphabetical), then filters. Deterministic.
- `--parallel N` (default `1`): concurrent via `asyncio.Semaphore(N)` + `asyncio.TaskGroup`. At `N>1`:
  - each scenario remains isolated (own MCP server, workspace, session);
  - console event order is by completion; per-scenario logs keep their own order;
  - the run-level log is written under `asyncio.Lock` so `---` separators are not interleaved;
  - `--record`/`--replay` with `--parallel` are allowed (per-scenario files do not conflict).

### 13.6. `--record` / `--replay` for Multi-Scenario

- **Path is mandatory.** No defaults.
- Directory → per-scenario `<dir>/<scenario_name>.jsonl`.
- File → only with a single `--scenario <file>`.
- `--record` directory is created if absent; parent must exist.
- Format: JSONL, one entry per turn (see §6.5).

### 13.7. Scenario Schema (full)

```yaml
name: firewall-permit-tcp
description: "Permit all TCP to 10.0.0.0/24"
initial_message: "how to permit all tcp packets to 10.0.0.0/24"

tool_vars:
  command_execute:
    responses:
      "display version": "Huawei VRP V8 ..."
    fail_on: ["reboot"]

transitions:
  - message: "Yes, write it to a file"
    include: ["\\?$", "confirm"]
    exclude: ["done"]
    once: false

checks:
  tags: ["firewall", "smoke"]
  final_include: ["tcp", "10\\.0\\.0\\.0/24"]
  final_exclude: ["I cannot", "unknown command"]
  required_tools: ["read_doc"]
  forbidden_tools: ["execute_shell"]
  max_agent_messages: 10
  max_context_tokens: 50000
  max_duration_secs: 120

timeouts:
  turn_secs: 120
```

- Defaults for `checks.*` come from `app.scenario_defaults`.
- Regexes are compiled during validation; a compile error → `exit 2`.
- Matching uses `re.search(pattern, text, re.MULTILINE)`; case-sensitive by default (use inline `(?i)` if needed).

### 13.8. Runner Logic

1. Validate YAML → `exit 2` on error.
2. Start the MCP server with the scenario's `tool_vars`.
3. Create a `Session` (headless) + `ScenarioObserver`.
4. Send `initial_message`.
5. Turn loop; after each turn's final assistant message:
   - Iterate `transitions` in order; pick the first whose `include` all match and `exclude` none match; send its `message`; if `once: true`, remove from pool. If none matched — finish the loop.
6. Run checks (see §13.9).
7. Write `session_end`; return exit code.

### 13.9. Checks (Observer on Every Message)

**`on_assistant_message`** (after receiving the response, **before** it is used):
- `agent_messages += 1`.
- If `agent_messages > checks.max_agent_messages` → `ScenarioAbort(reason="max_agent_messages", exit=1)`. **The message is not added to the next turn's context; no tools are called.**
- If `usage != null` and `usage.prompt_tokens + usage.completion_tokens > checks.max_context_tokens` → `ScenarioAbort(reason="max_context_tokens", exit=1)`. **The response is not used.**
- If `usage == null` — skip the context check; log `warning: usage_missing`.

**`on_tool_call_pending`** (for each tool_call, **before** any execution):
- If `call.name in checks.forbidden_tools` → `ScenarioAbort(reason="forbidden_tool:<name>", exit=1)`. **The tool is not called.**
- If `tools_count + 1 > limits.max_tool_calls` (general limit) → `ScenarioAbort(reason="max_tool_calls", exit=3)`. **The tool is not called.**

**Between turns** (orchestrator `check_limits`):
- `max_turns`, `max_duration_secs` → `limit_exceeded` → `exit 3`.
- `max_tool_calls` (general) → `exit 3`.

**`on_turn_end`**:
- Append `turn_end` to log; update metrics.
- Per-turn timeout (`timeouts.turn_secs`) enforced via `asyncio.wait_for` around the turn → `exit 3`.

**Final checks (after the loop)**:
- `final_include` / `final_exclude` — against the text of the last assistant message.
- `required_tools` ⊆ invoked; `forbidden_tools` ∩ invoked = ∅ (already enforced by Observer; re-checked for completeness).
- `max_agent_messages` / `max_context_tokens` / `max_duration_secs` — re-checked against final values (covers edge cases at the boundary).

On any failure — `exit 1`; on general limit/timeout — `exit 3`; on LLM error — `exit 4`.

### 13.10. Subagents in Scenarios

- If a subagent exceeds limits — it returns `tool_result(is_error=True, content="subagent aborted: <reason>")`; the parent's `ScenarioObserver` does **not** automatically fail on this (failure only occurs if the parent's `forbidden_tools` / `required_tools` / `checks` demand otherwise).

### 13.11. Multi-Run Logs

```
logs/<run_id>/
  run.yaml                       # run-level events
  <scenario_name>.yaml           # per-scenario full log
  <scenario_name>/workspace/     # if --workspace-mode copy and failure (or --keep-workspace)
```

`run.yaml` events:
- `run_start`: `run_id`, `scenarios_total`, `parallel`, `workspace_mode`, `record`/`replay` (if given), `filter`.
- `scenario_start`: `scenario_name`, `index`, `pid` (for `stdio` MCP).
- `scenario_end`: `scenario_name`, `exit_code`, `reason`, `duration_ms`, `usage_total`, `checks.passed`, `checks.failures`.
- `run_end`: `run_id`, `duration_ms`, `passed`, `failed`, `errored`, `aborted`, `exit_code`.

`session_id`: `<run_id>/<scenario_name>_<YYYYMMDD_HHMMSS>_<rand4>`; subagent: `<parent_session_id>/sub-<n>`.

### 13.12. Multi-Run Exit Codes

- All passed → `0`.
- Config/scenario/fixture validation at startup → `2` (fail-fast, no scenario runs).
- Otherwise — `exit code = max_severity(per-scenario exit codes)`, ranking: `5 (internal) > 4 (LLM/replay) > 3 (limits/timeout) > 1 (checks failed) > 0`.
- `--fail-fast`: on the first failure (`exit != 0`), remaining scenarios are aborted; `run_end` reports `aborted: N`.

Single-scenario runs (exactly one `--scenario <file>`) keep the direct exit codes `0/1/2/3/4/5` without aggregation.

---

## 14. Logging and Metrics

### 14.1. File Format (`logs/<session_id>.yaml`)

YAML stream with `---` separators. Full text (`content`, `arguments`, `tool_result.content`) recorded verbatim; `api_key` → `***`.

Events:
- `session_start`: `mode`, `scenario`, `model`, `limits`, `tool_transport`, `tool_vars_keys` (keys only, no values).
- `llm_request`: `turn`, `messages_count`, `tools_count`.
- `llm_response`: `turn`, `content`, `tool_calls`, `usage` (`prompt_tokens`, `completion_tokens`, `total_tokens` or `null`), `ttft_ms`, `latency_ms`.
- `tool_call`: `turn`, `call_id`, `name`, `arguments`.
- `tool_result`: `turn`, `call_id`, `name`, `is_error`, `duration_ms`, `content`, `artifacts`.
- `turn_end`: `turn`, `duration_ms`, `usage`, `tools`.
- `scenario_abort`: `reason`, `exit_code`, `turn`, `agent_messages`, `context_tokens`.
- `limit_exceeded` (general): `reason`, `limit`, `actual`.
- `session_end`: `duration_ms`, `turns`, `usage_total`, `tools_histogram`, `agent_messages`, `context_tokens_max`, `checks` (`passed`, `failures`), `exit_code`.
- `record`: fixture path (if `--record`); `replay`: path (if `--replay`).

`session_id`: `<mode>_<YYYYMMDD_HHMMSS>_<rand4>`. Subagent: `<parent>/sub-<n>`; its events are written to the parent file with `parent_session_id`.

Writing: append, flush after each event (crash-resilient).

### 14.2. Metrics

- Per turn: `usage`, `ttft_ms`, `latency_ms`, `tools`, `duration_ms`.
- Per session: aggregate `usage` (non-null only), tools histogram, `turns`, `agent_messages`, `context_tokens_max`, error count.
- `session_end` — totals.

### 14.3. Console Output

Levels: `quiet` / `info` (default) / `verbose`.

Info format:
```
[user] how to permit all tcp packets to 10.0.0.0/24
[assistant] To permit TCP traffic to 10.0.0.0/24, create a security policy…
→ read_doc(name=vrp_basic) [3ms]
→ write(path=policy.txt) [1ms]
tokens: in=1450 out=87 | turn 910ms | total 1.2s
```

Colors: user — cyan, assistant — green, tool — yellow, error — red, tokens — dim. With `color: never` or non-TTY — no ANSI.

---

## 15. CLI

### 15.1. Commands

```
agentprobe repl    --config PATH

agentprobe run     --config PATH
                   (--scenario PATH | --scenario-dir DIR | --scenario-glob PATTERN)+
                   [--filter TAG] [--filter-name REGEX]
                   [--parallel N] [--fail-fast]
                   [--workspace-mode {copy,shared,fresh}] [--keep-workspace]
                   (--record PATH | --replay PATH)?     # mutually exclusive, explicit path
                   [--summary [--summary-format {table,list}] [--summary-file PATH]]

agentprobe dry-run --config PATH
                   [(--scenario PATH | --scenario-dir DIR | --scenario-glob PATTERN)*]
```

### 15.2. Flag Semantics

- **`--record PATH`, `--replay PATH`**: both require an explicit path. Missing argument → `exit 2`. Both simultaneously → `exit 2`. `--record` directory parent must exist; the directory itself is created if absent.
- **`--summary`**: enables the summary table in stdout.
- **`--summary-format`**: `table` (default) or `list`.
- **`--summary-file PATH`**: path is **mandatory**; no default; missing argument → `exit 2`; parent must exist; file is created/overwritten. Implies `--summary`.
- **`--workspace-mode`**: `copy` (default) | `shared` | `fresh`.
- **`--keep-workspace`**: keep the copy even on success.
- **`--parallel N`**: default `1`.
- **`--fail-fast`**: stop remaining scenarios on first failure.

### 15.3. `--dry-run`

- Collects and prints to stdout: the final system prompt (with empty `# MEMORY` and current `# AVAILABLE SKILLS`), the tool list with JSON schemas, the skill list, allowed paths (`workspace`, `docs_dir`, `skills_dir`, `memory_file`), the actual list of files in `docs_dir`, flags (`spawn_agent` available/not).
- No LLM calls. `exit 0`.
- With `--scenario*`: prints the scenario list (one line per scenario: `name`, path, `initial_message` truncated, number of `transitions`, `checks.max_*`). No summary printed. `--summary-file` ignored with a warning.

### 15.4. `--summary`

**Enabled for `run`** (both single and multi-scenario).

**Table format** (default):

```
SCENARIO                     STATUS  REASON                        TURNS  TOK_IN  TOK_OUT  DURATION  EXIT
firewall_permit_tcp          PASS    —                             3      4520    612      5.4s      0
nat_server_basic             FAIL    forbidden_tool:execute_shell  2      2100    340      3.1s      1
vsys_create                  FAIL    max_context_tokens            4      61000   900      7.8s      1
crash_on_empty               ERROR   LLMTimeoutError               1      1200    0        120.0s    4
-----------------------------------------------------------------------------------------------------
TOTAL (4)                    —       passed 1, failed 2, errors 1                      135.3s    5
```

Rules:
- `STATUS`: `PASS` (0), `FAIL` (1,2), `LIMIT` (3), `ERROR` (4,5), `SKIP` (fail-fast).
- `REASON`: `—` on PASS; else `scenario_abort.reason` / `limit_exceeded.reason` / exception class; `fail-fast` for SKIP.
- `TOK_IN`/`TOK_OUT`: sum of non-null `usage` per session (subagents included). `null` → `—`; all-null → `—`.
- `DURATION`: wall-clock per scenario, `1.2s` / `1m 20.3s`.
- `TOTAL`: aggregates and the final multi-run exit code.
- Colors: PASS — green, FAIL/LIMIT — red, ERROR — red bold, SKIP — dim. Non-TTY / `color: never` — no ANSI.
- Long names truncated with `…`.
- `--summary-format list`:
  ```
  PASS  firewall_permit_tcp   exit=0  turns=3  tok=4520/612  dur=5.4s
  FAIL  nat_server_basic      exit=1  reason=forbidden_tool:execute_shell  turns=2  tok=2100/340  dur=3.1s
  ```

**`--summary-file` (YAML)** — schema:

```yaml
run:
  run_id: 20261022_101500_ab12
  scenarios_total: 4
  parallel: 1
  workspace_mode: copy
  record: null
  replay: tests/fixtures/llm_responses/20261022_101500_ab12
  exit_code: 5
  duration_ms: 135300

scenarios:
  - name: firewall_permit_tcp
    index: 1
    status: PASS
    exit_code: 0
    reason: null
    duration_ms: 5400
    turns: 3
    agent_messages: 4
    usage: {tokens_in: 4520, tokens_out: 612, tokens_total: 5132}
    tools_histogram: {read_doc: 1, write: 1}
    checks: {passed: true, failures: []}
    log: logs/20261022_101500_ab12/firewall_permit_tcp.yaml
    workspace: null                 # null when copy mode + PASS (deleted)
  - name: nat_server_basic
    ...
  - name: vsys_create
    ...
  - name: crash_on_empty
    index: 4
    status: ERROR
    exit_code: 4
    reason: LLMTimeoutError
    duration_ms: 120000
    turns: 1
    usage: {tokens_in: 1200, tokens_out: 0, tokens_total: 1200}
    tools_histogram: {}
    checks: {passed: false, failures: []}
    log: logs/20261022_101500_ab12/crash_on_empty.yaml
    workspace: logs/20261022_101500_ab12/crash_on_empty/workspace

totals:
  passed: 1
  failed: 2
  errored: 1
  skipped: 0
  usage: {tokens_in: 68820, tokens_out: 1852, tokens_total: 70672}
  duration_ms: 135300
```

Rules:
- `usage` is the sum of non-null values; if all are null — `null` (not `0`).
- `checks.failures` — strings like `final_include: missing "10\\.0\\.0\\.0/24"`, `required_tools: read_doc not called`, `max_agent_messages: 11 > 10`.
- `workspace` — path to preserved copy (if kept), else `null`.
- `log` — per-scenario log path.
- `scenarios` ordered by launch order.

**Interaction with `--fail-fast`:**
Remaining scenarios get `status: SKIP`, `exit_code: null`, `reason: fail-fast`, `duration_ms: 0`, `usage: null`, `tools_histogram: {}`, `checks: {passed: false, failures: ["skipped"]}`, `log: null`, `workspace: null`. `run.exit_code` = exit code of the first failure (not the aggregate). `totals.skipped: N`.

**In `repl`:** `--summary` → `exit 2`.

**In `dry-run`:** `--summary` not printed; `--summary-file` ignored with a warning.

### 15.5. Exit Codes

| Code | Meaning |
|---|---|
| 0 | Success (headless: all checks passed). |
| 1 | Scenario checks failed. |
| 2 | Config/scenario/fixture validation error. |
| 3 | Limit exceeded / timeout. |
| 4 | LLM error (after retries) / replay fixture error. |
| 5 | Internal error (uncaught). |

In REPL: only `2` at startup applies.

### 15.6. Examples

```bash
# single scenario, as before
agentprobe run --config config/config.yaml \
  --scenario scenarios/firewall_permit_tcp.yaml

# all scenarios in a directory, sequential, with summary
agentprobe run --config config/config.yaml \
  --scenario-dir scenarios/ --summary

# multiple explicit + tag filter, parallel, summary to file
agentprobe run --config config/config.yaml \
  --scenario scenarios/nat_server_basic.yaml \
  --scenario scenarios/vsys_create.yaml \
  --filter smoke \
  --parallel 4 --summary --summary-file logs/summary.yaml

# record fixtures for all scenarios
agentprobe run --config config/config.yaml \
  --scenario-glob 'scenarios/*.yaml' \
  --record tests/fixtures/llm_responses/20261022_101500_ab12/

# replay from a directory, fail-fast
agentprobe run --config config/config.yaml \
  --scenario-glob 'scenarios/*.yaml' \
  --replay tests/fixtures/llm_responses/20261022_101500_ab12/ \
  --fail-fast --summary

# dry-run for a single scenario
agentprobe dry-run --config config/config.yaml \
  --scenario scenarios/firewall_permit_tcp.yaml
```

---

## 16. Security

- **Filesystem sandbox**: `read`/`write`/`edit` — `workspace`; `read_doc` — `docs_dir`; `read_skill` — `skills_dir`.
- **`api_key`** — via env `${VAR}`; never logged or printed.
- **`command_execute` / `execute_shell`** — mocks (no real execution per spec).
- **Dangerous commands** in assistant text — responsibility of the prompt (`SOUL.md`); the application does not block.
- **Logs** may contain confidential dialogue data; `log_dir` is configurable; recommend not committing.
- **`tool_vars_keys`** are logged (keys only), never values — values may contain secrets.
- **`trust_env=False`** on the HTTP client: environment proxies are ignored unless `proxy` is set in config.

---

## 17. Testing

### 17.1. Unit Tests

- `Sandbox.resolve`: traversal, symlinks, absolute paths.
- `write` / `edit`: creation, existence, `old_string` not found, `replace_all`.
- `syntax_check`: `?`, `commit`, `#` comments, blank lines.
- `SkillLoader`: valid/invalid frontmatter, folder-name mismatch.
- `PromptBuilder`: `MEMORY.md` injection, `AVAILABLE SKILLS`.
- `ScenarioObserver`: `max_agent_messages`, `max_context_tokens`, `forbidden_tools` (abort before call); `usage == null` skip.
- `LLMClient`: stream parsing with `tool_calls` and `usage`; retries on 429/5xx; `trust_env=False` (proxy from config, not env).
- `Fixture`: record → replay round-trip.
- `ToolVars`: `in_memory` and `stdio`; tool receives `tool_vars`.

### 17.2. Application E2E (without real LLM)

Fixtures in `tests/fixtures/llm_responses/<run_id>/<scenario>.jsonl`; runs via `--replay`; check exit code and log content.

### 17.3. Acceptance Criteria

1. `agentprobe run --scenario scenarios/firewall_permit_tcp.yaml --replay tests/fixtures/.../firewall_permit_tcp.jsonl` → `exit 0`; `session_end.checks.passed == true` in the log.
2. Scenario with `forbidden_tools: [execute_shell]` and a fixture calling `execute_shell`: `exit 1`; `scenario_abort.reason == "forbidden_tool:execute_shell"`; **no** `tool_call` event for `execute_shell` (abort before execution).
3. Scenario with `max_agent_messages: 2` where the model emits 3 assistant messages: `exit 1`; `scenario_abort.reason == "max_agent_messages"`; the third model message is **not** added to context (no subsequent `llm_request`).
4. Scenario with `max_context_tokens` where `usage` exceeds: `exit 1`; `scenario_abort.reason == "max_context_tokens"`.
5. Scenario with `transitions` where the first response contains `?`: the second `message` is sent.
6. `tool_vars` for `command_execute` (mock with `responses`): for a configured command, `tool_result.content` matches; for `fail_on` — `is_error=true`.
7. `agentprobe repl` — streaming, `/stats`, `/tools`, `/reset`, `/reload`, Ctrl-C interrupt.
8. With `models.subagent` set, `spawn_agent` is in the tool list; without it — absent; subagent has no `spawn_agent`.
9. Subagent exceeding a limit → `tool_result(is_error=True, "subagent aborted: ...")` to the parent; the parent continues.
10. `--record` writes fixtures; `--replay` reproduces with no network calls (verify via `httpx.MockTransport`/absence of connections).
11. `--dry-run` prints the system prompt, tool schemas, skills, paths; `exit 0`; no LLM call.
12. Log is a valid YAML stream (`yaml.safe_load_all`); each event has `event`, `ts`, `session_id`.
13. `read_skill("huawei_vsys")` returns the body; `# AVAILABLE SKILLS` contains `name` + `description`.
14. `write` to `../../etc/passwd` → `tool_result(is_error=True)`; file is not created.
15. `trust_env=False`: with `HTTP_PROXY=http://bad:1` in env and `proxy: null` in config, the request goes direct (via `httpx.MockTransport`).
16. Tool Pydantic schema contains `description` for every field and constraints; violating (e.g. `limit > 1_000_000`) → MCP returns a validation error, which the orchestrator converts to `tool_result(is_error=True)`.
17. `--scenario-dir scenarios/` with 3 valid YAMLs → 3 runs, 3 per-scenario logs, `run.yaml` with 3 `scenario_end`, `--summary` prints 3 rows + TOTAL.
18. One of 3 scenarios has a YAML typo → `exit 2`; **no** scenario runs; stderr shows path and field.
19. `--parallel 3` with 3 scenarios: all isolated (distinct `session_id`, distinct workspace copies), `run.yaml` without interleaved `---`, `--summary` aggregates correctly.
20. `--record <dir>` + 3 scenarios → 3 files `<scenario>.jsonl` in `<dir>`; `--replay <dir>` reproduces all without network.
21. `--replay <dir>` missing a file for one scenario → that scenario `exit 4`; others pass; `--summary` shows `ERROR` and `TOTAL exit_code = 4`.
22. `--fail-fast` on second-of-three failure: third is `SKIP`; `run.exit_code` = second's code; `totals.skipped = 1`.
23. `--workspace-mode copy` + PASS → workspace copy deleted, `summary.scenarios[i].workspace == null`; FAIL → copy exists with path recorded.
24. `--workspace-mode shared` → warning in console and `run_start.workspace_mode == "shared"`.
25. `--summary-file` + multi → file is valid YAML containing `run`, `scenarios`, `totals`; `usage` sums non-null values.
26. `--summary` in `repl` → `exit 2`.
27. `--dry-run --scenario*` prints scenario list; `--summary` is not printed; `--summary-file` ignored with warning; `exit 0`; no LLM calls.
28. `--record` without PATH → `exit 2`; `--replay` without PATH → `exit 2`; both simultaneously → `exit 2`.
29. `--summary-file` without PATH → `exit 2`; with non-existent parent → `exit 2`.
30. `--summary` without `--summary-format` → table; `--summary-format list` → list.
31. `--workspace-mode` unspecified → `copy`; copy at PASS is deleted; at FAIL is preserved (or always with `--keep-workspace`).
32. `read_doc("vrp_basic")` and `read_doc("security_policy")` return stub contents; `read_doc("unknown")` → `is_error=true`.
33. `logs/<run_id>/` and `summary.yaml` contain only YAML; no XML/JSON is attempted.
34. Multi-scenario `--replay <dir>` with a missing file → that scenario `exit 4`; `--summary` reflects `ERROR`; `TOTAL exit_code = 4`.

---

## 18. Non-Functional Requirements

- **Python** 3.11+; `mypy` strict for `src/agentprobe`; `ruff` (line-length 100).
- **Performance**: per-turn overhead (excluding LLM and tools) < 50 ms; MCP `in_memory` runs without subprocess spawn.
- **Resilience**: log written incrementally; survives session crashes.
- **Portability**: Linux/macOS; Windows not required.
- **License**: internal.

---

## 19. Accepted Assumptions

1. `isolation = "task"`, `background = true` from the original `IDENTITY.md` are ignored.
2. `max_tokens = 1000000` is interpreted as `max_context_tokens` (context limit), not output.
3. Three filesystem roots: `workspace`, `docs_dir`, `skills_dir`; each traversal-protected.
4. `write` does not create parent directories; `edit` requires the file to exist and `old_string` to be unique (when `replace_all=False`).
5. `MEMORY.md` is injected into the main agent's system prompt before every turn; not into the subagent's.
6. `spawn_agent` is only available when `models.subagent` is set; depth 1; `parallel_safe=False`.
7. Parallel tool calls: all `parallel_safe=True` → `gather`; otherwise sequential.
8. `transitions` are re-scanned from the top on every response; `once` defaults to `false`.
9. "Number of agent messages" = count of assistant messages (including those with `tool_calls`).
10. `max_context_tokens` in checks = `usage.prompt_tokens + usage.completion_tokens` of the last response; skipped when `usage == null`.
11. `syntax_check` returns its result as data (`is_error=false`).
12. Log is a YAML stream; one file per session; subagents write to the parent's file with `parent_session_id`.
13. `spawn_agent` is **not** in `forbidden_tools`/`required_tools` by default; add explicitly if needed.
14. `tool_vars` in headless are applied to the MCP server at startup (fresh process/state). In REPL — `{}` (or from config, if set).
15. `--record`/`--replay` only work in headless.
16. `--workspace-mode` default `copy`; `--summary-format` default `table`.
17. `--parallel N` does not change isolation; at `N>1`, `run.yaml` order is completion-based, while `--summary` sorts by `index` (launch order).
18. Under `--workspace-mode copy`/`fresh`, relative `workspace`/`memory_file` in config are rewritten to `logs/<run_id>/<scenario>/workspace/`; `docs_dir`/`skills_dir` are not copied.
19. Multi-scenario `--replay` requires per-scenario files; a single file is valid only for a single `--scenario`.
20. `--summary-file` without `--summary` implicitly enables `--summary` (prints to stdout).
21. Severity ranking for aggregating exit codes: `5 > 4 > 3 > 1 > 0`; `2` only for startup fail-fast (no scenario ran).
22. `--record`/`--replay` paths are mandatory; no defaults.
23. `--summary-file` path is mandatory; no defaults.
24. `docs/` ships with exactly `vrp_basic.md` and `security_policy.md` as stubs.
25. All spec-defined artifacts are YAML (config, logs, summaries, scenarios). Fixtures for `--record`/`--replay` are JSONL because they must be replayed line-by-line.
26. Name `agentprobe` is the working name.

---

## 20. Appendix: Complete Examples

### 20.1. Complete `config/config.yaml`

```yaml
app:
  workspace: ./workspace
  docs_dir: ./docs
  skills_dir: ./skills
  prompt_file: ./prompts/system.md
  subagent_prompt_file: null
  memory_file: ./workspace/MEMORY.md
  user_tools_dir: null
  log_dir: ./logs
  tool_transport: in_memory
  scenario_defaults:
    turn_timeout_secs: 120
    max_agent_messages: 30
    max_context_tokens: 200000
    max_duration_secs: 300

models:
  main:
    endpoint: https://api.example.com/v1
    api_key: ${MAIN_API_KEY}
    model: qwen3.6-27b
    temperature: 0.6
    request_timeout_secs: 120
    max_retries: 3
    proxy: null
  subagent:
    endpoint: https://api.example.com/v1
    api_key: ${SUB_API_KEY}
    model: qwen3.6-27b
    temperature: 0.4
    request_timeout_secs: 120
    max_retries: 3
    proxy: null

limits:
  main:
    max_turns: 35
    max_tool_calls: 100
    max_duration_secs: 600
    max_context_tokens: 1000000
  subagent:
    max_turns: 20
    max_tool_calls: 50
    max_duration_secs: 300
    max_context_tokens: 200000

tools:
  enabled:
    - read_doc
    - read
    - write
    - edit
    - execute_shell
    - command_execute
    - read_skill
    - syntax_check
    - spawn_agent

logging:
  console_level: info
  console_truncate_chars: 400
  color: auto
```

### 20.2. Complete Scenario Example

`scenarios/firewall_permit_tcp.yaml`:

```yaml
name: firewall-permit-tcp
description: "Permit all TCP to 10.0.0.0/24"
initial_message: "how to permit all tcp packets to 10.0.0.0/24"

tool_vars:
  command_execute:
    responses:
      "display version": |
        Huawei Versatile Routing Platform Software
        VRP (R) software, Version 8.180 (USG6686F V600R025C10)
    fail_on: ["reboot", "reset"]
  read_config:
    source: ./fixtures/device_before.txt

transitions:
  - message: "Yes, write it to a file"
    include: ["\\?$", "confirm"]
    exclude: ["done"]
    once: false
  - message: "Now verify the rule"
    include: ["written to", "policy.txt"]
    exclude: []

checks:
  tags: ["firewall", "smoke"]
  final_include: ["tcp", "10\\.0\\.0\\.0/24"]
  final_exclude: ["I cannot", "unknown command"]
  required_tools: ["read_doc", "write"]
  forbidden_tools: ["execute_shell"]
  max_agent_messages: 10
  max_context_tokens: 50000
  max_duration_secs: 120

timeouts:
  turn_secs: 120
```

### 20.3. Complete Log Example (`logs/<session_id>.yaml`)

```yaml
---
event: session_start
ts: 2026-10-22T10:00:00.123Z
session_id: headless_20261022_100000_ab12
mode: headless
scenario: firewall-permit-tcp
model: qwen3.6-27b
limits: {max_turns: 35, max_tool_calls: 100, max_duration_secs: 600, max_context_tokens: 1000000}
tool_transport: in_memory
tool_vars_keys: [command_execute, read_config]
---
event: llm_request
ts: 2026-10-22T10:00:00.500Z
turn: 1
messages_count: 2
tools_count: 9
---
event: llm_response
ts: 2026-10-22T10:00:01.410Z
turn: 1
content: "Let me consult the documentation."
tool_calls:
  - id: call_1
    name: read_doc
    arguments: {"name": "vrp_basic"}
usage: {prompt_tokens: 1450, completion_tokens: 87, total_tokens: 1537}
ttft_ms: 320
latency_ms: 910
---
event: tool_call
ts: 2026-10-22T10:00:01.412Z
turn: 1
call_id: call_1
name: read_doc
arguments: {"name": "vrp_basic"}
---
event: tool_result
ts: 2026-10-22T10:00:01.415Z
turn: 1
call_id: call_1
name: read_doc
is_error: false
duration_ms: 3
content: "<full markdown content>"
artifacts: {bytes: 1024}
---
event: turn_end
ts: 2026-10-22T10:00:02.100Z
turn: 1
duration_ms: 1200
usage: {prompt_tokens: 1450, completion_tokens: 87, total_tokens: 1537}
tools: [read_doc]
---
event: session_end
ts: 2026-10-22T10:00:07.300Z
session_id: headless_20261022_100000_ab12
duration_ms: 5432
turns: 3
usage_total: {prompt_tokens: 4500, completion_tokens: 620, total_tokens: 5120}
tools_histogram: {read_doc: 2, write: 1}
agent_messages: 4
context_tokens_max: 5100
checks: {passed: true, failures: []}
exit_code: 0
```

### 20.4. Complete `--summary-file` Example

See §15.4.

### 20.5. Minimal `SKILL.md` Example

`skills/huawei_vsys/SKILL.md`:

```markdown
---
name: huawei_vsys
description: How to create and configure a virtual system (vsys) on VRPv8.
---

# Creating a vsys

1. Enter system view: `system-view`
2. Create the vsys: `vsys name <name>`
3. Allocate resources...
```

### 20.6. Minimal Tool with `tool_vars` (user tool)

`tools/read_config.py`:

```python
from pydantic import BaseModel, Field
from mcp.server.fastmcp import FastMCP
from agentprobe.tools.vars import get_tool_vars

class ReadConfigArgs(BaseModel):
    section: str | None = Field(
        default=None,
        description="Optional section name to filter the config output.",
        max_length=128,
    )

def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="read_config",
        description="Read the current device configuration from a fixture file. "
                    "The source path is provided via scenario `tool_vars.read_config.source`.",
    )
    async def read_config(args: ReadConfigArgs) -> str:
        vars_ = get_tool_vars().get("read_config", {})
        source = vars_.get("source")
        if not source:
            return "ERROR: missing_source: tool_vars.read_config.source is not configured"
        with open(source, "r", encoding="utf-8") as f:
            content = f.read()
        if args.section:
            # simplistic section filter for demonstration
            return "\n".join(line for line in content.splitlines() if args.section in line)
        return content
```
