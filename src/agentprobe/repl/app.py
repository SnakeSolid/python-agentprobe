from __future__ import annotations

import asyncio
from pathlib import Path

from agentprobe import __version__
from agentprobe.agent.observer import NoOpObserver, SessionCtx
from agentprobe.agent.orchestrator import Orchestrator
from agentprobe.agent.subagent import SubagentSpawner
from agentprobe.agent.ui import ConsoleUi
from agentprobe.config import Config, load_config
from agentprobe.llm.client import LLMClient
from agentprobe.llm.types import Message
from agentprobe.logging.console import Console
from agentprobe.logging.yaml_logger import YamlLogger, new_session_id
from agentprobe.prompt.builder import PromptBuilder
from agentprobe.repl.commands import handle_command
from agentprobe.skills.loader import SkillLoader
from agentprobe.tools.client import MCPToolClient


class ReplSession:
    def __init__(self, cfg: Config, config_path: Path):
        self.cfg = cfg
        self.config_path = config_path
        self.console = Console(
            level=cfg.logging.console_level,
            color=cfg.logging.color,
            truncate=cfg.logging.console_truncate_chars,
        )
        self.ui: ConsoleUi | None = None
        self.tools: MCPToolClient | None = None
        self.skills: SkillLoader | None = None
        self.llm: LLMClient | None = None
        self.logger: YamlLogger | None = None
        self.orchestrator: Orchestrator | None = None
        self.messages: list[Message] = []
        self.ctx = SessionCtx()
        self.spawner: SubagentSpawner | None = None
        self._started_at = 0.0

    async def start(self) -> None:
        await self._build_session()
        await self._print_banner()

    async def stop(self) -> None:
        if self.llm is not None:
            await self.llm.aclose()
        if self.tools is not None:
            await self.tools.close()
        if self.logger is not None:
            self.logger.close()

    async def _build_session(self) -> None:
        import time

        self._started_at = time.monotonic()
        self.ctx = SessionCtx()
        session_id = new_session_id("repl")
        log_path = self.cfg.app.log_dir / f"{session_id}.yaml"
        self.logger = YamlLogger(log_path, session_id=session_id)
        self.logger.log(
            "session_start",
            mode="repl",
            model=self.cfg.models.main.model,
            limits=self.cfg.limits.main.as_dict(),
            tool_transport=self.cfg.app.tool_transport,
            tool_vars_keys=[],
        )

        if self.tools is None:
            self.tools = await MCPToolClient.start(
                transport=self.cfg.app.tool_transport,
                config_path=self.config_path,
                tool_vars=self.cfg.app.tool_vars,
                workspace=self.cfg.app.workspace,
                docs_dir=self.cfg.app.docs_dir,
                skills_dir=self.cfg.app.skills_dir,
            )

        self.skills = SkillLoader(self.cfg.app.skills_dir)
        prompt = PromptBuilder(self.cfg.app.prompt_file, self.cfg.app.memory_file, self.skills)
        system_text = prompt.build()

        self.llm = LLMClient(self.cfg.models.main)
        enabled_tools = self.cfg.tools.enabled or None

        spawner = None
        if self.cfg.models.subagent is not None and (
            enabled_tools is None or "spawn_agent" in enabled_tools
        ):
            sp = self.cfg.app.subagent_prompt_file or self.cfg.app.prompt_file
            spawner = SubagentSpawner(
                cfg=self.cfg,
                parent_session_id=session_id,
                system_text=sp.read_text(encoding="utf-8"),
                tools_client=self.tools,
                logger=self.logger,
                enabled_tools=self.cfg.tools.enabled,
                console=self.console,
            )
        self.spawner = spawner

        self.ui = ConsoleUi(self.console, mode="repl")
        self.orchestrator = Orchestrator(
            llm=self.llm,
            tools=self.tools,
            observer=NoOpObserver(),
            logger=self.logger,
            limits=self.cfg.limits.main,
            ui=self.ui,
            spawner=spawner,
            is_repl=True,
            enabled_tools=enabled_tools,
        )
        self.messages = [Message(role="system", content=system_text)]

    async def _print_banner(self) -> None:
        assert self.logger is not None
        cfg = self.cfg
        main = cfg.models.main
        sub = cfg.models.subagent
        sub_line = (
            f"{sub.model}  (spawn_agent: enabled)" if sub else "(disabled; spawn_agent not offered)"
        )
        skills_names = self.skills.skill_names() if self.skills else []
        docs = sorted(p.name for p in cfg.app.docs_dir.glob("*.md"))
        enabled = await self._tool_names()
        self.console.plain(f"agentprobe {__version__}")
        self.console.plain(f"model:     {main.model}  @ {main.endpoint}  (proxy: {main.proxy or 'none'})")
        self.console.plain(f"subagent:  {sub_line}")
        self.console.plain(f"workspace: {cfg.app.workspace}")
        self.console.plain(f"docs:      {cfg.app.docs_dir}  ({len(docs)} files: {', '.join(docs)})")
        self.console.plain(
            f"skills:    {cfg.app.skills_dir}  ({len(skills_names)} skill{'' if len(skills_names) == 1 else 's'}: {', '.join(skills_names) or 'none'})"
        )
        self.console.plain(f"tools:     {len(enabled)} enabled: {', '.join(enabled)}")
        self.console.plain(f"log:       {self.logger.path}")
        self.console.plain("type /help for commands, Ctrl-D to exit.")
        self.console.plain()

    async def loop(self) -> None:
        while True:
            try:
                line = self._read_input()
            except EOFError:
                self.console.plain()
                return
            except KeyboardInterrupt:
                self.console.plain("^C")
                continue
            if not line.strip():
                continue
            if line.startswith("/"):
                exit_repl = await handle_command(line, self)
                if exit_repl:
                    return
                continue
            await self._run_turn(line)

    def _read_input(self) -> str:
        buf = input(">>> ")
        while buf.endswith("\\"):
            buf = buf[:-1] + "\n" + input("... ")
        return buf

    async def _run_turn(self, user_input: str) -> None:
        import time
        assert self.orchestrator is not None

        # The `>>> ` prompt already echoes the user input; no separate [user]
        # line is needed (spec 2.1.x). Assistant streaming, tool lines and
        # verbose metadata are rendered by the ConsoleUi inside the loop.
        t0 = time.monotonic()
        partial = False
        try:
            await self.orchestrator.turn(self.messages, user_input, self.ctx)
        except asyncio.CancelledError:
            partial = True
        except KeyboardInterrupt:
            partial = True
            self.console.interrupt("turn cancelled by user")
        except Exception as e:
            partial = True
            self.console.error(f"{type(e).__name__}: {e}")
            self.console.error("turn aborted; history preserved. Continue, retry, or /reset.")

        elapsed = (time.monotonic() - t0) * 1000
        tok_in, tok_out = self.ctx.tokens_in, self.ctx.tokens_out
        tok_total = tok_in + tok_out
        suffix = " (partial)" if partial else ""
        self.console.tokens(
            f"in={tok_in} out={tok_out}{suffix} | turn {self._fmt_duration(elapsed)} | total {self._fmt_duration((time.monotonic() - self._started_at) * 1000)}"
        )
        # Context warning (REPL applies no limits, only a warning)
        limit = self.cfg.limits.main.max_context_tokens
        if limit and tok_total > 0 and tok_total / limit >= 0.9:
            self.console.warning(
                f"context usage: {tok_total} / {limit} tokens ({tok_total / limit * 100:.1f}%)"
            )

    async def reset(self) -> None:
        self.cfg = load_config(self.config_path)
        await self._build_session()
        assert self.logger is not None
        self.console.info(f"new session: {self.logger.session_id}")
        self.console.info(f"log: {self.logger.path}")

    async def reload(self) -> None:
        try:
            new_cfg = load_config(self.config_path)
        except Exception as e:
            self.console.error(f"config error: {e}")
            self.console.error("keeping previous configuration; nothing changed")
            return
        self.cfg = new_cfg
        old_tools = self.tools
        await self._rebuild_with_preserved_history()
        if old_tools is not None:
            await old_tools.close()
        self.console.info(f"prompt reloaded: {self.cfg.app.prompt_file}")
        if self.skills is not None:
            self.console.info(f"skills rescanned: {len(self.skills.skill_names())} skill(s)")
        self.console.info(
            f"system message updated; history preserved ({self.ctx.turn} turns, {len(self.messages)} messages)"
        )

    async def _rebuild_with_preserved_history(self) -> None:
        assert self.logger is not None
        # Re-register tools, rebuild system message at messages[0], keep history.
        self.tools = await MCPToolClient.start(
            transport=self.cfg.app.tool_transport,
            config_path=self.config_path,
            tool_vars=self.cfg.app.tool_vars,
            workspace=self.cfg.app.workspace,
            docs_dir=self.cfg.app.docs_dir,
            skills_dir=self.cfg.app.skills_dir,
        )
        self.skills = SkillLoader(self.cfg.app.skills_dir)
        prompt = PromptBuilder(self.cfg.app.prompt_file, self.cfg.app.memory_file, self.skills)
        system_text = prompt.build()
        if self.messages:
            self.messages[0] = Message(role="system", content=system_text)
        else:
            self.messages = [Message(role="system", content=system_text)]
        enabled_tools = self.cfg.tools.enabled or None
        self.llm = LLMClient(self.cfg.models.main)
        self.ui = ConsoleUi(self.console, mode="repl")
        self.orchestrator = Orchestrator(
            llm=self.llm,
            tools=self.tools,
            observer=NoOpObserver(),
            logger=self.logger,
            limits=self.cfg.limits.main,
            ui=self.ui,
            spawner=self.spawner,
            is_repl=True,
            enabled_tools=enabled_tools,
        )

    async def tools_cmd(self) -> None:
        names = await self._tool_names()
        self.console.plain(f"{len(names)} tools enabled:")
        for n in names:
            self.console.plain(f"  {n}")

    async def stats_cmd(self) -> None:
        import time
        assert self.logger is not None

        self.console.plain(f"session:     {self.logger.session_id}")
        self.console.plain(f"duration:    {self._fmt_duration((time.monotonic() - self._started_at) * 1000)}")
        self.console.plain(f"turns:       {self.ctx.turn}")
        self.console.plain(f"agent msgs:  {self.ctx.agent_messages}")
        self.console.plain(
            f"tokens:      in={self.ctx.tokens_in}  out={self.ctx.tokens_out}  total={self.ctx.tokens_total}"
        )
        self.console.plain(f"context max: {self.ctx.context_tokens_max}")
        self.console.plain("tools:")
        for name, count in self.ctx.tools_histogram.items():
            self.console.plain(f"  {name}:        {count}")
        self.console.plain(f"log:         {self.logger.path}")

    async def model_cmd(self) -> None:
        main = self.cfg.models.main
        self.console.plain(f"main:     {main.model} @ {main.endpoint} (temperature={main.temperature})")
        sub = self.cfg.models.subagent
        if sub:
            self.console.plain(f"subagent: {sub.model} @ {sub.endpoint} (temperature={sub.temperature})")
        else:
            self.console.plain("subagent: (disabled; spawn_agent not offered)")

    async def memory_cmd(self) -> None:
        mem = self.cfg.app.memory_file
        if not mem.exists():
            self.console.plain("(no MEMORY.md)")
            return
        self.console.plain(f"# MEMORY.md\n\n{mem.read_text(encoding='utf-8').rstrip()}")

    @staticmethod
    def _fmt_duration(ms: float) -> str:
        secs = ms / 1000.0
        if secs < 60:
            return f"{secs:.2f}s"
        m = int(secs // 60)
        s = secs - m * 60
        return f"{m}m{s:.1f}s"


    async def _tool_names(self) -> list[str]:
        if self.tools is None:
            return []
        enabled = self.cfg.tools.enabled or None
        schemas = await self.tools.schemas(enabled=enabled)
        return [s["function"]["name"] for s in schemas]


async def run_repl(cfg: Config, config_path: Path) -> None:
    app = ReplSession(cfg, config_path)
    try:
        await app.start()
        await app.loop()
    finally:
        await app.stop()
