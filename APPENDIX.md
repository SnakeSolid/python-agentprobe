# Appendix: Code Snippets and Examples

This appendix provides implementation-oriented code for the `agentprobe` specification (v1.3). It is not a complete implementation; it is a set of **coherent, adapt-as-needed** snippets that map to the spec's sections. All snippets are Python 3.11+, Pydantic v2, `openai` SDK, and the `mcp` SDK.

**Reading guide:** each section is prefixed with the spec section it implements (e.g., "§7 → Orchestrator").

---

## A. Project skeleton and dependencies

### A.1. `pyproject.toml`

```toml
[project]
name = "agentprobe"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "openai>=1.40",
    "httpx[http2]>=0.27",
    "mcp>=1.0",
    "pydantic>=2.7",
    "pyyaml>=6.0",
    "rich>=13.7",
    "typer>=0.12",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.23", "ruff>=0.5", "mypy>=1.10"]

[project.scripts]
agentprobe = "agentprobe.cli:app"

[tool.ruff]
line-length = 100

[tool.mypy]
strict = true
python_version = "3.11"

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

### A.2. Entry point `src/agentprobe/__main__.py`

```python
from agentprobe.cli import app

if __name__ == "__main__":
    app()
```

---

## B. Core types

### B.1. `src/agentprobe/llm/types.py`

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Literal


Role = Literal["system", "user", "assistant", "tool"]


@dataclass
class Usage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class AssistantMessage:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage | None = None
    ttft_ms: float | None = None
    latency_ms: float | None = None
    raw: dict[str, Any] | None = None  # original response for record


@dataclass
class ToolResult:
    call_id: str
    name: str
    content: str
    is_error: bool = False
    duration_ms: float = 0.0
    artifacts: dict[str, Any] = field(default_factory=dict)


@dataclass
class Message:
    role: Role
    content: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    name: str | None = None

    def to_openai(self) -> dict[str, Any]:
        out: dict[str, Any] = {"role": self.role}
        if self.content is not None:
            out["content"] = self.content
        if self.tool_calls:
            out["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": __import__("json").dumps(tc.arguments),
                    },
                }
                for tc in self.tool_calls
            ]
        if self.tool_call_id is not None:
            out["tool_call_id"] = self.tool_call_id
        if self.name is not None:
            out["name"] = self.name
        return out
```

### B.2. `src/agentprobe/errors.py`

```python
class AgentProbeError(Exception):
    """Base class for all application errors."""


class ConfigError(AgentProbeError):
    """Configuration or scenario validation failure. Exit code 2."""


class SandboxViolation(AgentProbeError):
    """Path escapes the allowed root."""


class LimitExceeded(AgentProbeError):
    """General limits (turns/tool_calls/duration) exceeded. Exit code 3."""

    def __init__(self, reason: str, limit: int | float, actual: int | float):
        super().__init__(reason)
        self.reason = reason
        self.limit = limit
        self.actual = actual


class LLMError(AgentProbeError):
    """LLM request failed after retries. Exit code 4."""


class ReplayError(LLMError):
    """Replay fixture missing or exhausted. Exit code 4."""


class ScenarioAbort(Exception):
    """Raised by ScenarioObserver to abort a scenario immediately."""

    def __init__(self, reason: str, exit_code: int):
        super().__init__(reason)
        self.reason = reason
        self.exit_code = exit_code
```

---

## C. Configuration models

### C.1. `src/agentprobe/config.py`

```python
from __future__ import annotations
import os, re
from pathlib import Path
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator


_ENV_PATTERN = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


def _substitute_env(value: Any) -> Any:
    if isinstance(value, str):
        def repl(m: re.Match[str]) -> str:
            name = m.group(1)
            if name not in os.environ:
                raise ValueError(f"missing env var: {name}")
            return os.environ[name]
        return _ENV_PATTERN.sub(repl, value)
    if isinstance(value, dict):
        return {k: _substitute_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_env(v) for v in value]
    return value


class ScenarioDefaults(BaseModel):
    turn_timeout_secs: float = 120
    max_agent_messages: int = 30
    max_context_tokens: int = 200_000
    max_duration_secs: float = 300


class AppSection(BaseModel):
    workspace: Path
    docs_dir: Path
    skills_dir: Path
    prompt_file: Path
    subagent_prompt_file: Path | None = None
    memory_file: Path
    user_tools_dir: Path | None = None
    log_dir: Path
    tool_transport: Literal["in_memory", "stdio"] = "in_memory"
    scenario_defaults: ScenarioDefaults = ScenarioDefaults()


class ModelConfig(BaseModel):
    endpoint: str
    api_key: str
    model: str
    temperature: float = 0.6
    request_timeout_secs: float = 120
    max_retries: int = 3
    proxy: str | None = None


class ModelsSection(BaseModel):
    main: ModelConfig
    subagent: ModelConfig | None = None  # None → spawn_agent unavailable


class Limits(BaseModel):
    max_turns: int = 35
    max_tool_calls: int = 100
    max_duration_secs: float = 600
    max_context_tokens: int = 1_000_000


class LimitsSection(BaseModel):
    main: Limits = Limits()
    subagent: Limits = Limits(
        max_turns=20, max_tool_calls=50,
        max_duration_secs=300, max_context_tokens=200_000,
    )


class ToolsSection(BaseModel):
    enabled: list[str] = Field(default_factory=list)


class LoggingSection(BaseModel):
    console_level: Literal["quiet", "info", "verbose"] = "info"
    console_truncate_chars: int = 400
    color: Literal["auto", "always", "never"] = "auto"


class Config(BaseModel):
    app: AppSection
    models: ModelsSection
    limits: LimitsSection
    tools: ToolsSection
    logging: LoggingSection = LoggingSection()

    @field_validator("*", mode="before")
    @classmethod
    def _env(cls, v: Any) -> Any:
        return _substitute_env(v)

    def validate_paths(self) -> None:
        for p in (self.app.workspace, self.app.docs_dir, self.app.skills_dir,
                  self.app.prompt_file.parent, self.app.log_dir):
            if not p.exists():
                raise ValueError(f"path does not exist: {p}")


def load_config(path: Path) -> Config:
    import yaml
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    cfg = Config.model_validate(raw)
    cfg.validate_paths()
    return cfg
```

**Note:** `field_validator("*", mode="before")` runs on every field, substituting `${VAR}` before validation. Extend if you want per-field control.

---

## D. Scenario schema

### D.1. `src/agentprobe/scenario/schema.py`

```python
from __future__ import annotations
import re
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field, field_validator

from agentprobe.config import ScenarioDefaults


class Transition(BaseModel):
    message: str
    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    once: bool = False

    @field_validator("include", "exclude")
    @classmethod
    def _compile_check(cls, pats: list[str]) -> list[str]:
        for p in pats:
            re.compile(p)  # raises if invalid
        return pats


class Checks(BaseModel):
    tags: list[str] = Field(default_factory=list)
    final_include: list[str] = Field(default_factory=list)
    final_exclude: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    max_agent_messages: int | None = None
    max_context_tokens: int | None = None
    max_duration_secs: float | None = None

    @field_validator("final_include", "final_exclude")
    @classmethod
    def _compile_check(cls, pats: list[str]) -> list[str]:
        for p in pats:
            re.compile(p)
        return pats


class Timeouts(BaseModel):
    turn_secs: float | None = None


class Scenario(BaseModel):
    name: str
    description: str | None = None
    initial_message: str
    tool_vars: dict[str, dict[str, Any]] = Field(default_factory=dict)
    transitions: list[Transition] = Field(default_factory=list)
    checks: Checks = Checks()
    timeouts: Timeouts = Timeouts()

    def effective_defaults(self, d: ScenarioDefaults) -> Checks:
        """Fill None values in checks from scenario defaults."""
        return Checks(
            tags=self.checks.tags,
            final_include=self.checks.final_include,
            final_exclude=self.checks.final_exclude,
            required_tools=self.checks.required_tools,
            forbidden_tools=self.checks.forbidden_tools,
            max_agent_messages=self.checks.max_agent_messages or d.max_agent_messages,
            max_context_tokens=self.checks.max_context_tokens or d.max_context_tokens,
            max_duration_secs=self.checks.max_duration_secs or d.max_duration_secs,
        )


def load_scenario(path: Path) -> Scenario:
    import yaml
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return Scenario.model_validate(raw)
```

---

## E. Sandbox

### E.1. `src/agentprobe/tools/sandbox.py`

```python
from __future__ import annotations
import os
from pathlib import Path

from agentprobe.errors import SandboxViolation


class Sandbox:
    """Constrains all path resolution to a single root directory."""

    def __init__(self, root: Path):
        self.root = root.resolve()

    @classmethod
    def from_env(cls, env_var: str = "AGENTPROBE_WORKSPACE") -> "Sandbox":
        raw = os.environ.get(env_var)
        if not raw:
            raise SandboxViolation(f"{env_var} is not set")
        return cls(Path(raw))

    def resolve(self, user_path: str) -> Path:
        candidate = (self.root / user_path).resolve()
        # commonpath ensures `candidate` is inside `self.root`
        try:
            if Path(os.path.commonpath([self.root, candidate])) != self.root:
                raise SandboxViolation(f"path escapes root: {user_path}")
        except ValueError:  # different drives (Windows) or unresolvable
            raise SandboxViolation(f"path escapes root: {user_path}")
        return candidate
```

**Test sketch:**

```python
def test_sandbox_escapes(tmp_path):
    sb = Sandbox(tmp_path)
    with pytest.raises(SandboxViolation):
        sb.resolve("../../etc/passwd")

def test_sandbox_symlink_escapes(tmp_path):
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("x")
    (tmp_path / "link").symlink_to(outside)
    sb = Sandbox(tmp_path)
    with pytest.raises(SandboxViolation):
        sb.resolve("link")
```

---

## F. Tool contract (MCP, idiomatic)

### F.1. Tool module convention

- One file per tool under `tools/builtin/` or `user_tools_dir/`.
- Each file defines `register(mcp: FastMCP) -> None`.
- Parameters use `Annotated[T, Field(...)]` so FastMCP generates a schema with per-field descriptions and constraints.
- Context (workspace, `tool_vars`) is read from environment variables set by the runner (`AGENTPROBE_WORKSPACE`, `AGENTPROBE_TOOL_VARS`).
- Return a `str`; use the `ERROR: <code>: <msg>` prefix for business errors.

### F.2. `src/agentprobe/tools/server.py`

```python
from __future__ import annotations
import importlib, pkgutil
from pathlib import Path
from mcp.server.fastmcp import FastMCP

from agentprobe.errors import ConfigError


def build_server(*module_dirs: Path) -> FastMCP:
    """Build a FastMCP server, importing all tool modules from given directories."""
    mcp = FastMCP("agentprobe-tools")

    for d in module_dirs:
        if d is None:
            continue
        for info in pkgutil.iter_modules([str(d)]):
            if info.name.startswith("_"):
                continue
            mod = importlib.import_module(f"{info.module_finder.path}/{info.name}"
                                          .replace("/", ".")) if False else \
                  __import_from_path(d, info.name)
            if not hasattr(mod, "register"):
                raise ConfigError(f"{d / info.name}.py has no register(mcp)")
            mod.register(mcp)

    return mcp


def __import_from_path(d: Path, name: str):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, d / f"{name}.py")
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def cli_main() -> None:
    """Entry point for `python -m agentprobe.tools.server` (stdio transport)."""
    from agentprobe.config import load_config
    import os
    cfg_path = os.environ["AGENTPROBE_CONFIG"]
    cfg = load_config(Path(cfg_path))
    dirs = [Path(__file__).parent / "builtin"]
    if cfg.app.user_tools_dir:
        dirs.append(cfg.app.user_tools_dir)
    mcp = build_server(*dirs)
    mcp.run(transport="stdio")
```

**Note:** The exact import mechanism depends on whether tools are shipped as a Python package or loose files. The snippet above uses `spec_from_file_location` for loose files. If you ship tools as a subpackage (`agentprobe.tools.builtin`), simplify to `importlib.import_module(f"agentprobe.tools.builtin.{name}")`.

---

## G. Tool implementations (selected)

### G.1. `read`

```python
# src/agentprobe/tools/builtin/read.py
from typing import Annotated, Literal
from pydantic import Field
from mcp.server.fastmcp import FastMCP

from agentprobe.tools.sandbox import Sandbox


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="read",
        description=(
            "Read a text file inside the workspace. Truncates to `limit` chars "
            "and appends a marker when truncated. Fails on paths escaping the workspace."
        ),
    )
    async def read(
        path: Annotated[str, Field(
            description="Path to a text file, relative to the workspace root. "
                        "Absolute paths are rejected unless inside the workspace.",
            min_length=1, max_length=4096,
        )],
        offset: Annotated[int, Field(
            description="Byte offset to start reading from (0-based).", ge=0,
        )] = 0,
        limit: Annotated[int, Field(
            description="Maximum number of characters to return.", ge=1, le=1_000_000,
        )] = 100_000,
        encoding: Annotated[Literal["utf-8", "utf-8-sig", "latin-1"], Field(
            description="Text encoding used to decode the file.",
        )] = "utf-8",
    ) -> str:
        try:
            sb = Sandbox.from_env()
            target = sb.resolve(path)
            text = target.read_bytes().decode(encoding, errors="replace")
        except Exception as e:
            return f"ERROR: io_error: {e}"
        chunk = text[offset: offset + limit]
        if offset + limit < len(text):
            chunk += f"\n… [truncated {len(text) - offset - limit} chars]"
        return chunk
```

### G.2. `write`

```python
# src/agentprobe/tools/builtin/write.py
from typing import Annotated
from pydantic import Field
from mcp.server.fastmcp import FastMCP

from agentprobe.tools.sandbox import Sandbox


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="write",
        description="Create a NEW text file inside the workspace. Fails if it already "
                    "exists. Parent directories are not created.",
    )
    async def write(
        path: Annotated[str, Field(description="Relative path in the workspace.",
                                   min_length=1, max_length=4096)],
        content: Annotated[str, Field(description="File content (UTF-8).",
                                       max_length=1_000_000)],
    ) -> str:
        try:
            sb = Sandbox.from_env()
            target = sb.resolve(path)
            if target.exists():
                return f"ERROR: exists: {path}"
            if not target.parent.exists():
                return f"ERROR: missing_parent: {target.parent}"
            target.write_text(content, encoding="utf-8")
            return f"OK: wrote {len(content)} chars to {path}"
        except Exception as e:
            return f"ERROR: io_error: {e}"
```

### G.3. `command_execute` (mock with `tool_vars`)

```python
# src/agentprobe/tools/builtin/command_execute.py
import json
from typing import Annotated
from pydantic import Field
from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="command_execute",
        description="Mock command execution. Returns a fixed success, or a response "
                    "configured via scenario `tool_vars.command_execute.responses`.",
    )
    async def command_execute(
        command: Annotated[str, Field(description="VRP command to execute (mock).",
                                       min_length=1, max_length=8000)],
    ) -> str:
        from agentprobe.tools.vars import get_tool_vars
        tv = get_tool_vars().get("command_execute", {})
        responses: dict[str, str] = tv.get("responses", {})
        fail_on: list[str] = tv.get("fail_on", [])

        if command in responses:
            return responses[command]
        if any(sub in command for sub in fail_on):
            return f"ERROR: forbidden: {command}"
        return json.dumps({"ok": True, "output": "(mock) command accepted"})
```

### G.4. `syntax_check`

```python
# src/agentprobe/tools/builtin/syntax_check.py
import json
from typing import Annotated
from pydantic import Field
from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="syntax_check",
        description="Basic VRP syntax validation. Rejects '?' and 'commit' tokens. "
                    "Returns JSON {ok, errors}. This is a result, not an error.",
    )
    async def syntax_check(
        commands: Annotated[str, Field(description="Multi-line VRP script.",
                                        max_length=100_000)],
    ) -> str:
        errors: list[str] = []
        for i, raw in enumerate(commands.splitlines(), start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "?" in line:
                errors.append(f"line {i}: '?' not allowed")
            if "commit" in line.split():
                errors.append(f"line {i}: 'commit' not allowed")
        return json.dumps({"ok": not errors, "errors": errors})
```

### G.5. `read_skill`

```python
# src/agentprobe/tools/builtin/read_skill.py
from pathlib import Path
from typing import Annotated
import os
from pydantic import Field
from mcp.server.fastmcp import FastMCP
import yaml

from agentprobe.tools.sandbox import Sandbox


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="read_skill",
        description="Load the body of a skill (SKILL.md). Frontmatter is stripped.",
    )
    async def read_skill(
        name: Annotated[str, Field(description="Skill folder name.",
                                    min_length=1, max_length=128)],
    ) -> str:
        try:
            skills_root = Sandbox(Path(os.environ["AGENTPROBE_SKILLS_DIR"]))
            target = skills_root.resolve(f"{name}/SKILL.md")
            text = target.read_text(encoding="utf-8")
            # strip frontmatter
            if text.startswith("---"):
                parts = text.split("---", 2)
                if len(parts) >= 3:
                    return parts[2].lstrip("\n")
            return text
        except Exception as e:
            return f"ERROR: skill_not_found: {e}"
```

### G.6. `spawn_agent` (registered conditionally)

```python
# src/agentprobe/tools/builtin/spawn_agent.py
# This tool is special: it is NOT a plain MCP tool. It's registered by the
# orchestrator because it needs access to the parent's config, session,
# observer, and LLM client. In the MCP server, it appears as a regular tool,
# but its implementation delegates to the parent process via a callback
# mechanism (see orchestrator snippet H).

# See §7.2 / §8 for full behavior. The parameters:
#   task: str [1..8000]
#   context: str [0..32000]
# Returns JSON: {answer, usage, turns, tools, is_error, error}
```

**Note:** `spawn_agent` is implemented **in-process** (not as an MCP round-trip), because it needs to launch a nested LLM loop with its own session. The orchestrator registers its schema alongside MCP tools but intercepts calls to it before dispatching to MCP.

---

## H. `tool_vars` access

### H.1. `src/agentprobe/tools/vars.py`

```python
import json, os
from typing import Any


def get_tool_vars() -> dict[str, dict[str, Any]]:
    raw = os.environ.get("AGENTPROBE_TOOL_VARS")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}
```

The runner sets `AGENTPROBE_TOOL_VARS=<json>` when spawning the MCP subprocess (for `stdio` transport) or via `os.environ` for `in_memory` transport.

---

## I. LLM client

### I.1. `src/agentprobe/llm/client.py`

```python
from __future__ import annotations
import asyncio, time
from typing import Any
import httpx
from openai import AsyncOpenAI
from openai import APIConnectionError, APITimeoutError, RateLimitError

from agentprobe.config import ModelConfig
from agentprobe.errors import LLMError
from agentprobe.llm.types import AssistantMessage, ToolCall, Usage
from agentprobe.llm.fixture import Fixture


class LLMClient:
    def __init__(self, cfg: ModelConfig, fixture: Fixture | None = None):
        self.cfg = cfg
        self.fixture = fixture
        self._http = httpx.AsyncClient(
            proxy=cfg.proxy,
            trust_env=False,
            timeout=httpx.Timeout(cfg.request_timeout_secs),
        )
        self._client = AsyncOpenAI(
            base_url=cfg.endpoint,
            api_key=cfg.api_key,
            http_client=self._http,
            max_retries=0,  # we retry manually to control fixture replay
        )
        self._seq = 0  # fixture sequencing

    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
                   ) -> AssistantMessage:
        if self.fixture is not None:
            self._seq += 1
            return await self.fixture.next_response(self._seq)

        last_exc: Exception | None = None
        for attempt in range(self.cfg.max_retries):
            try:
                return await self._stream(messages, tools)
            except (RateLimitError, APIConnectionError, APITimeoutError) as e:
                last_exc = e
                await asyncio.sleep(2 ** attempt + 0.1)
            except Exception as e:
                # Non-retriable
                raise LLMError(f"{type(e).__name__}: {e}") from e
        raise LLMError(f"LLM failed after {self.cfg.max_retries} retries: {last_exc}")

    async def _stream(self, messages, tools) -> AssistantMessage:
        t0 = time.monotonic()
        ttft: float | None = None
        content_parts: list[str] = []
        tool_calls_acc: dict[int, dict[str, Any]] = {}
        usage: Usage | None = None

        stream = await self._client.chat.completions.create(
            model=self.cfg.model,
            messages=messages,  # type: ignore[arg-type]
            tools=tools,        # type: ignore[arg-type]
            tool_choice="auto" if tools else "none",
            temperature=self.cfg.temperature,
            stream=True,
            stream_options={"include_usage": True},
        )

        async for chunk in stream:
            if ttft is None:
                ttft = (time.monotonic() - t0) * 1000
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                content_parts.append(delta.content)
            if delta and delta.tool_calls:
                for tc in delta.tool_calls:
                    acc = tool_calls_acc.setdefault(tc.index, {
                        "id": "", "name": "", "arguments": "",
                    })
                    if tc.id:
                        acc["id"] = tc.id
                    if tc.function and tc.function.name:
                        acc["name"] += tc.function.name
                    if tc.function and tc.function.arguments:
                        acc["arguments"] += tc.function.arguments
            if chunk.usage is not None:
                usage = Usage(
                    prompt_tokens=chunk.usage.prompt_tokens,
                    completion_tokens=chunk.usage.completion_tokens,
                    total_tokens=chunk.usage.total_tokens,
                )

        latency = (time.monotonic() - t0) * 1000
        import json as _json
        calls = [
            ToolCall(id=v["id"], name=v["name"], arguments=_json.loads(v["arguments"] or "{}"))
            for v in tool_calls_acc.values()
        ]
        return AssistantMessage(
            content="".join(content_parts) or None,
            tool_calls=calls,
            usage=usage,
            ttft_ms=ttft,
            latency_ms=latency,
        )

    async def aclose(self) -> None:
        await self._http.aclose()
```

### I.2. `src/agentprobe/llm/fixture.py`

```python
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

from agentprobe.errors import ReplayError
from agentprobe.llm.types import AssistantMessage, ToolCall, Usage


class Fixture:
    """One fixture per scenario. JSONL: one line per LLM response."""

    def __init__(self, path: Path, mode: str):  # mode: "record" | "replay"
        self.path = path
        self.mode = mode
        self._lines: list[dict[str, Any]] = []
        self._fp = None
        if mode == "replay":
            if not path.exists():
                raise ReplayError(f"fixture not found: {path}")
            self._lines = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
            ]
        else:  # record
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._fp = self.path.open("w", encoding="utf-8")

    async def next_response(self, seq: int) -> AssistantMessage:
        if self.mode == "replay":
            if seq > len(self._lines):
                raise ReplayError(f"fixture exhausted at seq={seq}: {self.path}")
            line = self._lines[seq - 1]
            resp = line["response"]
            return AssistantMessage(
                content=resp.get("content"),
                tool_calls=[
                    ToolCall(id=tc["id"], name=tc["name"], arguments=tc["arguments"])
                    for tc in resp.get("tool_calls", [])
                ],
                usage=Usage(**resp["usage"]) if resp.get("usage") else None,
            )
        raise RuntimeError("record mode does not call next_response")

    def record(self, seq: int, turn: int, msg: AssistantMessage,
               request_meta: dict[str, Any]) -> None:
        if self._fp is None:
            return
        payload = {
            "seq": seq,
            "turn": turn,
            "request_meta": request_meta,
            "response": {
                "content": msg.content,
                "tool_calls": [
                    {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                    for tc in msg.tool_calls
                ],
                "usage": (
                    {
                        "prompt_tokens": msg.usage.prompt_tokens,
                        "completion_tokens": msg.usage.completion_tokens,
                        "total_tokens": msg.usage.total_tokens,
                    } if msg.usage else None
                ),
            },
        }
        self._fp.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self._fp.flush()

    def close(self) -> None:
        if self._fp is not None:
            self._fp.close()
```

**Wiring:** in `LLMClient._stream`, after a successful response in record mode, call `self.fixture.record(seq, turn, msg, request_meta)`. In replay mode, `next_response` is invoked by `chat`. The `seq` counter increments on every LLM call, not every turn.

---

## J. Prompt builder

### J.1. `src/agentprobe/prompt/builder.py`

```python
from __future__ import annotations
from pathlib import Path


class PromptBuilder:
    def __init__(self, prompt_file: Path, memory_file: Path, skill_loader):
        self._static = prompt_file.read_text(encoding="utf-8")
        self._memory_file = memory_file
        self._skills = skill_loader

    def build(self) -> str:
        memory = ""
        if self._memory_file.exists():
            memory = self._memory_file.read_text(encoding="utf-8").rstrip()
        skills = self._skills.available_skills_block()
        # Replace dynamic markers (present in the static file as "# MEMORY\n" etc.)
        # Simplest approach: append dynamic sections at the end if markers absent.
        parts = [self._static.rstrip()]
        parts.append("# MEMORY")
        parts.append(memory or "(empty)")
        parts.append("# AVAILABLE SKILLS")
        parts.append(skills or "(none)")
        return "\n\n".join(parts)
```

### J.2. `src/agentprobe/skills/loader.py`

```python
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import yaml


@dataclass
class SkillMeta:
    name: str
    description: str
    path: Path


class SkillLoader:
    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir
        self._skills: list[SkillMeta] = []
        self.scan()

    def scan(self) -> None:
        self._skills = []
        for skill_md in self.skills_dir.glob("*/SKILL.md"):
            try:
                text = skill_md.read_text(encoding="utf-8")
                if not text.startswith("---"):
                    continue
                _, fm, _ = text.split("---", 2)
                meta = yaml.safe_load(fm)
                name = meta.get("name")
                desc = meta.get("description")
                if not name or not desc:
                    continue
                if name != skill_md.parent.name:
                    continue  # warning logged elsewhere
                self._skills.append(SkillMeta(name=name, description=desc, path=skill_md))
            except Exception:
                continue

    def available_skills_block(self) -> str:
        if not self._skills:
            return ""
        return "\n".join(
            f"- name: {s.name}\n  description: {s.description}"
            for s in self._skills
        )
```

---

## K. Observer and `ScenarioObserver`

### K.1. `src/agentprobe/agent/observer.py`

```python
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Protocol

from agentprobe.errors import ScenarioAbort
from agentprobe.llm.types import AssistantMessage, ToolCall, ToolResult
from agentprobe.scenario.schema import Checks


@dataclass
class SessionCtx:
    turn: int = 0
    agent_messages: int = 0
    tools_count: int = 0
    tools_histogram: dict[str, int] = field(default_factory=dict)
    context_tokens_max: int = 0
    last_assistant_text: str = ""
    final_text_for_checks: str = ""


class Observer(Protocol):
    async def on_assistant_message(self, msg: AssistantMessage, ctx: SessionCtx) -> None: ...
    async def on_tool_call_pending(self, call: ToolCall, ctx: SessionCtx) -> None: ...
    async def on_tool_result(self, res: ToolResult, ctx: SessionCtx) -> None: ...
    async def on_turn_end(self, ctx: SessionCtx) -> None: ...


class NoOpObserver:
    async def on_assistant_message(self, msg, ctx): ...
    async def on_tool_call_pending(self, call, ctx): ...
    async def on_tool_result(self, res, ctx): ...
    async def on_turn_end(self, ctx): ...


class ScenarioObserver:
    def __init__(self, checks: Checks):
        self.checks = checks

    async def on_assistant_message(self, msg: AssistantMessage, ctx: SessionCtx) -> None:
        ctx.agent_messages += 1
        if self.checks.max_agent_messages is not None \
           and ctx.agent_messages > self.checks.max_agent_messages:
            raise ScenarioAbort("max_agent_messages", exit_code=1)

        if msg.usage is not None:
            used = msg.usage.prompt_tokens + msg.usage.completion_tokens
            ctx.context_tokens_max = max(ctx.context_tokens_max, used)
            if self.checks.max_context_tokens is not None \
               and used > self.checks.max_context_tokens:
                raise ScenarioAbort("max_context_tokens", exit_code=1)

        if msg.content:
            ctx.last_assistant_text = msg.content
            if not msg.tool_calls:
                ctx.final_text_for_checks = msg.content

    async def on_tool_call_pending(self, call: ToolCall, ctx: SessionCtx) -> None:
        if call.name in self.checks.forbidden_tools:
            raise ScenarioAbort(f"forbidden_tool:{call.name}", exit_code=1)

    async def on_tool_result(self, res: ToolResult, ctx: SessionCtx) -> None:
        ctx.tools_count += 1
        ctx.tools_histogram[res.name] = ctx.tools_histogram.get(res.name, 0) + 1

    async def on_turn_end(self, ctx: SessionCtx) -> None:
        pass

    def final_checks(self, ctx: SessionCtx) -> list[str]:
        failures: list[str] = []
        text = ctx.final_text_for_checks
        for pat in self.checks.final_include:
            if not re.search(pat, text, re.MULTILINE):
                failures.append(f'final_include: missing "{pat}"')
        for pat in self.checks.final_exclude:
            if re.search(pat, text, re.MULTILINE):
                failures.append(f'final_exclude: matched "{pat}"')
        for required in self.checks.required_tools:
            if required not in ctx.tools_histogram:
                failures.append(f"required_tools: {required} not called")
        return failures
```

---

## L. Orchestrator

### L.1. `src/agentprobe/agent/orchestrator.py` (simplified, single session)

```python
from __future__ import annotations
import asyncio, json, time
from typing import Any

from agentprobe.agent.observer import Observer, SessionCtx
from agentprobe.agent.subagent import SubagentSpawner
from agentprobe.errors import LimitExceeded, ScenarioAbort
from agentprobe.llm.client import LLMClient
from agentprobe.llm.types import AssistantMessage, Message, ToolCall, ToolResult
from agentprobe.logging.yaml_logger import YamlLogger
from agentprobe.tools.client import MCPToolClient


class Orchestrator:
    def __init__(
        self,
        llm: LLMClient,
        tools: MCPToolClient,
        observer: Observer,
        logger: YamlLogger,
        limits,
        spawner: SubagentSpawner | None = None,
        is_repl: bool = False,
    ):
        self.llm = llm
        self.tools = tools
        self.observer = observer
        self.logger = logger
        self.limits = limits
        self.spawner = spawner
        self.is_repl = is_repl

    async def turn(self, messages: list[Message], user_input: str,
                   ctx: SessionCtx) -> str | None:
        """Run one full turn. Returns final assistant text, or None if aborted."""
        ctx.turn += 1
        turn_start = time.monotonic()
        messages.append(Message(role="user", content=user_input))
        self.logger.log("user_message", turn=ctx.turn, text=user_input)

        tools_schema = await self.tools.schemas()
        if self.spawner is not None:
            tools_schema.append(self.spawner.tool_schema())

        try:
            while True:
                self.logger.log("llm_request", turn=ctx.turn,
                                messages_count=len(messages),
                                tools_count=len(tools_schema))
                response = await self.llm.chat(
                    [m.to_openai() for m in messages], tools_schema
                )
                self.logger.log(
                    "llm_response", turn=ctx.turn,
                    content=response.content,
                    tool_calls=[
                        {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                        for tc in response.tool_calls
                    ],
                    usage=response.usage.__dict__ if response.usage else None,
                    ttft_ms=response.ttft_ms,
                    latency_ms=response.latency_ms,
                )
                await self.observer.on_assistant_message(response, ctx)

                messages.append(Message(
                    role="assistant",
                    content=response.content,
                    tool_calls=response.tool_calls or None,
                ))

                if not response.tool_calls:
                    await self.observer.on_turn_end(ctx)
                    return response.content

                # Pre-check all pending calls
                for tc in response.tool_calls:
                    await self.observer.on_tool_call_pending(tc, ctx)

                # Execute
                results = await self._execute_tools(response.tool_calls)
                for res in results:
                    await self.observer.on_tool_result(res, ctx)
                    self.logger.log("tool_result", turn=ctx.turn,
                                    call_id=res.call_id, name=res.name,
                                    is_error=res.is_error,
                                    duration_ms=res.duration_ms,
                                    content=res.content,
                                    artifacts=res.artifacts)
                    messages.append(Message(
                        role="tool",
                        content=res.content,
                        tool_call_id=res.call_id,
                        name=res.name,
                    ))

                # Between-iteration limits
                if not self.is_repl:
                    self._check_limits(ctx, turn_start)
        except ScenarioAbort:
            raise
        except LimitExceeded:
            raise

    async def _execute_tools(self, calls: list[ToolCall]) -> list[ToolResult]:
        # Parallel only if ALL calls are parallel-safe.
        if all(c.name in PARALLEL_SAFE for c in calls):
            return await asyncio.gather(*(self._execute_one(c) for c in calls))
        out = []
        for c in calls:
            out.append(await self._execute_one(c))
        return out

    async def _execute_one(self, call: ToolCall) -> ToolResult:
        t0 = time.monotonic()
        if call.name == "spawn_agent" and self.spawner is not None:
            res = await self.spawner.call(call.arguments)
        else:
            res = await self.tools.call_tool(call.name, call.arguments)
        res.duration_ms = (time.monotonic() - t0) * 1000
        res.call_id = call.id
        return res

    def _check_limits(self, ctx: SessionCtx, turn_start: float) -> None:
        if ctx.turn > self.limits.max_turns:
            raise LimitExceeded("max_turns", self.limits.max_turns, ctx.turn)
        if ctx.tools_count > self.limits.max_tool_calls:
            raise LimitExceeded("max_tool_calls", self.limits.max_tool_calls, ctx.tools_count)
        elapsed = time.monotonic() - turn_start
        if elapsed > self.limits.max_duration_secs:
            raise LimitExceeded("max_duration_secs",
                                self.limits.max_duration_secs, int(elapsed))


PARALLEL_SAFE = {
    "read", "read_doc", "read_skill",
    "command_execute", "execute_shell", "syntax_check",
}
```

### L.2. `src/agentprobe/agent/subagent.py` (sketch)

```python
from __future__ import annotations
from typing import Any

from agentprobe.llm.types import ToolResult


class SubagentSpawner:
    def __init__(self, cfg, limits, llm_factory, tools_factory, prompt, observer_factory):
        self.cfg = cfg
        self.limits = limits
        self._llm_factory = llm_factory
        self._tools_factory = tools_factory
        self._prompt = prompt
        self._observer_factory = observer_factory

    def tool_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "spawn_agent",
                "description": "Delegate an isolated subtask to a subagent. "
                               "The subagent does not see the main dialogue history.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task": {"type": "string", "minLength": 1, "maxLength": 8000},
                        "context": {"type": "string", "maxLength": 32000},
                    },
                    "required": ["task"],
                },
            },
        }

    async def call(self, args: dict[str, Any]) -> ToolResult:
        from agentprobe.agent.orchestrator import Orchestrator
        from agentprobe.agent.observer import SessionCtx, NoOpObserver
        # Build an isolated session (no spawn_agent in the subagent tool list).
        # ... (see §8 for full behavior; return ToolResult with JSON payload)
        return ToolResult(call_id="", name="spawn_agent", content='{"answer": "TODO"}')
```

The subagent loop mirrors the main loop with its own `Session`, `Messages`, and `Limits`. On any error, return `ToolResult(is_error=True, content="subagent aborted: ...")` to the parent.

---

## M. YAML logger

### M.1. `src/agentprobe/logging/yaml_logger.py`

```python
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import yaml


class YamlLogger:
    def __init__(self, path: Path, session_id: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.session_id = session_id
        self._fp = path.open("a", encoding="utf-8")

    def log(self, event: str, **kwargs: Any) -> None:
        payload = {
            "event": event,
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "session_id": self.session_id,
            **kwargs,
        }
        self._fp.write("---\n")
        self._fp.write(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True))
        self._fp.flush()

    def close(self) -> None:
        self._fp.close()


def new_session_id(mode: str) -> str:
    import secrets
    return f"{mode}_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}_{secrets.token_hex(2)}"


def new_run_id() -> str:
    import secrets
    return f"{datetime.now(timezone.utc):%Y%m%d_%H%M%S}_{secrets.token_hex(2)}"
```

---

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

## P. Example unit test (sandbox)

### P.1. `tests/unit/test_sandbox.py`

```python
import pytest
from pathlib import Path
from agentprobe.tools.sandbox import Sandbox
from agentprobe.errors import SandboxViolation


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "a.txt").write_text("hello")
    return tmp_path


def test_resolve_ok(workspace):
    sb = Sandbox(workspace)
    assert sb.resolve("a.txt") == (workspace / "a.txt").resolve()


def test_traversal_rejected(workspace):
    sb = Sandbox(workspace)
    with pytest.raises(SandboxViolation):
        sb.resolve("../etc/passwd")


def test_symlink_escape_rejected(workspace):
    outside = workspace.parent / "outside.txt"
    outside.write_text("x")
    (workspace / "link").symlink_to(outside)
    sb = Sandbox(workspace)
    with pytest.raises(SandboxViolation):
        sb.resolve("link")
```

---

## Q. Example E2E test with `--replay`

### Q.1. Fixture: `tests/fixtures/llm_responses/test_run/firewall_permit_tcp.jsonl`

```jsonl
{"seq":1,"turn":1,"request_meta":{"model":"qwen3.6-27b","tools_count":9},"response":{"content":"Let me check the docs.","tool_calls":[{"id":"call_1","name":"read_doc","arguments":{"name":"vrp_basic"}}],"usage":{"prompt_tokens":1400,"completion_tokens":20,"total_tokens":1420}}}
{"seq":2,"turn":1,"request_meta":{"model":"qwen3.6-27b","tools_count":9},"response":{"content":"I will write the rule to a file.","tool_calls":[{"id":"call_2","name":"write","arguments":{"path":"policy.txt","content":"security-policy\n rule name permit_tcp_10_0_0_0_24\n  destination-address 10.0.0.0/24\n  service tcp\n  action permit\n"}}],"usage":{"prompt_tokens":1600,"completion_tokens":80,"total_tokens":1680}}}
{"seq":3,"turn":1,"request_meta":{"model":"qwen3.6-27b","tools_count":9},"response":{"content":"Wrote the rule to policy.txt. It permits all TCP to 10.0.0.0/24.","tool_calls":[],"usage":{"prompt_tokens":1800,"completion_tokens":30,"total_tokens":1830}}}
```

### Q.2. `tests/e2e/test_firewall.py`

```python
import subprocess, sys, yaml
from pathlib import Path


def test_firewall_replay(tmp_path):
    fixture_dir = Path("tests/fixtures/llm_responses/test_run")
    summary = tmp_path / "summary.yaml"
    result = subprocess.run([
        sys.executable, "-m", "agentprobe", "run",
        "--config", "config/config.yaml",
        "--scenario", "scenarios/firewall_permit_tcp.yaml",
        "--replay", str(fixture_dir),
        "--summary",
        "--summary-file", str(summary),
    ], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    data = yaml.safe_load(summary.read_text())
    assert data["scenarios"][0]["checks"]["passed"] is True
    assert "tcp" in result.stdout.lower()
```

---

## R. Example skill file

### R.1. `skills/huawei_vsys/SKILL.md`

```markdown
---
name: huawei_vsys
description: How to create and configure a virtual system (vsys) on VRPv8.
---

# Creating a vsys

1. Enter system view: `system-view`
2. Create the vsys: `vsys name <name>`
3. Allocate resources: `assign interface <if>`
4. Commit: `engine configuration commit`

**Note:** The `commit` command is forbidden inside `syntax_check`; use it only
as the final step of a live configuration workflow.
```

---

## S. Example complete scenario

### S.1. `scenarios/firewall_permit_tcp.yaml`

```yaml
name: firewall-permit-tcp
description: "Permit all TCP to 10.0.0.0/24"
initial_message: "how to permit all tcp packets to 10.0.0.0/24"

tool_vars:
  command_execute:
    responses:
      "display version": |
        Huawei Versatile Routing Platform Software
        VRP (R) software, Version 8.180 (USG6686F V600R025C10)
    fail_on: ["reboot", "reset"]

transitions:
  - message: "Yes, write it to a file"
    include: ["\\?$", "confirm"]
    exclude: ["done"]
  - message: "Verify the rule"
    include: ["written to", "policy.txt"]
    exclude: []

checks:
  tags: ["firewall", "smoke"]
  final_include: ["tcp", "10\\.0\\.0\\.0/24"]
  final_exclude: ["I cannot", "unknown command"]
  required_tools: ["read_doc", "write"]
  forbidden_tools: ["execute_shell"]
  max_agent_messages: 10
  max_context_tokens: 50000
  max_duration_secs: 120

timeouts:
  turn_secs: 60
```

---

## T. Sample output

### T.1. Console (`--summary`)

```
SCENARIO                     STATUS  REASON                        TURNS  DURATION  EXIT
firewall_permit_tcp          PASS    -                             3      5.4s      0
nat_server_basic             FAIL    forbidden_tool:execute_shell  2      3.1s      1
vsys_create                  LIMIT   max_context_tokens            4      7.8s      3
crash_on_empty               ERROR   LLMTimeoutError               1      120.0s    4
----------------------------------------------------------------------------------------
TOTAL                        -       -                             -      -         4
```

### T.2. `summary.yaml` (fragment)

```yaml
run:
  run_id: 20261022_101500_ab12
  scenarios_total: 4
  parallel: 1
  workspace_mode: copy
  exit_code: 4
scenarios:
  - name: firewall_permit_tcp
    index: 1
    status: PASS
    exit_code: 0
    reason: null
    duration_ms: 5400
    turns: 3
    agent_messages: 4
    tools_histogram: {read_doc: 1, write: 1}
    checks: {passed: true, failures: []}
    log: logs/20261022_101500_ab12/firewall_permit_tcp.yaml
    workspace: null
  # ...
totals:
  passed: 1
  failed: 1
  errored: 1
  skipped: 1
```

### T.3. Per-session log (`firewall_permit_tcp.yaml`, fragment)

```yaml
---
event: session_start
ts: '2026-10-22T10:00:00.123+00:00'
session_id: headless_20261022_100000_ab12
mode: headless
scenario: firewall-permit-tcp
model: qwen3.6-27b
limits: {max_turns: 35, max_tool_calls: 100, max_duration_secs: 600, max_context_tokens: 1000000}
tool_transport: in_memory
tool_vars_keys: [command_execute]
---
event: llm_request
ts: '2026-10-22T10:00:00.500+00:00'
session_id: headless_20261022_100000_ab12
turn: 1
messages_count: 2
tools_count: 9
---
event: llm_response
ts: '2026-10-22T10:00:01.410+00:00'
session_id: headless_20261022_100000_ab12
turn: 1
content: 'Let me check the docs.'
tool_calls:
  - {id: call_1, name: read_doc, arguments: {name: vrp_basic}}
usage: {prompt_tokens: 1400, completion_tokens: 20, total_tokens: 1420}
ttft_ms: 320.0
latency_ms: 910.0
---
event: tool_result
ts: '2026-10-22T10:00:01.415+00:00'
session_id: headless_20261022_100000_ab12
turn: 1
call_id: call_1
name: read_doc
is_error: false
duration_ms: 3.2
content: "<full markdown content>"
artifacts: {}
---
event: session_end
ts: '2026-10-22T10:00:07.300+00:00'
session_id: headless_20261022_100000_ab12
duration_ms: 5432.0
turns: 3
agent_messages: 4
tools_histogram: {read_doc: 1, write: 1}
context_tokens_max: 1830
checks: {passed: true, failures: []}
exit_code: 0
```

---

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
