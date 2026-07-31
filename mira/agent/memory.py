"""Compatibility facade for memory store, Dream helpers, and session compaction."""

from __future__ import annotations

from datetime import datetime

from mira.agent.memory_compact import Consolidator
from mira.agent.memory_dream import DreamRunProgress
from mira.agent.memory_store import (
    _ARCHIVE_SUMMARY_MAX_CHARS,
    _HISTORY_ENTRY_HARD_CAP,
    _RAW_ARCHIVE_MAX_CHARS,
    MemoryStore,
)
from mira.utils.helpers import estimate_message_tokens
from mira.utils.prompt_templates import render_template

__all__ = [
    "_ARCHIVE_SUMMARY_MAX_CHARS",
    "_HISTORY_ENTRY_HARD_CAP",
    "_RAW_ARCHIVE_MAX_CHARS",
    "Consolidator",
    "DreamRunProgress",
    "MemoryStore",
    "datetime",
    "estimate_message_tokens",
    "render_template",
]
