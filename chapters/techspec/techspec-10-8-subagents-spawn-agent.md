# Technical Specification: `agentprobe` — Asynchronous LLM Agent for E2E Testing

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

