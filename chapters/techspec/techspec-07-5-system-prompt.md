# Technical Specification: `agentprobe` — Asynchronous LLM Agent for E2E Testing

## 5. System Prompt

### 5.1. `prompts/system.md`

A single static file assembled by hand from the original `AGENTS.md + IDENTITY.md + SOUL.md + TOOLS.md + USER.md`. Section order:

```
# AGENTS
# IDENTITY
# SOUL
# TOOLS
# USER
# MEMORY               ← dynamic (re-read before every turn)
# AVAILABLE SKILLS     ← dynamic (at session start and on /reload)
```

- Remove duplicate rules (verification/evidence-based parts repeat in the source); merge CLI-formatting MUSTs.
- The YAML frontmatter of `IDENTITY.md` belongs in `config.yaml`, not in the prompt.

### 5.2. Dynamic Sections

- **`# MEMORY`** — re-read `memory_file` before every turn. If the file is missing, the section is empty.
- **`# AVAILABLE SKILLS`** — at session start and on `/reload`, scan `skills_dir`, parse frontmatter, produce:
  ```
  - name: huawei_vsys
    description: How to create and configure a virtual system (vsys) on VRPv8.
  ```
  Full body is delivered only via `read_skill`.

### 5.3. Caching

Not required (out of scope).

---

