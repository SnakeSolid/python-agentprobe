from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentprobe.repl.app import ReplSession


def help_text() -> str:
    return (
        "commands:\n"
        "  /help              show this help\n"
        "  /exit, /quit       exit the REPL\n"
        "  /reset             start a new session (clears history; MEMORY.md untouched)\n"
        "  /reload            re-read config, prompt, skills; re-register tools\n"
        "  /tools             list enabled tools with short descriptions\n"
        "  /stats             session statistics\n"
        "  /log               path to the current log file\n"
        "  /model             show main and subagent models\n"
        "  /memory            show MEMORY.md contents"
    )


async def handle_command(line: str, app: ReplSession) -> bool:
    """Handle a slash command. Returns True if the REPL should exit."""
    cmd = line.strip().split()[0] if line.strip() else ""
    if cmd in ("/help", "/?"):
        app.console.plain(help_text())
    elif cmd in ("/exit", "/quit"):
        return True
    elif cmd == "/reset":
        await app.reset()
    elif cmd == "/reload":
        await app.reload()
    elif cmd == "/tools":
        await app.tools_cmd()
    elif cmd == "/stats":
        await app.stats_cmd()
    elif cmd == "/log":
        assert app.logger is not None
        app.console.plain(str(app.logger.path))
    elif cmd == "/model":
        await app.model_cmd()
    elif cmd == "/memory":
        await app.memory_cmd()
    else:
        app.console.error(f"unknown command: {line.strip()} (try /help)")
    return False
