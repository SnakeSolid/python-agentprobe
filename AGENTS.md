# AGENTS.md

## Overview

`agentprobe` is an **async LLM agent** reproducing a reverse-engineered *Huawei
Security Expert* agent for **E2E testing** of LLM-driven config agents. It talks
to an OpenAI-compatible model, invokes tools over **MCP**, supports **subagents**
and **lazily loaded skills**, and runs **interactively** (REPL) or **headlessly**
against YAML **scenarios**.

The canonical spec lives under `chapters/` (start at `chapters/INDEX.md`).
**Treat `chapters/` as authoritative** — code should match it. Command execution
is **mocked**; output is **YAML only**.

## Environment & commands

- **Python 3.12**, **`uv`** is the runner. Deps in `pyproject.toml`.

```sh
uv sync                                    # install runtime + dev deps
uv run agentprobe repl --config config/config.yaml
uv run agentprobe run  --config config/config.yaml --scenario scenarios/firewall_permit_tcp.yaml
uv run agentprobe dry-run --config config/config.yaml   # prompt/tools, no model

uv run pytest                  # unit + replay-based E2E tests
uv run ruff check src tests    # lint (line-length 100)
uv run mypy src/agentprobe     # type check (strict)
```

- E2E (`tests/e2e/`) runs the CLI as a subprocess on `--record`/`--replay`
  fixtures — deterministic, no live model. `tests/unit/` covers the rest.
- MyPy is **strict**. Ruff ignores `B008` and `BLE001` — don't remove them.

## Architecture

Package root: `src/agentprobe/`.

```
cli.py               Typer CLI (repl, run, dry-run, exit-code mapping)
config.py            Pydantic config + ${VAR} substitution + validation
errors.py            Exception hierarchy (drives headless exit codes)
llm/                 client.py (streaming+retries), types.py, fixture.py (record/replay)
agent/               orchestrator.py (turn loop, parallel exec, limits),
                     observer.py (SessionCtx + ScenarioObserver),
                     subagent.py (spawn_agent, depth-1), ui.py, session.py
tools/               server.py (FastMCP, auto-imports), client.py (MCP transport),
                     sandbox.py (path escape guard), vars.py, builtin/*.py (one/tool)
skills/loader.py     Skill discovery from <name>/SKILL.md frontmatter
prompt/builder.py    System-prompt assembly (+ MEMORY + AVAILABLE SKILLS)
logging/             yaml_logger.py, console.py, metrics.py
scenario/            schema.py (models), runner.py (isolation, parallelism, summary)
repl/                app.py, commands.py, ui.py
config/config.yaml   runtime config
prompts/             system.md, subagent.md
skills/  docs/  scenarios/  workspace/  tests/  chapters/
```

### Data-flow (one headless run)

1. `cli.py run` → `scenario.runner.Runner`.
2. Runner isolates a workspace copy, loads the scenario, starts MCP tool + LLM
   clients, builds the system prompt.
3. `Orchestrator.turn()` loops: send messages → execute tool calls (parallel
   when all `PARALLEL_SAFE`) → append results, until the model stops or a limit
   aborts.
4. `ScenarioObserver` enforces `checks` (final_include/exclude, required/
   forbidden tools, message/token caps) and aborts via `ScenarioAbort`.
5. Runner aggregates results → exit code.

### Modes

- **REPL**: interactive, no limits (only warnings). Commands
  `/help /tools /stats /log /model /memory /reset /reload /exit`.
- **Headless** (`run`): scenario-driven, limits + checks enforced.
- **`dry-run`**: prints prompt/skills/docs/paths/scenarios, no model.

`--record`/`--replay` are mutually exclusive. Runner options: `--scenario*`,
`--filter*`, `--parallel`, `--fail-fast`, `--workspace-mode`
(`copy|shared|fresh`), `--keep-workspace`, `--summary*`.

### Headless `run` exit codes

| Code | Meaning |
|------|---------|
| 0 | All passed |
| 1 | Scenario failed checks / aborted (e.g. forbidden tool, `max_agent_messages`) |
| 2 | CLI / config / scenario validation error |
| 3 | Limit exceeded |
| 4 | Replay fixture missing / LLM error |
| 5 | Internal/runner error |

Maps to `errors.py`: `ConfigError`=2, `LimitExceeded`=3, `LLMError`/
`ReplayError`=4, `ScenarioAbort` carries its own.

## Conventions

- **Tools are auto-imported MCP servers**: any module under `tools/builtin/` (or
  `user_tools_dir`) with `register(mcp: FastMCP)` is loaded. To add a tool: add
  a file with `register(mcp)` + `@mcp.tool(...)`, return `ERROR: <code>: <msg>`
  on failure, then enable it in `config/config.yaml` `tools.enabled`.
- **`spawn_agent` is dynamic** — offered only if `models.subagent` is set.
- **Sandbox env vars** for tool modules: `AGENTPROBE_WORKSPACE`,
  `AGENTPROBE_TOOL_VARS`, `AGENTPROBE_DOCS_DIR`, `AGENTPROBE_SKILLS_DIR`,
  `AGENTPROBE_CONFIG`. Resolve filesystem paths via `tools/sandbox.py`.
- **Skills**: dir under `skills/` with `SKILL.md` frontmatter `name` (== folder
  name) + `description`.
- **Scenario files**: YAML with `name`, `initial_message`, optional
  `description`, `tool_vars`, `transitions`, `checks`, `timeouts`.

## Configuration

`config/config.yaml` mirrors spec section 4: `app` (paths, `tool_transport`
`in_memory|stdio`, scenario defaults, tool vars), `models` (`main` +
optional `subagent`), `limits` (turn/tool/duration/token caps), `tools.enabled`,
`logging`. Every string supports `${ENV_VAR}` substitution (missing var is an
error); config is validated on startup.

## Editing notes

- All modules use `from __future__ import annotations`; fully type-hinted.
- New app-level exceptions go in `errors.py`; keep exit-code semantics consistent.
- Scenario check regexes compile & validate at load time.
- `PARALLEL_SAFE` in `orchestrator.py` selects parallel-safe tools — add
  mutable/ordering-sensitive tools to the sequential path.
- Logs: `logs/<run_id>/*.yaml`; console output from `logging/console.py` +
  `agent/ui.py`.
