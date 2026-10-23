# Appendix 2: Session Output Examples (REPL and Test Modes)

## 2.5. Snapshot testing notes

These examples can be used as golden files for CLI snapshot tests. Only the following parts are variable and should be normalized before comparison:

| Variable | Normalization example |
|---|---|
| `run_id` | `20261023_143000_ab12` → `<RUN_ID>` |
| `session_id` | `repl_…_ab12`, `headless_…_ab12` → `<SESSION_ID>` |
| Absolute paths | `/home/user/...` → `<PATH>` |
| Durations / latencies | `\d+\.\d+ms`, `\d+\.\d+s` → `<MS>` / `<S>` |
| Token counts (when replayed from a live model) | `in=\d+ out=\d+` → `in=<N> out=<N>` (keep exact in `--replay` fixtures) |

**Recommended snapshot set:**

1. `repl_startup.txt` — §2.1.1
2. `repl_simple_turn.txt` — §2.1.2
3. `repl_tool_turn.txt` — §2.1.3
4. `repl_parallel_tools.txt` — §2.1.4
5. `repl_subagent.txt` — §2.1.5
6. `repl_sandbox_error.txt` — §2.1.6
7. `repl_ctrlc.txt` — §2.1.8
8. `headless_pass.txt` — §2.2.1
9. `headless_forbidden.txt` — §2.2.2
10. `headless_summary_table.txt` — §2.2.3
11. `headless_summary_yaml.yaml` — §2.2.5
12. `headless_fail_fast.txt` — §2.2.6
13. `headless_parallel.txt` — §2.2.7
14. `headless_max_agent_messages.txt` — §2.2.8
15. `headless_replay_missing.txt` — §2.2.10
16. `headless_config_error.txt` — §2.2.12
17. `dry_run.txt` — §2.2.13
18. `cli_arg_errors.txt` — §2.2.15
