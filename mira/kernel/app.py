"""Kernel-oriented runtime facade.

`mira` remains the full SDK surface. `KernelApp` narrows that surface for
products that want a stable mature-agent boundary: a small kernel API under a
thin GUI.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

from mira import __app_name__, __cli_name__
from mira.agent.loop import AgentLoop
from mira.bus.runtime_events import (
    GoalStateChanged,
    RuntimeEventBus,
    RuntimeEventContext,
    RuntimeModelChanged,
    SessionTurnStarted,
    TurnCompleted,
    TurnRunStatusChanged,
)
from mira.config.schema import Config
from mira.mira import RunResult, RunStream, mira
from mira.providers.image_generation import image_gen_provider_configs
from mira.session.goal_state import GOAL_STATE_KEY, goal_state_ws_blob, parse_goal_state
from mira.session.turn_continuation import (
    internal_continuation_pending,
    reset_goal_continuation_rounds,
)
from mira.tool_contracts import tool_contract_family

from .embedded_plane import build_board_snapshot, build_embedded_topology
from .events import (
    EXECUTION_LIFECYCLE_STATES,
    EXECUTION_SNAPSHOT_STATUSES,
    KERNEL_EVENT_ACTIONS,
    KERNEL_EVENT_STATES,
    KERNEL_EVENT_TYPES,
    ExecutionSnapshot,
    merge_snapshot_with_session_metadata,
    snapshot_from_run_result,
)
from .execution_plane import build_execution_lanes
from .module_registry import list_kernel_modules
from .native_bridge import dispatch_native_bridge_command, snapshot_native_bridge
from .observability import append_kernel_event, build_diagnostics_snapshot
from .operator_commands import execute_operator_command as _execute_operator_command
from .profile import KernelProfile, get_profile, list_profiles, lite_customer_profile
from .runtime_adapter import list_runtime_adapters
from .runtime_bridge import (
    activate_runtime_bridge,
    build_runtime_bridges,
    clear_bridge_fault,
    clone_runtime_bridges,
    mark_bridge_fault,
    restart_runtime_bridge,
    set_bridge_maintenance,
)
from .runtime_control import (
    attach_board as attach_runtime_board,
)
from .runtime_control import (
    build_runtime_control_state,
    clone_runtime_control_state,
    set_active_adapter,
    set_execution_gate,
    set_fault_level,
    set_maintenance_mode,
    set_module_focus,
)
from .runtime_control import detach_board as detach_runtime_board
from .runtime_probe import (
    attach_runtime_board_probe,
    board_status_runtime_probe,
    discover_serial_ports,
)
from .runtime_topology import build_runtime_topology
from .scheduler import (
    build_scheduler_state,
    clone_scheduler_state,
    prioritize_lane,
    request_background_drain,
)
from .shell import ShellDescriptor, default_engineering_shell, get_shell, list_shells
from .worker_plane import build_worker_registry

KERNEL_MANIFEST_VERSION = 1
KERNEL_EVENT_CONTRACT_VERSION = 1
KERNEL_SNAPSHOT_CONTRACT_VERSION = 1
_SHARED_KERNEL_APP: KernelApp | None = None


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


def _copy_rows(rows: list[dict[str, Any]], *, limit: int | None = None) -> list[dict[str, Any]]:
    source = rows[:limit] if isinstance(limit, int) else rows
    return [dict(row) for row in source]


_PRIVILEGED_REASON_RUNTIME = "requires elevated runtime control"
_PRIVILEGED_REASON_FAULT = "requires elevated fault control"
_PRIVILEGED_REASON_MAINTENANCE = "requires elevated maintenance control"
_PRIVILEGED_OPERATOR_COMMAND_PREFIXES = {
    "attach-board",
    "detach-board",
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
    "attach_board",
    "detach_board",
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


def active_kernel_app() -> KernelApp | None:
    return _SHARED_KERNEL_APP


def register_kernel_loop(
    loop: AgentLoop,
    *,
    config: Config | None = None,
    profile: KernelProfile | None = None,
    shell: ShellDescriptor | None = None,
) -> KernelApp:
    global _SHARED_KERNEL_APP
    if _SHARED_KERNEL_APP is not None:
        _SHARED_KERNEL_APP.attach_loop(loop)
        return _SHARED_KERNEL_APP
    _SHARED_KERNEL_APP = KernelApp.from_loop(
        loop,
        config=config,
        profile=profile,
        shell=shell,
    )
    return _SHARED_KERNEL_APP


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
    default_adapter = "c-serial-bridge" if "embedded-lab" in profile.runtime_targets else "python-inprocess"
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
                "attach_board",
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
                operator_action(
                    "attach_board",
                    "Attach board",
                    kind="planned",
                    target_pane="adapters",
                    availability="planned",
                    privileged=True,
                    privileged_reason="requires elevated board control",
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
                "board_attachment",
                "fault_posture",
            ],
            "embedded_transports": ["serial", "usb", "can"],
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
            for worker in build_worker_registry()
        ],
        "embedded_topology": build_embedded_topology(
            board=build_board_snapshot(
                attached=False,
                health="detached",
                transport=None,
                port=None,
                target="embedded" if "embedded-lab" in profile.runtime_targets else "desktop",
                preferred_transport="serial" if "embedded-lab" in profile.runtime_targets else "in_process",
            ),
            transports=["serial", "usb", "can"],
            active_adapter=default_adapter,
        ),
        "runtime_topology": build_runtime_topology(
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


class KernelApp:
    """Thin kernel wrapper around the existing agent loop."""

    def __init__(
        self,
        bot: mira,
        *,
        config: Config | None = None,
        profile: KernelProfile | None = None,
        shell: ShellDescriptor | None = None,
    ) -> None:
        self._bot = bot
        self._config = config
        self._profile = profile or lite_customer_profile()
        self._shell = shell or default_engineering_shell()
        self._loop = getattr(bot, "_loop", None)
        self._runtime_adapters = list_runtime_adapters()
        self._runtime_modules = list_kernel_modules(self._profile)
        default_adapter = (
            "c-serial-bridge" if "embedded-lab" in self._profile.runtime_targets else "python-inprocess"
        )
        self._runtime_bridges = build_runtime_bridges(
            self._runtime_adapters,
            active_adapter=default_adapter,
        )
        self._runtime_control = build_runtime_control_state(
            self._profile,
            default_adapter=default_adapter,
            module_names=[module["name"] for module in self._runtime_modules],
        )
        self._scheduler_state = build_scheduler_state()
        self._event_log: list[dict[str, Any]] = []
        self._native_module_states: dict[str, dict[str, Any]] = {}
        self._native_bridge_artifact: str | None = None
        self._native_recent_commands: list[dict[str, Any]] = []
        self._native_last_command: dict[str, Any] | None = None
        self._reset_native_command_state()
        self._dispatch_queue: list[dict[str, Any]] = []
        self._session_metadata: dict[str, dict[str, Any]] = {}
        self._session_status: dict[str, str] = {}
        self._session_runtime: dict[str, dict[str, Any]] = {}
        self._session_latency: dict[str, int | None] = {}
        self._active_session_key: str | None = None
        self._runtime_subscription_attached = False
        self._checkpoint_signatures: dict[str, tuple[Any, ...]] = {}
        self._subagent_signatures: dict[str, tuple[Any, ...]] = {}
        self._board_signatures: dict[str, tuple[Any, ...]] = {}
        self._attach_runtime_bus()
        self._record_kernel_event(
            "kernel_boot",
            state="ready",
            message=f"{self._profile.name} profile initialized",
        )

    @property
    def bot(self) -> mira:
        """Expose the underlying bot for advanced integrations."""
        return self._bot

    @property
    def config(self) -> Config | None:
        return self._config

    @property
    def profile(self) -> KernelProfile:
        return self._profile

    @property
    def shell(self) -> ShellDescriptor:
        return self._shell

    @property
    def runtime_control(self) -> dict[str, Any]:
        return clone_runtime_control_state(self._runtime_control)

    @property
    def runtime_bridges(self) -> list[dict[str, Any]]:
        return clone_runtime_bridges(self._runtime_bridges)

    def runtime_adapters_snapshot(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for adapter in self._runtime_adapters:
            row = dict(adapter)
            adapter_name = str(row.get("name") or "")
            row["actions"] = _adapter_actions(adapter_name)
            rows.append(row)
        return rows

    def runtime_modules_snapshot(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for module in self._runtime_modules:
            row = dict(module)
            module_name = str(row.get("name") or "")
            row["actions"] = _module_actions(module_name)
            native_state = self._native_module_states.get(str(row.get("name") or ""))
            if native_state:
                row = _merge_module_native_state(
                    row,
                    native_state,
                    module_name=module_name,
                )
            rows.append(row)
        return rows

    def runtime_bridges_snapshot(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for bridge in self._runtime_bridges:
            row = dict(bridge)
            adapter_name = str(row.get("adapter") or "")
            row["actions"] = _bridge_actions(adapter_name)
            rows.append(row)
        return rows

    def runtime_control_snapshot(self) -> dict[str, Any]:
        state = self.runtime_control
        fault_posture = dict(state.get("fault_posture", {}))
        fault_posture["actions"] = _fault_posture_actions()
        state["fault_posture"] = fault_posture
        return state

    def _workspace_root(self) -> Path:
        config = self._config
        workspace = getattr(config, "workspace_path", None) if config is not None else None
        if isinstance(workspace, Path):
            return workspace
        if isinstance(workspace, str) and workspace.strip():
            return Path(workspace).expanduser()
        return Path.cwd()

    def _repo_root(self) -> Path | None:
        workspace = self._workspace_root()
        for candidate in (workspace, *workspace.parents):
            if (candidate / ".git").exists():
                return candidate
        return None

    def attach_loop(self, loop: AgentLoop) -> None:
        self._loop = loop
        self._bot = mira(loop, config=self._config)
        self._attach_runtime_bus()

    def _attach_runtime_bus(self) -> None:
        if self._runtime_subscription_attached:
            return
        loop = self._loop
        if loop is None:
            return
        runtime_events = getattr(loop, "runtime_events", None)
        if not isinstance(runtime_events, RuntimeEventBus):
            return
        runtime_events.subscribe(self._handle_session_turn_started, SessionTurnStarted)
        runtime_events.subscribe(self._handle_run_status_changed, TurnRunStatusChanged)
        runtime_events.subscribe(self._handle_turn_completed, TurnCompleted)
        runtime_events.subscribe(self._handle_goal_state_changed, GoalStateChanged)
        runtime_events.subscribe(self._handle_runtime_model_changed, RuntimeModelChanged)
        self._runtime_subscription_attached = True

    def _active_session_metadata(self) -> dict[str, Any] | None:
        if self._active_session_key is None:
            return None
        return self._session_metadata.get(self._active_session_key)

    def _active_session_record(self) -> Any | None:
        loop = self._loop
        sessions = getattr(loop, "sessions", None) if loop is not None else None
        session_key = self._active_session_key
        if sessions is None or not session_key or not hasattr(sessions, "get_or_create"):
            return None
        return sessions.get_or_create(session_key)

    def _publish_goal_state_change(self, session_key: str, session_metadata: dict[str, Any]) -> None:
        self._session_metadata[session_key] = dict(session_metadata)
        loop = self._loop
        runtime_events = getattr(loop, "runtime_events", None) if loop is not None else None
        context = RuntimeEventContext(
            channel="webui",
            chat_id=session_key,
            session_key=session_key,
            metadata={},
        )
        if not isinstance(runtime_events, RuntimeEventBus):
            self._handle_goal_state_changed(
                GoalStateChanged(
                    context=context,
                    session_metadata=dict(session_metadata),
                )
            )
            return
        runtime_events.publish_nowait(
            GoalStateChanged(
                context=context,
                session_metadata=dict(session_metadata),
            )
        )

    def _operator_goal_update(self, action: str) -> tuple[str, dict[str, Any]]:
        session_key = self._active_session_key
        if not session_key:
            raise ValueError("no active session")
        metadata = dict(self._active_session_metadata() or {})
        prior = parse_goal_state(metadata.get(GOAL_STATE_KEY))
        if not isinstance(prior, dict) or prior.get("status") != "active":
            raise ValueError("no active goal")
        now = datetime.now().isoformat()
        if action == "resume":
            reset_goal_continuation_rounds(metadata)
            self.prioritize_goal_lane()
            message = "goal continuation budget reopened and scheduler pointed back to sustained goal lane"
            details = {
                "subject": "goal",
                "action": "resume",
                "status": "active",
                "session": session_key,
            }
        else:
            next_status = "completed" if action == "complete" else "cancelled"
            next_goal = {
                **prior,
                "status": next_status,
                "ended_at": now,
                "recap": f"operator shell marked goal {next_status}",
            }
            if action == "complete":
                next_goal["completed_at"] = now
            metadata[GOAL_STATE_KEY] = next_goal
            reset_goal_continuation_rounds(metadata)
            message = f"goal marked {next_status} by operator shell"
            details = {
                "subject": "goal",
                "action": action,
                "status": next_status,
                "session": session_key,
            }
        session = self._active_session_record()
        if session is not None:
            session.metadata.clear()
            session.metadata.update(metadata)
            sessions = getattr(self._loop, "sessions", None) if self._loop is not None else None
            if sessions is not None and hasattr(sessions, "save"):
                sessions.save(session)
        self._publish_goal_state_change(session_key, metadata)
        self._record_kernel_event(
            f"goal_{action}",
            state="ok" if action == "resume" else ("done" if action == "complete" else "cancelled"),
            message=message,
            session_key=session_key,
            event_type="goal",
        )
        return message, details

    def _loop_runtime_var(self, key: str, default: Any) -> Any:
        loop = self._loop
        if loop is None:
            return default
        runtime_vars = getattr(loop, "_runtime_vars", None)
        if not isinstance(runtime_vars, dict):
            return default
        return runtime_vars.get(key, default)

    def _active_checkpoint(self) -> dict[str, Any]:
        session_key = self._active_session_key
        checkpoints = self._loop_runtime_var("session_checkpoints", {})
        if (
            session_key is not None
            and isinstance(checkpoints, dict)
            and isinstance(checkpoints.get(session_key), dict)
        ):
            return dict(checkpoints[session_key])
        return {}

    def _subagent_snapshot(self, session_key: str | None = None) -> list[dict[str, Any]]:
        loop = self._loop
        if loop is None:
            return []
        subagents = getattr(loop, "subagents", None)
        if subagents is None or not hasattr(subagents, "status_snapshot"):
            return []
        try:
            return subagents.status_snapshot(session_key)
        except Exception:
            return []

    @staticmethod
    def _planning_snapshot(checkpoint: dict[str, Any]) -> dict[str, Any]:
        if not checkpoint:
            return {
                "plan_first_default": True,
                "active": False,
                "stage": "idle",
                "iteration": 0,
                "pending_tool_calls": 0,
                "completed_tool_results": 0,
            }
        phase = str(checkpoint.get("phase") or "running")
        iteration = int(checkpoint.get("iteration", 0) or 0)
        pending_tool_calls = len(list(checkpoint.get("pending_tool_calls", [])))
        completed_tool_results = len(list(checkpoint.get("completed_tool_results", [])))
        if phase == "awaiting_tools":
            stage = "executing"
        elif phase == "tools_completed":
            stage = "synthesizing"
        elif phase == "final_response":
            stage = "responding"
        elif phase == "error":
            stage = "error"
        elif iteration <= 1 and pending_tool_calls == 0 and completed_tool_results == 0:
            stage = "planning"
        else:
            stage = "coordinating"
        return {
            "plan_first_default": True,
            "active": True,
            "stage": stage,
            "iteration": iteration,
            "pending_tool_calls": pending_tool_calls,
            "completed_tool_results": completed_tool_results,
        }

    def _planning_trace(self, session_key: str | None, *, limit: int = 5) -> list[dict[str, Any]]:
        if not session_key:
            return []
        rows: list[dict[str, Any]] = []
        for row in self._event_log:
            if not isinstance(row, dict):
                continue
            if str(row.get("session_key") or "") != session_key:
                continue
            action = str(row.get("action") or "")
            if action not in {"execution_checkpoint", "tool_pending", "tool_completed"}:
                continue
            rows.append({
                "action": action,
                "state": str(row.get("state") or "unknown"),
                "message": str(row.get("message") or "").strip(),
                "iteration": int(row.get("iteration", 0) or 0),
            })
            if len(rows) >= limit:
                break
        return list(reversed(rows))

    def _refresh_live_event_log(self) -> None:
        native_snapshot = snapshot_native_bridge()
        if native_snapshot is not None:
            self._store_native_command_state(
                queue_depth=native_snapshot.queue_depth,
                command_depth=native_snapshot.command_depth,
                artifact=native_snapshot.artifact,
                recent_commands=native_snapshot.recent_commands,
                module_count=native_snapshot.module_count,
                module_states=native_snapshot.module_states,
                last_command=(
                    {
                        **native_snapshot.last_command,
                        "artifact": native_snapshot.artifact,
                    }
                    if native_snapshot.last_command
                    else None
                ),
            )
            for row in reversed(native_snapshot.events):
                self._event_log = [dict(row), *self._event_log][:24]
        session_key = self._active_session_key
        if not session_key:
            return
        checkpoint = self._active_checkpoint()
        if checkpoint:
            pending_tool_names = tuple(
                str(tool_call.get("function", {}).get("name") or tool_call.get("name") or "tool")
                for tool_call in list(checkpoint.get("pending_tool_calls", []))
                if isinstance(tool_call, dict)
            )
            completed_tool_names = tuple(
                str(tool_result.get("name") or "tool")
                for tool_result in list(checkpoint.get("completed_tool_results", []))
                if isinstance(tool_result, dict)
            )
            signature = (
                checkpoint.get("phase"),
                checkpoint.get("iteration"),
                pending_tool_names,
                completed_tool_names,
            )
            if self._checkpoint_signatures.get(session_key) != signature:
                self._checkpoint_signatures[session_key] = signature
                self._record_kernel_event(
                    "execution_checkpoint",
                    state=str(checkpoint.get("phase") or "running"),
                    message=(
                        f"session {session_key} iter {checkpoint.get('iteration', 0)}"
                        f" pending={len(pending_tool_names)}"
                        f" completed={len(completed_tool_names)}"
                    ),
                    session_key=session_key,
                    iteration=int(checkpoint.get("iteration", 0) or 0),
                )
                if pending_tool_names:
                    self._record_kernel_event(
                        "tool_pending",
                        state=str(checkpoint.get("phase") or "awaiting_tools"),
                        message=", ".join(pending_tool_names[:4]),
                        session_key=session_key,
                        iteration=int(checkpoint.get("iteration", 0) or 0),
                    )
                if completed_tool_names:
                    self._record_kernel_event(
                        "tool_completed",
                        state=str(checkpoint.get("phase") or "tools_completed"),
                        message=", ".join(completed_tool_names[:4]),
                        session_key=session_key,
                        iteration=int(checkpoint.get("iteration", 0) or 0),
                    )
        subagent_rows = self._subagent_snapshot(session_key)
        if subagent_rows:
            signature = tuple(
                (
                    row.get("task_id"),
                    row.get("phase"),
                    row.get("iteration"),
                    row.get("error"),
                    tuple(
                        (
                            event.get("name"),
                            event.get("status"),
                            event.get("detail"),
                        )
                        for event in list(row.get("tool_events", []))
                        if isinstance(event, dict)
                    ),
                )
                for row in subagent_rows
            )
            if self._subagent_signatures.get(session_key) != signature:
                self._subagent_signatures[session_key] = signature
                top = subagent_rows[0]
                self._record_kernel_event(
                    "subagent_runtime",
                    state=str(top.get("phase") or "running"),
                    message=(
                        f"{len(subagent_rows)} delegated worker(s) active;"
                        f" head={top.get('label', 'subagent')} iter {top.get('iteration', 0)}"
                    ),
                    session_key=session_key,
                    iteration=int(top.get("iteration", 0) or 0),
                )
                for event in list(top.get("tool_events", []))[:3]:
                    if not isinstance(event, dict):
                        continue
                    tool_name = str(event.get("name") or "tool")
                    tool_state = str(event.get("status") or top.get("phase") or "running")
                    tool_detail = str(event.get("detail") or tool_name)
                    self._record_kernel_event(
                        "subagent_tool",
                        state=tool_state,
                        message=f"{top.get('label', 'subagent')}: {tool_detail}",
                        session_key=session_key,
                        iteration=int(top.get("iteration", 0) or 0),
                    )

    def _handle_session_turn_started(self, event: SessionTurnStarted) -> None:
        session_key = event.context.session_key
        self._active_session_key = session_key
        self._session_status[session_key] = "queued"
        self._record_kernel_event(
            "session_turn_started",
            state="running",
            message=f"session {session_key} admitted to kernel",
            session_key=session_key,
            event_type="session",
        )

    def _handle_run_status_changed(self, event: TurnRunStatusChanged) -> None:
        session_key = event.context.session_key
        self._active_session_key = session_key
        self._session_status[session_key] = event.status
        if event.status == "running":
            self._scheduler_state = prioritize_lane(self._scheduler_state, lane="interactive")
        self._record_kernel_event(
            "turn_run_status_changed",
            state=event.status,
            message=f"session {session_key} status -> {event.status}",
            session_key=session_key,
            event_type="turn",
        )

    def _handle_turn_completed(self, event: TurnCompleted) -> None:
        session_key = event.context.session_key
        self._active_session_key = session_key
        self._session_status[session_key] = "idle"
        self._session_latency[session_key] = event.latency_ms
        runtime = event.runtime
        self._session_runtime[session_key] = (
            {}
            if runtime is None
            else {
                "model": getattr(runtime, "model", None),
                "model_preset": getattr(runtime, "model_preset", None),
                "context_window_tokens": getattr(runtime, "context_window_tokens", None),
            }
        )
        checkpoints = self._loop_runtime_var("session_checkpoints", {})
        if isinstance(checkpoints, dict):
            checkpoints.pop(session_key, None)
        self._checkpoint_signatures.pop(session_key, None)
        self._subagent_signatures.pop(session_key, None)
        self._record_kernel_event(
            "turn_completed",
            state="ok",
            message=f"session {session_key} completed",
            session_key=session_key,
            event_type="turn",
            latency_ms=event.latency_ms,
        )

    def _handle_goal_state_changed(self, event: GoalStateChanged) -> None:
        session_key = event.context.session_key
        self._active_session_key = session_key
        self._session_metadata[session_key] = dict(event.session_metadata or {})
        goal_blob = goal_state_ws_blob(event.session_metadata)
        self._record_kernel_event(
            "goal_state_changed",
            state="active" if goal_blob.get("active") else "idle",
            message=str(goal_blob.get("ui_summary") or goal_blob.get("objective") or "goal state updated"),
            session_key=session_key,
            event_type="goal",
        )

    def _handle_runtime_model_changed(self, event: RuntimeModelChanged) -> None:
        self._record_kernel_event(
            "runtime_model_changed",
            state="ready",
            message=f"runtime model -> {event.model}",
        )

    @classmethod
    def from_config(
        cls,
        config_path: str | Path | None = None,
        *,
        workspace: str | Path | None = None,
        model: str | None = None,
        model_preset: str | None = None,
        profile: KernelProfile | None = None,
        profile_name: str | None = None,
        shell_name: str | None = None,
        shell: ShellDescriptor | None = None,
    ) -> KernelApp:
        """Construct a kernel runtime from the standard mira config."""
        global _SHARED_KERNEL_APP
        if _SHARED_KERNEL_APP is not None:
            return _SHARED_KERNEL_APP
        bot = mira.from_config(
            config_path=config_path,
            workspace=workspace,
            model=model,
            model_preset=model_preset,
        )
        resolved_profile = profile or get_profile(
            profile_name or getattr(bot._config.kernel, "profile_name", None)
        )
        resolved_shell = shell or get_shell(shell_name or getattr(bot._config.kernel, "shell_name", None))
        _SHARED_KERNEL_APP = cls(bot, config=bot._config, profile=resolved_profile, shell=resolved_shell)
        return _SHARED_KERNEL_APP

    @classmethod
    def from_loop(
        cls,
        loop: AgentLoop,
        *,
        config: Config | None = None,
        profile: KernelProfile | None = None,
        shell: ShellDescriptor | None = None,
    ) -> KernelApp:
        global _SHARED_KERNEL_APP
        _SHARED_KERNEL_APP = cls(
            mira(loop, config=config),
            config=config,
            profile=profile,
            shell=shell,
        )
        return _SHARED_KERNEL_APP

    async def run(self, message: str, **kwargs: object) -> RunResult:
        """Single-turn execution via the kernel boundary."""
        return await self._bot.run(message, **kwargs)

    async def execute(self, message: str, **kwargs: object) -> ExecutionSnapshot:
        """Single-turn execution returning the stable kernel snapshot contract."""
        result = await self.run(message, **kwargs)
        return self.snapshot_from_result(result)

    async def run_streamed(self, message: str, **kwargs: object) -> RunStream:
        """Streamed execution for GUI shells.

        Consumers should normalize emitted SDK events with
        `kernel.normalize_stream_event` before rendering them.
        """
        return await self._bot.run_streamed(message, **kwargs)

    def snapshot_from_result(
        self,
        result: RunResult,
        *,
        session_metadata: dict[str, Any] | None = None,
    ) -> ExecutionSnapshot:
        """Project an SDK run result onto the stable execution snapshot contract.

        When session metadata is available, the snapshot is enriched with
        persisted runtime signals such as sustained-goal state and internal
        continuation markers.
        """
        snapshot = snapshot_from_run_result(result)
        if session_metadata:
            snapshot = merge_snapshot_with_session_metadata(snapshot, session_metadata)
        return snapshot

    def enrich_snapshot(
        self,
        snapshot: ExecutionSnapshot,
        *,
        session_metadata: dict[str, Any] | None = None,
    ) -> ExecutionSnapshot:
        """Apply session-layer runtime signals to an existing execution snapshot."""
        if not session_metadata:
            return snapshot
        enriched = merge_snapshot_with_session_metadata(snapshot, session_metadata)
        enriched.metadata["execution_lanes"] = self.execution_lanes(
            session_metadata=session_metadata,
        )
        return enriched

    def describe(self) -> dict[str, Any]:
        """Return the stable manifest a shell can use to configure itself."""
        self._refresh_board_runtime_status()
        self._refresh_live_event_log()
        manifest = build_kernel_manifest(profile=self.profile, shell=self.shell)
        manifest["runtime_adapters"] = self.runtime_adapters_snapshot()
        manifest["runtime_bridges"] = self.runtime_bridges_snapshot()
        manifest["runtime_modules"] = self.runtime_modules_snapshot()
        manifest["runtime_control"] = self.runtime_control_snapshot()
        manifest["diagnostics"] = self.diagnostics_snapshot
        manifest["session_controls"] = {
            "actions": _session_control_actions(),
        }
        manifest["worker_controls"] = {
            "actions": _worker_control_actions(),
        }
        manifest["execution_lanes"] = self.execution_lanes(session_metadata=self._active_session_metadata())
        manifest["scheduler"] = self.scheduler_snapshot(session_metadata=self._active_session_metadata())
        manifest["workers"] = self.worker_snapshot(session_metadata=self._active_session_metadata())
        manifest["embedded_topology"] = self.embedded_topology_snapshot()
        manifest["runtime_topology"] = self.runtime_topology_snapshot(
            session_metadata=self._active_session_metadata()
        )
        manifest["event_log"] = _copy_rows(self._event_log)
        targets = manifest.get("targets", {})
        adapter_target = dict(targets.get("adapter", {}))
        adapter_target["default_adapter"] = self._runtime_control.get("active_adapter")
        targets["adapter"] = adapter_target
        manifest["targets"] = targets
        return manifest

    def execute_operator_command(self, command_line: str) -> dict[str, Any]:
        return _execute_operator_command(self, command_line)

    def dispatch_control_action(self, action: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        normalized = str(action or "").strip()
        if not normalized:
            raise ValueError("missing action")
        payload = params or {}
        self.assert_control_action_allowed(normalized, raw=normalized)
        if normalized == "switch_adapter":
            adapter = str(payload.get("adapter") or "").strip()
            if not adapter:
                raise ValueError("missing adapter")
            return self.switch_runtime_adapter(adapter)
        if normalized == "focus_module":
            module = str(payload.get("module") or "").strip()
            if not module:
                raise ValueError("missing module")
            return self.focus_runtime_module(module)
        if normalized == "attach_board":
            return self.attach_board(
                transport=str(payload.get("transport") or "").strip() or None,
                port=str(payload.get("port") or "").strip() or None,
            )
        if normalized == "detach_board":
            return self.detach_board()
        if normalized == "record_fault":
            return self.record_fault(
                str(payload.get("level") or "fault").strip() or "fault",
                str(payload.get("adapter") or "").strip() or None,
            )
        if normalized == "clear_fault":
            return self.clear_fault(str(payload.get("adapter") or "").strip() or None)
        if normalized == "restart_bridge":
            return self.restart_bridge(str(payload.get("adapter") or "").strip() or None)
        if normalized == "pause_runtime":
            return self.pause_runtime(str(payload.get("reason") or "").strip() or None)
        if normalized == "resume_runtime":
            return self.resume_runtime()
        if normalized == "degrade_runtime":
            return self.degrade_runtime(str(payload.get("reason") or "").strip() or None)
        if normalized == "drain_background":
            return self.drain_background()
        if normalized == "prioritize_goal_lane":
            return self.prioritize_goal_lane()
        if normalized == "enter_maintenance":
            return self.enter_maintenance(str(payload.get("reason") or "").strip() or None)
        if normalized == "exit_maintenance":
            return self.exit_maintenance()
        raise ValueError(f"unknown kernel action: {normalized}")

    def _operator_privilege_role(self) -> str:
        geteuid = getattr(os, "geteuid", None)
        if callable(geteuid) and int(geteuid()) == 0:
            return "root"
        return "user"

    def _assert_operator_command_allowed(self, command: str, *, raw: str) -> None:
        if command not in _PRIVILEGED_OPERATOR_COMMAND_PREFIXES:
            return
        self.assert_control_action_allowed(command.replace("-", "_"), raw=raw)

    def assert_control_action_allowed(self, action: str, *, raw: str | None = None) -> None:
        if action not in _PRIVILEGED_CONTROL_ACTIONS:
            return
        host_contract = self._shell.host_contract if isinstance(self._shell.host_contract, dict) else {}
        surfaces = host_contract.get("surfaces", {}) if isinstance(host_contract.get("surfaces", {}), dict) else {}
        privilege = host_contract.get("privilege", {}) if isinstance(host_contract.get("privilege", {}), dict) else {}
        allows_privileged_controls = bool(surfaces.get("allowPrivilegedRuntimeControls"))
        privilege_role = str(privilege.get("role") or self._operator_privilege_role())
        can_elevate = bool(privilege.get("canElevate"))
        if allows_privileged_controls and (privilege_role == "root" or can_elevate):
            return
        raise PermissionError(f"operator action requires root privileges: {raw or action}")

    def _refresh_board_runtime_status(self) -> None:
        board = dict(self._runtime_control.get("board", {}))
        if not board.get("attached"):
            return
        active_adapter_name = str(self._runtime_control.get("active_adapter") or "")
        active_adapter = next(
            (adapter for adapter in self._runtime_adapters if adapter.get("name") == active_adapter_name),
            None,
        )
        if not isinstance(active_adapter, dict):
            return
        probe = board_status_runtime_probe(
            active_adapter,
            transport=board.get("transport"),
            port=board.get("port"),
        )
        if probe is None:
            return
        board["runtime_mode"] = probe.get("runtime_mode")
        board["bridge_artifact"] = probe.get("artifact")
        board["last_error"] = probe.get("error")
        board["health"] = probe.get("health") or ("ready" if probe.get("ok") else "fault")
        board["attached"] = bool(probe.get("ok"))
        self._runtime_control["board"] = board
        active_adapter_name = str(self._runtime_control.get("active_adapter") or "")
        signature = (
            bool(board.get("attached")),
            board.get("health"),
            board.get("runtime_mode"),
            board.get("bridge_artifact"),
            board.get("last_error"),
            board.get("transport"),
            board.get("port"),
        )
        if self._board_signatures.get(active_adapter_name) != signature:
            self._board_signatures[active_adapter_name] = signature
            self._record_kernel_event(
                "board_runtime_status",
                state="ok" if board.get("attached") and not board.get("last_error") else "fault",
                message=(
                    f"{active_adapter_name or 'board'} "
                    f"{'attached' if board.get('attached') else 'detached'} "
                    f"health={board.get('health') or 'unknown'} "
                    f"mode={board.get('runtime_mode') or 'unknown'} "
                    f"port={board.get('port') or 'unset'}"
                    + (
                        f" error={board.get('last_error')}"
                        if board.get("last_error")
                        else ""
                    )
                ),
            )

    def runtime_topology_snapshot(
        self,
        *,
        session_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        topology = build_runtime_topology(
            adapters=self.runtime_adapters_snapshot(),
            modules=self.runtime_modules_snapshot(),
            bridges=self.runtime_bridges_snapshot(),
            execution_lanes=self.execution_lanes(session_metadata=session_metadata),
            scheduler=self.scheduler_snapshot(session_metadata=session_metadata),
            workers=self.worker_snapshot(session_metadata=session_metadata),
        )
        topology["actions"] = [
            {
                "id": "inspect_runtime",
                "label": "inspect runtime",
                "pane": "runtime",
                "command": "topology runtime",
            },
            {
                "id": "runtime_orchestration",
                "label": "orchestration",
                "pane": "runtime",
                "command": "runtime orchestration",
            },
        ]
        return topology

    def embedded_topology_snapshot(self) -> dict[str, Any]:
        board = dict(self._runtime_control.get("board", {}))
        topology = build_embedded_topology(
            board=build_board_snapshot(
                attached=bool(board.get("attached", False)),
                transport=board.get("transport"),
                port=board.get("port"),
                target=board.get("target"),
                preferred_transport=board.get("preferred_transport"),
                health=board.get("health"),
                runtime_mode=board.get("runtime_mode"),
                bridge_artifact=board.get("bridge_artifact"),
                last_error=board.get("last_error"),
                available_ports=discover_serial_ports(),
            ),
            transports=["serial", "usb", "can"],
            active_adapter=self._runtime_control.get("active_adapter"),
        )
        topology["actions"] = [
            {
                "id": "inspect_embedded",
                "label": "inspect embedded",
                "pane": "runtime",
                "command": "topology embedded",
            },
            {
                "id": "refresh_board_ports",
                "label": "refresh ports",
                "pane": "adapters",
                "command": "board ports",
            },
            {
                "id": "board_status",
                "label": "board status",
                "pane": "adapters",
                "command": "board status",
            },
        ]
        return topology

    @property
    def diagnostics_snapshot(self) -> dict[str, Any]:
        fault_posture = dict(self._runtime_control.get("fault_posture", {}))
        execution_gate = dict(self._runtime_control.get("execution_gate", {}))
        maintenance_mode = dict(self._runtime_control.get("maintenance_mode", {}))
        board = dict(self._runtime_control.get("board", {}))
        dispatch_depth = len(self._dispatch_queue)
        native_depth = self._native_queue_depth
        scheduler_state = clone_scheduler_state(self._scheduler_state)
        dispatch_handoff_lane = str(scheduler_state.get("dispatch_handoff_lane") or "") or None
        dispatch_queue_state = (
            "delegated"
            if dispatch_handoff_lane and (dispatch_depth or native_depth)
            else (
                "preferred"
                if scheduler_state.get("dispatch_priority") and (dispatch_depth or native_depth)
                else ("queued" if (dispatch_depth or native_depth) else "ready")
            )
        )
        snapshot = {
            **build_diagnostics_snapshot(
                active_adapter=self._runtime_control.get("active_adapter"),
                module_count=len(self._runtime_modules),
                bridge_count=len(self._runtime_bridges),
                dispatch_queue_depth=dispatch_depth + native_depth,
                dispatch_queue_state=dispatch_queue_state,
                dispatch_handoff_lane=dispatch_handoff_lane,
                fault_level=str(fault_posture.get("last_level", "clear")),
                execution_gate=(
                    "busy"
                    if any(status == "running" for status in self._session_status.values())
                    else str(execution_gate.get("state", "open"))
                ),
                maintenance_mode=bool(maintenance_mode.get("enabled", False)),
                supervisor=str(fault_posture.get("supervisor", "userspace-kernel-loop")),
            )
        }
        checkpoint = self._active_checkpoint()
        if checkpoint:
            snapshot["snapshot"]["phase"] = checkpoint.get("phase")
            snapshot["snapshot"]["iteration"] = checkpoint.get("iteration")
            snapshot["snapshot"]["pending_tool_calls"] = len(list(checkpoint.get("pending_tool_calls", [])))
        snapshot["snapshot"]["planning"] = {
            **self._planning_snapshot(checkpoint),
            "trace": self._planning_trace(self._active_session_key),
        }
        subagent_rows = self._subagent_snapshot(self._active_session_key)
        if subagent_rows:
            snapshot["snapshot"]["subagent_workers"] = len(subagent_rows)
        board_snapshot = self._board_runtime_snapshot(board)
        native_snapshot = self._native_runtime_snapshot()
        session_metadata = self._active_session_metadata()
        snapshot["snapshot"]["board"] = board_snapshot
        snapshot["snapshot"]["native"] = native_snapshot
        snapshot["snapshot"]["goal_state"] = goal_state_ws_blob(session_metadata) if session_metadata else {"active": False}
        snapshot["snapshot"]["dispatch_contract"] = {
            "owner": (
                "goal"
                if dispatch_handoff_lane == "sustained_goal"
                else ("subagent" if dispatch_handoff_lane == "subagent" else "interactive")
            ),
            "mode": (
                "handoff"
                if dispatch_handoff_lane and dispatch_depth
                else ("priority" if scheduler_state.get("dispatch_priority") and dispatch_depth else "direct")
            ),
            "lane": dispatch_handoff_lane or "interactive",
        }
        return snapshot

    def execution_lanes(
        self,
        *,
        session_metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        goal_blob = goal_state_ws_blob(session_metadata) if session_metadata else {"active": False}
        continuation = internal_continuation_pending(session_metadata) if session_metadata else False
        scheduler_state = clone_scheduler_state(self._scheduler_state)
        session_key = self._active_session_key
        subagent_count = len(self._subagent_snapshot(session_key))
        dispatch_depth = len(self._dispatch_queue)
        dispatch_priority = bool(scheduler_state.get("dispatch_priority"))
        dispatch_handoff_lane = str(scheduler_state.get("dispatch_handoff_lane") or "")
        preferred_lane = (
            "interactive"
            if any(status == "running" for status in self._session_status.values())
            else str(scheduler_state.get("preferred_lane") or "interactive")
        )
        sustained_summary = (
            str(goal_blob.get("ui_summary") or goal_blob.get("objective") or "").strip()
            if goal_blob.get("active")
            else "Long-running objective slices with internal continuation support."
        )
        lanes = build_execution_lanes(
            preferred_lane=preferred_lane,
            goal_active=bool(goal_blob.get("active")),
            goal_continuing=continuation,
            goal_summary=sustained_summary or "Active sustained goal",
        )
        checkpoint = self._active_checkpoint()
        for lane in lanes:
            lane_id = str(lane.get("id") or "")
            lane["actions"] = [
                {
                    "id": "open_lane",
                    "label": "open lane",
                    "pane": "runtime",
                    "command": (
                        "session goal"
                        if lane_id == "sustained_goal"
                        else ("worker show" if lane_id == "subagent" else "lane show")
                    ),
                }
            ]
            if lane_id == "interactive" and checkpoint:
                lane["state"] = "running"
                lane["summary"] = f"{checkpoint.get('phase', 'running')} · iteration {checkpoint.get('iteration', 0)}"
            elif lane_id == "interactive" and dispatch_depth and not dispatch_handoff_lane:
                lane["state"] = "running" if dispatch_priority else "ready"
                lane["summary"] = (
                    f"{dispatch_depth} dispatch task(s) queued · "
                    f"{'priority active' if dispatch_priority else 'awaiting orchestration'}"
                )
            elif lane_id == "sustained_goal" and dispatch_handoff_lane == "sustained_goal" and dispatch_depth:
                lane["state"] = "running"
                lane["summary"] = f"{dispatch_depth} dispatch task(s) handed to sustained goal lane"
            elif lane_id == "subagent" and subagent_count:
                lane["state"] = "running"
                lane["summary"] = f"{subagent_count} delegated worker(s) active"
            elif lane_id == "subagent" and dispatch_handoff_lane == "subagent" and dispatch_depth:
                lane["state"] = "running"
                lane["summary"] = f"{dispatch_depth} dispatch task(s) handed to subagent lane"
        return lanes

    def scheduler_snapshot(
        self,
        *,
        session_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        lanes = {lane["id"]: lane for lane in self.execution_lanes(session_metadata=session_metadata)}
        goal_lane = lanes.get("sustained_goal", {})
        goal_state = str(goal_lane.get("state") or "idle")
        goal_depth = 1 if goal_state in {"active", "continuing"} else 0
        scheduler_state = clone_scheduler_state(self._scheduler_state)
        background_drain_requested = bool(scheduler_state.get("background_drain_requested"))
        dispatch_priority = bool(scheduler_state.get("dispatch_priority"))
        dispatch_handoff_lane = str(scheduler_state.get("dispatch_handoff_lane") or "")
        preferred_lane = str(scheduler_state.get("preferred_lane") or "interactive")
        checkpoint = self._active_checkpoint()
        subagent_rows = self._subagent_snapshot(self._active_session_key)
        active_adapter_name = str(self._runtime_control.get("active_adapter") or "")
        active_bridge = next(
            (
                dict(bridge)
                for bridge in self._runtime_bridges
                if str(bridge.get("adapter") or "") == active_adapter_name
            ),
            None,
        )
        interactive_depth = sum(
            1 for status in self._session_status.values() if status in {"queued", "running"}
        )
        automation_depth = len(subagent_rows)
        queue_snapshot = self._dispatch_queue_snapshot(limit=4)
        dispatch_depth = int(queue_snapshot["queue_depth"])
        dispatch_items = [dict(item) for item in list(queue_snapshot.get("queue_items") or [])]
        payload = {
            "policy": str(scheduler_state.get("policy") or "priority-foreground-with-background-drain"),
            "preferred_lane": preferred_lane,
            "background_drain_requested": background_drain_requested,
            "dispatch_priority": dispatch_priority,
            "dispatch_handoff_lane": dispatch_handoff_lane or None,
            "queues": [
                {
                    "id": "foreground",
                    "label": "Foreground Queue",
                    "lane": "interactive",
                    "depth": interactive_depth,
                    "state": "running" if interactive_depth else ("preferred" if preferred_lane == "interactive" else "ready"),
                    "job_class": "operator_turn",
                    "pending_tool_calls": len(list(checkpoint.get("pending_tool_calls", []))),
                    "completed_tool_results": len(list(checkpoint.get("completed_tool_results", []))),
                },
                {
                    "id": "goal_background",
                    "label": "Goal Background Queue",
                    "lane": "sustained_goal",
                    "depth": goal_depth,
                    "state": (
                        "handoff"
                        if dispatch_handoff_lane == "sustained_goal" and dispatch_depth
                        else ("draining" if background_drain_requested and goal_depth else goal_state)
                    ),
                    "job_class": "goal_slice",
                    "active_tasks": (
                        [f"dispatch:{item['label']}[{item.get('family', 'core')}]:{item['lifecycle']}" for item in dispatch_items[:3]]
                        if dispatch_handoff_lane == "sustained_goal" and dispatch_depth
                        else []
                    ),
                    "family_counts": queue_snapshot.get("families", "none")
                    if dispatch_handoff_lane == "sustained_goal" and dispatch_depth
                    else "none",
                    "family_rows": queue_snapshot.get("family_rows", [])
                    if dispatch_handoff_lane == "sustained_goal" and dispatch_depth
                    else [],
                    "dispatch_contract": {
                        "owner": "goal",
                        "mode": "handoff" if dispatch_handoff_lane == "sustained_goal" and dispatch_depth else "resident",
                        "lane": "sustained_goal",
                    },
                },
                {
                    "id": "automation",
                    "label": "Automation Queue",
                    "lane": "subagent",
                    "depth": automation_depth,
                    "state": (
                        "handoff"
                        if dispatch_handoff_lane == "subagent" and dispatch_depth
                        else ("running" if automation_depth else ("preferred" if preferred_lane == "subagent" else "available"))
                    ),
                    "job_class": "cron_or_trigger",
                    "active_tasks": (
                        [f"dispatch:{item['label']}[{item.get('family', 'core')}]:{item['lifecycle']}" for item in dispatch_items[:3]]
                        if dispatch_handoff_lane == "subagent" and dispatch_depth
                        else [row["label"] for row in subagent_rows[:4]]
                    ),
                    "family_counts": queue_snapshot.get("families", "none")
                    if dispatch_handoff_lane == "subagent" and dispatch_depth
                    else "none",
                    "family_rows": queue_snapshot.get("family_rows", [])
                    if dispatch_handoff_lane == "subagent" and dispatch_depth
                    else [],
                    "dispatch_contract": {
                        "owner": "subagent",
                        "mode": "handoff" if dispatch_handoff_lane == "subagent" and dispatch_depth else "resident",
                        "lane": "subagent",
                    },
                },
                {
                    "id": "tool_dispatch",
                    "label": "Tool Dispatch Queue",
                    "lane": "interactive",
                    "depth": dispatch_depth,
                    "state": (
                        "delegated"
                        if dispatch_handoff_lane and dispatch_depth
                        else (
                        "preferred"
                        if dispatch_priority and dispatch_depth
                        else ("queued" if dispatch_depth else "ready")
                        )
                    ),
                    "job_class": "tool_contract_dispatch",
                    "active_tasks": [
                        f"{item['label']}[{item.get('family', 'core')}]:{item['lifecycle']}"
                        for item in dispatch_items[:4]
                    ],
                    "family_counts": queue_snapshot.get("families", "none"),
                    "family_rows": queue_snapshot.get("family_rows", []),
                    "dispatch_contract": {
                        "owner": (
                            "goal"
                            if dispatch_handoff_lane == "sustained_goal"
                            else ("subagent" if dispatch_handoff_lane == "subagent" else "interactive")
                        ),
                        "mode": (
                            "handoff"
                            if dispatch_handoff_lane and dispatch_depth
                            else ("priority" if dispatch_priority and dispatch_depth else "direct")
                        ),
                        "lane": dispatch_handoff_lane or "interactive",
                    },
                    "actions": [
                        {
                            "id": "inspect_dispatch",
                            "label": "inspect",
                            "pane": "runtime",
                            "command": "tool status",
                        },
                        {
                            "id": "prioritize_dispatch",
                            "privileged": True,
                            "required_role": "root",
                            "privileged_reason": "requires elevated dispatch control",
                            "label": "prioritize",
                            "pane": "runtime",
                            "command": "tool prioritize",
                        },
                        {
                            "id": "delegate_goal",
                            "privileged": True,
                            "required_role": "root",
                            "privileged_reason": "requires elevated dispatch control",
                            "label": "goal lane",
                            "pane": "runtime",
                            "command": "tool delegate-goal",
                        },
                        {
                            "id": "delegate_subagent",
                            "privileged": True,
                            "required_role": "root",
                            "privileged_reason": "requires elevated dispatch control",
                            "label": "subagent",
                            "pane": "runtime",
                            "command": "tool delegate-subagent",
                        },
                        {
                            "id": "complete_dispatch",
                            "privileged": True,
                            "required_role": "root",
                            "privileged_reason": "requires elevated dispatch control",
                            "label": "complete",
                            "pane": "runtime",
                            "command": "tool complete",
                        },
                        {
                            "id": "fail_dispatch",
                            "privileged": True,
                            "required_role": "root",
                            "privileged_reason": "requires elevated dispatch control",
                            "label": "fail",
                            "pane": "faults",
                            "command": "tool fail",
                        },
                        {
                            "id": "drain_dispatch",
                            "privileged": True,
                            "required_role": "root",
                            "privileged_reason": "requires elevated dispatch control",
                            "label": "drain",
                            "pane": "runtime",
                            "command": "tool drain",
                        },
                        {
                            "id": "clear_dispatch",
                            "privileged": True,
                            "required_role": "root",
                            "privileged_reason": "requires elevated dispatch control",
                            "label": "clear",
                            "pane": "runtime",
                            "command": "tool clear-queue",
                        },
                    ],
                },
            ],
        }
        if active_bridge is not None:
            payload["active_runtime"] = {
                "adapter": active_bridge.get("adapter"),
                "health": active_bridge.get("health"),
                "runtime_mode": active_bridge.get("runtime_mode"),
                "runtime_stage": active_bridge.get("runtime_stage"),
                "artifact": active_bridge.get("manifest") or active_bridge.get("entrypoint"),
            }
        return payload

    def worker_snapshot(
        self,
        *,
        session_metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        goal_blob = goal_state_ws_blob(session_metadata) if session_metadata else {"active": False}
        continuation = internal_continuation_pending(session_metadata) if session_metadata else False
        scheduler_state = clone_scheduler_state(self._scheduler_state)
        preferred_lane = str(scheduler_state.get("preferred_lane") or "interactive")
        dispatch_handoff_lane = str(scheduler_state.get("dispatch_handoff_lane") or "")
        queue_snapshot = self._dispatch_queue_snapshot(limit=3)
        dispatch_depth = int(queue_snapshot["queue_depth"])
        dispatch_items = [dict(item) for item in list(queue_snapshot.get("queue_items") or [])]
        if any(status == "running" for status in self._session_status.values()):
            preferred_lane = "interactive"
        workers = build_worker_registry()
        for worker in workers:
            lane = str(worker.get("lane") or "")
            if lane == "interactive":
                worker["state"] = "preferred" if preferred_lane == "interactive" else "ready"
            elif lane == "sustained_goal":
                if continuation:
                    worker["state"] = "continuing"
                elif bool(goal_blob.get("active")):
                    worker["state"] = "active"
                elif preferred_lane == "sustained_goal":
                    worker["state"] = "preferred"
            elif lane == "subagent" and preferred_lane == "subagent":
                worker["state"] = "preferred"
        checkpoint = self._active_checkpoint()
        subagent_rows = self._subagent_snapshot(self._active_session_key)
        active_adapter_name = str(self._runtime_control.get("active_adapter") or "")
        active_bridge = next(
            (
                dict(bridge)
                for bridge in self._runtime_bridges
                if str(bridge.get("adapter") or "") == active_adapter_name
            ),
            None,
        )
        for worker in workers:
            lane = str(worker.get("lane") or "")
            if lane == "interactive" and checkpoint:
                worker["state"] = "running"
                worker["summary"] = f"{checkpoint.get('phase', 'running')} · iteration {checkpoint.get('iteration', 0)}"
            elif lane == "interactive" and dispatch_depth and not dispatch_handoff_lane:
                worker["state"] = "running" if bool(scheduler_state.get("dispatch_priority")) else "ready"
                worker["summary"] = (
                    f"{dispatch_depth} queued tool dispatch(es) · "
                    f"{'priority active' if scheduler_state.get('dispatch_priority') else 'awaiting orchestration'}"
                )
                worker["tasks"] = [
                    {
                        "task_id": f"dispatch-{index}",
                        "label": f"Dispatch {item['tool']}",
                        "phase": item["lifecycle"],
                        "iteration": 0,
                        "task_description": f"{item['label']}:{item['lifecycle']}",
                        "task_target": "dispatch",
                        "actions": [
                            {
                                "id": "inspect_dispatch",
                                "label": "inspect dispatch",
                                "pane": "runtime",
                                "command": "tool status",
                            }
                        ],
                        "dispatch_contract": {
                            "owner": "interactive",
                            "mode": "priority" if bool(scheduler_state.get("dispatch_priority")) else "direct",
                            "lane": "interactive",
                        },
                        "tool_events": [],
                        "error": None,
                    }
                    for index, item in enumerate(dispatch_items[:3], start=1)
                ]
            elif lane == "interactive" and active_bridge is not None:
                worker["summary"] = (
                    f"{active_bridge.get('adapter', 'runtime')} · "
                    f"{active_bridge.get('runtime_mode') or active_bridge.get('backend_kind') or 'unknown'} · "
                    f"{active_bridge.get('health') or 'unknown'}"
                )
                worker["runtime_backend"] = {
                    "adapter": active_bridge.get("adapter"),
                    "health": active_bridge.get("health"),
                    "runtime_mode": active_bridge.get("runtime_mode"),
                    "runtime_stage": active_bridge.get("runtime_stage"),
                    "artifact": active_bridge.get("manifest") or active_bridge.get("entrypoint"),
                }
            elif lane == "sustained_goal" and dispatch_handoff_lane == "sustained_goal" and dispatch_depth:
                worker["state"] = "running"
                worker["summary"] = f"{dispatch_depth} dispatch(es) handed to sustained goal lane"
                worker["tasks"] = [
                    {
                        "task_id": f"goal-dispatch-{index}",
                        "label": f"Goal handoff {item['tool']}",
                        "phase": item["lifecycle"],
                        "iteration": 0,
                        "task_description": f"{item['label']}:{item['lifecycle']}",
                        "task_target": "goal_dispatch",
                        "actions": [
                            {
                                "id": "inspect_dispatch",
                                "label": "inspect dispatch",
                                "pane": "runtime",
                                "command": "tool status",
                            },
                            {
                                "id": "open_goal_lane",
                                "label": "open goal lane",
                                "pane": "runtime",
                                "command": "session goal",
                            },
                        ],
                        "dispatch_contract": {
                            "owner": "goal",
                            "mode": "handoff",
                            "lane": "sustained_goal",
                        },
                        "tool_events": [],
                        "error": None,
                    }
                    for index, item in enumerate(dispatch_items[:3], start=1)
                ]
            elif lane == "subagent" and subagent_rows:
                worker["state"] = "running"
                top = subagent_rows[0]
                worker["summary"] = f"{len(subagent_rows)} active · {top.get('label')} / {top.get('phase')}"
                worker["tasks"] = subagent_rows[:3]
            elif lane == "subagent" and dispatch_handoff_lane == "subagent" and dispatch_depth:
                worker["state"] = "running"
                worker["summary"] = f"{dispatch_depth} dispatch(es) handed to subagent lane"
                worker["tasks"] = [
                    {
                        "task_id": f"subagent-dispatch-{index}",
                        "label": f"Subagent handoff {item['tool']}",
                        "phase": item["lifecycle"],
                        "iteration": 0,
                        "task_description": f"{item['label']}:{item['lifecycle']}",
                        "task_target": "subagent_dispatch",
                        "actions": [
                            {
                                "id": "inspect_dispatch",
                                "label": "inspect dispatch",
                                "pane": "runtime",
                                "command": "tool status",
                            },
                            {
                                "id": "open_subagent_lane",
                                "label": "open subagent lane",
                                "pane": "runtime",
                                "command": "worker show",
                            },
                        ],
                        "dispatch_contract": {
                            "owner": "subagent",
                            "mode": "handoff",
                            "lane": "subagent",
                        },
                        "tool_events": [],
                        "error": None,
                    }
                    for index, item in enumerate(dispatch_items[:3], start=1)
                ]
        return workers

    def drain_background(self) -> dict[str, Any]:
        self._scheduler_state = request_background_drain(self._scheduler_state)
        self._record_kernel_event(
            "drain_background",
            state="ok",
            message="background queues drained by operator request",
        )
        return self.runtime_control

    def prioritize_goal_lane(self) -> dict[str, Any]:
        self._scheduler_state = prioritize_lane(
            self._scheduler_state,
            lane="sustained_goal",
        )
        self._record_kernel_event(
            "prioritize_goal_lane",
            state="ok",
            message="scheduler priority shifted toward sustained goal lane",
        )
        return self.runtime_control

    def _record_kernel_event(
        self,
        action: str,
        *,
        state: str,
        message: str,
        event_type: str | None = None,
        session_key: str | None = None,
        iteration: int | None = None,
        latency_ms: int | None = None,
    ) -> None:
        self._event_log = append_kernel_event(
            self._event_log,
            action=action,
            state=state,
            message=message,
            event_type=event_type,
            session_key=session_key,
            iteration=iteration,
            latency_ms=latency_ms,
        )

    def _store_native_command_state(
        self,
        *,
        queue_depth: int | None = None,
        command_depth: int | None = None,
        artifact: str | None = None,
        last_command: dict[str, Any] | None = None,
        recent_commands: list[dict[str, Any]] | None = None,
        module_count: int | None = None,
        module_states: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        if queue_depth is not None:
            self._native_queue_depth = queue_depth
        if command_depth is not None:
            self._native_command_depth = command_depth
        if artifact is not None:
            self._native_bridge_artifact = artifact or None
        if recent_commands is not None:
            self._native_recent_commands = _copy_rows(recent_commands, limit=8)
        if module_count is not None:
            self._native_module_count = module_count
        if module_states is not None:
            self._native_module_states = {
                str(name): dict(state)
                for name, state in module_states.items()
            }
        if last_command is not None:
            self._native_last_command = dict(last_command)

    def _reset_native_command_state(self) -> None:
        self._store_native_command_state(
            queue_depth=0,
            command_depth=0,
            artifact=None,
            recent_commands=[],
            module_count=0,
            module_states={},
            last_command={},
        )

    def _dispatch_native_control(
        self,
        *,
        target: str,
        action: str,
        value: str = "",
    ) -> None:
        result = dispatch_native_bridge_command(target=target, action=action, value=value)
        if result.get("ok"):
            artifact = str(result.get("artifact") or "").strip()
            next_depth = int(result.get("queue_depth") or self._native_command_depth)
            self._store_native_command_state(
                command_depth=next_depth,
                artifact=artifact,
                last_command={
                    "target": target,
                    "action": action,
                    "command": str(result.get("command") or ""),
                    "value": value,
                    "health": str(result.get("health") or "ready"),
                    "status": str(result.get("status") or "queued"),
                    "code": int(result.get("code") or 0),
                    "queue_depth": next_depth,
                    "artifact": artifact or self._native_bridge_artifact,
                    "updated_at_ms": result.get("updated_at_ms"),
                },
            )
            self._record_kernel_event(
                "native_command",
                state="ok",
                message=(
                    f"{target}:{action} queued"
                    + (f" · {value}" if value else "")
                    + f" · depth={next_depth}"
                ),
            )
        else:
            error = str(result.get("error") or "native command rejected")
            self._record_kernel_event(
                "native_command",
                state="fault",
                message=f"{target}:{action} failed · {error}",
            )

    def _board_runtime_snapshot(self, board: dict[str, Any]) -> dict[str, Any]:
        return {
            "attached": bool(board.get("attached")),
            "health": board.get("health"),
            "transport": board.get("transport"),
            "port": board.get("port"),
            "target": board.get("target"),
            "preferred_transport": board.get("preferred_transport"),
            "runtime_mode": board.get("runtime_mode"),
            "bridge_artifact": board.get("bridge_artifact"),
            "last_error": board.get("last_error"),
            "available_ports": list(board.get("available_ports") or []),
        }

    def _native_runtime_snapshot(self) -> dict[str, Any]:
        last_command = dict(self._native_last_command or {})
        return {
            "health": str(last_command.get("health") or "ready"),
            "queue_depth": self._native_queue_depth,
            "bridge_artifact": self._native_bridge_artifact,
            "module_count": self._native_module_count or len(self._native_module_states),
            "command_depth": self._native_command_depth,
            "recent_commands": _copy_rows(self._native_recent_commands, limit=8),
            "last_command": last_command,
            "modules": {
                name: dict(state)
                for name, state in self._native_module_states.items()
            },
        }

    def _native_command_details(
        self,
        *,
        action: str,
        target: str,
        command: str,
        value: str = "",
        status: str | None = None,
        code: int | None = None,
        updated_at_ms: int | None = None,
    ) -> dict[str, Any]:
        native_snapshot = self._native_runtime_snapshot()
        native_last_command = dict(native_snapshot.get("last_command") or {})
        return {
            "subject": "native",
            "action": action,
            "target": target,
            "command": command,
            "value": value,
            "health": str(native_last_command.get("health") or "ready"),
            "status": status or str(native_last_command.get("status") or "queued"),
            "code": code if code is not None else int(native_last_command.get("code") or 0),
            "queue_depth": int(native_snapshot.get("queue_depth") or 0),
            "artifact": native_snapshot.get("bridge_artifact") or "none",
            "updated_at_ms": (
                updated_at_ms
                if updated_at_ms is not None
                else native_last_command.get("updated_at_ms")
            ),
        }

    def _native_summary_details(
        self,
        *,
        action: str,
        target: str = "runtime",
        command: str,
        value: str = "",
        status: str | None = None,
        code: int | None = None,
        updated_at_ms: int | None = None,
    ) -> dict[str, Any]:
        details = self._native_command_details(
            action=action,
            target=target,
            command=command,
            value=value,
            status=status,
            code=code,
            updated_at_ms=updated_at_ms,
        )
        native_snapshot = self._native_runtime_snapshot()
        native_last_command = dict(native_snapshot.get("last_command") or {})
        details["command_depth"] = int(native_snapshot.get("command_depth") or 0)
        details["module_count"] = int(native_snapshot.get("module_count") or 0)
        details["last_target"] = str(native_last_command.get("target") or "none")
        details["last_action"] = str(native_last_command.get("action") or "none")
        details["last_summary"] = str(native_last_command.get("summary") or "none:none")
        return details

    def _dispatch_native_action(
        self,
        *,
        action_label: str,
        target: str,
        command: str,
        value: str = "",
        pane: str = "adapters",
    ) -> tuple[dict[str, Any], str, dict[str, Any], str]:
        self._dispatch_native_control(target=target, action=command, value=value)
        state = self.runtime_control_snapshot()
        details = self._native_command_details(
            action=action_label,
            target=target,
            command=str(self._native_last_command.get("command") or command),
            value=value,
        )
        output = (
            f"native {action_label} target={target}"
            f" action={command}"
            f" depth={details.get('queue_depth', 0)}"
        )
        target_pane = pane
        return state, output, details, target_pane

    def _dispatch_queue_snapshot(self, *, limit: int = 6) -> dict[str, Any]:
        scheduler_state = clone_scheduler_state(self._scheduler_state)
        dispatch_handoff_lane = str(scheduler_state.get("dispatch_handoff_lane") or "none")
        dispatch_priority = bool(scheduler_state.get("dispatch_priority"))
        lifecycle_counts: dict[str, int] = {}
        family_counts: dict[str, int] = {}
        items: list[str] = []
        roots: list[str] = []
        queue_items: list[dict[str, Any]] = []
        for row in self._dispatch_queue:
            lifecycle = str(row.get("lifecycle") or row.get("status") or "queued")
            lifecycle_counts[lifecycle] = lifecycle_counts.get(lifecycle, 0) + 1
            family = str(row.get("family") or tool_contract_family(str(row.get("tool") or "")))
            family_counts[family] = family_counts.get(family, 0) + 1
        for row in self._dispatch_queue[:limit]:
            tool = str(row.get("tool") or "unknown")
            family = str(row.get("family") or tool_contract_family(tool))
            module = str(row.get("module") or "runtime")
            lifecycle = str(row.get("lifecycle") or row.get("status") or "queued")
            items.append(f"{tool}[{family}]@{module}:{lifecycle}")
            root = str(row.get("root") or "").strip()
            if root:
                roots.append(root)
            queue_items.append(
                {
                    "tool": tool,
                    "family": family,
                    "module": module,
                    "lifecycle": lifecycle,
                    "root": root or None,
                    "label": f"{tool}@{module}",
                }
            )
        lifecycle_rows = [
            {"state": name, "count": count}
            for name, count in lifecycle_counts.items()
        ]
        family_rows = [
            {"family": name, "count": count}
            for name, count in sorted(family_counts.items())
        ]
        return {
            "queue_depth": len(self._dispatch_queue),
            "priority": "on" if dispatch_priority else "off",
            "handoff": dispatch_handoff_lane,
            "items": ", ".join(items) or "none",
            "families": ", ".join(
                f"{name}:{count}" for name, count in sorted(family_counts.items())
            ) or "none",
            "lifecycle": ", ".join(
                f"{name}:{count}" for name, count in lifecycle_counts.items()
            ) or "none",
            "roots": ", ".join(roots[:limit]) or "none",
            "queue_items": queue_items,
            "root_items": roots[:limit],
            "lifecycle_rows": lifecycle_rows,
            "family_rows": family_rows,
        }

    def switch_runtime_adapter(self, adapter_name: str) -> dict[str, Any]:
        self._runtime_control = set_active_adapter(
            self._runtime_control,
            adapter_name=adapter_name,
            adapter_names=[adapter["name"] for adapter in self._runtime_adapters],
        )
        self._runtime_bridges = activate_runtime_bridge(
            self._runtime_bridges,
            adapter_name=adapter_name,
        )
        self._dispatch_native_control(
            target="runtime",
            action="switch_adapter",
            value=adapter_name,
        )
        self._record_kernel_event(
            "switch_adapter",
            state="ok",
            message=f"active adapter -> {adapter_name}",
        )
        return self.runtime_control

    def focus_runtime_module(self, module_name: str) -> dict[str, Any]:
        self._runtime_control = set_module_focus(
            self._runtime_control,
            module_name=module_name,
            module_names=[module["name"] for module in self._runtime_modules],
        )
        self._dispatch_native_control(
            target=module_name,
            action="focus_module",
            value=module_name,
        )
        self._record_kernel_event(
            "focus_module",
            state="ok",
            message=f"module focus -> {module_name}",
        )
        return self.runtime_control

    def attach_board(
        self,
        *,
        transport: str | None = None,
        port: str | None = None,
    ) -> dict[str, Any]:
        next_state = attach_runtime_board(
            self._runtime_control,
            transport=transport,
            port=port,
        )
        board = dict(next_state.get("board", {}))
        active_adapter_name = str(next_state.get("active_adapter") or "")
        active_adapter = next(
            (adapter for adapter in self._runtime_adapters if adapter.get("name") == active_adapter_name),
            None,
        )
        probe_result = (
            attach_runtime_board_probe(
                active_adapter,
                transport=str(board.get("transport") or "serial"),
                port=str(board.get("port") or "/dev/tty.mira"),
            )
            if isinstance(active_adapter, dict)
            else None
        )
        if probe_result is not None and not probe_result.get("ok"):
            self._runtime_bridges = mark_bridge_fault(
                self._runtime_bridges,
                adapter_name=active_adapter_name,
                error=str(probe_result.get("error") or "board attach failed"),
            )
            board["attached"] = False
            board["health"] = "fault"
            board["runtime_mode"] = None
            board["bridge_artifact"] = probe_result.get("artifact")
            board["last_error"] = probe_result.get("error")
            next_state["board"] = board
            self._runtime_control = next_state
            self._record_kernel_event(
                "attach_board",
                state="fault",
                message=str(probe_result.get("error") or "board attach failed"),
            )
            return self.runtime_control
        if probe_result is not None:
            board["health"] = probe_result.get("health") or ("ready" if probe_result.get("ok") else "fault")
            board["runtime_mode"] = probe_result.get("runtime_mode")
            board["bridge_artifact"] = probe_result.get("artifact")
            board["last_error"] = probe_result.get("error")
        next_state["board"] = board
        self._runtime_control = next_state
        self._dispatch_native_control(
            target="board",
            action="attach",
            value=f"{board.get('transport') or transport or 'serial'}:{board.get('port') or port or 'auto'}",
        )
        self._record_kernel_event(
            "attach_board",
            state="ok",
            message=(
                f"board attached via {board.get('transport') or transport or 'default'}"
                + (
                    f" ({probe_result.get('artifact')})"
                    if probe_result is not None and probe_result.get("artifact")
                    else ""
                )
            ),
        )
        return self.runtime_control

    def detach_board(self) -> dict[str, Any]:
        self._runtime_control = detach_runtime_board(self._runtime_control)
        active_adapter_name = str(self._runtime_control.get("active_adapter") or "")
        self._board_signatures.pop(active_adapter_name, None)
        self._dispatch_native_control(
            target="board",
            action="detach",
            value=active_adapter_name,
        )
        self._record_kernel_event(
            "detach_board",
            state="ok",
            message="board detached",
        )
        return self.runtime_control

    def record_fault(self, level: str = "fault", adapter_name: str | None = None) -> dict[str, Any]:
        self._runtime_control = set_fault_level(self._runtime_control, level=level)
        target_adapter = adapter_name or str(self._runtime_control.get("active_adapter") or "")
        if target_adapter:
            self._runtime_bridges = mark_bridge_fault(
                self._runtime_bridges,
                adapter_name=target_adapter,
                error=level,
            )
            self._dispatch_native_control(
                target=target_adapter,
                action="record_fault",
                value=level,
            )
            self._record_kernel_event(
                "record_fault",
                state="fault",
                message=f"{target_adapter or 'runtime'} marked {level}",
            )
            return self.runtime_control
        self._record_kernel_event(
            "record_fault",
            state="fault",
            message=f"{target_adapter or 'runtime'} marked {level}",
        )
        return self.runtime_control

    def clear_fault(self, adapter_name: str | None = None) -> dict[str, Any]:
        self._runtime_control = set_fault_level(self._runtime_control, level="clear")
        target_adapter = adapter_name or str(self._runtime_control.get("active_adapter") or "")
        if target_adapter:
            self._runtime_bridges = clear_bridge_fault(
                self._runtime_bridges,
                adapter_name=target_adapter,
            )
            self._dispatch_native_control(
                target=target_adapter,
                action="clear_fault",
                value="clear",
            )
            self._record_kernel_event(
                "clear_fault",
                state="ok",
                message=f"{target_adapter or 'runtime'} fault cleared",
            )
            return self.runtime_control
        self._record_kernel_event(
            "clear_fault",
            state="ok",
            message=f"{target_adapter or 'runtime'} fault cleared",
        )
        return self.runtime_control

    def restart_bridge(self, adapter_name: str | None = None) -> dict[str, Any]:
        target_adapter = adapter_name or str(self._runtime_control.get("active_adapter") or "")
        if not target_adapter:
            raise ValueError("No active bridge adapter")
        self._runtime_bridges = restart_runtime_bridge(
            self._runtime_bridges,
            adapter_name=target_adapter,
        )
        self._dispatch_native_control(
            target=target_adapter,
            action="restart_bridge",
        )
        self._record_kernel_event(
            "restart_bridge",
            state="ok",
            message=f"bridge restarted -> {target_adapter}",
        )
        return self.runtime_control

    def pause_runtime(self, reason: str | None = None) -> dict[str, Any]:
        pause_reason = reason or "operator-paused"
        self._runtime_control = set_execution_gate(
            self._runtime_control,
            gate_state="paused",
            reason=pause_reason,
        )
        self._dispatch_native_control(
            target="runtime",
            action="pause",
            value=pause_reason,
        )
        self._record_kernel_event(
            "pause_runtime",
            state="paused",
            message=reason or "runtime paused by operator",
        )
        return self.runtime_control

    def resume_runtime(self) -> dict[str, Any]:
        self._runtime_control = set_execution_gate(
            self._runtime_control,
            gate_state="open",
            reason="operator-ready",
        )
        self._runtime_control = set_maintenance_mode(self._runtime_control, enabled=False)
        self._runtime_bridges = set_bridge_maintenance(self._runtime_bridges, enabled=False)
        active_adapter = str(self._runtime_control.get("active_adapter") or "")
        if active_adapter:
            self._runtime_bridges = activate_runtime_bridge(
                self._runtime_bridges,
                adapter_name=active_adapter,
            )
        self._dispatch_native_control(
            target="runtime",
            action="resume",
            value="operator-ready",
        )
        self._record_kernel_event(
            "resume_runtime",
            state="ok",
            message="runtime resumed",
        )
        return self.runtime_control

    def degrade_runtime(self, reason: str | None = None) -> dict[str, Any]:
        degrade_reason = reason or "fault-containment"
        self._runtime_control = set_execution_gate(
            self._runtime_control,
            gate_state="degraded",
            reason=degrade_reason,
        )
        self._dispatch_native_control(
            target="runtime",
            action="degrade",
            value=degrade_reason,
        )
        self._record_kernel_event(
            "degrade_runtime",
            state="degraded",
            message=reason or "runtime degraded for containment",
        )
        return self.runtime_control

    def enter_maintenance(self, reason: str | None = None) -> dict[str, Any]:
        maintenance_reason = reason or "operator-maintenance-window"
        self._runtime_control = set_maintenance_mode(
            self._runtime_control,
            enabled=True,
            reason=maintenance_reason,
        )
        self._runtime_control = set_execution_gate(
            self._runtime_control,
            gate_state="paused",
            reason=maintenance_reason,
        )
        self._runtime_bridges = set_bridge_maintenance(
            self._runtime_bridges,
            enabled=True,
            reason=maintenance_reason,
        )
        self._dispatch_native_control(
            target="runtime",
            action="enter_maintenance",
            value=maintenance_reason,
        )
        self._record_kernel_event(
            "enter_maintenance",
            state="maintenance",
            message=maintenance_reason,
        )
        return self.runtime_control

    def exit_maintenance(self) -> dict[str, Any]:
        self._runtime_control = set_maintenance_mode(self._runtime_control, enabled=False)
        self._runtime_control = set_execution_gate(
            self._runtime_control,
            gate_state="open",
            reason="operator-ready",
        )
        self._runtime_bridges = set_bridge_maintenance(self._runtime_bridges, enabled=False)
        active_adapter = str(self._runtime_control.get("active_adapter") or "")
        if active_adapter:
            self._runtime_bridges = activate_runtime_bridge(
                self._runtime_bridges,
                adapter_name=active_adapter,
            )
        self._dispatch_native_control(
            target="runtime",
            action="exit_maintenance",
            value="operator-ready",
        )
        self._record_kernel_event(
            "exit_maintenance",
            state="ok",
            message="maintenance window closed",
        )
        return self.runtime_control

    @classmethod
    def build_loop(
        cls,
        config: Config,
    ) -> AgentLoop:
        """Expose loop construction behind the kernel namespace."""
        from mira.agent.hooks import create_file_edit_activity_hook

        return AgentLoop.from_config(
            config,
            image_generation_provider_configs=image_gen_provider_configs(config),
            hook_factories=[create_file_edit_activity_hook],
        )
