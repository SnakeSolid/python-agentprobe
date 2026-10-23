"""Interactive REPL mode."""

from __future__ import annotations

from pathlib import Path

from agentprobe.agent.observer import NoOpObserver, SessionCtx
from agentprobe.agent.orchestrator import Orchestrator
from agentprobe.config import Config, load_config
from agentprobe.llm.client import LLMClient
from agentprobe.llm.types import Message
from agentprobe.logging.console import Console
from agentprobe.logging.yaml_logger import YamlLogger, new_session_id
from agentprobe.prompt.builder import PromptBuilder
from agentprobe.skills.loader import SkillLoader
from agentprobe.tools.client import MCPToolClient


class ReplSession:
    def __init__(self, cfg: Config, config_path: Path, console: Console, session_id: str):
        self.cfg = cfg
        self.config_path = config_path
        self.console = console
        self.session_id = session_id
        self.logger = YamlLogger(cfg.app.log_dir / f"{session_id}.yaml", session_id)
        self.skills = SkillLoader(cfg.app.skills_dir)
        self.prompt = PromptBuilder(
            cfg.app.prompt_file, cfg.app.memory_file, self.skills
        )
        self.tools: MCPToolClient | None = None
        self.llm: LLMClient | None = None
        self.messages: list[Message] = []
        self.ctx = SessionCtx()
        import time

        self._t0 = time.monotonic()
        self._turns = 0

    async def start(self) -> None:
        self.tools = await MCPToolClient.start(
            cfg=self.cfg,
            config_path=self.config_path,
            tool_vars={},
            workspace=self.cfg.app.workspace,
        )
        self.llm = LLMClient(self.cfg.models.main)
        self.messages = [Message(role="system", content=self.prompt.build())]
        self.ctx = SessionCtx()
        self.logger.log("session_start", mode="repl", model=self.cfg.models.main.model)

    @property
    def orchestrator(self) -> Orchestrator:
        assert self.llm is not None  # set in start()
        assert self.tools is not None  # set in start()
        return Orchestrator(
            llm=self.llm,
            tools=self.tools,
            observer=NoOpObserver(),
            logger=self.logger,
            limits=self.cfg.limits.main,
            spawner=None,
            is_repl=True,
            console=self.console,
            system_refresh=self.prompt.build,
        )

    async def close(self) -> None:
        if self.llm is not None:
            await self.llm.aclose()
        if self.tools is not None:
            await self.tools.close()
        self.logger.close()

    async def send(self, text: str) -> None:
        self._turns += 1
        await self.orchestrator.turn(self.messages, text, self.ctx)

    async def reload(self) -> None:
        try:
            new_cfg = load_config(self.config_path)
        except Exception as e:
            self.console.error(f"reload failed: {e}; keeping current config")
            return
        # Keep existing session objects, update references.
        self.cfg = new_cfg
        self.skills = SkillLoader(new_cfg.app.skills_dir)
        self.prompt = PromptBuilder(
            new_cfg.app.prompt_file, new_cfg.app.memory_file, self.skills
        )
        if self.messages:
            self.messages[0] = Message(role="system", content=self.prompt.build())
        self.console.info("reloaded")


async def run_repl(cfg: Config, config_path: Path) -> None:
    console = Console(
        level=cfg.logging.console_level, color=cfg.logging.color,
        truncate=cfg.logging.console_truncate_chars,
    )
    session = ReplSession(cfg, config_path, console, new_session_id("repl"))
    await session.start()
    try:
        while True:
            try:
                line = input(">>> ")
            except EOFError:
                console.info("")
                break
            except KeyboardInterrupt:
                console.info("")
                continue

            if not line:
                continue
            if line.startswith("/"):
                if await _handle_command(session, line):
                    break
                continue

            while line.endswith("\\"):
                line = line[:-1]
                try:
                    line += "\n" + input("... ")
                except EOFError:
                    break
                except KeyboardInterrupt:
                    break

            try:
                await session.send(line)
            except KeyboardInterrupt:
                console.info("\n(interrupted)")
            except Exception as e:
                console.error(f"error: {e}")
    finally:
        await session.close()


async def _handle_command(session: ReplSession, line: str) -> bool:
    cmd = line.split()[0].lower()
    if cmd in ("/exit", "/quit"):
        return True
    if cmd == "/help":
        print(
            "/help /tools /stats /log /model /memory /reset /reload /exit"
        )
        return False
    if cmd == "/tools":
        assert session.tools is not None  # set in start()
        schemas = await session.tools.schemas()
        for s in schemas:
            print(f"{s['function']['name']}: {s['function']['description']}")
        return False
    if cmd == "/stats":
        print(
            f"turns={session.ctx.turn} agent_messages={session.ctx.agent_messages} "
            f"tools={len(session.ctx.tools_histogram)} "
            f"tokens={session.ctx.usage_total}"
        )
        return False
    if cmd == "/log":
        print(session.logger.path)
        return False
    if cmd == "/model":
        print(f"main: {session.cfg.models.main.model}")
        if session.cfg.models.subagent:
            print(f"subagent: {session.cfg.models.subagent.model}")
        else:
            print("subagent: disabled")
        return False
    if cmd == "/memory":
        print(session.prompt.memory_file.read_text(encoding="utf-8")
              if session.prompt.memory_file.exists() else "(empty)")
        return False
    if cmd == "/reset":
        await session.close()
        session_id = new_session_id("repl")
        replacement = ReplSession(session.cfg, session.config_path, session.console, session_id)
        session.__dict__.clear()
        session.__dict__.update(replacement.__dict__)
        await session.start()
        print("session reset")
        return False
    if cmd == "/reload":
        await session.reload()
        return False
    print(f"unknown command: {cmd}")
    return False
