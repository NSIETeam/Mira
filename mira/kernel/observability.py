"""Mira observability namespace forwarding to nanobot.kernel.observability."""

from nanobot.kernel.observability import *  # noqa: F401,F403
from nanobot.kernel.observability import (
    KERNEL_EVENT_LOG_LIMIT,
    append_kernel_event,
    build_diagnostics_snapshot,
)

__all__ = [
    "KERNEL_EVENT_LOG_LIMIT",
    "append_kernel_event",
    "build_diagnostics_snapshot",
]
