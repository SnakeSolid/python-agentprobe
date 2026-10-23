# Appendix 2: Session Output Examples (REPL and Test Modes)

## 2.3. Exit code summary

| Scenario | Cause | Output | Exit |
|---|---|---|---|
| PASS | all checks passed | `[scenario x] PASS  turns=…` | `0` |
| FAIL (checks) | `forbidden_tool`, `final_include`, `required_tools`, `max_agent_messages`, `max_context_tokens` | `[scenario x] FAIL  reason=…` | `1` |
| FAIL (config) | YAML/schema/regex | `error: scenario validation failed: …` + `no scenarios executed` | `2` |
| LIMIT | general limits / turn timeout | `[scenario x] LIMIT  reason=…` | `3` |
| ERROR (LLM) | timeout, 5xx after retries | `[scenario x] ERROR  reason=LLMTimeoutError` | `4` |
| ERROR (replay) | fixture missing / exhausted | `[scenario x] ERROR  reason=fixture not found: …` | `4` |
| SKIP | `--fail-fast` | `[scenario x] SKIP  reason=fail-fast` | (not counted) |

---

