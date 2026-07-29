from __future__ import annotations

import os
import subprocess
import sys


def test_packaged_desktop_entrypoint_smoke_mode() -> None:
    env = {**os.environ, "MIRA_DESKTOP_SMOKE": "1"}

    result = subprocess.run(
        [sys.executable, "scripts/mira_desktop.py"],
        check=False,
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert "mira desktop smoke ok" in result.stdout
