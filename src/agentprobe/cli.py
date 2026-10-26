from __future__ import annotations

import asyncio
import glob
import types
from pathlib import Path

import typer

from agentprobe.config import load_config
from agentprobe.errors import ConfigError
from agentprobe.logging.console import configure_logging

configure_logging()

app = typer.Typer(no_args_is_help=True)


def _fail(msg: str, code: int = 2) -> None:
    typer.echo(f"error: {msg}", err=True)
    raise typer.Exit(code)


def _parse_params(params: list[str]) -> dict[str, str]:
    """Parse ``--param key=value`` entries into a dict."""
    out: dict[str, str] = {}
    for item in params:
        key, sep, value = item.partition("=")
        if not sep or not key:
            _fail(f"invalid --param (expected key=value): {item}")
        out[key] = value
    return out


@app.command()
def repl(
    config: Path = typer.Option(..., "--config", exists=True),
    summary: bool = typer.Option(False, "--summary"),
    summary_file: Path | None = typer.Option(None, "--summary-file"),
) -> None:
    """Interactive REPL mode."""
    if summary or summary_file:
        _fail("--summary is not supported in repl mode")
    cfg = load_config(config)
    from agentprobe.repl.app import run_repl

    asyncio.run(run_repl(cfg, config))


@app.command()
def run(
    config: Path = typer.Option(..., "--config", exists=True),
    scenario: list[Path] = typer.Option([], "--scenario"),
    scenario_dir: Path | None = typer.Option(None, "--scenario-dir"),
    scenario_glob: str | None = typer.Option(None, "--scenario-glob"),
    filter: str | None = typer.Option(None, "--filter"),
    filter_name: str | None = typer.Option(None, "--filter-name"),
    parallel: int = typer.Option(1, "--parallel", min=1),
    fail_fast: bool = typer.Option(False, "--fail-fast"),
    workspace_mode: str = typer.Option("copy", "--workspace-mode", case_sensitive=False),
    keep_workspace: bool = typer.Option(False, "--keep-workspace"),
    param: list[str] = typer.Option([], "--param", help="Scenario template override key=value (repeatable)"),
    record: Path | None = typer.Option(None, "--record"),
    replay: Path | None = typer.Option(None, "--replay"),
    summary: bool = typer.Option(False, "--summary"),
    summary_format: str = typer.Option("table", "--summary-format"),
    summary_file: Path | None = typer.Option(None, "--summary-file"),
) -> None:
    """Headless mode: run one or more scenarios."""
    if record and replay:
        _fail("--record and --replay are mutually exclusive")
    if workspace_mode not in ("copy", "shared", "fresh"):
        _fail(f"invalid --workspace-mode: {workspace_mode}")
    if summary_format not in ("table", "list"):
        _fail(f"invalid --summary-format: {summary_format}")

    fr = record or replay
    if fr is not None:
        if fr.suffix == ".jsonl" and len(scenario) != 1:
            _fail(
                f"--{ 'record' if record else 'replay' } with a single file is only valid with exactly one --scenario"
            )
        if record is not None and not record.parent.exists():
            _fail(f"--record: parent directory does not exist: {record.parent}")

    if summary_file is not None and not summary_file.parent.exists():
        _fail(f"--summary-file: parent directory does not exist: {summary_file.parent}")

    args = types.SimpleNamespace(
        config=str(config),
        scenario=scenario,
        scenario_dir=scenario_dir,
        scenario_glob=scenario_glob,
        filter=filter,
        filter_name=filter_name,
        parallel=parallel,
        fail_fast=fail_fast,
        workspace_mode=workspace_mode.lower(),
        keep_workspace=keep_workspace,
        params=_parse_params(param),
        record=str(record) if record else None,
        replay=str(replay) if replay else None,
        summary=summary or summary_file is not None,
        summary_format=summary_format,
        summary_file=str(summary_file) if summary_file else None,
    )

    try:
        cfg = load_config(config)
        from agentprobe.scenario.runner import Runner

        code = asyncio.run(Runner(cfg, args).run_all())
    except ConfigError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(2)
    raise typer.Exit(code)


@app.command("dry-run")
def dry_run(
    config: Path = typer.Option(..., "--config", exists=True),
    scenario: list[Path] = typer.Option([], "--scenario"),
    scenario_dir: Path | None = typer.Option(None, "--scenario-dir"),
    scenario_glob: str | None = typer.Option(None, "--scenario-glob"),
    summary_file: Path | None = typer.Option(None, "--summary-file"),
) -> None:
    """Print the assembled prompt, tool schemas, skills, and paths."""
    if summary_file:
        typer.echo("warning: --summary-file ignored in dry-run", err=True)
    cfg = load_config(config)
    from agentprobe.prompt.builder import PromptBuilder
    from agentprobe.skills.loader import SkillLoader

    skills = SkillLoader(cfg.app.skills_dir)
    prompt = PromptBuilder(cfg.app.prompt_file, cfg.app.memory_file, skills).build()
    typer.echo("=== SYSTEM PROMPT ===")
    typer.echo(prompt)
    typer.echo("\n=== SKILLS ===")
    typer.echo(skills.available_skills_block() or "(none)")
    typer.echo("\n=== DOCS ===")
    for p in sorted(cfg.app.docs_dir.glob("*.md")):
        typer.echo(f"- {p.name}")
    typer.echo("\n=== PATHS ===")
    typer.echo(f"workspace: {cfg.app.workspace}")
    typer.echo(f"docs_dir:  {cfg.app.docs_dir}")
    typer.echo(f"skills_dir: {cfg.app.skills_dir}")
    typer.echo(f"memory_file: {cfg.app.memory_file}")
    typer.echo(f"spawn_agent: {'enabled' if cfg.models.subagent else 'disabled'}")
    typer.echo("\n=== SCENARIO ===")
    paths: list[Path] = list(scenario)
    if scenario_dir:
        paths.extend(sorted(Path(scenario_dir).glob("*.y*ml")))
    if scenario_glob:
        paths.extend(sorted(Path(p) for p in glob.glob(scenario_glob)))
    if not paths:
        typer.echo("(no scenarios specified)")
    else:
        from agentprobe.scenario.schema import load_scenario

        for p in paths:
            sc = load_scenario(p)
            checks = sc.effective_defaults(cfg.app.scenario_defaults)
            typer.echo(f"name: {sc.name}")
            typer.echo(f"path: {p}")
            typer.echo(f'initial_message: "{sc.initial_message}"')
            typer.echo(f"transitions: {len(sc.transitions)}")
            typer.echo(
                f"checks: max_agent_messages={checks.max_agent_messages} "
                f"max_context_tokens={checks.max_context_tokens} "
                f"max_duration_secs={checks.max_duration_secs}"
            )
    raise typer.Exit(0)
