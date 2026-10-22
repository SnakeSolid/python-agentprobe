# Technical Specification: `agentprobe` — Asynchronous LLM Agent for E2E Testing

## 6. LLM Client

### 6.1. SDK and Transport

- `openai.AsyncOpenAI(base_url=endpoint, api_key=api_key, http_client=httpx.AsyncClient(proxy=proxy, trust_env=False, timeout=...))`.
- Request: `client.chat.completions.create(model=..., messages=..., tools=..., tool_choice="auto", temperature=..., stream=True, stream_options={"include_usage": True})`.
- `stream_options={"include_usage": True}` is **mandatory** to receive `usage` in the final chunk (for providers supporting the OpenAI protocol).

### 6.2. Streaming

- Incrementally accumulate `content` and `tool_calls` (keyed by `index`).
- In REPL, print `content` as it arrives.
- Accumulate `usage` from the chunk with `finish_reason` or from the last chunk where `usage != null`.

### 6.3. Response Metrics

`ttft_ms`, `latency_ms`, `tokens_in`, `tokens_out`, `tokens_total` — all derived from `usage` (or `null`, see §3.4).

### 6.4. Retries and Timeouts

- 3 attempts, exponential backoff: 1s / 2s / 4s + jitter.
- Retry on: `429`, `5xx`, `httpx.TimeoutException`, `httpx.ConnectError`, `openai.APITimeoutError`, `openai.APIConnectionError`.
- Do not retry other `4xx`.
- Total per-request timeout — `request_timeout_secs`.

### 6.5. `--record` / `--replay`

**Both flags require an explicit path.** No defaults. Missing path → `exit 2`.

- **`--record PATH`**:
  - If `PATH` is a **directory** → writes `<PATH>/<scenario_name>.jsonl` for each scenario. The directory is created if absent; its parent must exist (else `exit 2`).
  - If `PATH` is a **file** → allowed only with a single `--scenario <file>` (otherwise `exit 2`).
  - One line per turn: `{"turn": int, "response": <OpenAI-compatible assistant message + usage>, "request_meta": {"model": ..., "tools_count": ...}}`.
- **`--replay PATH`**: no LLM calls; reads saved responses in order. Missing per-scenario file → that scenario ends with `exit 4`, remaining scenarios continue.
- `--record` and `--replay` are mutually exclusive (`exit 2` if both given).
- **Only YAML artifacts are allowed for spec-defined outputs; the fixture format is JSONL** (one JSON object per line) — this is the sole exception because it must be replayable line-by-line, and it is explicitly part of the `--record`/`--replay` contract, not a general output format. The rule "YAML only" (§1.3, §8 of the delta) applies to configs, logs, and summaries.

---

