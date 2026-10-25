import time

import pytest

from agentprobe.agent.observer import NoOpObserver, SessionCtx
from agentprobe.agent.orchestrator import Orchestrator
from agentprobe.agent.ui import NoOpUi
from agentprobe.config import Limits
from agentprobe.errors import LimitExceeded


def _orchestrator(limits: Limits) -> Orchestrator:
    return Orchestrator(
        llm=None,  # type: ignore[arg-type]
        tools=None,  # type: ignore[arg-type]
        observer=NoOpObserver(),
        logger=None,  # type: ignore[arg-type]
        limits=limits,
        ui=NoOpUi(),
    )


def test_context_tokens_within_limit_ok() -> None:
    lim = Limits(max_context_tokens=100)
    orch = _orchestrator(lim)
    ctx = SessionCtx(context_tokens_max=90)
    # No exception raised when below the app-level context limit.
    orch._check_limits(ctx, turn_start=time.monotonic())


def test_context_tokens_exceeds_limit_raises() -> None:
    lim = Limits(max_context_tokens=100)
    orch = _orchestrator(lim)
    ctx = SessionCtx(context_tokens_max=150)
    with pytest.raises(LimitExceeded) as ei:
        orch._check_limits(ctx, turn_start=time.monotonic())
    assert ei.value.reason == "max_context_tokens"
    assert ei.value.limit == 100
    assert ei.value.actual == 150


def test_context_tokens_limit_zero_disabled() -> None:
    # max_context_tokens = 0 disables the context check entirely.
    lim = Limits(max_context_tokens=0)
    orch = _orchestrator(lim)
    ctx = SessionCtx(context_tokens_max=10_000)
    orch._check_limits(ctx, turn_start=time.monotonic())


def test_context_tokens_respected_alongside_duration() -> None:
    # Duration is checked before the context check, so a large turn_start
    # aborts on duration rather than context.
    lim = Limits(max_turns=5, max_context_tokens=100)
    orch = _orchestrator(lim)
    ctx = SessionCtx(turn=1, context_tokens_max=50)
    with pytest.raises(LimitExceeded) as ei:
        orch._check_limits(ctx, turn_start=0.0)
    assert ei.value.reason == "max_duration_secs"
