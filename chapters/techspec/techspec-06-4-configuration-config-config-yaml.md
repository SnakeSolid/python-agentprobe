# Technical Specification: `agentprobe` — Asynchronous LLM Agent for E2E Testing

## 4. Configuration (`config/config.yaml`)

### 4.1. Schema

```yaml
app:
  workspace: ./workspace              # sandbox root for read/write/edit
  docs_dir: ./docs                    # for read_doc
  skills_dir: ./skills                # for read_skill / AVAILABLE SKILLS
  prompt_file: ./prompts/system.md
  subagent_prompt_file: null          # null → use prompt_file
  memory_file: ./workspace/MEMORY.md
  user_tools_dir: ./tools             # optional
  log_dir: ./logs
  tool_transport: in_memory           # in_memory | stdio
  scenario_defaults:
    turn_timeout_secs: 120
    max_agent_messages: 30
    max_context_tokens: 200000
    max_duration_secs: 300

models:
  main:
    endpoint: https://api.example.com/v1
    api_key: ${MAIN_API_KEY}          # env substitution
    model: qwen3.6-27b
    temperature: 0.6
    request_timeout_secs: 120
    max_retries: 3
    proxy: null                       # e.g. http://127.0.0.1:8080
  subagent:                           # absent/empty → spawn_agent unavailable
    endpoint: https://api.example.com/v1
    api_key: ${SUB_API_KEY}
    model: qwen3.6-27b
    temperature: 0.4
    request_timeout_secs: 120
    max_retries: 3
    proxy: null

limits:
  main:
    max_turns: 35
    max_tool_calls: 100
    max_duration_secs: 600
    max_context_tokens: 1000000
  subagent:
    max_turns: 20
    max_tool_calls: 50
    max_duration_secs: 300
    max_context_tokens: 200000

tools:
  enabled:
    - read_doc
    - read
    - write
    - edit
    - execute_shell
    - command_execute
    - read_skill
    - syntax_check

logging:
  console_level: info                 # quiet | info | verbose
  console_truncate_chars: 400
  color: auto                         # auto | always | never
```

### 4.2. Rules

- **Pydantic validation**: any validation error → `exit 2` with a human-readable message and the field path.
- **`${VAR}` substitution**: string values may contain `${VAR}`, substituted from the environment; a missing variable is a configuration error.
- **`models.subagent` absent** → `spawn_agent` is **not registered** and is not offered in `tools`.
- **`tools.enabled`** filters the final tool set; an unknown name is a configuration error (typo protection).
- **`subagent_prompt_file: null`** → the subagent uses `prompt_file`.
- **`proxy`** in `models.*` → `httpx.AsyncClient(proxy=proxy, trust_env=False)`. When `proxy: null`, `trust_env=False` is still applied (env vars like `HTTP_PROXY`/`HTTPS_PROXY` are ignored).
- **`tool_transport`**: `in_memory` runs the MCP server in the same process; `stdio` spawns `python -m agentprobe.tools.server` as a subprocess (env includes `AGENTPROBE_TOOL_VARS`, see 9.5).

---

