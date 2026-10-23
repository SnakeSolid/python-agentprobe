"""Assemble the system prompt from the static file plus dynamic sections."""

from __future__ import annotations

from pathlib import Path

from agentprobe.skills.loader import SkillLoader


class PromptBuilder:
    def __init__(
        self,
        prompt_file: Path,
        memory_file: Path,
        skill_loader: SkillLoader,
        include_memory: bool = True,
    ):
        self.static = prompt_file.read_text(encoding="utf-8")
        self.memory_file = memory_file
        self.skills = skill_loader
        self.include_memory = include_memory

    def build(self) -> str:
        parts = [self.static.rstrip()]
        if self.include_memory:
            memory = ""
            if self.memory_file.exists():
                memory = self.memory_file.read_text(encoding="utf-8").rstrip()
            parts.append("# MEMORY")
            parts.append(memory or "(empty)")
        skills = self.skills.available_skills_block()
        parts.append("# AVAILABLE SKILLS")
        parts.append(skills or "(none)")
        return "\n\n".join(parts)
