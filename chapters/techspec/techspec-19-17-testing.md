# Technical Specification: `agentprobe` — Asynchronous LLM Agent for E2E Testing

## 17. Testing

### 17.1. Unit Tests

- `Sandbox.resolve`: traversal, symlinks, absolute paths.
- `write` / `edit`: creation, existence, `old_string` not found, `replace_all`.
- `syntax_check`: `?`, `commit`, `#` comments, blank lines.
- `SkillLoader`: valid/invalid frontmatter, folder-name mismatch.
- `PromptBuilder`: `MEMORY.md` injection, `AVAILABLE SKILLS`.
- `ScenarioObserver`: `max_agent_messages`, `max_context_tokens`, `forbidden_tools` (abort before call); `usage == null` skip.
- `LLMClient`: stream parsing with `tool_calls` and `usage`; retries on 429/5xx; `trust_env=False` (proxy from config, not env).
- `Fixture`: record → replay round-trip.
- `ToolVars`: `in_memory` and `stdio`; tool receives `tool_vars`.

### 17.2. Application E2E (without real LLM)

Fixtures in `tests/fixtures/llm_responses/<run_id>/<scenario>.jsonl`; runs via `--replay`; check exit code and log content.

### 17.3. Acceptance Criteria

1. `agentprobe run --scenario scenarios/firewall_permit_tcp.yaml --replay tests/fixtures/.../firewall_permit_tcp.jsonl` → `exit 0`; `session_end.checks.passed == true` in the log.
2. Scenario with `forbidden_tools: [execute_shell]` and a fixture calling `execute_shell`: `exit 1`; `scenario_abort.reason == "forbidden_tool:execute_shell"`; **no** `tool_call` event for `execute_shell` (abort before execution).
3. Scenario with `max_agent_messages: 2` where the model emits 3 assistant messages: `exit 1`; `scenario_abort.reason == "max_agent_messages"`; the third model message is **not** added to context (no subsequent `llm_request`).
4. Scenario with `max_context_tokens` where `usage` exceeds: `exit 1`; `scenario_abort.reason == "max_context_tokens"`.
5. Scenario with `transitions` where the first response contains `?`: the second `message` is sent.
6. `tool_vars` for `command_execute` (mock with `responses`): for a configured command, `tool_result.content` matches; for `fail_on` — `is_error=true`.
7. `agentprobe repl` — streaming, `/stats`, `/tools`, `/reset`, `/reload`, Ctrl-C interrupt.
8. With `models.subagent` set, `spawn_agent` is in the tool list; without it — absent; subagent has no `spawn_agent`.
9. Subagent exceeding a limit → `tool_result(is_error=True, "subagent aborted: ...")` to the parent; the parent continues.
10. `--record` writes fixtures; `--replay` reproduces with no network calls (verify via `httpx.MockTransport`/absence of connections).
11. `--dry-run` prints the system prompt, tool schemas, skills, paths; `exit 0`; no LLM call.
12. Log is a valid YAML stream (`yaml.safe_load_all`); each event has `event`, `ts`, `session_id`.
13. `read_skill("huawei_vsys")` returns the body; `# AVAILABLE SKILLS` contains `name` + `description`.
14. `write` to `../../etc/passwd` → `tool_result(is_error=True)`; file is not created.
15. `trust_env=False`: with `HTTP_PROXY=http://bad:1` in env and `proxy: null` in config, the request goes direct (via `httpx.MockTransport`).
16. Tool Pydantic schema contains `description` for every field and constraints; violating (e.g. `limit > 1_000_000`) → MCP returns a validation error, which the orchestrator converts to `tool_result(is_error=True)`.
17. `--scenario-dir scenarios/` with 3 valid YAMLs → 3 runs, 3 per-scenario logs, `run.yaml` with 3 `scenario_end`, `--summary` prints 3 rows + TOTAL.
18. One of 3 scenarios has a YAML typo → `exit 2`; **no** scenario runs; stderr shows path and field.
19. `--parallel 3` with 3 scenarios: all isolated (distinct `session_id`, distinct workspace copies), `run.yaml` without interleaved `---`, `--summary` aggregates correctly.
20. `--record <dir>` + 3 scenarios → 3 files `<scenario>.jsonl` in `<dir>`; `--replay <dir>` reproduces all without network.
21. `--replay <dir>` missing a file for one scenario → that scenario `exit 4`; others pass; `--summary` shows `ERROR` and `TOTAL exit_code = 4`.
22. `--fail-fast` on second-of-three failure: third is `SKIP`; `run.exit_code` = second's code; `totals.skipped = 1`.
23. `--workspace-mode copy` + PASS → workspace copy deleted, `summary.scenarios[i].workspace == null`; FAIL → copy exists with path recorded.
24. `--workspace-mode shared` → warning in console and `run_start.workspace_mode == "shared"`.
25. `--summary-file` + multi → file is valid YAML containing `run`, `scenarios`, `totals`; `usage` sums non-null values.
26. `--summary` in `repl` → `exit 2`.
27. `--dry-run --scenario*` prints scenario list; `--summary` is not printed; `--summary-file` ignored with warning; `exit 0`; no LLM calls.
28. `--record` without PATH → `exit 2`; `--replay` without PATH → `exit 2`; both simultaneously → `exit 2`.
29. `--summary-file` without PATH → `exit 2`; with non-existent parent → `exit 2`.
30. `--summary` without `--summary-format` → table; `--summary-format list` → list.
31. `--workspace-mode` unspecified → `copy`; copy at PASS is deleted; at FAIL is preserved (or always with `--keep-workspace`).
32. `read_doc("vrp_basic")` and `read_doc("security_policy")` return stub contents; `read_doc("unknown")` → `is_error=true`.
33. `logs/<run_id>/` and `summary.yaml` contain only YAML; no XML/JSON is attempted.
34. Multi-scenario `--replay <dir>` with a missing file → that scenario `exit 4`; `--summary` reflects `ERROR`; `TOTAL exit_code = 4`.

---

