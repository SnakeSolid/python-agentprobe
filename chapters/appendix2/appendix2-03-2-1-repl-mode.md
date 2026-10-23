# Appendix 2: Session Output Examples (REPL and Test Modes)

## 2.1. REPL Mode

### 2.1.1. Startup banner

```
$ agentprobe repl --config config/config.yaml
agentprobe 0.1.0
model:     qwen3.6-27b  @ https://api.example.com/v1  (proxy: none)
subagent:  qwen3.6-27b  (spawn_agent: enabled)
workspace: /home/user/hwagent/workspace
docs:      /home/user/hwagent/docs  (2 files: security_policy.md, vrp_basic.md)
skills:    /home/user/hwagent/skills  (1 skill: huawei_vsys)
tools:     9 enabled: read_doc, read, write, edit, execute_shell, command_execute, read_skill, syntax_check, spawn_agent
log:       /home/user/hwagent/logs/repl_20261023_143000_ab12.yaml
type /help for commands, Ctrl-D to exit.

>>>
```

When `models.subagent` is absent:

```
subagent:  (disabled; spawn_agent not offered)
```

### 2.1.2. Simple turn (no tools)

```
>>> hi
[assistant] Hello. I'm the Huawei Security Expert. I can help with VRPv8 configuration and diagnostics on HiSecEngine devices. What would you like to do?
tokens: in=820 out=32 | turn 640ms | total 0.6s
>>>
```

### 2.1.3. Turn with a single tool (streaming + tool between segments)

```
>>> how to permit all tcp packets to 10.0.0.0/24
[assistant] Let me check the documentation for security-policy syntax.
→ read_doc(name=security_policy) [2ms]
[assistant] Create a security policy with destination 10.0.0.0/24 and service tcp:

security-policy
 rule name permit_tcp_10_0_0_0_24
  destination-address 10.0.0.0/24
  service tcp
  action permit

Would you like me to write this to a file?
tokens: in=1450 out=187 | turn 1.42s | total 2.0s
>>>
```

**Streaming note:** the first segment `[assistant] Let me check…` prints per chunk; after it completes, `read_doc` runs; then the second segment prints incrementally.

### 2.1.4. Turn with parallel tools (read-only batch)

```
>>> check version and zones
[assistant] I'll gather the device version and zone information.
→ command_execute(command=display version) [1ms]
→ command_execute(command=display zone) [0ms]
[assistant] Device: USG6686F, VRPv8 (USG V600R025C10). Zones: trust (2 ifaces), untrust (1 iface), dmz (0 ifaces).
tokens: in=1980 out=141 | turn 1.05s | total 3.1s
>>>
```

**Why parallel:** both calls are `parallel_safe=True` and are executed via `asyncio.gather`. If `write` or `edit` were in the same batch, the whole batch would run sequentially.

### 2.1.5. Turn with a subagent

```
>>> compare static route vs OSPF for the uplink
[assistant] Let me delegate the comparison to a research subagent.
→ spawn_agent(task="Compare static routing vs OSPF for a single uplink on USG6686F. Return a decision matrix and a recommendation for a small branch.", context="uplink is 100Mbps, single ISP, no dynamic routing today") [4.2s]
[assistant] Recommendation: OSPF for resilience if the branch will add a second WAN later; static otherwise. Decision matrix:
- Static: simplest, fastest convergence, no protocol overhead; no failover without floating static.
- OSPF: dynamic failover, equal-cost multipath, but more CPU and config surface.
For your current single-ISP branch: static route + floating default to backup is the smallest change.
tokens: in=2310 out=312 | turn 6.80s | total 9.9s
>>>
```

**Note:** subagent runs sequentially (`parallel_safe=False`); its `session_id` is `<parent>/sub-1`; events are written to the parent log with `parent_session_id`.

### 2.1.6. Tool error (`sandbox_violation`)

```
>>> write the config to /etc/passwd
[assistant] I'll write the configuration.
→ write(path=/etc/passwd) [1ms] ERROR: sandbox_violation
[assistant] I can't write outside the workspace. The file must be inside the workspace directory. Do you want me to write it to `policy.txt` instead?
tokens: in=1120 out=98 | turn 1.02s | total 11.0s
>>>
```

`is_error=true`; `tool_result.content` = `ERROR: sandbox_violation: /etc/passwd`.

### 2.1.7. LLM error after retries

```
>>> summarize the current policy
[assistant] Let me check the configuration.
→ command_execute(command=display current-configuration | include security-policy) [1ms]
[error] LLMTimeoutError: request timed out after 120.0s (attempts: 3, last: ReadTimeout)
[error] turn aborted; history preserved. Continue, retry, or /reset.
tokens: in=1620 out=0 (partial) | turn 120.3s | total 131.3s
>>>
```

REPL exit code does not change (only `2` at startup applies); the prompt returns after the error.

### 2.1.8. Ctrl-C interrupt

```
>>> now apply the change and commit
[assistant] I'll apply the change…
^C
[interrupt] turn cancelled by user
tokens: in=1450 out=42 (partial) | turn 2.30s | total 133.6s
>>>
```

History up to the interrupt is preserved; an unfinished assistant segment is not added to `messages` (only as a partial `llm_response` log event with `aborted: true`).

### 2.1.9. Context-limit warning

```
>>> list all firewall sessions
[assistant] …(response)…
tokens: in=183200 out=412 | turn 2.1s | total 3m20.4s
[warning] context usage: 183612 / 200000 tokens (91.8%)
>>>
```

Threshold: 90% of `limits.main.max_context_tokens`. REPL applies no limits — only a warning.

### 2.1.10. Commands

#### `/help`

```
>>> /help
commands:
  /help              show this help
  /exit, /quit       exit the REPL
  /reset             start a new session (clears history; MEMORY.md untouched)
  /reload            re-read config, prompt, skills; re-register tools
  /tools             list enabled tools with short descriptions
  /stats             session statistics
  /log               path to the current log file
  /model             show main and subagent models
  /memory            show MEMORY.md contents
>>>
```

#### `/tools`

```
>>> /tools
9 tools enabled:
  read_doc(name)                — read a markdown doc from docs/
  read(path, offset=0, limit=100000, encoding=utf-8) — read a file in workspace
  write(path, content)          — create a new file (fails if exists)
  edit(path, old_string, new_string, replace_all=False) — replace in an existing file
  execute_shell(command)        — mock; fixed success
  command_execute(command)      — mock; honors tool_vars
  read_skill(name)              — load a skill body
  syntax_check(commands)        — basic VRP syntax validation
  spawn_agent(task, context?)   — delegate to a subagent (depth 1)
>>>
```

#### `/stats`

```
>>> /stats
session:     repl_20261023_143000_ab12
duration:    4m 12.3s
turns:       5
agent msgs:  9
tokens:      in=24510  out=1832  total=26342
context max: 3120
tools:
  read_doc:        3
  command_execute: 4
  write:           1
  spawn_agent:     1
  subagents:       1  (parent session: repl_.../sub-1)
log:         /home/user/hwagent/logs/repl_20261023_143000_ab12.yaml
>>>
```

#### `/log`, `/model`, `/memory`

```
>>> /log
/home/user/hwagent/logs/repl_20261023_143000_ab12.yaml

>>> /model
main:     qwen3.6-27b @ https://api.example.com/v1 (temperature=0.6)
subagent: qwen3.6-27b @ https://api.example.com/v1 (temperature=0.4)

>>> /memory
# MEMORY.md

## Device Specs
- **Model**: HUAWEI USG6686F
- **Version**: V600R025C10
- **Memory**: 32768 MB

## Recent Changes
- display version
- display zone
```

#### `/reload`

```
>>> /reload
[info] re-reading config/config.yaml… ok
[info] prompt reloaded: prompts/system.md (12.4 KB)
[info] skills rescanned: 1 skill (huawei_vsys)
[info] tools re-registered: 9 (was 9)
[info] system message updated; history preserved (5 turns, 12 messages)
>>>
```

On error:

```
>>> /reload
[error] config error: path does not exist: ./tools
[error] keeping previous configuration; nothing changed
>>>
```

#### `/reset`

```
>>> /reset
[info] new session: repl_20261023_144500_cd34
[info] log: /home/user/hwagent/logs/repl_20261023_144500_cd34.yaml
>>>
```

#### Unknown command

```
>>> /foo
[error] unknown command: /foo (try /help)
>>>
```

### 2.1.11. Verbosity levels

**`quiet`** — assistant responses and errors only:

```
>>> how to permit tcp to 10.0.0.0/24
Create a security policy…
[warning] context usage: 183612 / 200000 tokens (91.8%)
```

**`info`** (default) — see §2.1.2–2.1.5.

**`verbose`** — adds turn metadata:

```
>>> hi
[info] turn 1 | messages=2 tools=9 | context≈820 tokens
[info] streaming… ttft=310ms
[assistant] Hello. I'm the Huawei Security Expert. …
[info] turn_end 1 | latency=640ms | tokens in=820 out=32
tokens: in=820 out=32 | turn 640ms | total 0.6s
```

### 2.1.12. Unsupported flags in REPL

```
$ agentprobe repl --config config/config.yaml --summary
error: --summary is not supported in repl mode
$ echo $?
2
```

---

