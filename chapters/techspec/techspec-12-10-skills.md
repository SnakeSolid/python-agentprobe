# Technical Specification: `agentprobe` — Asynchronous LLM Agent for E2E Testing

## 10. Skills

- Format: `skills/<name>/SKILL.md` with YAML frontmatter (`name`, `description` required; `name` must equal the folder name, else warning + skip).
- At session start and on `/reload`, scan; the `# AVAILABLE SKILLS` section lists only `name` + `description`.
- `read_skill(name)` returns the body (without frontmatter); `artifacts.metadata` carries the frontmatter.

Example `SKILL.md`:

```markdown
---
name: huawei_vsys
description: How to create and configure a virtual system (vsys) on VRPv8.
---

# Body
...instructions for the model...
```

---

