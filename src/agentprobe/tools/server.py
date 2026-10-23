from __future__ import annotations

import importlib
import importlib.util
import os
import pkgutil
from pathlib import Path
from types import ModuleType

from mcp.server.fastmcp import FastMCP

from agentprobe.errors import ConfigError

_BUILTIN_PREFIX = "agentprobe.tools.builtin"


def build_server(*module_dirs: Path | None) -> FastMCP:
    """Build a FastMCP server, importing all tool modules from given directories."""
    mcp = FastMCP("agentprobe-tools")

    for d in module_dirs:
        if d is None or not d.exists():
            continue
        for info in pkgutil.iter_modules([str(d)]):
            if info.name.startswith("_"):
                continue
            mod = _import_module(d, info.name)
            if not hasattr(mod, "register"):
                raise ConfigError(f"{d / info.name}.py has no register(mcp)")
            mod.register(mcp)

    return mcp


def _import_module(d: Path, name: str) -> ModuleType:
    # Builtin tools are a proper subpackage; import them by qualified name so
    # relative imports inside them keep working.
    if d.name == "builtin" and d.parent.name == "tools":
        return importlib.import_module(f"{_BUILTIN_PREFIX}.{name}")
    return _import_from_path(d, name)


def _import_from_path(d: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, d / f"{name}.py")
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def cli_main() -> None:
    """Entry point for `python -m agentprobe.tools.server` (stdio transport)."""
    from agentprobe.config import load_config
    from agentprobe.logging.console import configure_logging

    configure_logging()
    cfg_path = os.environ["AGENTPROBE_CONFIG"]
    cfg = load_config(Path(cfg_path))
    dirs = [Path(__file__).parent / "builtin"]
    if cfg.app.user_tools_dir:
        dirs.append(cfg.app.user_tools_dir)
    mcp = build_server(*dirs)
    mcp.run(transport="stdio")
