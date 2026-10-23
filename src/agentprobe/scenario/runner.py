from __future__ import annotations

import asyncio
import glob
import re
import shutil
import time
import types
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from agentprobe.agent.observer import ScenarioObserver, SessionCtx
from agentprobe.agent.orchestrator import Orchestrator
from agentprobe.agent.subagent import SubagentSpawner
from agentprobe.agent.ui import ConsoleUi
from agentprobe.config import Config
from agentprobe.errors import ConfigError, LimitExceeded, LLMError, ReplayError, ScenarioAbort
from agentprobe.llm.client import LLMClient
from agentprobe.llm.fixture import Fixture
from agentprobe.llm.types import Message
from agentprobe.logging.console import Console
from agentprobe.logging.yaml_logger import YamlLogger, new_run_id, new_session_id
from agentprobe.prompt.builder import PromptBuilder
from agentprobe.scenario.schema import Scenario, load_scenario
from agentprobe.skills.loader import SkillLoader
from agentprobe.tools.client import MCPToolClient

SEVERITY = {5: 5, 4: 4, 3: 3, 2: 2, 1: 1, 0: 0}


@dataclass
class ScenarioResult:
    name: str
    index: int
    status: str  # PASS | FAIL | LIMIT | ERROR | SKIP
    exit_code: int | None
    reason: str | None
    duration_ms: float
    turns: int = 0
    agent_messages: int = 0
    usage: dict[str, int] | None = None
    tools_histogram: dict[str, int] = field(default_factory=dict)
    checks: dict[str, Any] = field(default_factory=dict)
    log: str | None = None
    workspace: str | None = None


class Runner:
    def __init__(self, cfg: Config, args: types.SimpleNamespace):
        self.cfg = cfg
        self.args = args
        self.run_id = new_run_id()
        self.run_dir = cfg.app.log_dir / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._run_fp = (self.run_dir / "run.yaml").open("a", encoding="utf-8")
        self.console = Console(
            level=cfg.logging.console_level,
            color=cfg.logging.color,
            truncate=cfg.logging.console_truncate_chars,
        )
        self._t0 = time.monotonic()

    async def _run_log(self, event: str, **kw: Any) -> None:
        async with self._lock:
            payload = {
                "event": event,
                "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
                "run_id": self.run_id,
                **kw,
            }
            self._run_fp.write("---\n")
            self._run_fp.write(yaml.safe_dump(payload, sort_keys=False))
            self._run_fp.flush()

    async def run_all(self) -> int:
        try:
            scenarios = self._discover_scenarios()
        except ConfigError as e:
            self.console.error(f"scenario validation failed: {e}")
            self.console.error("no scenarios executed")
            await self._run_log("run_start", scenarios_total=0, parallel=self.args.parallel)
            await self._run_log("run_end", exit_code=2, passed=0, failed=0, errored=0, aborted=0)
            return 2

        await self._run_log(
            "run_start",
            scenarios_total=len(scenarios),
            parallel=self.args.parallel,
            workspace_mode=self.args.workspace_mode,
            record=self.args.record,
            replay=self.args.replay,
            filter=self.args.filter,
        )

        if self.args.workspace_mode == "shared":
            self.console.warning(
                "workspace-mode=shared: scenarios share the original workspace and may affect each other"
            )

        self.console.run(
            self.run_id,
            f"starting {len(scenarios)} scenarios (mode=headless, workspace={self.args.workspace_mode}"
            f"{', parallel=' + str(self.args.parallel) if self.args.parallel > 1 else ''}"
            f"{', fail_fast=on' if self.args.fail_fast else ''})",
        )

        results: list[ScenarioResult] = []
        aborted = False
        if self.args.parallel <= 1:
            for i, sc in enumerate(scenarios, start=1):
                r = await self._run_one(sc, i)
                results.append(r)
                if self.args.fail_fast and r.exit_code not in (0, None):
                    remaining = list(enumerate(scenarios[i:], start=i + 1))
                    for j, sc2 in remaining:
                        results.append(self._skip_result(sc2, j))
                    self.console.run(
                        self.run_id,
                        f"aborted after 1 failure ({len(scenarios) - len(remaining)} launched, {len(remaining)} skipped)",
                    )
                    aborted = True
                    break
            if not aborted:
                self._print_done(results)
        else:
            sem = asyncio.Semaphore(self.args.parallel)

            async def worker(i: int, sc: Scenario) -> ScenarioResult:
                async with sem:
                    return await self._run_one(sc, i)

            results = list(
                await asyncio.gather(*(worker(i, s) for i, s in enumerate(scenarios, start=1)))
            )
            self._print_done(results)

        # Re-sort to launch order for the summary
        results.sort(key=lambda r: r.index)
        exit_code = self._aggregate_exit(results)
        self._write_summary(results, exit_code)
        await self._run_log(
            "run_end",
            exit_code=exit_code,
            passed=sum(1 for r in results if r.status == "PASS"),
            failed=sum(1 for r in results if r.status == "FAIL"),
            errored=sum(1 for r in results if r.status == "ERROR"),
            aborted=sum(1 for r in results if r.status == "SKIP"),
        )
        self._run_fp.close()
        return exit_code

    def _print_done(self, results: list[ScenarioResult]) -> None:
        passed = sum(1 for r in results if r.status == "PASS")
        failed = sum(1 for r in results if r.status == "FAIL")
        limit = sum(1 for r in results if r.status == "LIMIT")
        errored = sum(1 for r in results if r.status == "ERROR")
        skipped = sum(1 for r in results if r.status == "SKIP")
        bits = []
        if passed:
            bits.append(f"{passed} passed")
        if failed:
            bits.append(f"{failed} failed")
        if limit:
            bits.append(f"{limit} limit")
        if errored:
            bits.append(f"{errored} error")
        if skipped:
            bits.append(f"{skipped} skipped")
        self.console.run(
            self.run_id,
            f"done: {', '.join(bits) or 'no scenarios'} ({self._fmt_duration((time.monotonic() - self._t0) * 1000)})",
        )

    async def _run_one(self, scenario: Scenario, index: int) -> ScenarioResult:
        t0 = time.monotonic()
        session_id = new_session_id("headless")
        log_path = self.run_dir / f"{scenario.name}.yaml"
        logger = YamlLogger(log_path, session_id=session_id)
        logger.log(
            "session_start",
            mode="headless",
            scenario=scenario.name,
            model=self.cfg.models.main.model,
            limits=self.cfg.limits.main.as_dict(),
            tool_transport=self.cfg.app.tool_transport,
            tool_vars_keys=list(scenario.tool_vars.keys()),
        )
        self.console.scenario(scenario.name, "started")
        await self._run_log(
            "scenario_start", scenario_name=scenario.name, index=index, pid=None
        )

        # Workspace isolation
        ws = self._prepare_workspace(scenario.name)
        memory_file = self._prepare_memory(ws)

        fixture = None
        if self.args.record:
            try:
                fixture = Fixture(self._fixture_path(scenario.name), mode="record")
            except Exception as e:
                logger.log("scenario_abort", reason=str(e), exit_code=2)
                logger.close()
                return ScenarioResult(
                    name=scenario.name, index=index, status="ERROR", exit_code=2,
                    reason=str(e), duration_ms=(time.monotonic() - t0) * 1000, log=str(log_path),
                )
        elif self.args.replay:
            try:
                fixture = Fixture(self._fixture_path(scenario.name), mode="replay")
            except ReplayError as e:
                logger.log("scenario_abort", reason=str(e), exit_code=4)
                logger.close()
                await self._run_log(
                    "scenario_end", scenario_name=scenario.name, exit_code=4,
                    reason=str(e), duration_ms=max(0, (time.monotonic() - t0) * 1000),
                    usage_total=None, checks_passed=False, checks_failures=[str(e)],
                )
                return ScenarioResult(
                    name=scenario.name, index=index, status="ERROR", exit_code=4,
                    reason=str(e), duration_ms=max(0, (time.monotonic() - t0) * 1000),
                    checks={"passed": False, "failures": [str(e)]}, log=str(log_path),
                )

        tools_client = await MCPToolClient.start(
            transport=self.cfg.app.tool_transport,
            config_path=Path(self.args.config),
            tool_vars=scenario.tool_vars,
            workspace=ws,
            docs_dir=self.cfg.app.docs_dir,
            skills_dir=self.cfg.app.skills_dir,
        )

        skills = SkillLoader(self.cfg.app.skills_dir)
        prompt = PromptBuilder(self.cfg.app.prompt_file, memory_file, skills)
        system_text = prompt.build()

        enabled_tools = self.cfg.tools.enabled or None
        llm = LLMClient(self.cfg.models.main, fixture=fixture)
        ctx = SessionCtx()
        checks = scenario.effective_defaults(self.cfg.app.scenario_defaults)
        observer = ScenarioObserver(checks)

        spawner = None
        subagent_text = system_text
        if self.cfg.models.subagent is not None and (
            enabled_tools is None or "spawn_agent" in enabled_tools
        ):
            sp = self.cfg.app.subagent_prompt_file or self.cfg.app.prompt_file
            subagent_text = sp.read_text(encoding="utf-8")
            spawner = SubagentSpawner(
                cfg=self.cfg,
                parent_session_id=session_id,
                system_text=subagent_text,
                tools_client=tools_client,
                logger=logger,
                enabled_tools=self.cfg.tools.enabled,
            )

        ui = ConsoleUi(self.console, mode="headless", scenario=scenario.name)
        orchestrator = Orchestrator(
            llm=llm,
            tools=tools_client,
            observer=observer,
            logger=logger,
            limits=self.cfg.limits.main,
            ui=ui,
            spawner=spawner,
            is_repl=False,
            enabled_tools=enabled_tools,
        )

        messages = [self._system_message(system_text)]

        status = "PASS"
        exit_code: int | None = 0
        failures: list[str] = []
        turn_secs = scenario.timeouts.turn_secs

        try:
            user = scenario.initial_message
            while True:
                self.console.scenario(scenario.name, f"turn {ctx.turn + 1}")
                if turn_secs is not None:
                    await asyncio.wait_for(
                        orchestrator.turn(messages, user, ctx), timeout=turn_secs
                    )
                else:
                    await orchestrator.turn(messages, user, ctx)
                nxt = self._next_transition(scenario, ctx.last_assistant_text)
                if nxt is None:
                    break
                user = nxt

            failures = observer.final_checks(ctx)
            # Re-check boundary limits per spec §13.9
            if checks.max_agent_messages is not None and ctx.agent_messages > checks.max_agent_messages:
                failures.append(f"max_agent_messages: {ctx.agent_messages} > {checks.max_agent_messages}")
            if checks.max_context_tokens is not None and ctx.context_tokens_max > checks.max_context_tokens:
                failures.append(f"max_context_tokens: {ctx.context_tokens_max} > {checks.max_context_tokens}")
            checks_ok = not failures
            logger.log(
                "session_end",
                duration_ms=(time.monotonic() - t0) * 1000,
                turns=ctx.turn,
                agent_messages=ctx.agent_messages,
                tools_histogram=ctx.tools_histogram,
                context_tokens_max=ctx.context_tokens_max,
                checks={"passed": checks_ok, "failures": failures},
                exit_code=0 if checks_ok else 1,
            )
            status = "PASS" if checks_ok else "FAIL"
            exit_code = 0 if checks_ok else 1
        except TimeoutError:
            reason = "turn_timeout"
            logger.log("limit_exceeded", reason=reason, limit=turn_secs, actual=turn_secs)
            status, exit_code, failures = "LIMIT", 3, [reason]
        except ScenarioAbort as e:
            logger.log("scenario_abort", reason=e.reason, exit_code=e.exit_code)
            status, exit_code, failures = "FAIL", e.exit_code, [e.reason]
        except LimitExceeded as e:
            logger.log("limit_exceeded", reason=e.reason, limit=e.limit, actual=e.actual)
            status, exit_code, failures = "LIMIT", 3, [e.reason]
        except LLMError as e:
            logger.log("scenario_abort", reason=str(e), exit_code=4)
            status, exit_code, failures = "ERROR", 4, [str(e)]
        finally:
            await llm.aclose()
            await tools_client.close()
            if fixture is not None:
                fixture.close()
            logger.close()

        usage = self._usage_ctx(ctx)

        # Workspace retention
        ws_path: str | None = None
        if self.args.workspace_mode == "copy":
            if status == "PASS" and not self.args.keep_workspace:
                shutil.rmtree(ws, ignore_errors=True)
            else:
                ws_path = str(ws)
        elif self.args.workspace_mode == "fresh":
            if status == "PASS" and not self.args.keep_workspace:
                shutil.rmtree(ws, ignore_errors=True)
            else:
                ws_path = str(ws) if status != "PASS" else None

        self.console.scenario(
            scenario.name,
            f"{status}  "
            + (f"reason={failures[0] if failures else None}  " if status != "PASS" else "")
            + f"turns={ctx.turn}"
            + (f"  agent_messages={ctx.agent_messages}" if status == "FAIL" else "")
            + (f"  tok={usage['tokens_in'] if usage else '-'}/{usage['tokens_out'] if usage else '-'}" if status != "PASS" else "")
            + f"  dur={self._fmt_duration(max(0, (time.monotonic() - t0) * 1000))}",
        )

        await self._run_log(
            "scenario_end",
            scenario_name=scenario.name,
            exit_code=exit_code,
            reason=failures[0] if failures else None,
            duration_ms=max(0, (time.monotonic() - t0) * 1000),
            usage_total=usage,
            checks_passed=status == "PASS",
            checks_failures=failures,
        )

        return ScenarioResult(
            name=scenario.name,
            index=index,
            status=status,
            exit_code=exit_code,
            reason=failures[0] if failures else None,
            duration_ms=max(0, (time.monotonic() - t0) * 1000),
            turns=ctx.turn,
            agent_messages=ctx.agent_messages,
            usage=usage,
            tools_histogram=ctx.tools_histogram,
            checks={"passed": status == "PASS", "failures": failures},
            log=str(log_path),
            workspace=ws_path,
        )

    @staticmethod
    def _system_message(text: str) -> Message:
        return Message(role="system", content=text)

    @staticmethod
    def _usage_ctx(ctx: SessionCtx) -> dict[str, int] | None:
        if ctx.tokens_total > 0:
            return {
                "tokens_in": ctx.tokens_in,
                "tokens_out": ctx.tokens_out,
                "tokens_total": ctx.tokens_total,
            }
        return None

    def _next_transition(self, scenario: Scenario, text: str) -> str | None:
        for i, t in enumerate(scenario.transitions):
            if all(re.search(p, text, re.MULTILINE) for p in t.include) and not any(
                re.search(p, text, re.MULTILINE) for p in t.exclude
            ):
                if t.once:
                    scenario.transitions.pop(i)
                return t.message
        return None

    def _prepare_workspace(self, name: str) -> Path:
        mode = self.args.workspace_mode
        if mode == "shared":
            return self.cfg.app.workspace
        ws = self.run_dir / name / "workspace"
        ws.mkdir(parents=True, exist_ok=True)
        if mode == "copy":
            src = self.cfg.app.workspace
            for p in src.iterdir():
                dest = ws / p.name
                if p.is_dir():
                    shutil.copytree(p, dest)
                else:
                    shutil.copy2(p, dest)
        return ws

    def _prepare_memory(self, ws: Path) -> Path:
        target = ws / "MEMORY.md"
        if not target.exists() and self.cfg.app.memory_file.exists():
            shutil.copy2(self.cfg.app.memory_file, target)
        return target

    def _fixture_path(self, name: str) -> Path:
        base = Path(self.args.record or self.args.replay)
        if base.suffix == ".jsonl":
            return base
        return base / f"{name}.jsonl"

    def _discover_scenarios(self) -> list[Scenario]:
        paths: list[Path] = []
        for p in self.args.scenario or []:
            paths.append(Path(p))
        if self.args.scenario_dir:
            paths.extend(sorted(Path(self.args.scenario_dir).glob("*.y*ml")))
        if self.args.scenario_glob:
            paths.extend(sorted(Path(p) for p in glob.glob(self.args.scenario_glob)))
        seen: set[Path] = set()
        unique: list[Path] = []
        for p in paths:
            rp = p.resolve()
            if rp not in seen:
                seen.add(rp)
                unique.append(rp)

        try:
            scenarios = [load_scenario(p) for p in unique]
        except Exception as e:
            raise ConfigError(str(e)) from e
        if self.args.filter:
            scenarios = [s for s in scenarios if self.args.filter in s.checks.tags]
        if self.args.filter_name:
            scenarios = [s for s in scenarios if re.search(self.args.filter_name, s.name)]
        if not scenarios:
            raise ConfigError("no scenarios matched")
        return scenarios

    def _skip_result(self, scenario: Scenario, index: int) -> ScenarioResult:
        return ScenarioResult(
            name=scenario.name,
            index=index,
            status="SKIP",
            exit_code=None,
            reason="fail-fast",
            duration_ms=0,
            checks={"passed": False, "failures": ["skipped"]},
        )

    def _aggregate_exit(self, results: list[ScenarioResult]) -> int:
        codes = [r.exit_code for r in results if r.exit_code is not None]
        if not codes:
            return 0
        return max(codes, key=lambda c: SEVERITY.get(c, 0))

    def _write_summary(self, results: list[ScenarioResult], exit_code: int) -> None:
        if self.args.summary_format == "list":
            self._print_list(results)
        else:
            self._print_table(results, exit_code)
        if self.args.summary_file:
            payload = {
                "run": {
                    "run_id": self.run_id,
                    "scenarios_total": len(results),
                    "parallel": self.args.parallel,
                    "workspace_mode": self.args.workspace_mode,
                    "record": self.args.record,
                    "replay": self.args.replay,
                    "exit_code": exit_code,
                    "duration_ms": int((time.monotonic() - self._t0) * 1000),
                },
                "scenarios": [self._result_dict(r) for r in results],
                "totals": self._totals(results),
            }
            Path(self.args.summary_file).write_text(
                yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8"
            )
            self.console.info(f"summary written to: {self.args.summary_file}")

    def _result_dict(self, r: ScenarioResult) -> dict[str, Any]:
        return {
            "name": r.name,
            "index": r.index,
            "status": r.status,
            "exit_code": r.exit_code if r.status != "SKIP" else None,
            "reason": r.reason,
            "duration_ms": r.duration_ms,
            "turns": r.turns,
            "agent_messages": r.agent_messages,
            "usage": r.usage,
            "tools_histogram": dict(r.tools_histogram),
            "checks": r.checks,
            "log": r.log,
            "workspace": r.workspace,
        }

    def _totals(self, results: list[ScenarioResult]) -> dict[str, Any]:
        usage_in = [r.usage["tokens_in"] for r in results if r.usage and r.usage.get("tokens_in")]
        usage_out = [r.usage["tokens_out"] for r in results if r.usage and r.usage.get("tokens_out")]
        usage_total = [r.usage["tokens_total"] for r in results if r.usage and r.usage.get("tokens_total")]
        return {
            "passed": sum(1 for r in results if r.status == "PASS"),
            "failed": sum(1 for r in results if r.status == "FAIL"),
            "errored": sum(1 for r in results if r.status == "ERROR"),
            "skipped": sum(1 for r in results if r.status == "SKIP"),
            "usage": (
                {
                    "tokens_in": sum(usage_in),
                    "tokens_out": sum(usage_out),
                    "tokens_total": sum(usage_total),
                }
                if usage_total
                else None
            ),
            "duration_ms": int((time.monotonic() - self._t0) * 1000),
        }

    def _print_list(self, results: list[ScenarioResult]) -> None:
        for r in results:
            pieces = [
                r.status,
                r.name,
                f"exit={r.exit_code}" if r.status != "SKIP" else "exit=-",
                f"turns={r.turns}",
                f"tok={r.usage['tokens_in'] if r.usage else '-'}/{r.usage['tokens_out'] if r.usage else '-'}",
                f"dur={self._fmt_duration(r.duration_ms)}",
            ]
            if r.status != "PASS" and r.status != "SKIP" and r.reason:
                pieces.insert(3, f"reason={r.reason}")
            self.console.status(r.status, "  ".join(pieces))

    def _print_table(self, results: list[ScenarioResult], exit_code: int) -> None:
        headers = ["SCENARIO", "STATUS", "REASON", "TURNS", "TOK_IN", "TOK_OUT", "DURATION", "EXIT"]
        rows = []
        for r in results:
            reason = r.reason or "\u2014"
            tok_in = str(r.usage["tokens_in"]) if r.usage and r.usage.get("tokens_in") else "\u2014"
            tok_out = str(r.usage["tokens_out"]) if r.usage and r.usage.get("tokens_out") else "\u2014"
            exit_s = str(r.exit_code) if r.exit_code is not None else "\u2014"
            turns = str(r.turns) if r.status != "SKIP" else "\u2014"
            dur = self._fmt_duration(r.duration_ms)
            rows.append([self._truncate(r.name), r.status, reason, turns, tok_in, tok_out, dur, exit_s])
        widths = [
            max(len(h), *(len(str(row[i])) for row in rows)) for i, h in enumerate(headers)
        ]

        def fmt(row: list[str]) -> str:
            return "  ".join(str(c).ljust(w) for c, w in zip(row, widths))

        self.console.plain(fmt(headers))
        self.console.plain("-" * (sum(widths) + 2 * (len(widths) - 1)))
        for row in rows:
            self.console.plain(fmt(row))
        passed = sum(1 for r in results if r.status == "PASS")
        failed = sum(1 for r in results if r.status == "FAIL")
        limit = sum(1 for r in results if r.status == "LIMIT")
        errored = sum(1 for r in results if r.status == "ERROR")
        skipped = sum(1 for r in results if r.status == "SKIP")
        bits = [f"passed {passed}"]
        if failed:
            bits.append(f"failed {failed}")
        if limit:
            bits.append(f"limit {limit}")
        if errored:
            bits.append(f"errors {errored}")
        if skipped:
            bits.append(f"skipped {skipped}")
        total_row = [f"TOTAL ({len(results)})", "\u2014", ", ".join(bits), "\u2014", "\u2014", "\u2014",
                     self._fmt_duration((time.monotonic() - self._t0) * 1000), str(exit_code)]
        self.console.plain(fmt(total_row))

    @staticmethod
    def _truncate(name: str, limit: int = 40) -> str:
        return name if len(name) <= limit else name[: limit - 1] + "\u2026"

    @staticmethod
    def _fmt_duration(ms: float) -> str:
        secs = ms / 1000.0
        if secs < 60:
            return f"{secs:.1f}s"
        m = int(secs // 60)
        s = secs - m * 60
        return f"{m}m {s:.1f}s"
