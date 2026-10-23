"""Metric aggregation helpers (tokens, tools, duration)."""

from __future__ import annotations

from agentprobe.llm.types import Usage


def add_usage(total: dict[str, int] | None, usage: Usage | None) -> dict[str, int] | None:
    """Accumulate non-null usage values; returns None if all values are null."""
    if usage is None:
        return total
    values = {
        "tokens_in": usage.prompt_tokens,
        "tokens_out": usage.completion_tokens,
        "tokens_total": usage.total_tokens,
    }
    if total is None:
        total = {"tokens_in": 0, "tokens_out": 0, "tokens_total": 0}
    for key, val in values.items():
        total[key] = (total.get(key) or 0) + val
    return total


def format_duration(ms: float) -> str:
    secs = ms / 1000.0
    if secs < 60:
        return f"{secs:.1f}s"
    m = int(secs // 60)
    s = secs - m * 60
    return f"{m}m {s:.1f}s"
