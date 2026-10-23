# agentprobe

An **asynchronous LLM agent** that reproduces the behavior of a reverse-engineered
Huawei Security Expert agent for **end-to-end testing** of LLM-driven configuration
agents. It dialogues with an OpenAI-compatible model, invokes tools over **MCP**,
supports **subagents**, **lazily loads skills**, and runs either **interactively**
(REPL) or **headlessly** against declarative YAML **scenarios**.

The primary use case is writing **E2E tests for LLM-based agents** whose prompt,
tool set, and subagent behavior must be validated against real **or recorded** model
outputs — without needing a live, authenticated model during CI via
`--record` / `--replay` JSONL fixtures.

## Features

- **Main agent** with an OpenAI-compatible streaming LLM backend, retries, and
  per-turn `MEMORY.md` injection.
- **Subagents** per Zed's model: `spawn_agent`, depth-1, isolated context, reusing
  the parent's MCP client.
- **MCP tool server** (one file per tool). Default tools: `read_doc`, `read`,
  `write`, `edit`, `execute_shell`, `read_skill`, `command_execute`,
  `syntax_check`, and dynamically-registered `spawn_agent`.
- **Lazy skill loading** across `skills/<name>/SKILL.md`; skills advertised in the
  system prompt and retrievable via `read_skill`.
- **Filesystem sandbox** constrained to `workspace` (plus separate roots for
  `docs_dir` / `skills_dir`).
- **Two mutually-exclusive run modes**: REPL and headless scenario (YAML).
- **Multi-scenario runs**: `--scenario`, `--scenario-dir`, `--scenario-glob`,
  filters, `--parallel`, `--fail-fast`, `--workspace-mode`.
- **`--record` / `--replay`** LLM response fixtures for offline, deterministic tests.
- **`--dry-run`**, **`--summary`**, **`--summary-file`**, `/reload` in the REPL.
- **YAML logs** (one event stream per scenario/REPL session) and a compact rich
  console output.

## Requirements

- Python **3.12** (see `.python-version`)
- `uv` (package manager and runner)

## Installation

```sh
uv sync          # install runtime + dev dependencies
uv run agentprobe --help
```

## Quickstart

Configure the model in `config/config.yaml` (endpoint, API key, model). Keys use
`${ENV_VAR}` substitution so secrets don't need to live in the file.

### REPL

```sh
uv run agentprobe repl --config config/config.yaml
```

Commands: `/help`, `/tools`, `/stats`, `/log`, `/model`, `/memory`, `/reset`, `/reload`, `/exit`.

### Headless scenario run

```sh
# single scenario
uv run agentprobe run --config config/config.yaml --scenario scenarios/firewall_permit_tcp.yaml

# multiple scenarios from a directory, with a YAML summary
uv run agentprobe run --config config/config.yaml \
  --scenario-dir scenarios --summary --summary-format list --summary-file summary.yaml
```

Each scenario runs in an isolated copy of the workspace by default
(`--workspace-mode copy`) and produces a YAML event log under `logs/<run_id>/`.

### Offline testing with fixtures

```sh
# record responses from a real model
uv run agentprobe run --config config/config.yaml \
  --scenario scenarios/firewall_permit_tcp.yaml --record fixtures/fw

# replay them deterministically (no model/network needed)
uv run agentprobe run --config config/config.yaml \
  --scenario scenarios/firewall_permit_tcp.yaml --replay fixtures/fw
```

### Inspect the assembled prompt / tools without a model

```sh
uv run agentprobe dry-run --config config/config.yaml
uv run agentprobe dry-run --config config/config.yaml --scenario-dir scenarios
```

## Exit codes (headless `run`)

The `run` command aggregates results across scenarios:

| Code | Meaning |
|------|---------|
| `0`  | All scenarios passed |
| `1`  | A scenario failed its checks or aborted (e.g. forbidden tool, `max_agent_messages`) |
| `2`  | CLI / config / scenario validation error (before any run) |
| `3`  | Limit exceeded |
| `4`  | Replay fixture missing or LLM error |
| `5`  | Internal/runner error |

## Configuration

`config/config.yaml` mirrors the spec's section 4:

- **`app`** — workspace, docs/skills/prompt/memory/memory paths, `log_dir`,
  `tool_transport` (`in_memory` or `stdio`), scenario defaults.
- **`models`** — `main` and optional `subagent` model endpoints. Without a
  `subagent` model, `spawn_agent` is absent.
- **`limits`** — per-agent turn/tool/duration/context-token caps.
- **`tools.enabled`** — the subset of tools exposed to the model.
- **`logging`** — console verbosity, truncation, colour.

Environment-variable substitution is applied to every string value
(`${VAR}`), and configuration is validated on startup.

## Scenario format

A scenario is a YAML file (see `scenarios/firewall_permit_tcp.yaml` and
`chapters/appendix/appendix-05-d-scenario-schema.md`) containing:

- `name`, `description`, `initial_message`
- `tool_vars` — behavior parameterization for `command_execute`/`execute_shell`
- `transitions` — follow-up messages triggered by regex `include`/`exclude`
- `checks` — `final_include`, `final_exclude`, `required_tools`,
  `forbidden_tools`, `max_agent_messages`, `max_context_tokens`,
  `max_duration_secs`, `tags`
- `timeouts` — per-turn timeout

## Project structure

```
src/agentprobe/
  cli.py               Typer CLI (repl, run, dry-run)
  config.py            Config models + ${VAR} substitution + validation
  errors.py            Exception hierarchy
  llm/                 client.py (streaming), types.py, fixture.py (record/replay)
  agent/               orchestrator.py (turn loop), observer.py, subagent.py
  tools/               sandbox.py, server.py (FastMCP), client.py, vars.py,
                       builtin/*.py (one file per tool)
  skills/loader.py     skill discovery / frontmatter
  prompt/builder.py    system + subagent prompt assembly
  logging/             yaml_logger.py, console.py, metrics.py
  scenario/            schema.py, runner.py (multi-run, isolation, summary)
  repl/                app.py, commands.py, ui.py
config/config.yaml     runtime configuration
prompts/               system.md, subagent.md
skills/                bundled skills (one dir per skill)
docs/                  bundled documentation stubs
scenarios/             example scenarios
workspace/             agent working directory (incl. MEMORY.md)
tests/                 unit + replay-based E2E acceptance tests
chapters/              the original TECHSPEC + APPENDIX (canonical reference)
```

The full technical specification and code appendix live under `chapters/` (see
`chapters/INDEX.md`).

## Testing

```sh
uv run pytest              # unit + replay-based E2E acceptance tests
uv run ruff check src tests
uv run mypy src/agentprobe
```

The E2E suite (`tests/e2e/`) runs the CLI as a subprocess against `--record` /
`--replay` fixtures, covering the acceptance criteria in the spec's testing
chapter without a live model. `tests/unit/` covers the sandbox, tool modules,
observer, skills loader, prompt builder, config, LLM streaming, fixtures, tool
vars, and both MCP transports (in-memory and stdio).

## Notes / scope

- Command execution is **mocked** (`command_execute`, `execute_shell`);
  `syntax_check` performs only basic VRP validation.
- Only **YAML** output is produced (no XML/JSON), per the spec.
