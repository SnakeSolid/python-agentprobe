from __future__ import annotations

import json
import os
from typing import Any


def get_tool_vars() -> dict[str, dict[str, Any]]:
    raw = os.environ.get("AGENTPROBE_TOOL_VARS")
    if not raw:
        return {}
    try:
        return json.loads(raw)  # type: ignore[no-any-return]
    except json.JSONDecodeError:
        return {}
