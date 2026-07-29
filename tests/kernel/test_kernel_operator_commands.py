from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from mira.kernel.app import KernelApp
from mira.kernel.authorization import KernelAuthorizer, KernelPrincipal
from mira.kernel.operator_commands import execute_operator_command
from mira.kernel.shell import default_engineering_shell, desktop_customer_shell


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


def test_can_elevate_hint_does_not_authorize_privileged_operator_command() -> None:
    app = KernelApp(SimpleNamespace(_loop=None), shell=default_engineering_shell())
    app._authorizer = KernelAuthorizer(KernelPrincipal(role="user"))

    with pytest.raises(PermissionError):
        app.execute_operator_command("runtime pause token=sk-test")

    assert app._authorizer.audit_log[-1]["allowed"] is False
    assert app._authorizer.audit_log[-1]["detail"] == "[redacted]"


def test_server_root_principal_authorizes_privileged_operator_command() -> None:
    app = KernelApp(SimpleNamespace(_loop=None), shell=default_engineering_shell())
    app._authorizer = KernelAuthorizer(KernelPrincipal(role="root"))

    result = app.execute_operator_command("runtime pause maintenance")

    assert result["ok"] is True
    assert result["runtime_control"]["execution_gate"]["state"] == "paused"


def test_tool_dispatch_uses_live_tool_registry() -> None:
    tools = SimpleNamespace(execute=AsyncMock(return_value="tool result"))
    app = KernelApp(SimpleNamespace(_loop=SimpleNamespace(tools=tools)), shell=desktop_customer_shell())

    result = app.execute_operator_command("tool dispatch filesystem path=README.md")

    assert result["ok"] is True
    assert result["details"]["status"] == "ok"
    assert result["details"]["lifecycle"] == "completed"
    assert result["details"]["result"] == "tool result"
    tools.execute.assert_awaited_once_with("filesystem", {"path": "README.md"})


def test_tool_dispatch_without_live_registry_fails_closed() -> None:
    app = KernelApp(SimpleNamespace(_loop=None), shell=desktop_customer_shell())

    result = app.execute_operator_command("tool dispatch filesystem path=README.md")

    assert result["ok"] is True
    assert result["details"]["status"] == "unavailable"
    assert result["details"]["lifecycle"] == "unavailable"
    assert "ToolRegistry" in result["details"]["error"]
