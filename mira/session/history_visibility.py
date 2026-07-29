"""Visibility helpers for persisted session history messages."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from mira.session.automation_turns import is_automation_history_message

HIDDEN_HISTORY_META = "_hidden_history"


def _has_hidden_history_marker(message: Mapping[str, Any] | None) -> bool:
    if not message:
        return False
    marker = message.get(HIDDEN_HISTORY_META)
    return marker is True or isinstance(marker, Mapping)


def is_hidden_history_message(message: Mapping[str, Any] | None) -> bool:
    """True for persisted messages that should not be shown as chat turns."""
    if not message:
        return False
    if _has_hidden_history_marker(message) or is_automation_history_message(message):
        return True
    return message.get("_cron_history") is True
