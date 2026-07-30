from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import mira.kernel.app as kernel_app_module
from mira.kernel.app import (
    KERNEL_EVENT_CONTRACT_VERSION,
    KERNEL_MANIFEST_VERSION,
    KERNEL_SNAPSHOT_CONTRACT_VERSION,
    KernelApp,
    _adapter_actions,
    _bridge_actions,
    _copy_rows,
    _fault_posture_actions,
    _merge_module_native_state,
    _module_actions,
    _native_module_actions,
    _session_control_actions,
    _worker_control_actions,
    active_kernel_app,
    build_kernel_manifest,
    register_kernel_loop,
)
from mira.kernel.profile import lite_customer_profile, mira_embedded_lab_profile
from mira.kernel.shell import desktop_customer_shell


def _app() -> KernelApp:
    return KernelApp(SimpleNamespace(_loop=None), profile=lite_customer_profile(), shell=desktop_customer_shell())


def _native_ok(*, target: str, action: str, value: str = "") -> dict[str, object]:
    return {
        "ok": True,
        "target": target,
        "action": action,
        "command": f"{target}:{action}",
        "status": "queued",
        "health": "ready",
        "code": 0,
        "queue_depth": 1,
        "artifact": "native/mira-launcher",
        "updated_at_ms": 123,
        "summary": f"{target}:{action}:{value or 'none'}",
    }


def test_kernel_manifest_contract_snapshot_for_desktop_shell() -> None:
    manifest = build_kernel_manifest(
        profile=lite_customer_profile(),
        shell=desktop_customer_shell(),
        runtime_capabilities={"restart_engine": True},
    )

    snapshot = {
        "contracts": manifest["contracts"],
        "identity": manifest["identity"],
        "profile": {
            "name": manifest["profile"]["name"],
            "runtime_targets": manifest["profile"]["runtime_targets"],
            "implementation_languages": manifest["profile"]["implementation_languages"],
        },
        "capabilities": {
            key: manifest["capabilities"][key]
            for key in (
                "gui",
                "api",
                "automations",
                "memory",
                "threads",
                "runtime_controls",
                "restart_engine",
            )
        },
        "execution": {
            "supports_streaming": manifest["execution"]["supports_streaming"],
            "supports_snapshots": manifest["execution"]["supports_snapshots"],
            "supports_background": manifest["execution"]["supports_background"],
            "supports_resumption": manifest["execution"]["supports_resumption"],
        },
        "adapter": manifest["targets"]["adapter"]["default_adapter"],
        "operator_actions": manifest["operator_console"]["actions"],
        "session_actions": [row["id"] for row in manifest["session_controls"]["actions"]],
        "worker_actions": [row["id"] for row in manifest["worker_controls"]["actions"]],
    }

    assert json.loads(json.dumps(snapshot, sort_keys=True)) == {
        "adapter": "python-inprocess",
        "capabilities": {
            "api": False,
            "automations": False,
            "gui": True,
            "memory": True,
            "restart_engine": True,
            "runtime_controls": True,
            "threads": False,
        },
        "contracts": {
            "event_version": KERNEL_EVENT_CONTRACT_VERSION,
            "manifest_version": KERNEL_MANIFEST_VERSION,
            "snapshot_version": KERNEL_SNAPSHOT_CONTRACT_VERSION,
        },
        "execution": {
            "supports_background": True,
            "supports_resumption": True,
            "supports_snapshots": True,
            "supports_streaming": True,
        },
        "identity": {"app_name": "Mira", "cli_name": "mira"},
        "operator_actions": [
            "open_kernel_settings",
            "restart_runtime",
            "restart_engine",
            "drain_background",
            "prioritize_goal_lane",
            "inspect_faults",
            "record_fault",
            "clear_fault",
            "restart_bridge",
            "pause_runtime",
            "resume_runtime",
            "degrade_runtime",
            "enter_maintenance",
            "exit_maintenance",
            "inspect_modules",
            "switch_adapter",
            "attach_board",
        ],
        "profile": {
            "implementation_languages": ["python"],
            "name": "lite-customer",
            "runtime_targets": ["desktop"],
        },
        "session_actions": [
            "inspect_session",
            "inspect_goal",
            "inspect_continuation",
            "resume_goal",
            "complete_goal",
            "cancel_goal",
        ],
        "worker_actions": ["inspect_workers"],
    }


def test_embedded_manifest_defaults_to_serial_bridge_contract() -> None:
    manifest = build_kernel_manifest(
        profile=mira_embedded_lab_profile(),
        shell=desktop_customer_shell(),
    )

    assert manifest["targets"]["adapter"]["default_adapter"] == "c-serial-bridge"
    assert manifest["targets"]["adapter"]["transport_modes"] == [
        "in_process",
        "ffi",
        "stdio",
        "serial",
        "usb",
        "can",
    ]
    assert manifest["operator_console"]["embedded_transports"] == ["serial", "usb", "can"]
    assert manifest["capabilities"]["automations"] is True
    assert manifest["runtime_control"]["active_adapter"] == "c-serial-bridge"


def test_operator_action_factories_keep_public_shape() -> None:
    assert [row["id"] for row in _session_control_actions()] == [
        "inspect_session",
        "inspect_goal",
        "inspect_continuation",
        "resume_goal",
        "complete_goal",
        "cancel_goal",
    ]
    assert _worker_control_actions() == [
        {
            "id": "inspect_workers",
            "label": "inspect workers",
            "pane": "runtime",
            "command": "worker show",
        }
    ]
    assert _adapter_actions("python-inprocess")[0]["command"] == "adapter status python-inprocess"
    assert _module_actions("session_state")[0]["command"] == "module show session_state"
    assert _native_module_actions("session_state")[0]["command"] == "native inspect session_state"

    bridge_actions = {row["id"]: row for row in _bridge_actions("python-inprocess")}
    assert bridge_actions["restart_bridge"]["privileged"] is True
    assert bridge_actions["restart_bridge"]["required_role"] == "root"
    assert bridge_actions["clear_bridge_fault"]["pane"] == "faults"

    fault_actions = {row["id"]: row for row in _fault_posture_actions()}
    assert "privileged" not in fault_actions["inspect_faults"]
    assert fault_actions["record_fault"]["privileged_reason"] == "requires elevated fault control"


def test_copy_rows_and_native_module_merge_are_defensive_contracts() -> None:
    rows = [{"name": "a", "actions": []}, {"name": "b", "actions": []}]
    copied = _copy_rows(rows, limit=1)
    copied[0]["name"] = "changed"
    assert rows[0]["name"] == "a"
    assert copied == [{"name": "changed", "actions": []}]

    merged = _merge_module_native_state(
        {"name": "session_state", "summary": "Session State", "actions": []},
        {
            "status": "fault",
            "status_code": 503,
            "last_code": 12,
            "updated_at_ms": 42,
            "summary": "bridge unavailable",
        },
        module_name="session_state",
    )
    assert merged["status"] == "fault"
    assert merged["native_status_code"] == 503
    assert merged["summary"] == "Session State · bridge unavailable"
    assert [row["id"] for row in merged["actions"]] == ["inspect_native", "inspect_native_status"]


def test_kernel_app_describe_projects_runtime_contracts() -> None:
    app = _app()

    manifest = app.describe()

    assert manifest["contracts"]["manifest_version"] == KERNEL_MANIFEST_VERSION
    assert manifest["runtime_adapters"][0]["actions"][0]["id"] == "inspect_adapter"
    assert manifest["runtime_modules"][0]["actions"][0]["id"] == "show_module"
    assert manifest["runtime_bridges"][0]["actions"][0]["id"] == "inspect_bridge"
    assert manifest["runtime_control"]["execution_gate"]["state"] == "open"
    assert manifest["diagnostics"]["snapshot"]["active_adapter"] == "python-inprocess"
    assert manifest["event_log"][0]["action"] == "kernel_boot"
    assert manifest["targets"]["adapter"]["default_adapter"] == "python-inprocess"


def test_native_state_is_visible_in_modules_and_diagnostics() -> None:
    app = _app()
    app._store_native_command_state(
        queue_depth=2,
        command_depth=3,
        artifact="native/mira-sandbox",
        recent_commands=[{"target": "session_state", "action": "inspect"}],
        module_count=1,
        module_states={
            "session_state": {
                "status": "ready",
                "status_code": 200,
                "summary": "native bridge ready",
            }
        },
        last_command={
            "target": "session_state",
            "action": "inspect",
            "status": "ok",
            "health": "ready",
            "code": 0,
            "updated_at_ms": 10,
        },
    )

    session_state = next(row for row in app.runtime_modules_snapshot() if row["name"] == "session_state")
    diagnostics = app.diagnostics_snapshot["snapshot"]

    assert session_state["native_status"] == "ready"
    assert session_state["native_status_code"] == 200
    assert "native bridge ready" in session_state["summary"]
    assert diagnostics["native"]["queue_depth"] == 2
    assert diagnostics["native"]["module_count"] == 1
    assert diagnostics["native"]["last_command"]["target"] == "session_state"


def test_dispatch_queue_scheduler_and_worker_contracts() -> None:
    app = _app()
    app._dispatch_queue = [
        {
            "tool": "filesystem",
            "family": "io",
            "module": "workspace",
            "lifecycle": "queued",
            "root": "/tmp/project",
        },
        {
            "tool": "shell",
            "module": "runtime",
            "lifecycle": "running",
        },
    ]
    app._scheduler_state["dispatch_handoff_lane"] = "sustained_goal"

    queue = app._dispatch_queue_snapshot(limit=2)
    scheduler = app.scheduler_snapshot()
    workers = {row["lane"]: row for row in app.worker_snapshot()}

    assert queue["queue_depth"] == 2
    assert queue["families"] == "io:1, shell:1"
    assert queue["root_items"] == ["/tmp/project"]
    assert scheduler["dispatch_handoff_lane"] == "sustained_goal"
    assert scheduler["queues"][1]["state"] == "handoff"
    assert scheduler["queues"][3]["dispatch_contract"] == {
        "owner": "goal",
        "mode": "handoff",
        "lane": "sustained_goal",
    }
    assert workers["sustained_goal"]["state"] == "running"
    assert workers["sustained_goal"]["tasks"][0]["dispatch_contract"]["owner"] == "goal"


def test_planning_snapshot_contract_for_runner_phases() -> None:
    assert KernelApp._planning_snapshot({}) == {
        "plan_first_default": True,
        "active": False,
        "stage": "idle",
        "iteration": 0,
        "pending_tool_calls": 0,
        "completed_tool_results": 0,
    }

    assert KernelApp._planning_snapshot({
        "phase": "awaiting_tools",
        "iteration": 2,
        "pending_tool_calls": [{"name": "shell"}],
        "completed_tool_results": [],
    }) == {
        "plan_first_default": True,
        "active": True,
        "stage": "executing",
        "iteration": 2,
        "pending_tool_calls": 1,
        "completed_tool_results": 0,
    }
    assert KernelApp._planning_snapshot({"phase": "tools_completed"})["stage"] == "synthesizing"
    assert KernelApp._planning_snapshot({"phase": "final_response"})["stage"] == "responding"
    assert KernelApp._planning_snapshot({"phase": "error"})["stage"] == "error"


def test_register_kernel_loop_reuses_shared_app(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kernel_app_module, "_SHARED_KERNEL_APP", None)
    loop_a = SimpleNamespace(execution_gate=None)
    loop_b = SimpleNamespace(execution_gate=None)

    first = register_kernel_loop(loop_a, profile=lite_customer_profile(), shell=desktop_customer_shell())
    second = register_kernel_loop(loop_b)

    assert first is second
    assert active_kernel_app() is first
    assert second._loop is loop_b


def test_workspace_and_repo_root_resolution(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    child = repo / "a" / "b"
    child.mkdir(parents=True)
    (repo / ".git").mkdir()
    app = KernelApp(
        SimpleNamespace(_loop=None),
        config=SimpleNamespace(workspace_path=child),
        profile=lite_customer_profile(),
        shell=desktop_customer_shell(),
    )

    assert app._workspace_root() == child
    assert app._repo_root() == repo


def test_runtime_control_methods_record_native_backed_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kernel_app_module, "dispatch_native_bridge_command", _native_ok)
    monkeypatch.setattr(
        kernel_app_module,
        "attach_runtime_board_probe",
        lambda *_args, **_kwargs: {
            "ok": True,
            "health": "ready",
            "runtime_mode": "serial",
            "artifact": "runtimes/mira-c/runtime.json",
            "error": None,
        },
    )
    app = _app()

    assert app.switch_runtime_adapter("python-inprocess")["active_adapter"] == "python-inprocess"
    assert app.focus_runtime_module("session_state")["module_focus"] == "session_state"
    assert app.attach_board(transport="serial", port="/dev/tty.test")["board"]["attached"] is True
    assert app.detach_board()["board"]["attached"] is False
    assert app.record_fault("fault")["fault_posture"]["last_level"] == "fault"
    assert app.clear_fault()["fault_posture"]["last_level"] == "clear"
    assert app.restart_bridge("python-inprocess")["active_adapter"] == "python-inprocess"
    assert app.pause_runtime("test-pause")["execution_gate"]["state"] == "paused"
    assert app.degrade_runtime("test-degrade")["execution_gate"]["state"] == "degraded"
    assert app.enter_maintenance("test-maintenance")["maintenance_mode"]["enabled"] is True
    assert app.exit_maintenance()["maintenance_mode"]["enabled"] is False
    assert app.resume_runtime()["execution_gate"]["state"] == "open"

    native = app._native_runtime_snapshot()
    assert native["command_depth"] == 1
    assert native["last_command"]["artifact"] == "native/mira-launcher"
    assert app._event_log[0]["action"] == "resume_runtime"


def test_dispatch_control_action_validates_payload_and_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kernel_app_module, "dispatch_native_bridge_command", _native_ok)
    app = _app()

    with pytest.raises(ValueError, match="missing action"):
        app.dispatch_control_action("")
    with pytest.raises(ValueError, match="missing module"):
        app.dispatch_control_action("focus_module", {})
    with pytest.raises(ValueError, match="unknown kernel action"):
        app.dispatch_control_action("unknown_action")

    result = app.dispatch_control_action("focus_module", {"module": "session_state"})
    assert result["module_focus"] == "session_state"


def test_active_checkpoint_planning_trace_and_diagnostics() -> None:
    app = _app()
    app._active_session_key = "websocket:one"
    app._loop = SimpleNamespace(
        _runtime_vars={
            "session_checkpoints": {
                "websocket:one": {
                    "phase": "awaiting_tools",
                    "iteration": 3,
                    "pending_tool_calls": [{"function": {"name": "shell"}}],
                    "completed_tool_results": [{"name": "filesystem"}],
                }
            }
        },
        subagents=SimpleNamespace(
            status_snapshot=lambda session_key: [
                {
                    "task_id": "sub-1",
                    "label": f"worker:{session_key}",
                    "phase": "running",
                    "iteration": 1,
                    "tool_events": [{"name": "shell", "status": "running", "detail": "exec"}],
                    "error": None,
                }
            ]
        ),
    )
    app._refresh_live_event_log()

    diagnostics = app.diagnostics_snapshot["snapshot"]

    assert diagnostics["phase"] == "awaiting_tools"
    assert diagnostics["pending_tool_calls"] == 1
    assert diagnostics["planning"]["stage"] == "executing"
    assert diagnostics["planning"]["trace"][0]["action"] == "execution_checkpoint"
    assert diagnostics["subagent_workers"] == 1


def test_native_command_detail_contracts() -> None:
    app = _app()
    app._store_native_command_state(
        queue_depth=4,
        command_depth=5,
        artifact="native/mira-pack",
        last_command={
            "target": "runtime",
            "action": "pack",
            "status": "ok",
            "health": "ready",
            "code": 7,
            "updated_at_ms": 99,
            "summary": "runtime:pack",
        },
    )

    details = app._native_command_details(
        action="pack",
        target="runtime",
        command="mira-pack",
        value="audit",
    )
    summary = app._native_summary_details(action="summary", command="native summary")

    assert details == {
        "subject": "native",
        "action": "pack",
        "target": "runtime",
        "command": "mira-pack",
        "value": "audit",
        "health": "ready",
        "status": "ok",
        "code": 7,
        "queue_depth": 4,
        "artifact": "native/mira-pack",
        "updated_at_ms": 99,
    }
    assert summary["command_depth"] == 5
    assert summary["last_target"] == "runtime"
    assert summary["last_summary"] == "runtime:pack"
