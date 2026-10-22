# Technical Specification: `agentprobe` — Asynchronous LLM Agent for E2E Testing

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

