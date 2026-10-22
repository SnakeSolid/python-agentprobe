# Technical Specification: `agentprobe` — Asynchronous LLM Agent for E2E Testing

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

