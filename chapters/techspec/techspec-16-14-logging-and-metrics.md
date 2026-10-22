# Technical Specification: `agentprobe` — Asynchronous LLM Agent for E2E Testing

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

