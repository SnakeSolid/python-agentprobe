"""Access to scenario ``tool_vars`` from within tool implementations."""

from __future__ import annotations

import json
import os
from typing import Any, cast


def get_tool_vars() -> dict[str, dict[str, Any]]:
    raw = os.environ.get("AGENTPROBE_TOOL_VARS")
    if not raw:
        return {}
    try:
        return cast(dict[str, dict[str, Any]], json.loads(raw))
    except json.JSONDecodeError:
        return {}
