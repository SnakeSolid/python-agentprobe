# Technical Specification: `agentprobe` — Asynchronous LLM Agent for E2E Testing

## 20. Appendix: Complete Examples

### 20.1. Complete `config/config.yaml`

```yaml
app:
  workspace: ./workspace
  docs_dir: ./docs
  skills_dir: ./skills
  prompt_file: ./prompts/system.md
  subagent_prompt_file: null
  memory_file: ./workspace/MEMORY.md
  user_tools_dir: null
  log_dir: ./logs
  tool_transport: in_memory
  scenario_defaults:
    turn_timeout_secs: 120
    max_agent_messages: 30
    max_context_tokens: 200000
    max_duration_secs: 300

models:
  main:
    endpoint: https://api.example.com/v1
    api_key: ${MAIN_API_KEY}
    model: qwen3.6-27b
    temperature: 0.6
    request_timeout_secs: 120
    max_retries: 3
    proxy: null
  subagent:
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
    - spawn_agent

logging:
  console_level: info
  console_truncate_chars: 400
  color: auto
```

### 20.2. Complete Scenario Example

`scenarios/firewall_permit_tcp.yaml`:

```yaml
name: firewall-permit-tcp
description: "Permit all TCP to 10.0.0.0/24"
initial_message: "how to permit all tcp packets to 10.0.0.0/24"

tool_vars:
  command_execute:
    responses:
      "display version": |
        Huawei Versatile Routing Platform Software
        VRP (R) software, Version 8.180 (USG6686F V600R025C10)
    fail_on: ["reboot", "reset"]
  read_config:
    source: ./fixtures/device_before.txt

transitions:
  - message: "Yes, write it to a file"
    include: ["\\?$", "confirm"]
    exclude: ["done"]
    once: false
  - message: "Now verify the rule"
    include: ["written to", "policy.txt"]
    exclude: []

checks:
  tags: ["firewall", "smoke"]
  final_include: ["tcp", "10\\.0\\.0\\.0/24"]
  final_exclude: ["I cannot", "unknown command"]
  required_tools: ["read_doc", "write"]
  forbidden_tools: ["execute_shell"]
  max_agent_messages: 10
  max_context_tokens: 50000
  max_duration_secs: 120

timeouts:
  turn_secs: 120
```

### 20.3. Complete Log Example (`logs/<session_id>.yaml`)

```yaml
---
event: session_start
ts: 2026-10-22T10:00:00.123Z
session_id: headless_20261022_100000_ab12
mode: headless
scenario: firewall-permit-tcp
model: qwen3.6-27b
limits: {max_turns: 35, max_tool_calls: 100, max_duration_secs: 600, max_context_tokens: 1000000}
tool_transport: in_memory
tool_vars_keys: [command_execute, read_config]
---
event: llm_request
ts: 2026-10-22T10:00:00.500Z
turn: 1
messages_count: 2
tools_count: 9
---
event: llm_response
ts: 2026-10-22T10:00:01.410Z
turn: 1
content: "Let me consult the documentation."
tool_calls:
  - id: call_1
    name: read_doc
    arguments: {"name": "vrp_basic"}
usage: {prompt_tokens: 1450, completion_tokens: 87, total_tokens: 1537}
ttft_ms: 320
latency_ms: 910
---
event: tool_call
ts: 2026-10-22T10:00:01.412Z
turn: 1
call_id: call_1
name: read_doc
arguments: {"name": "vrp_basic"}
---
event: tool_result
ts: 2026-10-22T10:00:01.415Z
turn: 1
call_id: call_1
name: read_doc
is_error: false
duration_ms: 3
content: "<full markdown content>"
artifacts: {bytes: 1024}
---
event: turn_end
ts: 2026-10-22T10:00:02.100Z
turn: 1
duration_ms: 1200
usage: {prompt_tokens: 1450, completion_tokens: 87, total_tokens: 1537}
tools: [read_doc]
---
event: session_end
ts: 2026-10-22T10:00:07.300Z
session_id: headless_20261022_100000_ab12
duration_ms: 5432
turns: 3
usage_total: {prompt_tokens: 4500, completion_tokens: 620, total_tokens: 5120}
tools_histogram: {read_doc: 2, write: 1}
agent_messages: 4
context_tokens_max: 5100
checks: {passed: true, failures: []}
exit_code: 0
```

### 20.4. Complete `--summary-file` Example

See §15.4.

### 20.5. Minimal `SKILL.md` Example

`skills/huawei_vsys/SKILL.md`:

```markdown
---
name: huawei_vsys
description: How to create and configure a virtual system (vsys) on VRPv8.
---

# Creating a vsys

1. Enter system view: `system-view`
2. Create the vsys: `vsys name <name>`
3. Allocate resources...
```

### 20.6. Minimal Tool with `tool_vars` (user tool)

`tools/read_config.py`:

```python
from pydantic import BaseModel, Field
from mcp.server.fastmcp import FastMCP
from agentprobe.tools.vars import get_tool_vars

class ReadConfigArgs(BaseModel):
    section: str | None = Field(
        default=None,
        description="Optional section name to filter the config output.",
        max_length=128,
    )

def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="read_config",
        description="Read the current device configuration from a fixture file. "
                    "The source path is provided via scenario `tool_vars.read_config.source`.",
    )
    async def read_config(args: ReadConfigArgs) -> str:
        vars_ = get_tool_vars().get("read_config", {})
        source = vars_.get("source")
        if not source:
            return "ERROR: missing_source: tool_vars.read_config.source is not configured"
        with open(source, "r", encoding="utf-8") as f:
            content = f.read()
        if args.section:
            # simplistic section filter for demonstration
            return "\n".join(line for line in content.splitlines() if args.section in line)
        return content
```
