from __future__ import annotations

import os
import subprocess
import sys
import types

from mira.cli import commands
from mira.desktop import bootstrap as desktop_bootstrap
from mira.config.loader import load_config
import scripts.mira_desktop as mira_desktop


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


def test_native_launcher_helper_delegates_when_available(monkeypatch, tmp_path) -> None:
    launcher = tmp_path / "mira-launcher"
    launcher.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    launcher.chmod(0o755)
    calls: list[list[str]] = []

    monkeypatch.setattr(desktop_bootstrap, "find_native_launcher", lambda: launcher)
    monkeypatch.setattr(
        desktop_bootstrap.subprocess,
        "run",
        lambda argv, check=False: calls.append(list(argv)) or subprocess.CompletedProcess(argv, 0),
    )

    exit_code = desktop_bootstrap.launch_via_native_launcher(("desktop", "--yes"))

    assert exit_code == 0
    assert calls == [[str(launcher), "desktop", "--yes"]]


def test_native_launcher_lookup_checks_macos_frameworks_native_dir(monkeypatch, tmp_path) -> None:
    macos_dir = tmp_path / "Mira.app" / "Contents" / "MacOS"
    native_dir = tmp_path / "Mira.app" / "Contents" / "Frameworks" / "native"
    macos_dir.mkdir(parents=True)
    native_dir.mkdir(parents=True)
    launcher = native_dir / "mira-launcher"
    launcher.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    launcher.chmod(0o755)

    monkeypatch.delenv("MIRA_NATIVE_LAUNCHER", raising=False)
    monkeypatch.setenv("PATH", "")
    source_file = tmp_path / "src" / "mira" / "desktop" / "bootstrap.py"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("", encoding="utf-8")
    monkeypatch.setattr(desktop_bootstrap, "__file__", str(source_file))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(desktop_bootstrap.sys, "executable", str(macos_dir / "Mira"))

    assert desktop_bootstrap.find_native_launcher() == launcher


def test_desktop_entrypoint_shows_failure_page_for_native_launcher_error(
    monkeypatch,
    tmp_path,
) -> None:
    windows: list[dict[str, object]] = []

    class FakeWebview(types.SimpleNamespace):
        def create_window(self, title: str, **kwargs):
            windows.append({"title": title, **kwargs})

        def start(self):
            return None

    monkeypatch.setenv("MIRA_DIAGNOSTICS_DIR", str(tmp_path))
    monkeypatch.setattr(mira_desktop, "launch_via_native_launcher", lambda _args: 2)
    monkeypatch.setitem(sys.modules, "webview", FakeWebview())

    assert mira_desktop.main() == 2
    log_path = tmp_path / "desktop-startup.log"
    assert log_path.exists()
    assert "native launcher exited with status 2" in log_path.read_text(encoding="utf-8")
    assert windows
    assert windows[0]["title"] == "Mira could not start"
    assert "mira doctor --profile lightweight" in str(windows[0]["html"])


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
