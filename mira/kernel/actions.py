"""Pure kernel action contract builders."""

from __future__ import annotations

from typing import Any

_PRIVILEGED_REASON_RUNTIME = "requires elevated runtime control"
_PRIVILEGED_REASON_FAULT = "requires elevated fault control"
_PRIVILEGED_REASON_MAINTENANCE = "requires elevated maintenance control"

def _session_control_actions() -> list[dict[str, str]]:
    return [
        {
            "id": "inspect_session",
            "label": "inspect session",
            "pane": "runtime",
            "command": "session status",
        },
        {
            "id": "inspect_goal",
            "label": "inspect goal",
            "pane": "runtime",
            "command": "session goal",
        },
        {
            "id": "inspect_continuation",
            "label": "inspect continuation",
            "pane": "runtime",
            "command": "session continuation",
        },
        {
            "id": "resume_goal",
            "label": "resume goal",
            "pane": "runtime",
            "command": "goal resume",
        },
        {
            "id": "complete_goal",
            "label": "complete goal",
            "pane": "runtime",
            "command": "goal complete",
        },
        {
            "id": "cancel_goal",
            "label": "cancel goal",
            "pane": "runtime",
            "command": "goal cancel",
        },
    ]


def _worker_control_actions() -> list[dict[str, str]]:
    return [
        {
            "id": "inspect_workers",
            "label": "inspect workers",
            "pane": "runtime",
            "command": "worker show",
        },
    ]


def _fault_posture_actions() -> list[dict[str, Any]]:
    return [
        {
            "id": "inspect_faults",
            "label": "inspect",
            "pane": "faults",
            "command": "fault show",
        },
        {
            "id": "clear_faults",
            "label": "clear",
            "pane": "faults",
            "command": "fault clear",
            "privileged": True,
            "required_role": "root",
            "privileged_reason": _PRIVILEGED_REASON_FAULT,
        },
        {
            "id": "record_fault",
            "label": "record",
            "pane": "faults",
            "command": "fault record",
            "privileged": True,
            "required_role": "root",
            "privileged_reason": _PRIVILEGED_REASON_FAULT,
        },
        {
            "id": "enter_maintenance",
            "label": "maintenance on",
            "pane": "control_plane",
            "command": "enter-maintenance",
            "privileged": True,
            "required_role": "root",
            "privileged_reason": _PRIVILEGED_REASON_MAINTENANCE,
        },
        {
            "id": "exit_maintenance",
            "label": "maintenance off",
            "pane": "control_plane",
            "command": "exit-maintenance",
            "privileged": True,
            "required_role": "root",
            "privileged_reason": _PRIVILEGED_REASON_MAINTENANCE,
        },
    ]


def _adapter_actions(adapter_name: str) -> list[dict[str, str]]:
    return [
        {
            "id": "inspect_adapter",
            "label": "inspect",
            "pane": "adapters",
            "command": f"adapter status {adapter_name}".strip(),
        }
    ]


def _module_actions(module_name: str) -> list[dict[str, str]]:
    return [
        {
            "id": "show_module",
            "label": "open",
            "pane": "modules",
            "command": f"module show {module_name}".strip(),
        },
        {
            "id": "focus_native",
            "label": "focus",
            "pane": "modules",
            "command": f"native focus {module_name}".strip(),
        },
        {
            "id": "fill_native_inspect",
            "label": "fill inspect",
            "pane": "modules",
            "command": f"native inspect {module_name}".strip(),
        },
        {
            "id": "fill_native_replay",
            "label": "fill replay",
            "pane": "modules",
            "command": f"native replay {module_name} inspect status".strip(),
        },
    ]


def _bridge_actions(adapter_name: str) -> list[dict[str, Any]]:
    return [
        {
            "id": "inspect_bridge",
            "label": "inspect",
            "pane": "adapters",
            "command": f"bridge status {adapter_name}".strip(),
        },
        {
            "id": "restart_bridge",
            "label": "restart",
            "pane": "adapters",
            "command": f"restart-bridge {adapter_name}".strip(),
            "privileged": True,
            "required_role": "root",
            "privileged_reason": _PRIVILEGED_REASON_RUNTIME,
        },
        {
            "id": "mark_bridge_fault",
            "label": "mark fault",
            "pane": "faults",
            "command": f"bridge fault {adapter_name}".strip(),
            "privileged": True,
            "required_role": "root",
            "privileged_reason": _PRIVILEGED_REASON_FAULT,
        },
        {
            "id": "clear_bridge_fault",
            "label": "clear fault",
            "pane": "faults",
            "command": f"clear-fault {adapter_name}".strip(),
            "privileged": True,
            "required_role": "root",
            "privileged_reason": _PRIVILEGED_REASON_FAULT,
        },
    ]


def _native_module_actions(module_name: str) -> list[dict[str, str]]:
    return [
        {
            "id": "inspect_native",
            "label": "inspect",
            "pane": "modules",
            "command": f"native inspect {module_name}".strip(),
        },
        {
            "id": "inspect_native_status",
            "label": "inspect native",
            "pane": "adapters",
            "command": "native last-command",
        },
    ]


def _merge_module_native_state(
    row: dict[str, Any],
    native_state: dict[str, Any],
    *,
    module_name: str,
) -> dict[str, Any]:
    status = str(native_state.get("status") or row.get("status") or "ready")
    row["status"] = status
    row["native_status"] = status
    row["native_status_code"] = native_state.get("status_code")
    row["native_last_code"] = native_state.get("last_code")
    row["native_updated_at_ms"] = native_state.get("updated_at_ms")
    summary = str(row.get("summary") or "").strip()
    native_summary = str(native_state.get("summary") or f"native bridge {status}").strip()
    row["summary"] = f"{summary} · {native_summary}" if summary else native_summary
    row["actions"].extend(_native_module_actions(module_name))
    return row

_PRIVILEGED_OPERATOR_COMMAND_PREFIXES = {
    "switch-adapter",
    "restart-bridge",
    "clear-fault",
    "record-fault",
    "pause-runtime",
    "resume-runtime",
    "degrade-runtime",
    "drain-background",
    "prioritize-goal-lane",
    "enter-maintenance",
    "exit-maintenance",
}
_PRIVILEGED_CONTROL_ACTIONS = {
    "switch_adapter",
    "clear_fault",
    "record_fault",
    "restart_bridge",
    "pause_runtime",
    "resume_runtime",
    "degrade_runtime",
    "drain_background",
    "prioritize_goal_lane",
    "enter_maintenance",
    "exit_maintenance",
}
