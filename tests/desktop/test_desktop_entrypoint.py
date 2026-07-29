from __future__ import annotations

import os
import subprocess
import sys

from mira.cli import commands
from mira.config.loader import load_config


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


def test_desktop_command_defaults_to_customer_shell(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    monkeypatch.setattr(commands, "webui", lambda **_kwargs: None)
    monkeypatch.setattr(commands, "_gateway_health_ready", lambda *_args: False)
    monkeypatch.setattr(commands, "_webui_endpoint_reachable", lambda *_args: False)

    class FakeRuntime:
        def shutdown(self):
            return None

    class FakeGatewayRuntime:
        def __init__(self, paths):
            self.paths = paths

        def read_state(self):
            return FakeRuntime()

    monkeypatch.setattr("mira.gateway.GatewayRuntime", FakeGatewayRuntime)
    monkeypatch.setattr(
        "mira.desktop.app.launch_native_window",
        lambda *_args, **_kwargs: None,
    )

    commands.desktop(
        port=None,
        gateway_port=None,
        workspace=str(workspace),
        config=str(config_path),
        yes=True,
        debug=False,
        stop_on_close=True,
    )

    assert load_config(config_path).kernel.shell_name == "desktop-customer"
