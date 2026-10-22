# Technical Specification: `agentprobe` — Asynchronous LLM Agent for E2E Testing

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

