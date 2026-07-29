from __future__ import annotations

from types import SimpleNamespace

import pytest

from mira.kernel.app import KernelApp
from mira.kernel.operator_commands import execute_operator_command
from mira.kernel.shell import desktop_customer_shell


def test_kernel_app_delegates_operator_commands() -> None:
    assert KernelApp.execute_operator_command.__module__ == "mira.kernel.app"
    assert execute_operator_command.__module__ == "mira.kernel.operator_commands"


def test_operator_command_help_keeps_public_shape() -> None:
    app = KernelApp(SimpleNamespace(_loop=None), shell=desktop_customer_shell())

    result = app.execute_operator_command("help")

    assert result["ok"] is True
    assert result["target_pane"] == "control_plane"
    assert "commands:" in result["output"]
    assert "runtime_control" in result


def test_desktop_shell_rejects_privileged_operator_command() -> None:
    app = KernelApp(SimpleNamespace(_loop=None), shell=desktop_customer_shell())

    with pytest.raises(PermissionError):
        app.execute_operator_command("runtime pause")
