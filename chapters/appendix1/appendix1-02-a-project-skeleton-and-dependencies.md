# Appendix: Code Snippets and Examples

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

