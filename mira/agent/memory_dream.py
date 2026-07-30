"""Dream run progress and session helper utilities."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from mira.session.manager import SessionManager


def _facade_datetime() -> Any:
    facade = sys.modules.get("mira.agent.memory")
    return getattr(facade, "datetime", datetime) if facade is not None else datetime


class DreamRunProgress:
    """Track tool failures that make a nominally completed Dream run unsafe to advance."""

    def __init__(self) -> None:
        self.had_tool_errors = False

    async def __call__(
        self,
        *_args: Any,
        tool_events: list[dict[str, Any]] | None = None,
        **_kwargs: Any,
    ) -> None:
        if any(
            isinstance(event, dict) and event.get("phase") == "error"
            for event in tool_events or ()
        ):
            self.had_tool_errors = True


def dream_run_completed(
    resp: object | None,
    *,
    had_tool_errors: bool = False,
) -> bool:
    """Return True only when a Dream turn completed without tool failures."""
    metadata = getattr(resp, "metadata", None)
    return (
        not had_tool_errors
        and isinstance(metadata, dict)
        and metadata.get("_stop_reason") == "completed"
    )


def dream_session_key() -> str:
    """Return a unique session key for a Dream run, e.g. ``dream:20260528-100000``."""
    return f"dream:{_facade_datetime().now():%Y%m%d-%H%M%S}"


def build_dream_commit_message(prefix: str, diff_body: str | None) -> str:
    """Build a Dream commit message grounded in the real working-tree diff."""
    diff_body = (diff_body or "").strip()
    if not diff_body:
        return prefix
    return f"{prefix}\n\n{diff_body}"


def prune_dream_sessions(sessions_dir: Path, *, keep: int = 10) -> None:
    """Remove the oldest Dream session files, keeping only the N most recent."""
    dream_files = []
    for path in sessions_dir.glob("*.jsonl"):
        decoded_key = SessionManager._decode_storage_key(path.stem)
        if decoded_key is not None and decoded_key.startswith("dream:"):
            dream_files.append(path)
    dream_files.sort(key=lambda p: p.stat().st_mtime)
    if len(dream_files) <= keep:
        return

    to_remove = dream_files[: len(dream_files) - keep]
    for path in to_remove:
        try:
            path.unlink()
            logger.debug("Pruned old dream session: {}", path.stem)
        except OSError:
            logger.warning("Failed to prune dream session {}", path)
