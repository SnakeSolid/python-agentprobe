# E2E acceptance tests (replay-based)

These tests exercise the **real CLI** as a subprocess (`python -m agentprobe ...`)
against `--record` / `--replay` JSONL fixtures, **without a real LLM**. Each test
builds its scenario YAML, fixture JSONL and `config.yaml` inside its own
`tmp_path`, so the suite is self-contained and never touches the repo's
`logs/`, `scenarios/`, `workspace/` or `config/` trees.

## What is covered (acceptance criteria)

| File | Criteria |
| --- | --- |
| `test_fixture_replay.py` | 1 (firewall replay passes), 4 (missing fixture -> exit 4), 5 (record -> replay round-trip) |
| `test_aborts.py` | 2 (forbidden `execute_shell` aborts, no `tool_call` event), 3 (`max_agent_messages` abort, no subsequent `llm_request`) |
| `test_cli_errors.py` | 6 (unknown tool in config -> exit 2), 7 (`repl --summary` -> exit 2), 8 (`--record`/`--replay` together and `--record` w/o path -> exit 2) |
| `test_multi_scenario.py` | 9 (multi-scenario summary + summary-file), 10 (scenario YAML typo -> exit 2, no runs) |

Exit-code contract verified: `0` pass, `1` scenario abort/fail, `2` config/CLI/
validation error, `4` missing replay fixture.

## Running

From the repo root:

```sh
uv run pytest tests/e2e -q
uv run ruff check tests/e2e tests/fixtures
```

The `record` -> `replay` round-trip starts a tiny local OpenAI-compatible stub
server (`fake_llm.py`) so `--record` can write a real fixture without any
network access.
