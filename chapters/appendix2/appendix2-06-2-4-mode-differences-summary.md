# Appendix 2: Session Output Examples (REPL and Test Modes)

## 2.4. Mode differences summary

| Aspect | REPL | Headless |
|---|---|---|
| Input | interactive | `initial_message` + `transitions` |
| Assistant streaming | yes (visible per chunk) | no (final turn segment only) |
| Console prefixes | `[user]`, `[assistant]`, `→ tool`, `[error]`, `[interrupt]`, `[warning]` | `[run …]`, `[scenario …]`, `[warning]`, `[error]` |
| Limits | not applied | applied; on exceed — `LIMIT`/`FAIL` and `exit 3/1` |
| `forbidden_tools` | not checked | checked on every `tool_call_pending` (abort **before** call) |
| `max_agent_messages` / `max_context_tokens` | warning at 90% context only | abort on exceed |
| `--summary` | `exit 2` | table + `summary.yaml` (if specified) |
| `--record` / `--replay` | not supported | required with explicit PATH |
| Termination | Ctrl-D | exit code |
| `MEMORY.md` | shared `workspace/` | per-scenario `workspace/` copy |
| MCP server | one per process | new per scenario (`stdio`: subprocess; `in_memory`: reset) |

---

