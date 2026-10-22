# Appendix: Code Snippets and Examples

## O. CLI (`typer`)

### O.1. `src/agentprobe/cli.py`

```python
from __future__ import annotations
from pathlib import Path
from typing import Optional
import asyncio
import typer

from agentprobe.config import load_config
from agentprobe.errors import ConfigError

app = typer.Typer(no_args_is_help=True)


@app.command()
def repl(
    config: Path = typer.Option(..., "--config", exists=True),
) -> None:
    """Interactive REPL mode."""
    cfg = load_config(config)
    from agentprobe.repl.app import run_repl
    asyncio.run(run_repl(cfg, config))


@app.command()
def run(
    config: Path = typer.Option(..., "--config", exists=True),
    scenario: list[Path] = typer.Option([], "--scenario"),
    scenario_dir: Optional[Path] = typer.Option(None, "--scenario-dir"),
    scenario_glob: Optional[str] = typer.Option(None, "--scenario-glob"),
    filter: Optional[str] = typer.Option(None, "--filter"),
    filter_name: Optional[str] = typer.Option(None, "--filter-name"),
    parallel: int = typer.Option(1, "--parallel", min=1),
    fail_fast: bool = typer.Option(False, "--fail-fast"),
    workspace_mode: str = typer.Option("copy", "--workspace-mode",
                                       case_sensitive=False),
    keep_workspace: bool = typer.Option(False, "--keep-workspace"),
    record: Optional[Path] = typer.Option(None, "--record"),
    replay: Optional[Path] = typer.Option(None, "--replay"),
    summary: bool = typer.Option(False, "--summary"),
    summary_format: str = typer.Option("table", "--summary-format"),
    summary_file: Optional[Path] = typer.Option(None, "--summary-file"),
) -> None:
    """Headless mode: run one or more scenarios."""
    if record and replay:
        raise typer.Exit(2)
    if (record or replay) and not (record or replay).parent.exists():
        raise typer.Exit(2)
    if workspace_mode not in ("copy", "shared", "fresh"):
        raise typer.Exit(2)
    if summary_format not in ("table", "list"):
        raise typer.Exit(2)
    cfg = load_config(config)
    from agentprobe.scenario.runner import Runner
    args = typer.Context and None  # placeholder; build SimpleNamespace
    import types
    args = types.SimpleNamespace(
        config=str(config), scenario=scenario,
        scenario_dir=scenario_dir, scenario_glob=scenario_glob,
        filter=filter, filter_name=filter_name,
        parallel=parallel, fail_fast=fail_fast,
        workspace_mode=workspace_mode, keep_workspace=keep_workspace,
        record=str(record) if record else None,
        replay=str(replay) if replay else None,
        summary=summary or summary_file is not None,
        summary_format=summary_format,
        summary_file=str(summary_file) if summary_file else None,
    )
    try:
        code = asyncio.run(Runner(cfg, args).run_all())
    except ConfigError as e:
        typer.echo(f"config error: {e}", err=True)
        raise typer.Exit(2)
    raise typer.Exit(code)


@app.command("dry-run")
def dry_run(
    config: Path = typer.Option(..., "--config", exists=True),
    scenario: list[Path] = typer.Option([], "--scenario"),
) -> None:
    """Print the assembled prompt, tool schemas, skills, and paths."""
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
    typer.echo(f"docs_dir: {cfg.app.docs_dir}")
    typer.echo(f"skills_dir: {cfg.app.skills_dir}")
    typer.echo(f"memory_file: {cfg.app.memory_file}")
    typer.echo(f"spawn_agent: {'enabled' if cfg.models.subagent else 'disabled'}")
    raise typer.Exit(0)
```

---

