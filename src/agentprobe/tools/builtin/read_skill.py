"""Load the body of a skill (strip YAML frontmatter)."""

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
        description="Load the body of a skill (`<skills_dir>/<name>/SKILL.md`). "
                    "YAML frontmatter is stripped.",
    )
    async def read_skill(
        name: Annotated[str, Field(
            description="Skill folder name.", min_length=1, max_length=128,
        )],
    ) -> str:
        try:
            root = Path(os.environ["AGENTPROBE_SKILLS_DIR"])
            sb = Sandbox(root)
            target = sb.resolve(f"{name}/SKILL.md")
            text = target.read_text(encoding="utf-8")
            if text.startswith("---"):
                parts = text.split("---", 2)
                if len(parts) >= 3:
                    return parts[2].lstrip("\n")
            return text
        except Exception as e:
            return f"ERROR: skill_not_found: {e}"
