"""Bootstrap helpers for the native Mira desktop entrypoint."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence


def _launcher_filename() -> str:
    return "mira-launcher.exe" if sys.platform == "win32" else "mira-launcher"


def _launcher_filenames() -> tuple[str, ...]:
    names = (_launcher_filename(), "mira-launcher", "mira-launcher.exe")
    return tuple(dict.fromkeys(names))


def _launcher_candidate_roots() -> list[Path]:
    roots: list[Path] = []
    script_path = Path(__file__).resolve()
    executable_path = Path(sys.executable).resolve()
    bundle_resource_path = executable_path.parent.parent / "Resources"
    bundle_frameworks_path = executable_path.parent.parent / "Frameworks"
    pyinstaller_path = Path(getattr(sys, "_MEIPASS", "")) if getattr(sys, "_MEIPASS", "") else None

    for path in (
        pyinstaller_path,
        script_path.parent,
        script_path.parent.parent,
        script_path.parent.parent.parent,
        executable_path.parent,
        executable_path.parent.parent,
        bundle_resource_path,
        bundle_frameworks_path,
        Path.cwd(),
    ):
        if path is not None and path not in roots:
            roots.append(path)
    return roots


def find_native_launcher() -> Path | None:
    """Return the first native launcher candidate that exists on disk."""
    override = os.environ.get("MIRA_NATIVE_LAUNCHER")
    if override:
        candidate = Path(override).expanduser()
        if candidate.is_file():
            return candidate

    for root in _launcher_candidate_roots():
        for launcher_name in _launcher_filenames():
            for relative in (
                Path(launcher_name),
                Path("native") / launcher_name,
                Path("dist") / "native" / launcher_name,
            ):
                candidate = root / relative
                if candidate.is_file():
                    return candidate

    for launcher_name in _launcher_filenames():
        which = shutil.which(launcher_name)
        if which:
            candidate = Path(which)
            if candidate.is_file():
                return candidate
    return None


def launch_via_native_launcher(args: Sequence[str]) -> int | None:
    """Run the packaged native launcher when it is available."""
    launcher = find_native_launcher()
    if launcher is None:
        return None
    result = subprocess.run([str(launcher), *args], check=False)
    return result.returncode
