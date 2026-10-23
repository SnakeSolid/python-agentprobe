# Appendix: Code Snippets and Examples

## J. Prompt builder

### J.1. `src/agentprobe/prompt/builder.py`

```python
from __future__ import annotations
from pathlib import Path


class PromptBuilder:
    def __init__(self, prompt_file: Path, memory_file: Path, skill_loader):
        self._static = prompt_file.read_text(encoding="utf-8")
        self._memory_file = memory_file
        self._skills = skill_loader

    def build(self) -> str:
        memory = ""
        if self._memory_file.exists():
            memory = self._memory_file.read_text(encoding="utf-8").rstrip()
        skills = self._skills.available_skills_block()
        # Replace dynamic markers (present in the static file as "# MEMORY\n" etc.)
        # Simplest approach: append dynamic sections at the end if markers absent.
        parts = [self._static.rstrip()]
        parts.append("# MEMORY")
        parts.append(memory or "(empty)")
        parts.append("# AVAILABLE SKILLS")
        parts.append(skills or "(none)")
        return "\n\n".join(parts)
```

### J.2. `src/agentprobe/skills/loader.py`

```python
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import yaml


@dataclass
class SkillMeta:
    name: str
    description: str
    path: Path


class SkillLoader:
    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir
        self._skills: list[SkillMeta] = []
        self.scan()

    def scan(self) -> None:
        self._skills = []
        for skill_md in self.skills_dir.glob("*/SKILL.md"):
            try:
                text = skill_md.read_text(encoding="utf-8")
                if not text.startswith("---"):
                    continue
                _, fm, _ = text.split("---", 2)
                meta = yaml.safe_load(fm)
                name = meta.get("name")
                desc = meta.get("description")
                if not name or not desc:
                    continue
                if name != skill_md.parent.name:
                    continue  # warning logged elsewhere
                self._skills.append(SkillMeta(name=name, description=desc, path=skill_md))
            except Exception:
                continue

    def available_skills_block(self) -> str:
        if not self._skills:
            return ""
        return "\n".join(
            f"- name: {s.name}\n  description: {s.description}"
            for s in self._skills
        )
```

---

