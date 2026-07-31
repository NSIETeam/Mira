"""Structured log context helpers."""

from __future__ import annotations

from typing import Any

from loguru import logger


def session_logger(session_key: str | None, **extra: Any):
    """Return a logger bound to a session when one is available."""
    fields = dict(extra)
    fields["session_key"] = session_key
    return logger.bind(**fields)


def turn_logger(session_key: str | None, turn_id: str | None = None, **extra: Any):
    """Return a logger bound to a session turn."""
    fields = dict(extra)
    if turn_id:
        fields["turn_id"] = turn_id
    return session_logger(session_key, **fields)


def tool_logger(
    session_key: str | None,
    tool_call_id: str | None,
    tool_name: str | None,
    **extra: Any,
):
    """Return a logger bound to a model-requested tool call."""
    fields = dict(extra)
    if tool_call_id:
        fields["tool_call_id"] = tool_call_id
    if tool_name:
        fields["tool_name"] = tool_name
    return session_logger(session_key, **fields)
