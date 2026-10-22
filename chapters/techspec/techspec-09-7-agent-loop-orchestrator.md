# Technical Specification: `agentprobe` — Asynchronous LLM Agent for E2E Testing

## 7. Agent Loop (Orchestrator)

### 7.1. Main Turn Loop

```
messages += [user_message]
loop:
  response = LLMClient.chat(messages, tools=mcp_client.schemas())
  observer.on_assistant_message(response)        # may abort
  messages.append(assistant_message)
  if not response.tool_calls: break
  for call in tool_calls:
      observer.on_tool_call_pending(call)        # may abort BEFORE execution
      result = await execute_tool(call)
      observer.on_tool_result(result)
      messages.append(tool_result_message)
  check_limits()                                 # turns / tool_calls / duration
finish_turn()
```

### 7.2. Observer Protocol

```python
class Observer(Protocol):
    async def on_assistant_message(self, msg: AssistantMessage, ctx: SessionCtx) -> None: ...
    async def on_tool_call_pending(self, call: ToolCall, ctx: SessionCtx) -> None: ...
    async def on_tool_result(self, res: ToolResult, ctx: SessionCtx) -> None: ...
    async def on_turn_end(self, stats: TurnStats, ctx: SessionCtx) -> None: ...
```

- `NoOpObserver` — used in REPL.
- `ScenarioObserver` — used in headless; on a failed check, raises `ScenarioAbort(reason, exit_code)`.
- The orchestrator catches `ScenarioAbort` → writes `scenario_abort` to the log → `session_end` → propagates upward (CLI returns the exit code).

### 7.3. Parallel Tool Calls

- `parallel_safe=True`: `read`, `read_doc`, `read_skill`, `command_execute`, `execute_shell`, `syntax_check`.
- `parallel_safe=False`: `write`, `edit`, `spawn_agent`.
- If **all** calls in the batch are `parallel_safe=True` → run via `asyncio.gather`; otherwise — sequential in the order received.
- Results are appended to `messages` in the original order.
- **`on_tool_call_pending`** is called for **every** call **before** any parallel batch starts; if it aborts, the batch does not run.

### 7.4. General Limits (`limits.*`)

Checked between loop iterations: `max_turns` (session turns), `max_tool_calls` (cumulative), `max_duration_secs` (wall-clock), `max_context_tokens` (`tokens_in + tokens_out` of the last response; skipped when `null`).

- **REPL**: not applied; a warning is shown as the model approaches `max_context_tokens`.
- **Headless**: exceeded → `limit_exceeded` in log → `exit 3`.
- **Subagent**: exceeded → subagent session aborted with an error; parent receives `tool_result(is_error=True, content="subagent aborted: <reason>")`; the parent continues. The parent's own scenario checks apply independently.

---

