"""Thin native desktop shell for the Mira WebUI."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass


@dataclass(frozen=True)
class NativeWindowOptions:
    """Configuration for a native Mira desktop window."""

    url: str
    title: str = "Mira"
    width: int = 1440
    height: int = 960
    min_width: int = 1100
    min_height: int = 720
    debug: bool = False
    confirm_close: bool = False


def launch_native_window(
    options: NativeWindowOptions,
    *,
    on_closed: Callable[[], None] | None = None,
) -> None:
    """Open *options.url* inside a native webview window."""
    try:
        import webview
    except ImportError as exc:  # pragma: no cover - import path depends on local install
        raise RuntimeError(
            "Desktop host requires pywebview. Install `mira[desktop]` or use a packaged release."
        ) from exc

    window = webview.create_window(
        title=options.title,
        url=options.url,
        width=options.width,
        height=options.height,
        min_size=(options.min_width, options.min_height),
        confirm_close=options.confirm_close,
        text_select=True,
    )
    if on_closed is not None:
        window.events.closed += lambda: _safe_on_closed(on_closed)
    webview.start(debug=options.debug)


def _safe_on_closed(callback: Callable[[], None]) -> None:
    with suppress(Exception):
        callback()
