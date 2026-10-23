# Appendix: Code Snippets and Examples

## H. `tool_vars` access

### H.1. `src/agentprobe/tools/vars.py`

```python
import json, os
from typing import Any


def get_tool_vars() -> dict[str, dict[str, Any]]:
    raw = os.environ.get("AGENTPROBE_TOOL_VARS")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}
```

The runner sets `AGENTPROBE_TOOL_VARS=<json>` when spawning the MCP subprocess (for `stdio` transport) or via `os.environ` for `in_memory` transport.

---

