# Appendix: Code Snippets and Examples

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

