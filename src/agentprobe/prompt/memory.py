"""Helpers for reading/editing the agent memory file."""

from __future__ import annotations

from pathlib import Path


def read_memory(memory_file: Path) -> str:
    """Return the current memory contents, or empty string if absent."""
    if not memory_file.exists():
        return ""
    return memory_file.read_text(encoding="utf-8")
