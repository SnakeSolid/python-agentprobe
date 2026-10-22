# Technical Specification: `agentprobe` — Asynchronous LLM Agent for E2E Testing

## 1. Purpose and Scope

### 1.1. Goal

`agentprobe` is a Python application that reproduces the behavior of a reverse-engineered Huawei Security Expert agent: it dialogues with an LLM, invokes tools, supports subagents, and lazily loads skills — while allowing **automated scenario execution** (headless) for E2E verification of model behavior.

The primary use case is **writing end-to-end tests** for LLM-based agents whose prompt, tool set, and subagent behavior must be validated against real or recorded model outputs.

### 1.2. In Scope

- Main agent with an OpenAI-compatible LLM backend (streaming).
- Subagents per Zed's model: `spawn_agent`, depth 1, isolated context, parallel execution.
- Tools implemented as an **MCP server** (one file per tool).
- Default tool set: `read_doc`, `read`, `write`, `edit`, `execute_shell`, `read_skill`, `command_execute`, `syntax_check`, `spawn_agent` (dynamically).
- Lazy skill loading via `read_skill`; skills advertised in the system prompt.
- `MEMORY.md`: a file editable by the agent, re-read and injected before every turn.
- Two mutually exclusive run modes: **REPL** and **headless scenario** (YAML).
- Compact console output; complete YAML log file.
- Metrics: tokens (from model `usage` only), latency, tool calls, turns, duration.
- Filesystem sandbox within `workspace` (and separate roots for `docs_dir`, `skills_dir`).
- `tool_vars` section in scenario for parameterizing tool behavior.
- Multi-scenario runs: `--scenario`, `--scenario-dir`, `--scenario-glob`, filters, `--parallel`, `--fail-fast`, `--workspace-mode`.
- `--record` / `--replay` for LLM response fixtures (explicit paths only).
- `--dry-run`, `--summary`, `--summary-file` (explicit path), `/reload` in REPL.

### 1.3. Out of Scope (current version)

- Real execution of commands on the device (`command_execute`, `execute_shell` are mocks).
- Approval mechanisms for dangerous commands (only textual warnings in the prompt).
- Prompt caching (e.g., Anthropic-style `cache_control`).
- Multi-user mode, web UI, database.
- Full VRP parser for `syntax_check` (only basic validation).
- Non-YAML output formats (JUnit XML, JSON summaries, etc.).
- `--summary` in REPL mode.

---

