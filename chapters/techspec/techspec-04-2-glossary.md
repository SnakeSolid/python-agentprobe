# Technical Specification: `agentprobe` — Asynchronous LLM Agent for E2E Testing

## 2. Glossary

| Term | Meaning |
|---|---|
| **Main agent** | Dialogue orchestrator; has all tools and `spawn_agent`. |
| **Subagent** | Isolated agent at depth 1; has no `spawn_agent`. |
| **Tool** | An MCP tool exposed to the model via `tools` in Chat Completions. |
| **MCP server** | In-process or subprocess `mcp.server.fastmcp.FastMCP` instance registering tools. |
| **Skill** | `skills/<name>/SKILL.md` with YAML frontmatter; loaded lazily via `read_skill`. |
| **Session** | One dialogue: messages, counters, log file, `session_id`. |
| **Turn** | One cycle of `LLM → (optional) tool_calls → tool results → LLM` until an assistant message with no `tool_calls`. |
| **Scenario** | YAML file with `initial_message`, `transitions`, `checks`, `tool_vars`. |
| **Mock** | A tool returning a fixed successful result. |
| **`tool_vars`** | Scenario section parameterizing behavior of specific tools. |
| **Observer** | A hook in the orchestrator invoked on every event (message, tool_call); the scenario runner uses it for checks. |
| **Run** | A single `agentprobe run` invocation, potentially covering multiple scenarios. |
| **`run_id`** | Identifier of a run: `<YYYYMMDD_HHMMSS>_<rand4>`. |

---

