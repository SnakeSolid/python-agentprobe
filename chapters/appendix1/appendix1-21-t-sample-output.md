# Appendix: Code Snippets and Examples

## T. Sample output

### T.1. Console (`--summary`)

```
SCENARIO                     STATUS  REASON                        TURNS  DURATION  EXIT
firewall_permit_tcp          PASS    -                             3      5.4s      0
nat_server_basic             FAIL    forbidden_tool:execute_shell  2      3.1s      1
vsys_create                  LIMIT   max_context_tokens            4      7.8s      3
crash_on_empty               ERROR   LLMTimeoutError               1      120.0s    4
----------------------------------------------------------------------------------------
TOTAL                        -       -                             -      -         4
```

### T.2. `summary.yaml` (fragment)

```yaml
run:
  run_id: 20261022_101500_ab12
  scenarios_total: 4
  parallel: 1
  workspace_mode: copy
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
    tools_histogram: {read_doc: 1, write: 1}
    checks: {passed: true, failures: []}
    log: logs/20261022_101500_ab12/firewall_permit_tcp.yaml
    workspace: null
  # ...
totals:
  passed: 1
  failed: 1
  errored: 1
  skipped: 1
```

### T.3. Per-session log (`firewall_permit_tcp.yaml`, fragment)

```yaml
---
event: session_start
ts: '2026-10-22T10:00:00.123+00:00'
session_id: headless_20261022_100000_ab12
mode: headless
scenario: firewall-permit-tcp
model: qwen3.6-27b
limits: {max_turns: 35, max_tool_calls: 100, max_duration_secs: 600, max_context_tokens: 1000000}
tool_transport: in_memory
tool_vars_keys: [command_execute]
---
event: llm_request
ts: '2026-10-22T10:00:00.500+00:00'
session_id: headless_20261022_100000_ab12
turn: 1
messages_count: 2
tools_count: 9
---
event: llm_response
ts: '2026-10-22T10:00:01.410+00:00'
session_id: headless_20261022_100000_ab12
turn: 1
content: 'Let me check the docs.'
tool_calls:
  - {id: call_1, name: read_doc, arguments: {name: vrp_basic}}
usage: {prompt_tokens: 1400, completion_tokens: 20, total_tokens: 1420}
ttft_ms: 320.0
latency_ms: 910.0
---
event: tool_result
ts: '2026-10-22T10:00:01.415+00:00'
session_id: headless_20261022_100000_ab12
turn: 1
call_id: call_1
name: read_doc
is_error: false
duration_ms: 3.2
content: "<full markdown content>"
artifacts: {}
---
event: session_end
ts: '2026-10-22T10:00:07.300+00:00'
session_id: headless_20261022_100000_ab12
duration_ms: 5432.0
turns: 3
agent_messages: 4
tools_histogram: {read_doc: 1, write: 1}
context_tokens_max: 1830
checks: {passed: true, failures: []}
exit_code: 0
```

---

