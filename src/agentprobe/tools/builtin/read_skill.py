from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from agentprobe.tools.sandbox import Sandbox


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="read_skill",
        description="Load the body of a skill (SKILL.md). Frontmatter is stripped.",
    )
    async def read_skill(
        name: Annotated[str, Field(description="Skill folder name.", min_length=1, max_length=128)],
    ) -> str:
        try:
            skills_root = Sandbox(Path(os.environ["AGENTPROBE_SKILLS_DIR"]))
            target = skills_root.resolve(f"{name}/SKILL.md")
            if not target.exists():
                return f"ERROR: skill_not_found: {name}"
            text = target.read_text(encoding="utf-8")
            if text.startswith("---"):
                parts = text.split("---", 2)
                if len(parts) >= 3:
                    return parts[2].lstrip("\n")
            return text
        except Exception as e:
            return f"ERROR: skill_not_found: {e}"
