# Technical Specification: `agentprobe` — Asynchronous LLM Agent for E2E Testing

## 16. Security

- **Filesystem sandbox**: `read`/`write`/`edit` — `workspace`; `read_doc` — `docs_dir`; `read_skill` — `skills_dir`.
- **`api_key`** — via env `${VAR}`; never logged or printed.
- **`command_execute` / `execute_shell`** — mocks (no real execution per spec).
- **Dangerous commands** in assistant text — responsibility of the prompt (`SOUL.md`); the application does not block.
- **Logs** may contain confidential dialogue data; `log_dir` is configurable; recommend not committing.
- **`tool_vars_keys`** are logged (keys only), never values — values may contain secrets.
- **`trust_env=False`** on the HTTP client: environment proxies are ignored unless `proxy` is set in config.

---

