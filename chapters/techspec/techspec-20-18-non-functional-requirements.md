# Technical Specification: `agentprobe` — Asynchronous LLM Agent for E2E Testing

## 18. Non-Functional Requirements

- **Python** 3.11+; `mypy` strict for `src/agentprobe`; `ruff` (line-length 100).
- **Performance**: per-turn overhead (excluding LLM and tools) < 50 ms; MCP `in_memory` runs without subprocess spawn.
- **Resilience**: log written incrementally; survives session crashes.
- **Portability**: Linux/macOS; Windows not required.
- **License**: internal.

---

