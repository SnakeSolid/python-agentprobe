from __future__ import annotations

from pathlib import Path

from agentprobe.skills.loader import SkillLoader


class PromptBuilder:
    def __init__(self, prompt_file: Path, memory_file: Path, skill_loader: SkillLoader):
        self._static = prompt_file.read_text(encoding="utf-8")
        self._memory_file = memory_file
        self._skills = skill_loader

    def build(self) -> str:
        memory = ""
        if self._memory_file.exists():
            memory = self._memory_file.read_text(encoding="utf-8").rstrip()
        skills = self._skills.available_skills_block()
        parts = [self._static.rstrip()]
        parts.append("# MEMORY")
        parts.append(memory or "(empty)")
        parts.append("# AVAILABLE SKILLS")
        parts.append(skills or "(none)")
        return "\n\n".join(parts)
