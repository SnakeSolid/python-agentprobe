from __future__ import annotations

import os
from pathlib import Path

from agentprobe.errors import SandboxViolation


class Sandbox:
    """Constrains all path resolution to a single root directory."""

    def __init__(self, root: Path):
        self.root = root.resolve()

    @classmethod
    def from_env(cls, env_var: str = "AGENTPROBE_WORKSPACE") -> Sandbox:
        raw = os.environ.get(env_var)
        if not raw:
            raise SandboxViolation(f"{env_var} is not set")
        return cls(Path(raw))

    def resolve(self, user_path: str) -> Path:
        candidate = (self.root / user_path).resolve()
        try:
            if Path(os.path.commonpath([self.root, candidate])) != self.root:
                raise SandboxViolation(f"path escapes root: {user_path}")
        except ValueError:  # different drives (Windows) or unresolvable
            raise SandboxViolation(f"path escapes root: {user_path}")
        return candidate
