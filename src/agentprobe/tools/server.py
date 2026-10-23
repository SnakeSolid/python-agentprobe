"""FastMCP server that aggregates all tool modules.

Each tool module lives in its own file and exposes ``register(mcp)``. This module
also provides the ``stdio`` transport entry point used by ``MCPToolClient``.
"""

from __future__ import annotations

import importlib
import os
import types
from pathlib import Path
from typing import TYPE_CHECKING

from mcp.server.fastmcp import FastMCP

from agentprobe.errors import ConfigError

if TYPE_CHECKING:
    from agentprobe.config import Config


def build_server(include_user: bool = True) -> FastMCP:
    """Build a FastMCP server, importing builtin and (optionally) user tool modules."""
    mcp = FastMCP("agentprobe-tools")
    _load_package_modules(mcp, "agentprobe.tools.builtin")

    if include_user:
        cfg = _load_config_or_none()
        if cfg is not None and cfg.app.user_tools_dir:
            _load_dir_modules(mcp, cfg.app.user_tools_dir)
    return mcp


def _load_package_modules(mcp: FastMCP, package: str) -> None:
    import pkgutil

    pkg = importlib.import_module(package)
    for info in pkgutil.iter_modules(pkg.__path__):
        if info.name.startswith("_"):
            continue
        mod = importlib.import_module(f"{package}.{info.name}")
        _register(mcp, mod, info.name)


def _load_dir_modules(mcp: FastMCP, directory: Path) -> None:
    import pkgutil

    for info in pkgutil.iter_modules([str(directory)]):
        if info.name.startswith("_"):
            continue
        mod = _import_from_path(directory, info.name)
        _register(mcp, mod, info.name)


def _import_from_path(directory: Path, name: str) -> types.ModuleType:
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, directory / f"{name}.py")
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _register(mcp: FastMCP, mod: types.ModuleType, name: str) -> None:
    if not hasattr(mod, "register"):
        raise ConfigError(f"{name}.py has no register(mcp)")
    mod.register(mcp)


def _load_config_or_none() -> Config | None:
    try:
        from agentprobe.config import load_config

        cfg_path = os.environ.get("AGENTPROBE_CONFIG")
        if not cfg_path:
            return None
        return load_config(Path(cfg_path))
    except Exception:
        return None


def cli_main() -> None:
    """Entry point for `python -m agentprobe.tools.server` (stdio transport)."""
    cfg_path = os.environ["AGENTPROBE_CONFIG"]
    from agentprobe.config import load_config

    _ = load_config(Path(cfg_path))
    mcp = build_server(include_user=True)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    cli_main()
