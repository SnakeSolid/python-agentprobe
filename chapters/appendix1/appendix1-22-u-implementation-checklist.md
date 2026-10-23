# Appendix: Code Snippets and Examples

## U. Implementation checklist

Use this to track progress when building out the spec:

- [ ] `pyproject.toml`, `__main__.py`, `cli.py` skeleton
- [ ] `config.py` with `${VAR}` substitution and validation
- [ ] `errors.py`
- [ ] `llm/types.py`, `llm/client.py` (streaming), `llm/fixture.py` (record/replay)
- [ ] `agent/observer.py` (`ScenarioObserver` with all checks)
- [ ] `agent/orchestrator.py` (single turn, parallel tools, limits)
- [ ] `agent/subagent.py` (`spawn_agent`, depth 1, isolation)
- [ ] `tools/sandbox.py`
- [ ] `tools/server.py` (FastMCP, discovery, `stdio` entry point)
- [ ] `tools/client.py` (in-memory and stdio transports)
- [ ] `tools/vars.py`
- [ ] `tools/builtin/{read,write,edit,read_doc,read_skill,command_execute,execute_shell,syntax_check}.py`
- [ ] `skills/loader.py`, `prompt/builder.py`
- [ ] `logging/yaml_logger.py`, `logging/console.py`, `logging/metrics.py`
- [ ] `scenario/schema.py`, `scenario/runner.py` (multi-run, isolation, summary)
- [ ] `repl/app.py`, `repl/commands.py`
- [ ] `docs/{vrp_basic,security_policy}.md` stubs
- [ ] Example scenario, example skill, example fixture
- [ ] Unit tests: sandbox, tool modules, observer, config
- [ ] E2E test with `--replay`
- [ ] `--dry-run`, `--summary`, `--summary-file`, `--record`, `--replay` flags
- [ ] `--workspace-mode {copy,shared,fresh}`, `--keep-workspace`, `--parallel`, `--fail-fast`
