# Appendix 2: Session Output Examples (REPL and Test Modes)

## 2.2. Headless (Test) Mode

### 2.2.1. Single scenario, PASS (no `--summary`)

```
$ agentprobe run --config config/config.yaml \
    --scenario scenarios/firewall_permit_tcp.yaml
[run 20261023_143500_ab12] starting 1 scenario (mode=headless, workspace=copy)
[scenario firewall-permit-tcp] started
[scenario firewall-permit-tcp] turn 1
[scenario firewall-permit-tcp]   → read_doc(name=vrp_basic) [2ms]
[scenario firewall-permit-tcp] turn 2
[scenario firewall-permit-tcp]   → write(path=policy.txt) [1ms]
[scenario firewall-permit-tcp] turn 3
[scenario firewall-permit-tcp] PASS  turns=3  tok=4520/612  dur=5.4s
[run 20261023_143500_ab12] done: 1 passed, 0 failed, 0 errored (5.4s)
$ echo $?
0
```

### 2.2.2. Single scenario, FAIL (`forbidden_tool`)

```
$ agentprobe run --config config/config.yaml \
    --scenario scenarios/nat_server_basic.yaml
[run 20261023_150200_ef56] starting 1 scenario (mode=headless, workspace=copy)
[scenario nat_server_basic] started
[scenario nat_server_basic] turn 1
[scenario nat_server_basic]   → read_doc(name=vrp_basic) [2ms]
[scenario nat_server_basic] turn 2
[scenario nat_server_basic] FAIL  reason=forbidden_tool:execute_shell  turn=2  tok=2100/340  dur=3.1s
[run 20261023_150200_ef56] done: 0 passed, 1 failed, 0 errored (3.1s)
$ echo $?
1
```

**Note:** abort occurs **before** `execute_shell` is invoked — the per-session log contains no `tool_call` event for it, only `scenario_abort`.

### 2.2.3. Multi-run with `--summary` (table)

```
$ agentprobe run --config config/config.yaml \
    --scenario-dir scenarios/ --summary
[run 20261023_151000_aa11] starting 4 scenarios (mode=headless, workspace=copy)
[scenario crash_on_empty] started
[scenario nat_server_basic] started
[scenario firewall_permit_tcp] started
[scenario vsys_create] started
[scenario firewall_permit_tcp] PASS  turns=3  tok=4520/612  dur=5.4s
[scenario nat_server_basic] FAIL  reason=forbidden_tool:execute_shell  turns=2  tok=2100/340  dur=3.1s
[scenario vsys_create] LIMIT  reason=max_context_tokens  turns=4  tok=61000/900  dur=7.8s
[scenario crash_on_empty] ERROR  reason=LLMTimeoutError  turns=1  tok=1200/0  dur=120.0s
[run 20261023_151000_aa11] done: 1 passed, 1 failed, 1 limit, 1 error (135.3s)

SCENARIO                     STATUS  REASON                        TURNS  TOK_IN  TOK_OUT  DURATION  EXIT
firewall_permit_tcp          PASS    -                             3      4520    612      5.4s      0
nat_server_basic             FAIL    forbidden_tool:execute_shell  2      2100    340      3.1s      1
vsys_create                  LIMIT   max_context_tokens            4      61000   900      7.8s      3
crash_on_empty               ERROR   LLMTimeoutError               1      1200    0        120.0s    4
-----------------------------------------------------------------------------------------------------
TOTAL (4)                    -       passed 1, failed 1, limit 1, error 1                135.3s    4
$ echo $?
4
```

`TOK_IN` / `TOK_OUT` — sum over non-null `usage` for the session (including subagents); `null` shows as `-`.

### 2.2.4. Multi-run with `--summary-format list`

```
$ agentprobe run --config config/config.yaml \
    --scenario-dir scenarios/ --summary --summary-format list
… (run/scenario lines as above) …

PASS   firewall_permit_tcp   exit=0  turns=3  tok=4520/612   dur=5.4s
FAIL   nat_server_basic      exit=1  reason=forbidden_tool:execute_shell  turns=2  tok=2100/340  dur=3.1s
LIMIT  vsys_create           exit=3  reason=max_context_tokens  turns=4  tok=61000/900  dur=7.8s
ERROR  crash_on_empty        exit=4  reason=LLMTimeoutError  turns=1  tok=1200/0  dur=120.0s
$ echo $?
4
```

### 2.2.5. `--summary-file` (plus table on stdout)

```
$ agentprobe run --config config/config.yaml \
    --scenario-dir scenarios/ --summary --summary-file logs/summary.yaml
… (table as in §2.2.3) …
[info] summary written to: logs/summary.yaml
$ echo $?
4
```

Fragment of `logs/summary.yaml`:

```yaml
run:
  run_id: 20261023_151000_aa11
  scenarios_total: 4
  parallel: 1
  workspace_mode: copy
  record: null
  replay: null
  exit_code: 4

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
    log: logs/20261023_151000_aa11/firewall_permit_tcp.yaml
    workspace: null
  - name: nat_server_basic
    index: 2
    status: FAIL
    exit_code: 1
    reason: "forbidden_tool:execute_shell"
    duration_ms: 3100
    turns: 2
    agent_messages: 3
    usage: {tokens_in: 2100, tokens_out: 340, tokens_total: 2440}
    tools_histogram: {read_doc: 1}
    checks: {passed: false, failures: ["forbidden_tool:execute_shell"]}
    log: logs/20261023_151000_aa11/nat_server_basic.yaml
    workspace: logs/20261023_151000_aa11/nat_server_basic/workspace
  # …

totals:
  passed: 1
  failed: 1
  errored: 1
  skipped: 0
  usage: {tokens_in: 68820, tokens_out: 1852, tokens_total: 70672}
  duration_ms: 135300
```

### 2.2.6. `--fail-fast`

```
$ agentprobe run --config config/config.yaml \
    --scenario a.yaml --scenario b.yaml --scenario c.yaml \
    --fail-fast --summary
[run 20261023_152000_bb22] starting 3 scenarios (mode=headless, workspace=copy, fail_fast=on)
[scenario a] PASS  turns=2  tok=1800/200  dur=2.1s
[scenario b] FAIL  reason=forbidden_tool:execute_shell  turns=2  tok=2100/340  dur=3.1s
[scenario c] SKIP  reason=fail-fast
[run 20261023_152000_bb22] aborted after 1 failure (2 launched, 1 skipped)

SCENARIO  STATUS  REASON                        TURNS  TOK_IN  TOK_OUT  DURATION  EXIT
a         PASS    -                             2      1800    200      2.1s      0
b         FAIL    forbidden_tool:execute_shell  2      2100    340      3.1s      1
c         SKIP    fail-fast                     -      -       -        0.0s      -
----------------------------------------------------------------------------------------
TOTAL (3) -       passed 1, failed 1, skipped 1                         5.2s      1
$ echo $?
1
```

With `--fail-fast`, `run.exit_code` is the **first** failing scenario's code, not the aggregate.

### 2.2.7. `--parallel 4`

```
$ agentprobe run --config config/config.yaml \
    --scenario-dir scenarios/ --parallel 4 --summary
[run 20261023_153000_cc33] starting 4 scenarios (mode=headless, workspace=copy, parallel=4)
[scenario nat_server_basic] started
[scenario vsys_create] started
[scenario firewall_permit_tcp] started
[scenario crash_on_empty] started
[scenario firewall_permit_tcp] PASS  turns=3  tok=4520/612  dur=5.4s
[scenario nat_server_basic] FAIL  reason=forbidden_tool:execute_shell  turns=2  tok=2100/340  dur=3.1s
[scenario vsys_create] LIMIT  reason=max_context_tokens  turns=4  tok=61000/900  dur=7.8s
[scenario crash_on_empty] ERROR  reason=LLMTimeoutError  turns=1  tok=1200/0  dur=120.0s
[run 20261023_153000_cc33] done: 1 passed, 1 failed, 1 limit, 1 error (123.4s)
… (table as in §2.2.3, sorted by index, not completion) …
$ echo $?
4
```

**Note:** console completion order is by completion; `--summary` and `summary.yaml` are sorted by `index` (launch order).

### 2.2.8. Abort by `max_agent_messages`

```
$ agentprobe run --config config/config.yaml --scenario scenarios/chatty.yaml
[run 20261023_154000_dd44] starting 1 scenario (mode=headless, workspace=copy)
[scenario chatty] started
[scenario chatty] turn 1
[scenario chatty]   → read_doc(name=vrp_basic) [2ms]
[scenario chatty] turn 2
[scenario chatty] turn 3
[scenario chatty] FAIL  reason=max_agent_messages  turn=3  agent_messages=3 (limit=2)  tok=3400/220  dur=2.9s
[run 20261023_154000_dd44] done: 0 passed, 1 failed, 0 errored (2.9s)
$ echo $?
1
```

**Important:** the third assistant message is **not** added to context; there is no subsequent `llm_request` in the log.

### 2.2.9. Abort by `max_context_tokens`

```
$ agentprobe run --config config/config.yaml --scenario scenarios/big_ctx.yaml
[run 20261023_155000_ee55] starting 1 scenario (mode=headless, workspace=copy)
[scenario big_ctx] started
[scenario big_ctx] turn 1
[scenario big_ctx] turn 2
[scenario big_ctx] FAIL  reason=max_context_tokens  turn=2  used=61200 (limit=50000)  tok=61000/200  dur=4.2s
[run 20261023_155000_ee55] done: 0 passed, 1 failed, 0 errored (4.2s)
$ echo $?
1
```

If the provider did not return `usage`:

```
[warning] usage_missing: context check skipped at turn=2
```

### 2.2.10. `--replay` error: missing fixture

```
$ agentprobe run --config config/config.yaml \
    --scenario a.yaml --scenario b.yaml \
    --replay tests/fixtures/llm_responses/20261023_151000_aa11/
[run 20261023_160000_ff66] starting 2 scenarios (mode=headless, workspace=copy, replay=...)
[scenario a] PASS  turns=3  tok=4520/612  dur=0.4s
[scenario b] ERROR  reason=fixture not found: tests/fixtures/.../b.jsonl
[run 20261023_160000_ff66] done: 1 passed, 0 failed, 1 errored (0.4s)

SCENARIO  STATUS  REASON                                                TURNS  TOK_IN  TOK_OUT  DURATION  EXIT
a         PASS    -                                                     3      4520    612      0.4s      0
b         ERROR   fixture not found: tests/fixtures/.../b.jsonl        0      -       -        0.0s      4
----------------------------------------------------------------------------------------------------------
TOTAL (2) -       passed 1, errored 1                                              0.4s      4
$ echo $?
4
```

### 2.2.11. `--record`

```
$ agentprobe run --config config/config.yaml \
    --scenario-dir scenarios/ \
    --record tests/fixtures/llm_responses/20261023_161000_gg77/
[run 20261023_161000_gg77] starting 3 scenarios (mode=headless, workspace=copy, record=tests/.../gg77/)
[scenario firewall_permit_tcp] PASS  turns=3  tok=4520/612  dur=5.4s
[scenario nat_server_basic] PASS  turns=2  tok=2100/340  dur=3.1s
[scenario vsys_create] PASS  turns=4  tok=5100/900  dur=7.8s
[run 20261023_161000_gg77] done: 3 passed, 0 failed, 0 errored (16.3s)
[info] recorded fixtures in: tests/fixtures/llm_responses/20261023_161000_gg77/
$ echo $?
0
```

Contents of `tests/fixtures/llm_responses/20261023_161000_gg77/`:

```
firewall_permit_tcp.jsonl
nat_server_basic.jsonl
vsys_create.jsonl
```

### 2.2.12. Configuration error (fail-fast at startup)

```
$ agentprobe run --config config/config.yaml --scenario-dir scenarios/
error: scenario validation failed: scenarios/vsys_create.yaml
  field: checks.max_agent_messages
  reason: value must be >= 1, got 0
no scenarios executed
$ echo $?
2
```

No scenario runs; `logs/<run_id>/` contains only `run.yaml` with `run_start` and `run_end` (`exit_code: 2`).

### 2.2.13. `--dry-run`

```
$ agentprobe dry-run --config config/config.yaml \
    --scenario scenarios/firewall_permit_tcp.yaml
=== SYSTEM PROMPT ===
# AGENTS
The main agent responsible for user interaction.
… (12.4 KB total) …

# MEMORY
(empty)

# AVAILABLE SKILLS
- name: huawei_vsys
  description: How to create and configure a virtual system (vsys) on VRPv8.

=== SKILLS ===
- name: huawei_vsys
  description: How to create and configure a virtual system (vsys) on VRPv8.

=== DOCS ===
- security_policy.md
- vrp_basic.md

=== PATHS ===
workspace: /home/user/hwagent/workspace
docs_dir:  /home/user/hwagent/docs
skills_dir: /home/user/hwagent/skills
memory_file: /home/user/hwagent/workspace/MEMORY.md
spawn_agent: enabled

=== SCENARIO ===
name: firewall-permit-tcp
path: scenarios/firewall_permit_tcp.yaml
initial_message: "how to permit all tcp packets to 10.0.0.0/24"
transitions: 2
checks: max_agent_messages=10 max_context_tokens=50000 max_duration_secs=120
$ echo $?
0
```

LLM is not called; `--summary` / `--summary-file` are ignored with a stderr warning (`warning: --summary ignored in dry-run`).

### 2.2.14. `--dry-run` without `--scenario*`

```
$ agentprobe dry-run --config config/config.yaml
=== SYSTEM PROMPT ===
…
=== SCENARIO ===
(no scenarios specified)
$ echo $?
0
```

### 2.2.15. CLI argument errors

```
$ agentprobe run --config config/config.yaml --scenario a.yaml --record
error: --record requires a PATH
$ echo $?
2

$ agentprobe run --config config/config.yaml --scenario a.yaml \
    --record /tmp/x/ --replay /tmp/y/
error: --record and --replay are mutually exclusive
$ echo $?
2

$ agentprobe run --config config/config.yaml --scenario a.yaml \
    --summary-file /no/such/dir/summary.yaml
error: --summary-file: parent directory does not exist: /no/such/dir
$ echo $?
2

$ agentprobe run --config config/config.yaml --scenario a.yaml --scenario b.yaml \
    --replay tests/fixtures/llm_responses/one_file.jsonl
error: --replay with a single file is only valid with exactly one --scenario
$ echo $?
2
```

---

