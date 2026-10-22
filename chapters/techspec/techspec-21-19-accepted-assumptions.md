# Technical Specification: `agentprobe` — Asynchronous LLM Agent for E2E Testing

## 19. Accepted Assumptions

1. `isolation = "task"`, `background = true` from the original `IDENTITY.md` are ignored.
2. `max_tokens = 1000000` is interpreted as `max_context_tokens` (context limit), not output.
3. Three filesystem roots: `workspace`, `docs_dir`, `skills_dir`; each traversal-protected.
4. `write` does not create parent directories; `edit` requires the file to exist and `old_string` to be unique (when `replace_all=False`).
5. `MEMORY.md` is injected into the main agent's system prompt before every turn; not into the subagent's.
6. `spawn_agent` is only available when `models.subagent` is set; depth 1; `parallel_safe=False`.
7. Parallel tool calls: all `parallel_safe=True` → `gather`; otherwise sequential.
8. `transitions` are re-scanned from the top on every response; `once` defaults to `false`.
9. "Number of agent messages" = count of assistant messages (including those with `tool_calls`).
10. `max_context_tokens` in checks = `usage.prompt_tokens + usage.completion_tokens` of the last response; skipped when `usage == null`.
11. `syntax_check` returns its result as data (`is_error=false`).
12. Log is a YAML stream; one file per session; subagents write to the parent's file with `parent_session_id`.
13. `spawn_agent` is **not** in `forbidden_tools`/`required_tools` by default; add explicitly if needed.
14. `tool_vars` in headless are applied to the MCP server at startup (fresh process/state). In REPL — `{}` (or from config, if set).
15. `--record`/`--replay` only work in headless.
16. `--workspace-mode` default `copy`; `--summary-format` default `table`.
17. `--parallel N` does not change isolation; at `N>1`, `run.yaml` order is completion-based, while `--summary` sorts by `index` (launch order).
18. Under `--workspace-mode copy`/`fresh`, relative `workspace`/`memory_file` in config are rewritten to `logs/<run_id>/<scenario>/workspace/`; `docs_dir`/`skills_dir` are not copied.
19. Multi-scenario `--replay` requires per-scenario files; a single file is valid only for a single `--scenario`.
20. `--summary-file` without `--summary` implicitly enables `--summary` (prints to stdout).
21. Severity ranking for aggregating exit codes: `5 > 4 > 3 > 1 > 0`; `2` only for startup fail-fast (no scenario ran).
22. `--record`/`--replay` paths are mandatory; no defaults.
23. `--summary-file` path is mandatory; no defaults.
24. `docs/` ships with exactly `vrp_basic.md` and `security_policy.md` as stubs.
25. All spec-defined artifacts are YAML (config, logs, summaries, scenarios). Fixtures for `--record`/`--replay` are JSONL because they must be replayed line-by-line.
26. Name `agentprobe` is the working name.

---

