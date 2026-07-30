from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from mira.kernel.app import KernelApp
from mira.kernel.authorization import KernelAuthorizer, KernelPrincipal
from mira.kernel.operator_commands import execute_operator_command
from mira.kernel.shell import default_engineering_shell, desktop_customer_shell
from mira.session.goal_state import GOAL_STATE_KEY


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


def _root_app() -> KernelApp:
    app = KernelApp(SimpleNamespace(_loop=None), shell=default_engineering_shell())
    app._authorizer = KernelAuthorizer(KernelPrincipal(role="root"))
    app._active_session_key = "webui:local"
    app._session_metadata["webui:local"] = {}
    return app


@pytest.mark.parametrize(
    ("command", "subject", "action"),
    [
        ("adapter status python-inprocess", "adapter", "status"),
        ("adapter list", "adapter", "list"),
        ("adapter switch python-inprocess", "adapter", "switch"),
        ("module show session_state", "module", "status"),
        ("module list", "module", "list"),
        ("module actions session_state", "module", "actions"),
        ("module focus session_state", "module", "focus"),
        ("native status", "native", "status"),
        ("native last-command", "native", "last-command"),
        ("native modules", "native", "modules"),
        ("native focus session_state", "native", "focus"),
        ("native inspect session_state", "native", "inspect"),
        ("bridge status python-inprocess", "bridge", "status"),
        ("bridge list", "bridge", "list"),
        ("bridge fault python-inprocess", "bridge", "fault"),
        ("scheduler status", "scheduler", "status"),
        ("lane show", "lane", "status"),
        ("lane list", "lane", "list"),
        ("maintenance status", "maintenance", "status"),
        ("worker show", "worker", "status"),
        ("worker list", "worker", "list"),
        ("event show", "event", "status"),
        ("event tail 2", "event", "tail"),
        ("session status", "session", "status"),
        ("session goal", "session", "goal"),
        ("session continuation", "session", "continuation"),
        ("privilege status", "privilege", "status"),
        ("goal reset", "goal", "reset"),
        ("kernel profile", "kernel", "profile"),
        ("kernel manifest", "kernel", "manifest"),
        ("topology runtime", "topology", "runtime"),
        ("workspace status", "workspace", "status"),
        ("workspace scope", "workspace", "scope"),
        ("workspace modules", "workspace", "modules"),
        ("workspace focus-module session_state", "workspace", "focus-module"),
        ("repo status", "repo", "status"),
        ("repo tools", "repo", "tools"),
        ("repo prepare-tool filesystem", "repo", "prepare-tool"),
        ("tool inspect filesystem", "tool", "inspect"),
        ("tool queue", "tool", "queue"),
        ("tool status", "tool", "status"),
        ("runtime status", "runtime", "status"),
        ("runtime gate", "runtime", "gate"),
        ("runtime health", "runtime", "health"),
        ("runtime orchestration", "runtime", "orchestration"),
        ("runtime queues", "runtime", "queues"),
        ("runtime adapters", "runtime", "adapters"),
        ("runtime bridges", "runtime", "bridges"),
    ],
)
def test_operator_status_command_matrix(command: str, subject: str, action: str, monkeypatch) -> None:
    app = _root_app()
    monkeypatch.setattr("mira.kernel.app.dispatch_native_bridge_command", lambda **_: {"ok": False})

    result = app.execute_operator_command(command)

    assert result["ok"] is True
    assert result["details"]["subject"] == subject
    assert result["details"]["action"] == action
    assert result["action_result"]["subject"] == subject
    assert isinstance(result["runtime_control"], dict)


@pytest.mark.parametrize(
    ("command", "expected_gate"),
    [
        ("runtime pause maintenance", "paused"),
        ("runtime resume", "open"),
        ("runtime degrade fault", "degraded"),
        ("runtime drain", "open"),
        ("fault record fault python-inprocess", "open"),
        ("fault clear python-inprocess", "open"),
        ("maintenance enter deploy", "maintenance"),
        ("maintenance exit", "open"),
        ("lane prioritize-goal", "open"),
    ],
)
def test_privileged_operator_commands_update_runtime_control(command: str, expected_gate: str) -> None:
    app = _root_app()

    result = app.execute_operator_command(command)

    assert result["ok"] is True
    assert result["runtime_control"]["execution_gate"]["state"] == expected_gate


def test_tool_queue_lifecycle_operator_commands() -> None:
    app = _root_app()
    app.execute_operator_command("tool dispatch filesystem path=README.md")

    queue = app.execute_operator_command("tool queue")
    assert queue["details"]["count"] == 1

    prioritized = app.execute_operator_command("tool prioritize")
    assert prioritized["details"]["priority"] == "on"

    delegated_goal = app.execute_operator_command("tool delegate-goal")
    assert delegated_goal["details"]["lane"] == "sustained_goal"

    delegated_subagent = app.execute_operator_command("tool delegate-subagent")
    assert delegated_subagent["details"]["lane"] == "subagent"

    completed = app.execute_operator_command("tool complete")
    assert completed["details"]["completed"] == 1

    app.execute_operator_command("tool dispatch filesystem path=README.md")
    failed = app.execute_operator_command("tool fail")
    assert failed["details"]["failed"] == 1

    cleared = app.execute_operator_command("tool clear-queue")
    assert cleared["details"]["cleared"] == 0


@pytest.mark.parametrize("command", ["goal resume", "goal complete", "goal cancel"])
def test_goal_operator_commands_require_active_goal(command: str) -> None:
    app = _root_app()

    with pytest.raises(ValueError, match="no active goal"):
        app.execute_operator_command(command)


@pytest.mark.parametrize(
    ("command", "status"),
    [
        ("goal resume", "active"),
        ("goal complete", "completed"),
        ("goal cancel", "cancelled"),
    ],
)
def test_goal_operator_commands_update_active_goal(command: str, status: str) -> None:
    app = _root_app()
    app._session_metadata["webui:local"][GOAL_STATE_KEY] = {
        "status": "active",
        "objective": "finish open issues",
    }

    result = app.execute_operator_command(command)

    assert result["ok"] is True
    assert result["details"]["status"] == status
