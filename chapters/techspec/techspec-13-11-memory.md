# Technical Specification: `agentprobe` — Asynchronous LLM Agent for E2E Testing

## 11. Memory

- Path: `app.memory_file` (default `workspace/MEMORY.md`).
- The agent edits it via `write`/`edit`; the application does **not** impose a format.
- Before every turn, `PromptBuilder` re-reads the file and injects its contents under `# MEMORY` in the system message. If the file is absent, the section is empty.
- `MEMORY.md` is **not** injected into the subagent's system prompt.

---

