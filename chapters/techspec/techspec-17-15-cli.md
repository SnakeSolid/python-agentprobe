# Technical Specification: `agentprobe` — Asynchronous LLM Agent for E2E Testing

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

