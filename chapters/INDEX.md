# Chapters Index

This directory contains `TECHSPEC.md`, `APPENDIX1.md`, and `APPENDIX2.md`, split into chapters (one file per top-level section, plus a short `Introduction` for each document). The monolithic source files were removed after the split — these chapters are the canonical reference.

---

## `TECHSPEC.md` — Technical Specification

| # | Chapter | File |
|---|---------|------|
| — | Introduction | [`techspec/techspec-01-introduction.md`](techspec/techspec-01-introduction.md) |
| — | Table of Contents | [`techspec/techspec-02-table-of-contents.md`](techspec/techspec-02-table-of-contents.md) |
| 1 | Purpose and Scope | [`techspec/techspec-03-1-purpose-and-scope.md`](techspec/techspec-03-1-purpose-and-scope.md) |
| 2 | Glossary | [`techspec/techspec-04-2-glossary.md`](techspec/techspec-04-2-glossary.md) |
| 3 | Architecture | [`techspec/techspec-05-3-architecture.md`](techspec/techspec-05-3-architecture.md) |
| 4 | Configuration (`config/config.yaml`) | [`techspec/techspec-06-4-configuration-config-config-yaml.md`](techspec/techspec-06-4-configuration-config-config-yaml.md) |
| 5 | System Prompt | [`techspec/techspec-07-5-system-prompt.md`](techspec/techspec-07-5-system-prompt.md) |
| 6 | LLM Client | [`techspec/techspec-08-6-llm-client.md`](techspec/techspec-08-6-llm-client.md) |
| 7 | Agent Loop (Orchestrator) | [`techspec/techspec-09-7-agent-loop-orchestrator.md`](techspec/techspec-09-7-agent-loop-orchestrator.md) |
| 8 | Subagents (`spawn_agent`) | [`techspec/techspec-10-8-subagents-spawn-agent.md`](techspec/techspec-10-8-subagents-spawn-agent.md) |
| 9 | Tools (MCP) | [`techspec/techspec-11-9-tools-mcp.md`](techspec/techspec-11-9-tools-mcp.md) |
| 10 | Skills | [`techspec/techspec-12-10-skills.md`](techspec/techspec-12-10-skills.md) |
| 11 | Memory | [`techspec/techspec-13-11-memory.md`](techspec/techspec-13-11-memory.md) |
| 12 | REPL Mode | [`techspec/techspec-14-12-repl-mode.md`](techspec/techspec-14-12-repl-mode.md) |
| 13 | Headless Mode (Scenarios) | [`techspec/techspec-15-13-headless-mode-scenarios.md`](techspec/techspec-15-13-headless-mode-scenarios.md) |
| 14 | Logging and Metrics | [`techspec/techspec-16-14-logging-and-metrics.md`](techspec/techspec-16-14-logging-and-metrics.md) |
| 15 | CLI | [`techspec/techspec-17-15-cli.md`](techspec/techspec-17-15-cli.md) |
| 16 | Security | [`techspec/techspec-18-16-security.md`](techspec/techspec-18-16-security.md) |
| 17 | Testing | [`techspec/techspec-19-17-testing.md`](techspec/techspec-19-17-testing.md) |
| 18 | Non-Functional Requirements | [`techspec/techspec-20-18-non-functional-requirements.md`](techspec/techspec-20-18-non-functional-requirements.md) |
| 19 | Accepted Assumptions | [`techspec/techspec-21-19-accepted-assumptions.md`](techspec/techspec-21-19-accepted-assumptions.md) |
| 20 | Appendix: Complete Examples | [`techspec/techspec-22-20-appendix-complete-examples.md`](techspec/techspec-22-20-appendix-complete-examples.md) |

---

## `APPENDIX1.md` — Code Snippets and Examples

| # | Section | File |
|---|---------|------|
| — | Introduction | [`appendix1/appendix1-01-introduction.md`](appendix1/appendix1-01-introduction.md) |
| A | Project skeleton and dependencies | [`appendix1/appendix1-02-a-project-skeleton-and-dependencies.md`](appendix1/appendix1-02-a-project-skeleton-and-dependencies.md) |
| B | Core types | [`appendix1/appendix1-03-b-core-types.md`](appendix1/appendix1-03-b-core-types.md) |
| C | Configuration models | [`appendix1/appendix1-04-c-configuration-models.md`](appendix1/appendix1-04-c-configuration-models.md) |
| D | Scenario schema | [`appendix1/appendix1-05-d-scenario-schema.md`](appendix1/appendix1-05-d-scenario-schema.md) |
| E | Sandbox | [`appendix1/appendix1-06-e-sandbox.md`](appendix1/appendix1-06-e-sandbox.md) |
| F | Tool contract (MCP, idiomatic) | [`appendix1/appendix1-07-f-tool-contract-mcp-idiomatic.md`](appendix1/appendix1-07-f-tool-contract-mcp-idiomatic.md) |
| G | Tool implementations (selected) | [`appendix1/appendix1-08-g-tool-implementations-selected.md`](appendix1/appendix1-08-g-tool-implementations-selected.md) |
| H | `tool_vars` access | [`appendix1/appendix1-09-h-tool-vars-access.md`](appendix1/appendix1-09-h-tool-vars-access.md) |
| I | LLM client | [`appendix1/appendix1-10-i-llm-client.md`](appendix1/appendix1-10-i-llm-client.md) |
| J | Prompt builder | [`appendix1/appendix1-11-j-prompt-builder.md`](appendix1/appendix1-11-j-prompt-builder.md) |
| K | Observer and `ScenarioObserver` | [`appendix1/appendix1-12-k-observer-and-scenarioobserver.md`](appendix1/appendix1-12-k-observer-and-scenarioobserver.md) |
| L | Orchestrator | [`appendix1/appendix1-13-l-orchestrator.md`](appendix1/appendix1-13-l-orchestrator.md) |
| M | YAML logger | [`appendix1/appendix1-14-m-yaml-logger.md`](appendix1/appendix1-14-m-yaml-logger.md) |
| N | Scenario runner (multi-run, isolation, summary) | [`appendix1/appendix1-15-n-scenario-runner-multi-run-isolation-summary.md`](appendix1/appendix1-15-n-scenario-runner-multi-run-isolation-summary.md) |
| O | CLI (`typer`) | [`appendix1/appendix1-16-o-cli-typer.md`](appendix1/appendix1-16-o-cli-typer.md) |
| P | Example unit test (sandbox) | [`appendix1/appendix1-17-p-example-unit-test-sandbox.md`](appendix1/appendix1-17-p-example-unit-test-sandbox.md) |
| Q | Example E2E test with `--replay` | [`appendix1/appendix1-18-q-example-e2e-test-with-replay.md`](appendix1/appendix1-18-q-example-e2e-test-with-replay.md) |
| R | Example skill file | [`appendix1/appendix1-19-r-example-skill-file.md`](appendix1/appendix1-19-r-example-skill-file.md) |
| S | Example complete scenario | [`appendix1/appendix1-20-s-example-complete-scenario.md`](appendix1/appendix1-20-s-example-complete-scenario.md) |
| T | Sample output | [`appendix1/appendix1-21-t-sample-output.md`](appendix1/appendix1-21-t-sample-output.md) |
| U | Implementation checklist | [`appendix1/appendix1-22-u-implementation-checklist.md`](appendix1/appendix1-22-u-implementation-checklist.md) |

---

## `APPENDIX2.md` — Session Output Examples (REPL and Test Modes)

| # | Section | File |
|---|---------|------|
| — | Introduction | [`appendix2/appendix2-01-introduction.md`](appendix2/appendix2-01-introduction.md) |
| 2.0 | Conventions (both modes) | [`appendix2/appendix2-02-2-0-conventions-both-modes.md`](appendix2/appendix2-02-2-0-conventions-both-modes.md) |
| 2.1 | REPL Mode | [`appendix2/appendix2-03-2-1-repl-mode.md`](appendix2/appendix2-03-2-1-repl-mode.md) |
| 2.2 | Headless (Test) Mode | [`appendix2/appendix2-04-2-2-headless-test-mode.md`](appendix2/appendix2-04-2-2-headless-test-mode.md) |
| 2.3 | Exit code summary | [`appendix2/appendix2-05-2-3-exit-code-summary.md`](appendix2/appendix2-05-2-3-exit-code-summary.md) |
| 2.4 | Mode differences summary | [`appendix2/appendix2-06-2-4-mode-differences-summary.md`](appendix2/appendix2-06-2-4-mode-differences-summary.md) |
| 2.5 | Snapshot testing notes | [`appendix2/appendix2-07-2-5-snapshot-testing-notes.md`](appendix2/appendix2-07-2-5-snapshot-testing-notes.md) |

---

## Helper scripts

- `split.py` — splits the original `TECHSPEC.md`, `APPENDIX1.md`, and `APPENDIX2.md` into these chapters (requires the source files to be re-added to the parent directory to run; aware of fenced code blocks so `## ` inside code examples is not treated as a section).
- `verify.py` — checks that no non-blank content was lost during the split (same requirement).
