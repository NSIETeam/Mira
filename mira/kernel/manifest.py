"""Pure kernel manifest and topology builders."""

from __future__ import annotations

from typing import Any

from mira import __app_name__, __cli_name__

from .actions import _session_control_actions, _worker_control_actions
from .events import (
    EXECUTION_LIFECYCLE_STATES,
    EXECUTION_SNAPSHOT_STATUSES,
    KERNEL_EVENT_ACTIONS,
    KERNEL_EVENT_STATES,
    KERNEL_EVENT_TYPES,
)
from .module_registry import list_kernel_modules
from .observability import build_diagnostics_snapshot
from .profile import KernelProfile, list_profiles
from .runtime_adapter import list_runtime_adapters
from .runtime_bridge import build_runtime_bridges
from .runtime_control import build_runtime_control_state
from .shell import ShellDescriptor, list_shells

KERNEL_MANIFEST_VERSION = 1
KERNEL_EVENT_CONTRACT_VERSION = 1
KERNEL_SNAPSHOT_CONTRACT_VERSION = 1

def _copy_rows(rows: list[dict[str, Any]], *, limit: int | None = None) -> list[dict[str, Any]]:
    source = rows[:limit] if isinstance(limit, int) else rows
    return [dict(row) for row in source]


def _build_scheduler_state() -> dict[str, Any]:
    return {
        "policy": "priority-foreground-with-background-drain",
        "preferred_lane": "interactive",
        "background_drain_requested": False,
    }


def _clone_scheduler_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        **dict(state),
        "queues": [dict(row) for row in list(state.get("queues", []))],
    }


def _request_background_drain(state: dict[str, Any]) -> dict[str, Any]:
    next_state = _clone_scheduler_state(state)
    next_state["background_drain_requested"] = True
    next_state["policy"] = "background-drain-priority"
    return next_state


def _prioritize_lane(state: dict[str, Any], *, lane: str) -> dict[str, Any]:
    if lane not in {"interactive", "sustained_goal", "subagent"}:
        raise ValueError(f"Unknown scheduler lane: {lane}")
    next_state = _clone_scheduler_state(state)
    next_state["preferred_lane"] = lane
    next_state["policy"] = (
        "goal-lane-priority" if lane == "sustained_goal" else f"{lane}-lane-priority"
    )
    return next_state


def _build_execution_lanes(
    *,
    preferred_lane: str,
    goal_active: bool,
    goal_continuing: bool,
    goal_summary: str | None = None,
) -> list[dict[str, Any]]:
    sustained_state = "active" if goal_active else "idle"
    if goal_continuing:
        sustained_state = "continuing"
    return [
        {
            "id": "interactive",
            "label": "Interactive Lane",
            "mode": "foreground",
            "state": "preferred" if preferred_lane == "interactive" else "ready",
            "summary": "Direct operator-driven execution in the active shell.",
        },
        {
            "id": "sustained_goal",
            "label": "Sustained Goal Lane",
            "mode": "background",
            "state": (
                "preferred"
                if preferred_lane == "sustained_goal" and sustained_state in {"active", "continuing"}
                else sustained_state
            ),
            "summary": goal_summary or "Long-running objective slices with internal continuation support.",
        },
        {
            "id": "subagent",
            "label": "Subagent Lane",
            "mode": "background",
            "state": "preferred" if preferred_lane == "subagent" else "available",
            "summary": "Delegated execution workers for specialized or parallel tasks.",
        },
    ]


def _build_worker_registry() -> list[dict[str, Any]]:
    return [
        {
            "id": "interactive_worker",
            "label": "Interactive Worker",
            "lane": "interactive",
            "kind": "foreground",
            "state": "ready",
            "summary": "Primary worker bound to the active operator session.",
        },
        {
            "id": "goal_worker",
            "label": "Goal Worker",
            "lane": "sustained_goal",
            "kind": "background",
            "state": "idle",
            "summary": "Continuation-capable worker for sustained goals.",
        },
        {
            "id": "subagent_worker",
            "label": "Subagent Worker",
            "lane": "subagent",
            "kind": "background",
            "state": "available",
            "summary": "Delegated worker pool for parallel or specialized execution.",
        },
    ]


def _build_runtime_topology(
    *,
    adapters: list[dict[str, Any]],
    modules: list[dict[str, Any]],
    bridges: list[dict[str, Any]],
    execution_lanes: list[dict[str, Any]],
    scheduler: dict[str, Any],
    workers: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "adapters": [dict(row) for row in adapters],
        "modules": [dict(row) for row in modules],
        "bridges": [dict(row) for row in bridges],
        "execution_lanes": [dict(row) for row in execution_lanes],
        "scheduler": _clone_scheduler_state(scheduler),
        "workers": [dict(row) for row in workers],
    }

def build_kernel_manifest(
    *,
    profile: KernelProfile,
    shell: ShellDescriptor,
    runtime_capabilities: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the stable shell-facing kernel manifest.

    ``runtime_capabilities`` carries host/runtime affordances discovered by the
    transport layer (restart engine, pick folder, diagnostics export, and so
    on). The kernel manifest folds those capabilities into the stable profile
    and shell contract so GUI shells can bootstrap from one object.
    """
    runtime_adapters = list_runtime_adapters()
    runtime_modules = list_kernel_modules(profile)
    default_adapter = "python-inprocess"
    runtime_bridges = build_runtime_bridges(runtime_adapters, active_adapter=default_adapter)
    def operator_action(
        action_id: str,
        label: str,
        *,
        kind: str,
        target_pane: str,
        availability: str = "available",
        privileged: bool = False,
        required_role: str | None = None,
        privileged_reason: str | None = None,
    ) -> dict[str, Any]:
        item: dict[str, Any] = {
            "id": action_id,
            "label": label,
            "kind": kind,
            "availability": availability,
            "target_pane": target_pane,
        }
        if privileged:
            item["privileged"] = True
            item["required_role"] = required_role or "root"
            item["privileged_reason"] = privileged_reason or "requires elevated runtime control"
        return item
    return {
        "contracts": {
            "manifest_version": KERNEL_MANIFEST_VERSION,
            "event_version": KERNEL_EVENT_CONTRACT_VERSION,
            "snapshot_version": KERNEL_SNAPSHOT_CONTRACT_VERSION,
        },
        "identity": {
            "app_name": __app_name__,
            "cli_name": __cli_name__,
        },
        "profile": profile.to_dict(),
        "profile_registry": list_profiles(),
        "shell": shell.to_dict(),
        "shell_registry": list_shells(),
        "execution": {
            "supports_streaming": True,
            "supports_snapshots": True,
            "supports_background": True,
            "supports_resumption": True,
            "event_types": list(KERNEL_EVENT_TYPES),
            "event_actions": list(KERNEL_EVENT_ACTIONS),
            "event_states": list(KERNEL_EVENT_STATES),
            "snapshot_statuses": list(EXECUTION_SNAPSHOT_STATUSES),
            "lifecycle_states": list(EXECUTION_LIFECYCLE_STATES),
        },
        "capabilities": {
            "gui": profile.gui_enabled,
            "api": profile.api_enabled,
            "automations": profile.automations_enabled,
            "memory": profile.memory_enabled,
            "threads": shell.supports_threads,
            "file_activity": shell.supports_file_activity,
            "approvals": shell.supports_approvals,
            "runtime_controls": shell.supports_runtime_controls,
            **(runtime_capabilities or {}),
        },
        "targets": {
            "runtime": list(profile.runtime_targets),
            "languages": list(profile.implementation_languages),
            "adapter": {
                "api_version": 1,
                "preferred_languages": list(profile.implementation_languages),
                "transport_modes": ["in_process", "ffi", "stdio", "serial", "usb", "can"],
                "control_plane": [
                    "fault_stream",
                    "module_state",
                    "task_exec",
                    "workspace_sync",
                    "diagnostics",
                    "adapter_select",
                    "module_control",
                ],
                "deployment_targets": list(profile.runtime_targets),
                "default_adapter": default_adapter,
                "supports_hot_swap": False,
            },
        },
        "runtime_adapters": runtime_adapters,
        "runtime_bridges": runtime_bridges,
        "runtime_modules": runtime_modules,
        "runtime_control": build_runtime_control_state(
            profile,
            default_adapter=default_adapter,
            module_names=[module["name"] for module in runtime_modules],
        ),
        "operator_console": {
            "api_version": 1,
            "panes": [
                "control_plane",
                "runtime",
                "workspace",
                "faults",
                "modules",
                "adapters",
            ],
            "actions": [
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
            ],
            "action_registry": [
                operator_action("open_kernel_settings", "Kernel settings", kind="host", target_pane="control_plane"),
                operator_action("restart_runtime", "Restart runtime", kind="host", target_pane="runtime"),
                operator_action("restart_engine", "Restart engine", kind="host", target_pane="runtime"),
                operator_action(
                    "drain_background",
                    "Drain background",
                    kind="console",
                    target_pane="runtime",
                    privileged=True,
                    privileged_reason="requires elevated dispatch control",
                ),
                operator_action(
                    "prioritize_goal_lane",
                    "Prioritize goal lane",
                    kind="console",
                    target_pane="runtime",
                    privileged=True,
                    privileged_reason="requires elevated dispatch control",
                ),
                operator_action("inspect_faults", "Inspect faults", kind="console", target_pane="faults"),
                operator_action(
                    "record_fault",
                    "Record fault",
                    kind="console",
                    target_pane="faults",
                    privileged=True,
                    privileged_reason="requires elevated fault control",
                ),
                operator_action(
                    "clear_fault",
                    "Clear fault",
                    kind="console",
                    target_pane="faults",
                    privileged=True,
                    privileged_reason="requires elevated fault control",
                ),
                operator_action(
                    "restart_bridge",
                    "Restart bridge",
                    kind="console",
                    target_pane="adapters",
                    privileged=True,
                    privileged_reason="requires elevated runtime bridge control",
                ),
                operator_action(
                    "pause_runtime",
                    "Pause runtime",
                    kind="console",
                    target_pane="runtime",
                    privileged=True,
                    privileged_reason="requires elevated runtime control",
                ),
                operator_action(
                    "resume_runtime",
                    "Resume runtime",
                    kind="console",
                    target_pane="runtime",
                    privileged=True,
                    privileged_reason="requires elevated runtime control",
                ),
                operator_action(
                    "degrade_runtime",
                    "Degrade runtime",
                    kind="console",
                    target_pane="runtime",
                    privileged=True,
                    privileged_reason="requires elevated runtime control",
                ),
                operator_action(
                    "enter_maintenance",
                    "Enter maintenance",
                    kind="console",
                    target_pane="control_plane",
                    privileged=True,
                    privileged_reason="requires elevated maintenance control",
                ),
                operator_action(
                    "exit_maintenance",
                    "Exit maintenance",
                    kind="console",
                    target_pane="control_plane",
                    privileged=True,
                    privileged_reason="requires elevated maintenance control",
                ),
                operator_action("inspect_modules", "Inspect modules", kind="console", target_pane="modules"),
                operator_action(
                    "switch_adapter",
                    "Switch adapter",
                    kind="console",
                    target_pane="adapters",
                    privileged=True,
                    privileged_reason="requires elevated adapter control",
                ),
            ],
            "telemetry": [
                "connection_status",
                "runtime_model",
                "run_state",
                "execution_gate",
                "maintenance_mode",
                "workspace_health",
                "module_status",
                "adapter_status",
                "fault_posture",
            ],
        },
        "diagnostics": {
            **build_diagnostics_snapshot(
                active_adapter=default_adapter,
                module_count=len(runtime_modules),
                bridge_count=len(runtime_bridges),
                fault_level="clear",
                execution_gate="open",
                maintenance_mode=False,
            ),
        },
        "session_controls": {
            "actions": _session_control_actions(),
        },
        "worker_controls": {
            "actions": _worker_control_actions(),
        },
        "execution_lanes": [
            {
                "id": "interactive",
                "label": "Interactive Lane",
                "mode": "foreground",
                "state": "ready",
                "summary": "Direct operator-driven execution in the active shell.",
            },
            {
                "id": "sustained_goal",
                "label": "Sustained Goal Lane",
                "mode": "background",
                "state": "idle",
                "summary": "Long-running objective slices with internal continuation support.",
            },
            {
                "id": "subagent",
                "label": "Subagent Lane",
                "mode": "background",
                "state": "available",
                "summary": "Delegated execution workers for specialized or parallel tasks.",
            },
        ],
        "scheduler": {
            "policy": "priority-foreground-with-background-drain",
            "queues": [
                {
                    "id": "foreground",
                    "label": "Foreground Queue",
                    "lane": "interactive",
                    "depth": 0,
                    "state": "ready",
                    "job_class": "operator_turn",
                },
                {
                    "id": "goal_background",
                    "label": "Goal Background Queue",
                    "lane": "sustained_goal",
                    "depth": 0,
                    "state": "idle",
                    "job_class": "goal_slice",
                },
                {
                    "id": "automation",
                    "label": "Automation Queue",
                    "lane": "subagent",
                    "depth": 0,
                    "state": "available",
                    "job_class": "cron_or_trigger",
                },
            ],
        },
        "workers": [
            {
                **worker,
                "state": "preferred" if str(worker.get("lane") or "") == "interactive" else worker.get("state"),
            }
            for worker in _build_worker_registry()
        ],
        "runtime_topology": _build_runtime_topology(
            adapters=runtime_adapters,
            modules=runtime_modules,
            bridges=runtime_bridges,
            execution_lanes=[],
            scheduler={
                "policy": "priority-foreground-with-background-drain",
                "queues": [],
            },
            workers=[],
        ),
        "event_log": [],
    }
