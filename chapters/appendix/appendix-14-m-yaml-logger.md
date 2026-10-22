# Appendix: Code Snippets and Examples

## M. YAML logger

### M.1. `src/agentprobe/logging/yaml_logger.py`

```python
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import yaml


class YamlLogger:
    def __init__(self, path: Path, session_id: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.session_id = session_id
        self._fp = path.open("a", encoding="utf-8")

    def log(self, event: str, **kwargs: Any) -> None:
        payload = {
            "event": event,
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "session_id": self.session_id,
            **kwargs,
        }
        self._fp.write("---\n")
        self._fp.write(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True))
        self._fp.flush()

    def close(self) -> None:
        self._fp.close()


def new_session_id(mode: str) -> str:
    import secrets
    return f"{mode}_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}_{secrets.token_hex(2)}"


def new_run_id() -> str:
    import secrets
    return f"{datetime.now(timezone.utc):%Y%m%d_%H%M%S}_{secrets.token_hex(2)}"
```

---

