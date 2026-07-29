"""PyInstaller entrypoint for the Mira desktop app."""

from __future__ import annotations

import html
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

from mira.cli.commands import desktop


def _diagnostics_dir() -> Path:
    base = Path(os.environ.get("MIRA_DIAGNOSTICS_DIR") or Path.home() / ".mira" / "diagnostics")
    base.mkdir(parents=True, exist_ok=True)
    return base


def _write_startup_diagnostics(exc: BaseException) -> Path:
    path = _diagnostics_dir() / "desktop-startup.log"
    path.write_text(
        "\n".join(
            [
                f"timestamp={datetime.now().isoformat()}",
                f"python={sys.version}",
                f"executable={sys.executable}",
                f"error={type(exc).__name__}: {exc}",
                "",
                "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
            ]
        ),
        encoding="utf-8",
    )
    return path


def _show_startup_failure(exc: BaseException, log_path: Path) -> None:
    try:
        import webview
    except Exception:
        return

    message = html.escape(f"{type(exc).__name__}: {exc}")
    log = html.escape(str(log_path))
    webview.create_window(
        "Mira could not start",
        html=(
            "<!doctype html><html><body style='font:14px -apple-system,BlinkMacSystemFont,sans-serif;"
            "padding:32px;line-height:1.5'>"
            "<h2>Mira could not start</h2>"
            f"<p>{message}</p>"
            f"<p>Startup diagnostics were written to:<br><code>{log}</code></p>"
            "</body></html>"
        ),
        width=720,
        height=420,
    )
    webview.start()


def main() -> int:
    if os.environ.get("MIRA_DESKTOP_SMOKE") == "1":
        print("mira desktop smoke ok")
        return 0
    try:
        desktop(
            port=None,
            gateway_port=None,
            workspace=None,
            config=None,
            yes=True,
            debug=False,
            stop_on_close=True,
        )
        return 0
    except BaseException as exc:
        log_path = _write_startup_diagnostics(exc)
        _show_startup_failure(exc, log_path)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
