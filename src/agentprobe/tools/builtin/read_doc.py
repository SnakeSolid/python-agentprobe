"""Read a bundled documentation stub from `docs_dir`."""

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
            "Read a bundled documentation stub by name. `name` is the file basename "
            "without the `.md` extension. Fails if the doc is absent."
        ),
    )
    async def read_doc(
        name: Annotated[str, Field(
            description="Doc basename without the `.md` extension.",
            min_length=1, max_length=256,
        )],
    ) -> str:
        try:
            root = Path(os.environ["AGENTPROBE_DOCS_DIR"])
            sb = Sandbox(root)
            target = sb.resolve(f"{name}.md")
            return target.read_text(encoding="utf-8")
        except Exception as e:
            return f"ERROR: doc_not_found: {e}"
