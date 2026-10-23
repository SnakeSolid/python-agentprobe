"""Headless scenario runner: multi-run, isolation, workspace modes, summary."""

from __future__ import annotations

import asyncio
import glob
import re
import shutil
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from agentprobe.agent.observer import ScenarioObserver, SessionCtx
from agentprobe.agent.orchestrator import Orchestrator
from agentprobe.agent.subagent import SubagentSpawner
from agentprobe.config import Config
from agentprobe.errors import (
    ConfigError,
    LimitExceeded,
    LLMError,
    ReplayError,
    ScenarioAbort,
)
from agentprobe.llm.client import LLMClient
from agentprobe.llm.fixture import Fixture
from agentprobe.llm.types import Message, Usage
from agentprobe.logging.console import Console
from agentprobe.logging.metrics import add_usage, format_duration
from agentprobe.logging.yaml_logger import YamlLogger, new_run_id
from agentprobe.prompt.builder import PromptBuilder
from agentprobe.scenario.schema import Checks, Scenario, load_scenario
from agentprobe.skills.loader import SkillLoader
from agentprobe.tools.client import MCPToolClient

_SEVERITY = {"5": 5, "4": 4, "3": 3, "1": 1, "0": 0}


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
    def __init__(self, cfg: Config, args: Any):
        self.cfg = cfg
        self.args = args
        self.run_id = new_run_id()
        self.run_dir = cfg.app.log_dir / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._run_lock = asyncio.Lock()
        self._run_fp = (self.run_dir / "run.yaml").open("a", encoding="utf-8")
        self.console = Console(
            level=cfg.logging.console_level, color=cfg.logging.color,
            truncate=cfg.logging.console_truncate_chars,
        )
        self._scenario_names: list[str] = []

    async def run_all(self) -> int:
        scenarios = self._discover_scenarios()
        self._scenario_names = [s.name for s in scenarios]
        await self._run_log(
            "run_start",
            scenarios_total=len(scenarios),
            parallel=self.args.parallel,
            workspace_mode=self.args.workspace_mode,
            record=self.args.record,
            replay=self.args.replay,
            filter=self.args.filter,
        )

        results: list[ScenarioResult] = []
        if self.args.parallel <= 1:
            for i, sc in enumerate(scenarios, start=1):
                await self._run_log(
                    "scenario_start", scenario_name=sc.name, index=i, pid=None
                )
                r = await self._run_one(sc, i)
                await self._run_log(
                    "scenario_end",
                    scenario_name=sc.name,
                    exit_code=r.exit_code,
                    reason=r.reason,
                    duration_ms=r.duration_ms,
                    usage_total=r.usage,
                    checks=r.checks,
                )
                results.append(r)
                if self.args.fail_fast and r.exit_code not in (0, None):
                    for j, sc2 in enumerate(scenarios[i:], start=i + 1):
                        results.append(self._skip_result(sc2, j))
                    break
        else:
            sem = asyncio.Semaphore(self.args.parallel)

            async def worker(i: int, sc: Scenario) -> ScenarioResult:
                async with sem:
                    await self._run_log(
                        "scenario_start", scenario_name=sc.name, index=i, pid=None
                    )
                    r = await self._run_one(sc, i)
                    await self._run_log(
                        "scenario_end",
                        scenario_name=sc.name,
                        exit_code=r.exit_code,
                        reason=r.reason,
                        duration_ms=r.duration_ms,
                        usage_total=r.usage,
                        checks=r.checks,
                    )
                    return r

            results = list(
                await asyncio.gather(
                    *(worker(i, sc) for i, sc in enumerate(scenarios, start=1))
                )
            )

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

    async def _run_one(self, scenario: Scenario, index: int) -> ScenarioResult:
        t0 = time.monotonic()
        session_id = f"{self.run_id}/{scenario.name}_{datetime.now(UTC):%Y%m%d_%H%M%S}_{self._rand4()}"
        log_path = self.run_dir / f"{scenario.name}.yaml"
        logger = YamlLogger(log_path, session_id=session_id)
        logger.log(
            "session_start",
            mode="headless",
            scenario=scenario.name,
            model=self.cfg.models.main.model,
            limits=self.cfg.limits.main.__dict__,
            tool_transport=self.cfg.app.tool_transport,
            tool_vars_keys=list(scenario.tool_vars.keys()),
        )

        checks = scenario.effective_defaults(self.cfg.app.scenario_defaults)
        ws, memory_file = self._prepare_workspace(scenario, checks)

        fixture: Fixture | None = None
        try:
            if self.args.record:
                fixture = Fixture(self._fixture_path(scenario.name), mode="record")
            elif self.args.replay:
                try:
                    fixture = Fixture(self._fixture_path(scenario.name), mode="replay")
                except ReplayError as e:
                    logger.log("scenario_abort", reason=str(e), exit_code=4)
                    logger.close()
                    return ScenarioResult(
                        name=scenario.name, index=index, status="ERROR", exit_code=4,
                        reason=str(e), duration_ms=(time.monotonic() - t0) * 1000,
                        checks={"passed": False, "failures": [str(e)]},
                        log=str(log_path),
                    )

            tools_client = await MCPToolClient.start(
                cfg=self.cfg,
                config_path=Path(self.args.config),
                tool_vars=scenario.tool_vars,
                workspace=ws,
            )

            skills = SkillLoader(self.cfg.app.skills_dir)
            prompt = PromptBuilder(self.cfg.app.prompt_file, memory_file, skills)
            system_text = prompt.build()

            llm = LLMClient(self.cfg.models.main, fixture=fixture)
            ctx = SessionCtx()
            observer = ScenarioObserver(
                checks, max_tool_calls=self.cfg.limits.main.max_tool_calls
            )
            spawner: SubagentSpawner | None = None
            if self.cfg.models.subagent is not None:
                spawner = SubagentSpawner(
                    self.cfg, Path(self.args.config), logger, session_id,
                    tools_client, fixture,
                )

            orchestrator = Orchestrator(
                llm=llm, tools=tools_client, observer=observer,
                logger=logger, limits=self.cfg.limits.main,
                spawner=spawner, is_repl=False,
                system_refresh=prompt.build,
            )

            messages = [Message(role="system", content=system_text)]
            user = scenario.initial_message
            turn_secs = (
                scenario.timeouts.turn_secs
                or self.cfg.app.scenario_defaults.turn_timeout_secs
            )

            try:
                while True:
                    coro = orchestrator.turn(messages, user, ctx)
                    if turn_secs:
                        await asyncio.wait_for(coro, timeout=turn_secs)
                    else:
                        await coro

                    elapsed = time.monotonic() - t0
                    if (
                        checks.max_duration_secs is not None
                        and elapsed > checks.max_duration_secs
                    ):
                        raise LimitExceeded(
                            "max_duration_secs", checks.max_duration_secs, int(elapsed)
                        )

                    nxt = self._next_transition(scenario, ctx.last_assistant_text)
                    if nxt is None:
                        break
                    user = nxt

                failures = observer.final_checks(ctx)
                status = "PASS" if not failures else "FAIL"
                exit_code = 0 if not failures else 1
                logger.log(
                    "session_end",
                    duration_ms=(time.monotonic() - t0) * 1000,
                    turns=ctx.turn,
                    usage_total=_summary_usage(ctx),
                    tools_histogram=ctx.tools_histogram,
                    agent_messages=ctx.agent_messages,
                    context_tokens_max=ctx.context_tokens_max,
                    checks={"passed": not failures, "failures": failures},
                    exit_code=exit_code,
                )
            except ScenarioAbort as e:
                logger.log(
                    "scenario_abort", reason=e.reason, exit_code=e.exit_code,
                    turn=ctx.turn, agent_messages=ctx.agent_messages,
                    context_tokens=ctx.context_tokens_max,
                )
                status, exit_code, failures = _status_for(e.exit_code), e.exit_code, [e.reason]
            except LimitExceeded as e:
                logger.log(
                    "limit_exceeded", reason=e.reason, limit=e.limit, actual=e.actual
                )
                status, exit_code, failures = ("LIMIT", 3, [e.reason])
            except TimeoutError:
                logger.log("limit_exceeded", reason="turn_timeout", limit=turn_secs, actual=0)
                status, exit_code, failures = ("LIMIT", 3, ["turn_timeout"])
            except LLMError as e:
                logger.log("scenario_abort", reason=str(e), exit_code=4)
                status, exit_code, failures = ("ERROR", 4, [str(e)])
            finally:
                await llm.aclose()
                await tools_client.close()
                if fixture is not None:
                    fixture.close()
                logger.close()

        except LLMError as e:
            logger.log("scenario_abort", reason=str(e), exit_code=4)
            logger.close()
            return ScenarioResult(
                name=scenario.name, index=index, status="ERROR", exit_code=4,
                reason=str(e), duration_ms=(time.monotonic() - t0) * 1000,
                checks={"passed": False, "failures": [str(e)]}, log=str(log_path),
            )
        except Exception as e:  # internal error → exit 5
            logger.log("scenario_abort", reason=type(e).__name__, exit_code=5)
            logger.close()
            return ScenarioResult(
                name=scenario.name, index=index, status="ERROR", exit_code=5,
                reason=type(e).__name__, duration_ms=(time.monotonic() - t0) * 1000,
                checks={"passed": False, "failures": [str(e)]}, log=str(log_path),
            )

        # Workspace retention (copy mode only).
        ws_path: str | None = None
        if self.args.workspace_mode == "copy":
            if status == "PASS" and not self.args.keep_workspace:
                shutil.rmtree(ws, ignore_errors=True)
                ws_path = None
            else:
                ws_path = str(ws)

        return ScenarioResult(
            name=scenario.name, index=index, status=status, exit_code=exit_code,
            reason=failures[0] if failures else None,
            duration_ms=(time.monotonic() - t0) * 1000,
            turns=ctx.turn, agent_messages=ctx.agent_messages,
            usage=_summary_usage(ctx), tools_histogram=ctx.tools_histogram,
            checks={"passed": status == "PASS", "failures": failures},
            log=str(log_path), workspace=ws_path,
        )

    # ---- workspace ----

    def _prepare_workspace(
        self, scenario: Scenario, checks: Checks
    ) -> tuple[Path, Path]:
        mode = self.args.workspace_mode
        if mode == "shared":
            self.console.warn("shared workspace: scenarios may affect each other")
            return self.cfg.app.workspace, self.cfg.app.memory_file
        ws = self.run_dir / scenario.name / "workspace"
        ws.mkdir(parents=True, exist_ok=True)
        if mode == "copy":
            src = self.cfg.app.workspace
            if src.exists():
                for p in src.iterdir():
                    dest = ws / p.name
                    if p.is_dir():
                        shutil.copytree(p, dest)
                    else:
                        shutil.copy2(p, dest)
        memory = ws / "MEMORY.md"
        if not memory.exists() and self.cfg.app.memory_file.exists():
            shutil.copy2(self.cfg.app.memory_file, memory)
        return ws, memory

    def _fixture_path(self, name: str) -> Path:
        base = Path(self.args.record or self.args.replay)
        if base.suffix == ".jsonl":
            return base
        return base / f"{name}.jsonl"

    def _next_transition(self, scenario: Scenario, text: str) -> str | None:
        for i, t in enumerate(scenario.transitions):
            if all(re.search(p, text, re.MULTILINE) for p in t.include) and not any(
                re.search(p, text, re.MULTILINE) for p in t.exclude
            ):
                if t.once:
                    scenario.transitions.pop(i)
                return t.message
        return None

    # ---- discovery ----

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
        if not unique:
            raise ConfigError("no scenarios given")

        # Fixture file paths require exactly one scenario.
        fixture_path = self.args.record or self.args.replay
        if fixture_path and Path(fixture_path).suffix == ".jsonl" and len(unique) != 1:
            raise ConfigError("fixture file requires exactly one --scenario")

        scenarios = [load_scenario(p) for p in unique]  # validates all first
        if self.args.filter:
            scenarios = [s for s in scenarios if self.args.filter in s.checks.tags]
        if self.args.filter_name:
            scenarios = [
                s for s in scenarios if re.search(self.args.filter_name, s.name)
            ]
        if not scenarios:
            raise ConfigError("no scenarios matched")
        return scenarios

    def _skip_result(self, scenario: Scenario, index: int) -> ScenarioResult:
        return ScenarioResult(
            name=scenario.name, index=index, status="SKIP", exit_code=None,
            reason="fail-fast", duration_ms=0,
            checks={"passed": False, "failures": ["skipped"]},
        )

    def _aggregate_exit(self, results: list[ScenarioResult]) -> int:
        if self.args.fail_fast:
            for r in results:
                if r.exit_code not in (0, None):
                    return r.exit_code
        codes = [r.exit_code for r in results if r.exit_code is not None]
        if not codes:
            return 0
        return max(codes, key=lambda c: _SEVERITY.get(str(c), 0))

    # ---- logging ----

    async def _run_log(self, event: str, **kw: Any) -> None:
        payload = {
            "event": event,
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "run_id": self.run_id,
            **kw,
        }
        async with self._run_lock:
            self._run_fp.write("---\n")
            self._run_fp.write(yaml.safe_dump(payload, sort_keys=False))
            self._run_fp.flush()

    @staticmethod
    def _rand4() -> str:
        import secrets

        return secrets.token_hex(2)

    # ---- summary ----

    def _write_summary(self, results: list[ScenarioResult], exit_code: int) -> None:
        if self.args.summary:
            if self.args.summary_format == "list":
                self._print_list(results)
            else:
                self._print_table(results, exit_code)
        if self.args.summary_file:
            self._write_summary_file(results, exit_code)

    def _write_summary_file(self, results: list[ScenarioResult], exit_code: int) -> None:
        payload = {
            "run": {
                "run_id": self.run_id,
                "scenarios_total": len(results),
                "parallel": self.args.parallel,
                "workspace_mode": self.args.workspace_mode,
                "record": self.args.record,
                "replay": self.args.replay,
                "exit_code": exit_code,
                "duration_ms": sum(r.duration_ms for r in results),
            },
            "scenarios": [self._result_payload(r) for r in results],
            "totals": self._totals(results),
        }
        target = Path(self.args.summary_file)
        target.write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )

    @staticmethod
    def _result_payload(r: ScenarioResult) -> dict[str, Any]:
        return {
            "name": r.name,
            "index": r.index,
            "status": r.status,
            "exit_code": r.exit_code,
            "reason": r.reason,
            "duration_ms": r.duration_ms,
            "turns": r.turns,
            "agent_messages": r.agent_messages,
            "usage": r.usage,
            "tools_histogram": r.tools_histogram,
            "checks": r.checks,
            "log": r.log,
            "workspace": r.workspace,
        }

    def _totals(self, results: list[ScenarioResult]) -> dict[str, Any]:
        usage = None
        for r in results:
            usage = add_usage(usage, _usage_to_obj(r.usage))
        return {
            "passed": sum(1 for r in results if r.status == "PASS"),
            "failed": sum(1 for r in results if r.status == "FAIL"),
            "errored": sum(1 for r in results if r.status == "ERROR"),
            "skipped": sum(1 for r in results if r.status == "SKIP"),
            "usage": usage,
            "duration_ms": sum(r.duration_ms for r in results),
        }

    def _print_table(self, results: list[ScenarioResult], exit_code: int) -> None:
        headers = ["SCENARIO", "STATUS", "REASON", "TURNS", "TOK_IN", "TOK_OUT", "DURATION", "EXIT"]
        rows: list[list[str]] = []
        for r in results:
            tok_in = "—" if r.usage is None else str(r.usage["tokens_in"])
            tok_out = "—" if r.usage is None else str(r.usage["tokens_out"])
            rows.append(
                [
                    r.name, r.status, r.reason or "—", str(r.turns),
                    tok_in, tok_out, format_duration(r.duration_ms), str(r.exit_code),
                ]
            )
        rows.append(["TOTAL", "—", "—", "—", "—", "—", format_duration(sum(r.duration_ms for r in results)), str(exit_code)])
        widths = [
            max(len(h), *(len(row[i]) for row in rows)) for i, h in enumerate(headers)
        ]

        def fmt(row: list[str]) -> str:
            return "  ".join(c.ljust(w) for c, w in zip(row, widths))

        print(fmt(headers))
        print("-" * (sum(widths) + 2 * (len(widths) - 1)))
        for row in rows:
            print(fmt(row))

    def _print_list(self, results: list[ScenarioResult]) -> None:
        for r in results:
            if r.exit_code is None:
                exit_s = "exit=—"
            else:
                exit_s = f"exit={r.exit_code}"
            tok = (
                "—"
                if r.usage is None
                else f"{r.usage['tokens_in']}/{r.usage['tokens_out']}"
            )
            parts = [
                r.status, r.name, exit_s, f"turns={r.turns}", f"tok={tok}",
                f"dur={format_duration(r.duration_ms)}",
            ]
            if r.reason and r.status != "PASS":
                parts.append(f"reason={r.reason}")
            print("  ".join(parts))


def _status_for(exit_code: int) -> str:
    if exit_code == 3:
        return "LIMIT"
    if exit_code in (4, 5):
        return "ERROR"
    return "FAIL"


def _summary_usage(ctx: SessionCtx) -> dict[str, int] | None:
    total = ctx.usage_total
    if not any(total.values()):
        return None
    return dict(total)


def _usage_to_obj(usage: dict[str, int] | None) -> Usage | None:
    if usage is None:
        return None

    return Usage(
        prompt_tokens=usage["tokens_in"],
        completion_tokens=usage["tokens_out"],
        total_tokens=usage.get("tokens_total", usage["tokens_in"] + usage["tokens_out"]),
    )
