# Appendix 2: Session Output Examples (REPL and Test Modes)

## 2.0. Conventions (both modes)

### 2.0.1. Colors

Applied only when stdout is a TTY and `logging.color != never`:

| Element | Color |
|---|---|
| `[user]` | cyan |
| `[assistant]` | green |
| `→ <tool>` | yellow |
| `[error]` / `[interrupt]` | red |
| `tokens:` | dim |

### 2.0.2. Streams

- **stdout** — session content (REPL) or run events + `--summary` (headless).
- **stderr** — configuration errors, fatal errors, exit codes in multi-run mode (optional; `--summary` remains on stdout).

### 2.0.3. Console levels (`logging.console_level`)

- `quiet` — assistant text and errors only.
- `info` — + user, tool lines, tokens.
- `verbose` — + turn metadata, full tool arguments, `messages_count`.

### 2.0.4. Prefixes

`[run <run_id>]`, `[scenario <name>]`, `[warning]`, `[error]`, `[interrupt]`, `[info]`.

### 2.0.5. Streaming

In REPL, assistant text appears incrementally per chunk; in headless, only the final segment of each turn is displayed. In the examples below, the final view is shown; streaming points are noted in parentheses where relevant.

---

