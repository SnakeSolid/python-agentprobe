from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from agentprobe.tools.sandbox import Sandbox


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="read_doc",
        description=(
            "Read a bundled markdown documentation stub from docs/ by basename "
            "(without .md). Paths escaping docs_dir are rejected."
        ),
    )
    async def read_doc(
        name: Annotated[str, Field(description="Document basename without the .md extension.", min_length=1, max_length=256)],
    ) -> str:
        try:
            root = Sandbox(Path(os.environ["AGENTPROBE_DOCS_DIR"]))
            target = root.resolve(f"{name}.md")
            if not target.exists():
                return f"ERROR: doc_not_found: {name}"
            return target.read_text(encoding="utf-8")
        except Exception as e:
            return f"ERROR: doc_error: {e}"
