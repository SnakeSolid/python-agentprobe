# Appendix: Code Snippets and Examples

## E. Sandbox

### E.1. `src/agentprobe/tools/sandbox.py`

```python
from __future__ import annotations
import os
from pathlib import Path

from agentprobe.errors import SandboxViolation


class Sandbox:
    """Constrains all path resolution to a single root directory."""

    def __init__(self, root: Path):
        self.root = root.resolve()

    @classmethod
    def from_env(cls, env_var: str = "AGENTPROBE_WORKSPACE") -> "Sandbox":
        raw = os.environ.get(env_var)
        if not raw:
            raise SandboxViolation(f"{env_var} is not set")
        return cls(Path(raw))

    def resolve(self, user_path: str) -> Path:
        candidate = (self.root / user_path).resolve()
        # commonpath ensures `candidate` is inside `self.root`
        try:
            if Path(os.path.commonpath([self.root, candidate])) != self.root:
                raise SandboxViolation(f"path escapes root: {user_path}")
        except ValueError:  # different drives (Windows) or unresolvable
            raise SandboxViolation(f"path escapes root: {user_path}")
        return candidate
```

**Test sketch:**

```python
def test_sandbox_escapes(tmp_path):
    sb = Sandbox(tmp_path)
    with pytest.raises(SandboxViolation):
        sb.resolve("../../etc/passwd")

def test_sandbox_symlink_escapes(tmp_path):
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("x")
    (tmp_path / "link").symlink_to(outside)
    sb = Sandbox(tmp_path)
    with pytest.raises(SandboxViolation):
        sb.resolve("link")
```

---

