"""Stable kernel surface for GUI and external clients.

The existing codebase exposes many powerful internals, but mature agent shells
benefit from a narrow contract:

- one app object that owns runtime construction;
- one normalized event model that GUI code can render directly;
- raw internals still available underneath for advanced integrations.

This package is that contract. It does not replace the current runtime; it
stabilizes the boundary around it.
"""

from .app import KernelApp
from .events import KernelEvent, KernelEventType, normalize_stream_event
from .profile import (
    KernelProfile,
    automation_customer_profile,
    desktop_customer_profile,
    lite_customer_profile,
)

__all__ = [
    "KernelApp",
    "KernelEvent",
    "KernelEventType",
    "KernelProfile",
    "lite_customer_profile",
    "desktop_customer_profile",
    "automation_customer_profile",
    "normalize_stream_event",
]
