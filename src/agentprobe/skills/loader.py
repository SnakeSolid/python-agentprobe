"""Skill discovery and metadata (used for the `# AVAILABLE SKILLS` block)."""

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
        for skill_md in sorted(self.skills_dir.glob("*/SKILL.md")):
            try:
                text = skill_md.read_text(encoding="utf-8")
                if not text.startswith("---"):
                    continue
                _, fm, _ = text.split("---", 2)
                meta = yaml.safe_load(fm) or {}
                name = meta.get("name")
                desc = meta.get("description")
                if not name or not desc:
                    continue
                if name != skill_md.parent.name:
                    continue  # folder-name mismatch: skip
                self._skills.append(SkillMeta(name=name, description=desc, path=skill_md))
            except Exception:  # noqa: S112 - skip malformed skill dirs silently
                continue

    def available_skills_block(self) -> str:
        if not self._skills:
            return ""
        return "\n".join(
            f"- name: {s.name}\n  description: {s.description}" for s in self._skills
        )
