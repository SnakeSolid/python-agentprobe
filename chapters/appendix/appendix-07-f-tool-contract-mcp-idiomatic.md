# Appendix: Code Snippets and Examples

## F. Tool contract (MCP, idiomatic)

### F.1. Tool module convention

- One file per tool under `tools/builtin/` or `user_tools_dir/`.
- Each file defines `register(mcp: FastMCP) -> None`.
- Parameters use `Annotated[T, Field(...)]` so FastMCP generates a schema with per-field descriptions and constraints.
- Context (workspace, `tool_vars`) is read from environment variables set by the runner (`AGENTPROBE_WORKSPACE`, `AGENTPROBE_TOOL_VARS`).
- Return a `str`; use the `ERROR: <code>: <msg>` prefix for business errors.

### F.2. `src/agentprobe/tools/server.py`

```python
from __future__ import annotations
import importlib, pkgutil
from pathlib import Path
from mcp.server.fastmcp import FastMCP

from agentprobe.errors import ConfigError


def build_server(*module_dirs: Path) -> FastMCP:
    """Build a FastMCP server, importing all tool modules from given directories."""
    mcp = FastMCP("agentprobe-tools")

    for d in module_dirs:
        if d is None:
            continue
        for info in pkgutil.iter_modules([str(d)]):
            if info.name.startswith("_"):
                continue
            mod = importlib.import_module(f"{info.module_finder.path}/{info.name}"
                                          .replace("/", ".")) if False else \
                  __import_from_path(d, info.name)
            if not hasattr(mod, "register"):
                raise ConfigError(f"{d / info.name}.py has no register(mcp)")
            mod.register(mcp)

    return mcp


def __import_from_path(d: Path, name: str):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, d / f"{name}.py")
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def cli_main() -> None:
    """Entry point for `python -m agentprobe.tools.server` (stdio transport)."""
    from agentprobe.config import load_config
    import os
    cfg_path = os.environ["AGENTPROBE_CONFIG"]
    cfg = load_config(Path(cfg_path))
    dirs = [Path(__file__).parent / "builtin"]
    if cfg.app.user_tools_dir:
        dirs.append(cfg.app.user_tools_dir)
    mcp = build_server(*dirs)
    mcp.run(transport="stdio")
```

**Note:** The exact import mechanism depends on whether tools are shipped as a Python package or loose files. The snippet above uses `spec_from_file_location` for loose files. If you ship tools as a subpackage (`agentprobe.tools.builtin`), simplify to `importlib.import_module(f"agentprobe.tools.builtin.{name}")`.

---

