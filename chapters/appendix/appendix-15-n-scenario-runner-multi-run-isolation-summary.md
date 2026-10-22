# Appendix: Code Snippets and Examples

## N. Scenario runner (multi-run, isolation, summary)

### N.1. `src/agentprobe/scenario/runner.py` (skeleton)

```python
from __future__ import annotations
import asyncio, shutil, time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from agentprobe.agent.observer import ScenarioObserver, SessionCtx
from agentprobe.agent.orchestrator import Orchestrator
from agentprobe.config import Config
from agentprobe.errors import ConfigError, LimitExceeded, LLMError, ReplayError, ScenarioAbort
from agentprobe.llm.client import LLMClient
from agentprobe.llm.fixture import Fixture
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
    status: str                     # PASS | FAIL | LIMIT | ERROR | SKIP
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
    def __init__(self, cfg: Config, args):
        self.cfg = cfg
        self.args = args
        self.run_id = new_run_id()
        self.run_dir = cfg.app.log_dir / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._run_lock = asyncio.Lock()
        self._run_fp = (self.run_dir / "run.yaml").open("a", encoding="utf-8")

    def _run_log(self, event: str, **kw):
        import yaml as _y
        from datetime import datetime, timezone
        payload = {"event": event,
                   "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                   "run_id": self.run_id, **kw}
        self._run_fp.write("---\n")
        self._run_fp.write(_y.safe_dump(payload, sort_keys=False))
        self._run_fp.flush()

    async def run_all(self) -> int:
        scenarios = self._discover_scenarios()
        self._run_log("run_start",
                      scenarios_total=len(scenarios),
                      parallel=self.args.parallel,
                      workspace_mode=self.args.workspace_mode,
                      record=self.args.record, replay=self.args.replay,
                      filter=self.args.filter)
        results: list[ScenarioResult] = []

        if self.args.parallel <= 1:
            for i, sc in enumerate(scenarios, start=1):
                r = await self._run_one(sc, i)
                results.append(r)
                if self.args.fail_fast and r.exit_code not in (0, None):
                    for j, sc2 in enumerate(scenarios[i:], start=i + 1):
                        results.append(self._skip_result(sc2, j))
                    break
        else:
            sem = asyncio.Semaphore(self.args.parallel)
            async def worker(i, sc):
                async with sem:
                    return await self._run_one(sc, i)
            results = list(await asyncio.gather(*(worker(i, s)
                                                  for i, s in enumerate(scenarios, start=1))))

        exit_code = self._aggregate_exit(results)
        self._write_summary(results, exit_code)
        self._run_log("run_end", exit_code=exit_code,
                      passed=sum(1 for r in results if r.status == "PASS"),
                      failed=sum(1 for r in results if r.status == "FAIL"),
                      errored=sum(1 for r in results if r.status == "ERROR"),
                      aborted=sum(1 for r in results if r.status == "SKIP"))
        self._run_fp.close()
        return exit_code

    async def _run_one(self, scenario: Scenario, index: int) -> ScenarioResult:
        t0 = time.monotonic()
        session_id = new_session_id("headless")
        log_path = self.run_dir / f"{scenario.name}.yaml"
        logger = YamlLogger(log_path, session_id=session_id)
        logger.log("session_start", mode="headless", scenario=scenario.name,
                   model=self.cfg.models.main.model,
                   limits=self.cfg.limits.main.__dict__,
                   tool_transport=self.cfg.app.tool_transport,
                   tool_vars_keys=list(scenario.tool_vars.keys()))

        # Workspace isolation
        ws = self._prepare_workspace(scenario.name)
        memory_file = self._prepare_memory(ws)

        # Fixture
        fixture = None
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
                    log=str(log_path),
                )

        # Tools
        tools_client = await MCPToolClient.start(
            transport=self.cfg.app.tool_transport,
            config_path=Path(self.args.config),
            tool_vars=scenario.tool_vars,
            workspace=ws,
        )

        # Prompt & skills
        skills = SkillLoader(self.cfg.app.skills_dir)
        prompt = PromptBuilder(self.cfg.app.prompt_file, memory_file, skills)
        system_text = prompt.build()

        # LLM + orchestrator
        llm = LLMClient(self.cfg.models.main, fixture=fixture)
        ctx = SessionCtx()
        observer = ScenarioObserver(scenario.effective_defaults(self.cfg.app.scenario_defaults))

        orchestrator = Orchestrator(
            llm=llm, tools=tools_client, observer=observer,
            logger=logger, limits=self.cfg.limits.main,
            spawner=None, is_repl=False,
        )

        messages = [__import__("agentprobe.llm.types", fromlist=["Message"])
                    .Message(role="system", content=system_text)]

        try:
            user = scenario.initial_message
            while True:
                await orchestrator.turn(messages, user, ctx)
                # find next transition
                nxt = self._next_transition(scenario, ctx.last_assistant_text)
                if nxt is None:
                    break
                user = nxt

            failures = observer.final_checks(ctx)
            checks_ok = not failures
            logger.log("session_end",
                       duration_ms=(time.monotonic() - t0) * 1000,
                       turns=ctx.turn,
                       agent_messages=ctx.agent_messages,
                       tools_histogram=ctx.tools_histogram,
                       context_tokens_max=ctx.context_tokens_max,
                       checks={"passed": checks_ok, "failures": failures},
                       exit_code=0 if checks_ok else 1)
            status = "PASS" if checks_ok else "FAIL"
            exit_code = 0 if checks_ok else 1
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

        # workspace retention
        if self.args.workspace_mode == "copy" and status == "PASS" \
           and not self.args.keep_workspace:
            shutil.rmtree(ws, ignore_errors=True)
            ws_path = None
        else:
            ws_path = str(ws) if self.args.workspace_mode == "copy" else None

        return ScenarioResult(
            name=scenario.name, index=index, status=status, exit_code=exit_code,
            reason=failures[0] if failures else None,
            duration_ms=(time.monotonic() - t0) * 1000,
            turns=ctx.turn, agent_messages=ctx.agent_messages,
            usage={"tokens_in": 0, "tokens_out": 0},  # aggregate elsewhere
            tools_histogram=ctx.tools_histogram,
            checks={"passed": status == "PASS", "failures": failures},
            log=str(log_path),
            workspace=ws_path,
        )

    def _next_transition(self, scenario: Scenario, text: str) -> str | None:
        import re
        for i, t in enumerate(scenario.transitions):
            if all(re.search(p, text, re.MULTILINE) for p in t.include) \
               and not any(re.search(p, text, re.MULTILINE) for p in t.exclude):
                if t.once:
                    scenario.transitions.pop(i)
                return t.message
        return None

    def _prepare_workspace(self, name: str) -> Path:
        ws = self.run_dir / name / "workspace"
        ws.mkdir(parents=True, exist_ok=True)
        if self.args.workspace_mode == "copy":
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
        import glob
        paths: list[Path] = []
        for p in self.args.scenario or []:
            paths.append(Path(p))
        if self.args.scenario_dir:
            paths.extend(sorted(Path(self.args.scenario_dir).glob("*.y*ml")))
        if self.args.scenario_glob:
            paths.extend(sorted(Path(p) for p in glob.glob(self.args.scenario_glob)))
        seen = set()
        unique: list[Path] = []
        for p in paths:
            rp = p.resolve()
            if rp not in seen:
                seen.add(rp)
                unique.append(rp)

        scenarios = [load_scenario(p) for p in unique]  # validates all first
        if self.args.filter:
            scenarios = [s for s in scenarios if self.args.filter in s.checks.tags]
        if self.args.filter_name:
            import re
            scenarios = [s for s in scenarios if re.search(self.args.filter_name, s.name)]
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
        codes = [r.exit_code for r in results if r.exit_code is not None]
        if not codes:
            return 0
        return max(codes, key=lambda c: SEVERITY.get(c, 0))

    def _write_summary(self, results: list[ScenarioResult], exit_code: int) -> None:
        # Print table to stdout
        self._print_table(results, exit_code)
        # Write YAML if requested
        if self.args.summary_file:
            from datetime import datetime, timezone
            payload = {
                "run": {
                    "run_id": self.run_id,
                    "scenarios_total": len(results),
                    "parallel": self.args.parallel,
                    "workspace_mode": self.args.workspace_mode,
                    "record": self.args.record,
                    "replay": self.args.replay,
                    "exit_code": exit_code,
                },
                "scenarios": [r.__dict__ for r in results],
                "totals": self._totals(results),
            }
            Path(self.args.summary_file).write_text(
                yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )

    def _totals(self, results: list[ScenarioResult]) -> dict[str, Any]:
        return {
            "passed": sum(1 for r in results if r.status == "PASS"),
            "failed": sum(1 for r in results if r.status == "FAIL"),
            "errored": sum(1 for r in results if r.status == "ERROR"),
            "skipped": sum(1 for r in results if r.status == "SKIP"),
        }

    def _print_table(self, results: list[ScenarioResult], exit_code: int) -> None:
        headers = ["SCENARIO", "STATUS", "REASON", "TURNS", "DURATION", "EXIT"]
        rows = [[r.name, r.status, r.reason or "-", str(r.turns),
                 f"{r.duration_ms / 1000:.1f}s", str(r.exit_code)] for r in results]
        widths = [max(len(h), *(len(row[i]) for row in rows))
                  for i, h in enumerate(headers)]
        def fmt(row): return "  ".join(c.ljust(w) for c, w in zip(row, widths))
        print(fmt(headers))
        print("-" * (sum(widths) + 2 * (len(widths) - 1)))
        for row in rows:
            print(fmt(row))
        print(fmt(["TOTAL", "-", "-", "-", "-", str(exit_code)]))
```

**Notes:**
- `MCPToolClient.start(...)` is a helper you implement to launch either an in-memory `ClientSession` or a `stdio_client` subprocess (see §I.2 for stdio params). It must accept `tool_vars` and inject them into the environment for `stdio` mode, and into `os.environ` for `in_memory` mode (with a lock around session lifecycle to avoid races under `--parallel`).
- The summary table here omits `TOK_IN`/`TOK_OUT` columns for brevity; extend `ScenarioResult.usage` and the table renderer.
- The `_run_log` writes to `run.yaml`; the per-scenario logger writes to `<scenario>.yaml`.

---

