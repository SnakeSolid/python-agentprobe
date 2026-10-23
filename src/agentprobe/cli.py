"""Typer CLI: `repl`, `run`, `dry-run`."""

from __future__ import annotations

import asyncio
import types
from pathlib import Path
from typing import Any

import typer

from agentprobe.config import Config, load_config
from agentprobe.errors import ConfigError

app = typer.Typer(no_args_is_help=True)


def _validate_fixture_path(record: Path | None, replay: Path | None) -> None:
    if record and replay:
        raise typer.Exit(2)
    path = record or replay
    if path is not None and not path.parent.exists():
        raise typer.Exit(2)


@app.command()
def repl(
    config: Path = typer.Option(..., "--config", exists=True),
    summary: bool = typer.Option(False, "--summary"),
) -> None:
    """Interactive REPL mode."""
    if summary:
        typer.echo("--summary is not supported in repl", err=True)
        raise typer.Exit(2)
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
    record: Path | None = typer.Option(None, "--record"),
    replay: Path | None = typer.Option(None, "--replay"),
    summary: bool = typer.Option(False, "--summary"),
    summary_format: str = typer.Option("table", "--summary-format"),
    summary_file: Path | None = typer.Option(None, "--summary-file"),
) -> None:
    """Headless mode: run one or more scenarios."""
    _validate_fixture_path(record, replay)
    if workspace_mode not in ("copy", "shared", "fresh"):
        raise typer.Exit(2)
    if summary_format not in ("table", "list"):
        raise typer.Exit(2)
    if summary_file is not None and not summary_file.parent.exists():
        raise typer.Exit(2)
    try:
        cfg = load_config(config)
    except ValueError as e:
        typer.echo(f"config error: {e}", err=True)
        raise typer.Exit(2)

    args = types.SimpleNamespace(
        config=str(config),
        scenario=scenario,
        scenario_dir=scenario_dir,
        scenario_glob=scenario_glob,
        filter=filter,
        filter_name=filter_name,
        parallel=parallel,
        fail_fast=fail_fast,
        workspace_mode=workspace_mode,
        keep_workspace=keep_workspace,
        record=str(record) if record else None,
        replay=str(replay) if replay else None,
        summary=summary or summary_file is not None,
        summary_format=summary_format,
        summary_file=str(summary_file) if summary_file else None,
    )
    from agentprobe.scenario.runner import Runner

    try:
        code = asyncio.run(Runner(cfg, args).run_all())
    except ConfigError as e:
        typer.echo(f"config error: {e}", err=True)
        raise typer.Exit(2)
    except ValueError as e:
        typer.echo(f"config error: {e}", err=True)
        raise typer.Exit(2)
    raise typer.Exit(code)


@app.command("dry-run")
def dry_run(
    config: Path = typer.Option(..., "--config", exists=True),
    scenario: list[Path] = typer.Option([], "--scenario"),
    scenario_dir: Path | None = typer.Option(None, "--scenario-dir"),
    scenario_glob: str | None = typer.Option(None, "--scenario-glob"),
    filter: str | None = typer.Option(None, "--filter"),
    filter_name: str | None = typer.Option(None, "--filter-name"),
    summary_file: Path | None = typer.Option(None, "--summary-file"),
) -> None:
    """Print the assembled prompt, tool schemas, skills, and paths."""
    cfg = load_config(config)

    scenario_paths = list(scenario)
    if scenario_dir:
        scenario_paths.extend(sorted(Path(scenario_dir).glob("*.y*ml")))
    if scenario_glob:
        import glob

        scenario_paths.extend(sorted(Path(p) for p in glob.glob(scenario_glob)))

    if summary_file is not None:
        typer.echo("warning: --summary-file ignored in dry-run", err=True)

    if scenario_paths:
        _dry_run_scenarios(cfg, scenario_paths, filter, filter_name)
        raise typer.Exit(0)

    from agentprobe.prompt.builder import PromptBuilder
    from agentprobe.skills.loader import SkillLoader

    skills = SkillLoader(cfg.app.skills_dir)
    prompt = PromptBuilder(cfg.app.prompt_file, cfg.app.memory_file, skills).build()
    typer.echo("=== SYSTEM PROMPT ===")
    typer.echo(prompt)
    typer.echo("\n=== TOOLS ===")
    for schema in _tool_schemas(cfg):
        typer.echo(f"- {schema['function']['name']}")
    typer.echo("\n=== SKILLS ===")
    typer.echo(skills.available_skills_block() or "(none)")
    typer.echo("\n=== DOCS ===")
    for p in sorted(cfg.app.docs_dir.glob("*.md")):
        typer.echo(f"- {p.name}")
    typer.echo("\n=== PATHS ===")
    typer.echo(f"workspace: {cfg.app.workspace}")
    typer.echo(f"docs_dir: {cfg.app.docs_dir}")
    typer.echo(f"skills_dir: {cfg.app.skills_dir}")
    typer.echo(f"memory_file: {cfg.app.memory_file}")
    typer.echo(f"spawn_agent: {'enabled' if cfg.models.subagent else 'disabled'}")
    raise typer.Exit(0)


def _tool_schemas(cfg: Config) -> list[dict[str, Any]]:
    import asyncio

    from mcp.shared.memory import create_connected_server_and_client_session

    from agentprobe.tools.client import MCPToolClient
    from agentprobe.tools.server import build_server

    async def do() -> list[dict[str, Any]]:
        server = build_server(include_user=False)
        async with create_connected_server_and_client_session(server) as session:
            client = MCPToolClient(session, set(cfg.tools.enabled), {})
            return await client.schemas()

    return asyncio.run(do())


def _dry_run_scenarios(
    cfg: Config,
    paths: list[Path],
    filter: str | None,
    filter_name: str | None,
) -> None:
    import re

    from agentprobe.scenario.schema import load_scenario

    seen: set[str] = set()
    unique: list[Path] = []
    for p in paths:
        rp = str(p.resolve())
        if rp not in seen:
            seen.add(rp)
            unique.append(p)
    scenarios = [load_scenario(p) for p in unique]
    if filter:
        scenarios = [s for s in scenarios if filter in s.checks.tags]
    if filter_name:
        scenarios = [s for s in scenarios if re.search(filter_name, s.name)]
    for s in scenarios:
        checks = s.effective_defaults(cfg.app.scenario_defaults)
        msg = s.initial_message[:50] + ("…" if len(s.initial_message) > 50 else "")
        print(
            f"{s.name}\tinitial={msg!r}\ttransitions={len(s.transitions)}\t"
            f"max_agent_messages={checks.max_agent_messages} "
            f"max_context_tokens={checks.max_context_tokens} "
            f"max_duration_secs={checks.max_duration_secs}"
        )
