"""Kernel-oriented runtime facade.

`mira` remains the full SDK surface. `KernelApp` narrows that surface for
products that want a stable mature-agent boundary: a small kernel API under a
thin GUI.
"""

from __future__ import annotations

import os
from pathlib import Path
import shlex
from typing import Any

from mira.agent.loop import AgentLoop
from mira import __app_name__, __cli_name__
from mira.bus.runtime_events import (
    GoalStateChanged,
    RuntimeEventBus,
    RuntimeModelChanged,
    SessionTurnStarted,
    TurnCompleted,
    TurnRunStatusChanged,
)
from mira.config.schema import Config
from mira.mira import mira, RunResult, RunStream
from mira.providers.image_generation import image_gen_provider_configs
from .execution_plane import build_execution_lanes
from mira.session.goal_state import goal_state_ws_blob, sustained_goal_active
from mira.session.turn_continuation import (
    internal_continuation_pending,
    reset_goal_continuation_rounds,
)
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
from .module_registry import list_kernel_modules
from .profile import KernelProfile, get_profile, lite_customer_profile, list_profiles
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
from .runtime_probe import attach_runtime_board_probe, board_status_runtime_probe, discover_serial_ports
from .native_bridge import dispatch_native_bridge_command, snapshot_native_bridge
from .runtime_control import build_runtime_control_state
from .runtime_control import (
    attach_board as attach_runtime_board,
    clone_runtime_control_state,
    detach_board as detach_runtime_board,
    set_active_adapter,
    set_execution_gate,
    set_fault_level,
    set_maintenance_mode,
    set_module_focus,
)
from .shell import ShellDescriptor, default_engineering_shell, get_shell, list_shells
from .scheduler import (
    build_scheduler_state,
    clone_scheduler_state,
    prioritize_lane,
    request_background_drain,
)
from .observability import append_kernel_event, build_diagnostics_snapshot
from .worker_plane import build_worker_registry
from .runtime_topology import build_runtime_topology
from .embedded_plane import build_board_snapshot, build_embedded_topology

KERNEL_MANIFEST_VERSION = 1
KERNEL_EVENT_CONTRACT_VERSION = 1
KERNEL_SNAPSHOT_CONTRACT_VERSION = 1
_SHARED_KERNEL_APP: KernelApp | None = None
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
            "actions": [
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
            ],
        },
        "worker_controls": {
            "actions": [
                {
                    "id": "inspect_workers",
                    "label": "inspect workers",
                    "pane": "runtime",
                    "command": "worker show",
                },
            ],
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


def tool_contract_family(tool_name: str) -> str:
    name = str(tool_name or "").strip().lower()
    if not name:
        return "unknown"
    if name.startswith("mcp") or name.startswith("browser"):
        return "mcp"
    if name.startswith("web"):
        return "web"
    if name.startswith("file") or name.startswith("fs"):
        return "filesystem"
    if name.startswith("shell") or name.startswith("exec"):
        return "shell"
    if "subagent" in name:
        return "subagent"
    if "goal" in name or "long" in name or "task" in name:
        return "long-task"
    return "core"


def tool_contract_family_counts(tools: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for tool in tools:
        family = tool_contract_family(tool)
        counts[family] = counts.get(family, 0) + 1
    return counts


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
            row["actions"] = [
                {
                    "id": "inspect_adapter",
                    "label": "inspect",
                    "pane": "adapters",
                    "command": f"adapter status {adapter_name}".strip(),
                }
            ]
            rows.append(row)
        return rows

    def runtime_modules_snapshot(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for module in self._runtime_modules:
            row = dict(module)
            module_name = str(row.get("name") or "")
            row["actions"] = [
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
                }
            ]
            native_state = self._native_module_states.get(str(row.get("name") or ""))
            if native_state:
                status = str(native_state.get("status") or row.get("status") or "ready")
                row["status"] = status
                row["native_status"] = status
                row["native_status_code"] = native_state.get("status_code")
                row["native_last_code"] = native_state.get("last_code")
                row["native_updated_at_ms"] = native_state.get("updated_at_ms")
                summary = str(row.get("summary") or "").strip()
                native_summary = str(native_state.get("summary") or f"native bridge {status}").strip()
                row["summary"] = f"{summary} · {native_summary}" if summary else native_summary
                row["actions"].append(
                    {
                        "id": "inspect_native",
                        "label": "inspect",
                        "pane": "modules",
                        "command": f"native inspect {module_name}".strip(),
                    }
                )
                row["actions"].append(
                    {
                        "id": "inspect_native_status",
                        "label": "inspect native",
                        "pane": "adapters",
                        "command": "native last-command",
                    }
                )
            rows.append(row)
        return rows

    def runtime_bridges_snapshot(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for bridge in self._runtime_bridges:
            row = dict(bridge)
            adapter_name = str(row.get("adapter") or "")
            row["actions"] = [
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
                    "privileged_reason": "requires elevated runtime control",
                },
                {
                    "id": "mark_bridge_fault",
                    "label": "mark fault",
                    "pane": "faults",
                    "command": f"bridge fault {adapter_name}".strip(),
                    "privileged": True,
                    "required_role": "root",
                    "privileged_reason": "requires elevated fault control",
                },
                {
                    "id": "clear_bridge_fault",
                    "label": "clear fault",
                    "pane": "faults",
                    "command": f"clear-fault {adapter_name}".strip(),
                    "privileged": True,
                    "required_role": "root",
                    "privileged_reason": "requires elevated fault control",
                },
            ]
            rows.append(row)
        return rows

    def runtime_control_snapshot(self) -> dict[str, Any]:
        state = self.runtime_control
        fault_posture = dict(state.get("fault_posture", {}))
        fault_posture["actions"] = [
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
                "privileged_reason": "requires elevated fault control",
            },
            {
                "id": "record_fault",
                "label": "record",
                "pane": "faults",
                "command": "fault record",
                "privileged": True,
                "required_role": "root",
                "privileged_reason": "requires elevated fault control",
            },
            {
                "id": "enter_maintenance",
                "label": "maintenance on",
                "pane": "control_plane",
                "command": "enter-maintenance",
                "privileged": True,
                "required_role": "root",
                "privileged_reason": "requires elevated maintenance control",
            },
            {
                "id": "exit_maintenance",
                "label": "maintenance off",
                "pane": "control_plane",
                "command": "exit-maintenance",
                "privileged": True,
                "required_role": "root",
                "privileged_reason": "requires elevated maintenance control",
            },
        ]
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
                )
                if pending_tool_names:
                    self._record_kernel_event(
                        "tool_pending",
                        state=str(checkpoint.get("phase") or "awaiting_tools"),
                        message=", ".join(pending_tool_names[:4]),
                    )
                if completed_tool_names:
                    self._record_kernel_event(
                        "tool_completed",
                        state=str(checkpoint.get("phase") or "tools_completed"),
                        message=", ".join(completed_tool_names[:4]),
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
                    )

    def _handle_session_turn_started(self, event: SessionTurnStarted) -> None:
        session_key = event.context.session_key
        self._active_session_key = session_key
        self._session_status[session_key] = "queued"
        self._record_kernel_event(
            "session_turn_started",
            state="running",
            message=f"session {session_key} admitted to kernel",
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
            "actions": [
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
            ],
        }
        manifest["worker_controls"] = {
            "actions": [
                {
                    "id": "inspect_workers",
                    "label": "inspect workers",
                    "pane": "runtime",
                    "command": "worker show",
                },
            ],
        }
        manifest["execution_lanes"] = self.execution_lanes(session_metadata=self._active_session_metadata())
        manifest["scheduler"] = self.scheduler_snapshot(session_metadata=self._active_session_metadata())
        manifest["workers"] = self.worker_snapshot(session_metadata=self._active_session_metadata())
        manifest["embedded_topology"] = self.embedded_topology_snapshot()
        manifest["runtime_topology"] = self.runtime_topology_snapshot(
            session_metadata=self._active_session_metadata()
        )
        manifest["event_log"] = [dict(row) for row in self._event_log]
        targets = manifest.get("targets", {})
        adapter_target = dict(targets.get("adapter", {}))
        adapter_target["default_adapter"] = self._runtime_control.get("active_adapter")
        targets["adapter"] = adapter_target
        manifest["targets"] = targets
        return manifest

    def execute_operator_command(self, command_line: str) -> dict[str, Any]:
        raw = str(command_line or "").strip()
        if not raw:
            raise ValueError("missing command")
        parts = shlex.split(raw)
        command = (parts[0] if parts else "").strip().lower()
        args = parts[1:]
        if command in {"adapter", "board", "bridge", "runtime", "fault", "goal", "lane", "maintenance", "module", "scheduler", "worker", "event", "session", "workspace", "repo", "tool"}:
            subject = command
            verb = (args[0] if args else "").strip().lower()
            tail = args[1:]
            alias_map = {
                ("adapter", "switch"): ("switch-adapter", tail),
                ("adapter", "status"): ("adapter-status", tail),
                ("adapter", "list"): ("adapter-list", tail),
                ("board", "attach"): ("attach-board", tail),
                ("board", "detach"): ("detach-board", tail),
                ("board", "status"): ("board-status", tail),
                ("board", "ports"): ("board-ports", tail),
                ("board", "target"): ("board-target", tail),
                ("board", "transport"): ("board-transport", tail),
                ("board", "mode"): ("board-mode", tail),
                ("bridge", "status"): ("bridge-status", tail),
                ("bridge", "list"): ("bridge-list", tail),
                ("bridge", "fault"): ("bridge-fault", tail),
                ("runtime", "gate"): ("runtime-gate", tail),
                ("runtime", "health"): ("runtime-health", tail),
                ("runtime", "orchestration"): ("runtime-orchestration", tail),
                ("runtime", "queues"): ("runtime-queues", tail),
                ("runtime", "adapters"): ("runtime-adapters", tail),
                ("runtime", "bridges"): ("runtime-bridges", tail),
                ("runtime", "pause"): ("pause-runtime", tail),
                ("runtime", "resume"): ("resume-runtime", tail),
                ("runtime", "degrade"): ("degrade-runtime", tail),
                ("runtime", "drain"): ("drain-background", tail),
                ("runtime", "status"): ("runtime-status", tail),
                ("fault", "clear"): ("clear-fault", tail),
                ("fault", "record"): ("record-fault", tail),
                ("fault", "show"): ("fault-status", tail),
                ("scheduler", "status"): ("scheduler-status", tail),
                ("lane", "prioritize-goal"): ("prioritize-goal-lane", tail),
                ("lane", "show"): ("lane-status", tail),
                ("lane", "list"): ("lane-list", tail),
                ("maintenance", "enter"): ("enter-maintenance", tail),
                ("maintenance", "exit"): ("exit-maintenance", tail),
                ("maintenance", "status"): ("maintenance-status", tail),
                ("module", "focus"): ("focus-module", tail),
                ("module", "show"): ("module-status", tail),
                ("module", "list"): ("module-list", tail),
                ("module", "actions"): ("module-actions", tail),
                ("worker", "show"): ("worker-status", tail),
                ("worker", "list"): ("worker-list", tail),
                ("event", "show"): ("event-status", tail),
                ("event", "tail"): ("event-tail", tail),
                ("session", "status"): ("session-status", tail),
                ("session", "goal"): ("session-goal", tail),
                ("session", "continuation"): ("session-continuation", tail),
                ("goal", "reset"): ("goal-reset", tail),
                ("kernel", "profile"): ("kernel-profile", tail),
                ("kernel", "manifest"): ("kernel-manifest", tail),
                ("topology", "runtime"): ("runtime-topology", tail),
                ("topology", "embedded"): ("embedded-topology", tail),
                ("workspace", "status"): ("workspace-status", tail),
                ("workspace", "scope"): ("workspace-scope", tail),
                ("workspace", "modules"): ("workspace-modules", tail),
                ("workspace", "focus-module"): ("workspace-focus-module", tail),
                ("native", "status"): ("native-status", tail),
                ("native", "last-command"): ("native-last-command", tail),
                ("native", "replay-last"): ("native-replay-last", tail),
                ("native", "replay"): ("native-replay", tail),
                ("native", "focus"): ("native-focus", tail),
                ("native", "inspect"): ("native-inspect", tail),
                ("native", "modules"): ("native-modules", tail),
                ("repo", "status"): ("repo-status", tail),
                ("repo", "root"): ("repo-root", tail),
                ("repo", "tools"): ("repo-tools", tail),
                ("repo", "prepare-tool"): ("repo-prepare-tool", tail),
                ("tool", "inspect"): ("tool-inspect", tail),
                ("tool", "dispatch"): ("tool-dispatch", tail),
                ("tool", "queue"): ("tool-queue", tail),
                ("tool", "clear-queue"): ("tool-clear-queue", tail),
                ("tool", "prioritize"): ("tool-prioritize", tail),
                ("tool", "drain"): ("tool-drain", tail),
                ("tool", "delegate-goal"): ("tool-delegate-goal", tail),
                ("tool", "delegate-subagent"): ("tool-delegate-subagent", tail),
                ("tool", "complete"): ("tool-complete", tail),
                ("tool", "fail"): ("tool-fail", tail),
                ("tool", "status"): ("tool-status", tail),
            }
            mapped = alias_map.get((subject, verb))
            if mapped is None:
                raise ValueError(f"unknown operator command: {raw}")
            command, args = mapped
        self._assert_operator_command_allowed(command, raw=raw)
        if command == "help":
            return {
                "command": raw,
                "ok": True,
                "target_pane": "control_plane",
                "output": (
                    "commands: help, pane <name>, switch-adapter [name], focus-module <name>, "
                    "adapter-status [name], adapter-list, module-status [name], module-list, module-actions [name], board-status, board-ports, board-target, board-transport, board-mode, native-status, native-last-command, native-replay-last, native-replay <target> <action> [value], native-focus <module>, native-inspect <module>, native-modules, bridge-status [name], bridge-list, bridge-fault [name], runtime-status, runtime-gate, runtime-health, runtime-orchestration, runtime-queues, runtime-adapters, runtime-bridges, fault-status, scheduler-status, lane-status, lane-list, maintenance-status, worker-status, worker-list, "
                    "event-status, event-tail [count], session-status, session-goal, session-continuation, goal-reset, kernel-profile, kernel-manifest, runtime-topology, embedded-topology, workspace-status, workspace-scope, workspace-modules, workspace-focus-module <name>, repo-status, repo-root, repo-tools, repo-prepare-tool <name>, tool-inspect <name>, tool-dispatch <name>, tool-queue, tool-clear-queue, tool-prioritize, tool-drain, tool-delegate-goal, tool-delegate-subagent, tool-complete, tool-fail, tool-status, "
                    "attach-board [port] [transport], detach-board, restart-bridge [adapter], "
                    "clear-fault [adapter], record-fault [level] [adapter], pause-runtime [reason], "
                    "resume-runtime, degrade-runtime [reason], drain-background, "
                    "prioritize-goal-lane, enter-maintenance [reason], exit-maintenance; "
                    "aliases: adapter switch|status|list <name>, module focus|show|list|actions <name>, "
                    "board attach|detach|status|ports|target|transport|mode [port] [transport], native status|last-command|replay-last|replay <target> <action> [value]|focus <module>|inspect <module>|modules, bridge status|list|fault <name>, runtime pause|resume|degrade|drain|status|gate|health|orchestration|queues|adapters|bridges, fault clear|record|show, "
                    "scheduler status, worker show|list, maintenance enter|exit|status, lane prioritize-goal|show|list, event show|tail [count], session status|goal|continuation, goal reset, kernel profile|manifest, topology runtime|embedded, workspace status|scope|modules|focus-module <name>, repo status|root|tools|prepare-tool <name>, tool inspect|dispatch <name>, tool queue|clear-queue|prioritize|drain|delegate-goal|delegate-subagent|complete|fail|status"
                ),
                "runtime_control": self.runtime_control_snapshot(),
                "details": {
                    "subject": "help",
                    "mode": "reference",
                },
            }
        if command == "pane":
            if not args:
                raise ValueError("missing pane")
            return {
                "command": raw,
                "ok": True,
                "target_pane": args[0],
                "output": f"pane -> {args[0]}",
                "runtime_control": self.runtime_control_snapshot(),
                "details": {
                    "subject": "pane",
                    "target": args[0],
                },
            }

        target_pane: str | None = None
        output = ""
        details: dict[str, Any] = {}
        if command == "switch-adapter":
            adapter = args[0] if args else self._runtime_control.get("active_adapter")
            if not adapter:
                raise ValueError("missing adapter")
            state = self.switch_runtime_adapter(str(adapter))
            target_pane = "adapters"
            output = f"adapter -> {adapter}"
            details = {"subject": "adapter", "action": "switch", "adapter": adapter}
        elif command == "adapter-status":
            adapter_name = str(args[0] if args else self._runtime_control.get("active_adapter") or "")
            bridge = next(
                (row for row in self._runtime_bridges if str(row.get("adapter") or "") == adapter_name),
                None,
            )
            adapter = next(
                (row for row in self._runtime_adapters if str(row.get("name") or "") == adapter_name),
                None,
            )
            target_pane = "adapters"
            state = self.runtime_control_snapshot()
            output = (
                f"adapter {adapter_name or 'unset'}"
                f" stage={adapter.get('runtime_stage') if isinstance(adapter, dict) else 'unknown'}"
                f" health={bridge.get('health') if isinstance(bridge, dict) else 'unknown'}"
                f" mode={bridge.get('runtime_mode') if isinstance(bridge, dict) else 'unknown'}"
            )
            details = {
                "subject": "adapter",
                "action": "status",
                "adapter": adapter_name or "unset",
                "stage": adapter.get("runtime_stage") if isinstance(adapter, dict) else "unknown",
                "health": bridge.get("health") if isinstance(bridge, dict) else "unknown",
                "mode": bridge.get("runtime_mode") if isinstance(bridge, dict) else "unknown",
            }
        elif command == "adapter-list":
            adapters = [str(row.get("name") or "unknown") for row in self._runtime_adapters]
            target_pane = "adapters"
            state = self.runtime_control_snapshot()
            output = f"adapters count={len(adapters)} active={self._runtime_control.get('active_adapter') or 'unset'}"
            details = {
                "subject": "adapter",
                "action": "list",
                "count": len(adapters),
                "active": self._runtime_control.get("active_adapter") or "unset",
                "items": ", ".join(adapters) or "none",
            }
        elif command == "focus-module":
            if not args:
                raise ValueError("missing module")
            module_name = " ".join(args).strip()
            state = self.focus_runtime_module(module_name)
            target_pane = "modules"
            output = f"module focus -> {module_name}"
            details = {"subject": "module", "action": "focus", "module": module_name}
        elif command == "module-status":
            module_name = " ".join(args).strip() if args else str(
                self._runtime_control.get("module_focus")
                or (self._runtime_modules[0].get("name") if self._runtime_modules else "")
            )
            module = next(
                (row for row in self._runtime_modules if str(row.get("name") or "") == module_name),
                None,
            )
            if not module_name:
                raise ValueError("missing module")
            target_pane = "modules"
            state = self.runtime_control_snapshot()
            output = (
                f"module {module_name}"
                f" status={module.get('status') if isinstance(module, dict) else 'unknown'}"
                f" category={module.get('category') if isinstance(module, dict) else 'unknown'}"
            )
            details = {
                "subject": "module",
                "action": "status",
                "module": module_name,
                "status": module.get("status") if isinstance(module, dict) else "unknown",
                "category": module.get("category") if isinstance(module, dict) else "unknown",
            }
        elif command == "module-list":
            modules = [str(row.get("name") or "unknown") for row in self._runtime_modules]
            target_pane = "modules"
            state = self.runtime_control_snapshot()
            output = f"modules count={len(modules)} focus={self._runtime_control.get('module_focus') or 'unset'}"
            details = {
                "subject": "module",
                "action": "list",
                "count": len(modules),
                "focus": self._runtime_control.get("module_focus") or "unset",
                "items": ", ".join(modules) or "none",
            }
        elif command == "module-actions":
            module_name = " ".join(args).strip() if args else str(
                self._runtime_control.get("module_focus")
                or (self._runtime_modules[0].get("name") if self._runtime_modules else "")
            )
            module = next(
                (row for row in self._runtime_modules if str(row.get("name") or "") == module_name),
                None,
            )
            if not module_name:
                raise ValueError("missing module")
            actions = list(module.get("operator_actions", [])) if isinstance(module, dict) else []
            target_pane = "modules"
            state = self.runtime_control_snapshot()
            output = f"module actions {module_name} count={len(actions)}"
            details = {
                "subject": "module",
                "action": "actions",
                "module": module_name,
                "count": len(actions),
                "items": ", ".join(str(action) for action in actions) or "none",
            }
        elif command == "attach-board":
            port = args[0] if args else None
            transport = args[1] if len(args) > 1 else None
            state = self.attach_board(
                port=str(port).strip() or None if port is not None else None,
                transport=str(transport).strip() or None if transport is not None else None,
            )
            target_pane = "adapters"
            output = f"board attach -> {port or state.get('board', {}).get('port') or 'auto'}"
            board = self._board_runtime_snapshot(dict(state.get("board", {})))
            details = {
                "subject": "board",
                "action": "attach",
                "transport": board.get("transport"),
                "port": board.get("port"),
                "attached": board.get("attached"),
                "health": board.get("health"),
                "mode": board.get("runtime_mode"),
                "error": board.get("last_error"),
            }
        elif command == "detach-board":
            state = self.detach_board()
            target_pane = "adapters"
            output = "board detached"
            details = {"subject": "board", "action": "detach"}
        elif command == "board-status":
            board = self._board_runtime_snapshot(dict(self._runtime_control.get("board", {})))
            target_pane = "adapters"
            state = self.runtime_control_snapshot()
            output = (
                f"board attached={bool(board.get('attached'))}"
                f" health={board.get('health') or 'unknown'}"
                f" transport={board.get('transport') or board.get('preferred_transport') or 'unset'}"
                f" port={board.get('port') or 'auto'}"
                f" mode={board.get('runtime_mode') or 'unprobed'}"
                f" error={board.get('last_error') or 'none'}"
            )
            details = {
                "subject": "board",
                "action": "status",
                "attached": bool(board.get("attached")),
                "health": board.get("health") or "unknown",
                "transport": board.get("transport") or board.get("preferred_transport") or "unset",
                "port": board.get("port") or "auto",
                "mode": board.get("runtime_mode") or "unprobed",
                "error": board.get("last_error") or "none",
            }
        elif command == "board-ports":
            board = self._board_runtime_snapshot(dict(self._runtime_control.get("board", {})))
            ports = list(board.get("available_ports") or [])
            target_pane = "adapters"
            state = self.runtime_control_snapshot()
            output = f"board ports count={len(ports)} preferred={board.get('preferred_transport') or 'unset'}"
            details = {
                "subject": "board",
                "action": "ports",
                "count": len(ports),
                "preferred_transport": board.get("preferred_transport") or "unset",
                "items": ", ".join(str(port) for port in ports) or "none",
            }
        elif command == "board-target":
            board = self._board_runtime_snapshot(dict(self._runtime_control.get("board", {})))
            target_pane = "adapters"
            state = self.runtime_control_snapshot()
            output, details = (
                f"board target={board.get('target') or 'unknown'}"
                f" attached={bool(board.get('attached'))}",
                {
                    "subject": "board",
                    "action": "target",
                    "target": board.get("target") or "unknown",
                    "attached": bool(board.get("attached")),
                    "mode": board.get("runtime_mode") or "unprobed",
                },
            )
        elif command == "board-transport":
            board = self._board_runtime_snapshot(dict(self._runtime_control.get("board", {})))
            target_pane = "adapters"
            state = self.runtime_control_snapshot()
            transport = board.get("transport") or board.get("preferred_transport") or "unset"
            output, details = (
                f"board transport={transport}"
                f" port={board.get('port') or 'auto'}",
                {
                    "subject": "board",
                    "action": "transport",
                    "transport": transport,
                    "preferred_transport": board.get("preferred_transport") or "unset",
                    "port": board.get("port") or "auto",
                    "ports_known": len(list(board.get("available_ports") or [])),
                },
            )
        elif command == "board-mode":
            board = self._board_runtime_snapshot(dict(self._runtime_control.get("board", {})))
            target_pane = "adapters"
            state = self.runtime_control_snapshot()
            output, details = (
                f"board mode={board.get('runtime_mode') or 'unprobed'}"
                f" artifact={board.get('bridge_artifact') or 'none'}",
                {
                    "subject": "board",
                    "action": "mode",
                    "mode": board.get("runtime_mode") or "unprobed",
                    "artifact": board.get("bridge_artifact") or "none",
                    "error": board.get("last_error") or "none",
                },
            )
        elif command == "native-status":
            native_context = self._native_runtime_snapshot()
            native_last_command = dict(native_context.get("last_command") or {})
            target_pane = "adapters"
            state = self.runtime_control_snapshot()
            queue_depth = native_context.get("queue_depth", 0)
            command_depth = native_context.get("command_depth", 0)
            module_count = native_context.get("module_count", 0)
            last_summary = native_last_command.get("summary") or "none:none"
            artifact = native_context.get("bridge_artifact") or "none"
            output, details = (
                f"native queue={queue_depth}"
                f" modules={module_count}"
                f" last={last_summary}"
                f" artifact={artifact}",
                {
                    "subject": "native",
                    "action": "status",
                    "queue_depth": queue_depth,
                    "command_depth": command_depth,
                    "module_count": module_count,
                    "last_target": native_last_command.get("target") or "none",
                    "last_action": native_last_command.get("action") or "none",
                    "last_summary": last_summary,
                    "module_focus": self._runtime_control.get("module_focus") or "none",
                    "artifact": artifact,
                },
            )
        elif command == "native-last-command":
            native_context = self._native_runtime_snapshot()
            native_last_command = dict(native_context.get("last_command") or {})
            target_pane = "adapters"
            state = self.runtime_control_snapshot()
            target = native_last_command.get("target") or "none"
            action = native_last_command.get("action") or "none"
            command_text = native_last_command.get("command") or action
            queue_depth = native_last_command.get("queue_depth", 0)
            output, details = (
                f"native last-command target={target}"
                f" action={action}"
                f" depth={queue_depth}",
                {
                    "subject": "native",
                    "action": "last-command",
                    "target": target,
                    "command": command_text,
                    "value": native_last_command.get("value") or "",
                    "status": native_last_command.get("status") or "idle",
                    "code": native_last_command.get("code", 0),
                    "queue_depth": queue_depth,
                    "artifact": native_last_command.get("artifact") or "none",
                    "updated_at_ms": native_last_command.get("updated_at_ms"),
                },
            )
        elif command == "native-replay-last":
            native_context = self._native_runtime_snapshot()
            native_last_command = dict(native_context.get("last_command") or {})
            target = str(native_last_command.get("target") or "").strip()
            action = str(native_last_command.get("action") or "").strip()
            value = str(native_last_command.get("value") or "")
            if not target or not action:
                raise ValueError("native replay unavailable")
            state, output, details, target_pane = self._dispatch_native_action(
                action_label="replay-last",
                target=target,
                command=action,
                value=value,
            )
        elif command == "native-replay":
            target = str(args[0] if len(args) > 0 else "").strip()
            action = str(args[1] if len(args) > 1 else "").strip()
            value = " ".join(str(arg) for arg in args[2:]).strip() if len(args) > 2 else ""
            if not target or not action:
                raise ValueError("usage: native replay <target> <action> [value]")
            state, output, details, target_pane = self._dispatch_native_action(
                action_label="replay",
                target=target,
                command=action,
                value=value,
            )
        elif command == "native-focus":
            module_name = str(args[0] if args else self._runtime_control.get("module_focus") or "").strip()
            if not module_name:
                raise ValueError("missing module")
            state = self.focus_runtime_module(module_name)
            details = self._native_command_details(
                action="focus",
                target=module_name,
                command="focus_module",
                value=module_name,
            )
            output = f"native focus module={module_name} depth={details.get('queue_depth', 0)}"
            target_pane = "modules"
        elif command == "native-inspect":
            module_name = str(args[0] if args else self._runtime_control.get("module_focus") or "").strip()
            if not module_name:
                raise ValueError("missing module")
            self._dispatch_native_control(target=module_name, action="inspect", value="status")
            native_context = self._native_runtime_snapshot()
            native_modules = dict(native_context.get("modules") or {})
            native_state = dict(native_modules.get(module_name) or {})
            state = self.runtime_control_snapshot()
            status = native_state.get("status") or "unknown"
            last_code = native_state.get("last_code") if native_state else 0
            details = self._native_command_details(
                action="inspect",
                target=module_name,
                command="inspect",
                value="status",
                status=status,
                code=last_code,
                updated_at_ms=native_state.get("updated_at_ms") if native_state else None,
            )
            output = (
                f"native inspect module={module_name}"
                f" status={status}"
                f" code={last_code}"
                f" depth={details.get('queue_depth', 0)}"
            )
            details["last_code"] = last_code
            target_pane = "modules"
        elif command == "native-modules":
            native_context = self._native_runtime_snapshot()
            native_modules = dict(native_context.get("modules") or {})
            module_count = int(native_context.get("module_count", len(native_modules)))
            target_pane = "modules"
            state = self.runtime_control_snapshot()
            output, details = (
                f"native modules count={module_count}",
                {
                    "subject": "native",
                    "action": "modules",
                    "count": module_count,
                    "items": ", ".join(
                        f"{name}:{row.get('status', 'unknown')}"
                        for name, row in native_modules.items()
                        if isinstance(row, dict)
                    ) or "none",
                    "codes": ", ".join(
                        f"{name}:{row.get('last_code', 0)}"
                        for name, row in native_modules.items()
                        if isinstance(row, dict)
                    ) or "none",
                    "updated": ", ".join(
                        f"{name}:{row.get('updated_at_ms', 0)}"
                        for name, row in native_modules.items()
                        if isinstance(row, dict)
                    ) or "none",
                },
            )
        elif command == "bridge-status":
            bridge_name = str(args[0] if args else self._runtime_control.get("active_adapter") or "")
            bridge = next(
                (row for row in self._runtime_bridges if str(row.get("adapter") or "") == bridge_name),
                None,
            )
            target_pane = "adapters"
            state = self.runtime_control_snapshot()
            bridge = bridge if isinstance(bridge, dict) else {}
            health = bridge.get("health") or "unknown"
            status = bridge.get("status") or "unknown"
            mode = bridge.get("runtime_mode") or "unknown"
            output, details = (
                f"bridge {bridge_name or 'unset'}"
                f" health={health}"
                f" status={status}"
                f" mode={mode}",
                {
                    "subject": "bridge",
                    "action": "status",
                    "bridge": bridge_name or "unset",
                    "health": health,
                    "status": status,
                    "mode": mode,
                    "board_capable": bool(bridge.get("board_capable")),
                },
            )
        elif command == "bridge-list":
            bridges = [str(row.get("adapter") or "unknown") for row in self._runtime_bridges]
            target_pane = "adapters"
            state = self.runtime_control_snapshot()
            active_adapter = str(self._runtime_control.get("active_adapter") or "")
            output, details = (
                f"bridges count={len(bridges)} active={active_adapter or 'unset'}",
                {
                    "subject": "bridge",
                    "action": "list",
                    "count": len(bridges),
                    "active": active_adapter or "unset",
                    "items": ", ".join(bridges) or "none",
                },
            )
        elif command == "bridge-fault":
            bridge_name = str(args[0] if args else self._runtime_control.get("active_adapter") or "")
            bridge = next(
                (row for row in self._runtime_bridges if str(row.get("adapter") or "") == bridge_name),
                None,
            )
            target_pane = "faults"
            state = self.runtime_control_snapshot()
            bridge = bridge if isinstance(bridge, dict) else {}
            health = bridge.get("health") or "unknown"
            error = bridge.get("last_error") or "none"
            output, details = (
                f"bridge fault {bridge_name or 'unset'}"
                f" health={health}"
                f" error={error}",
                {
                    "subject": "bridge",
                    "action": "fault",
                    "bridge": bridge_name or "unset",
                    "health": health,
                    "error": error,
                    "status": bridge.get("status") or "unknown",
                },
            )
        elif command == "restart-bridge":
            adapter = args[0] if args else None
            state = self.restart_bridge(str(adapter).strip() or None if adapter is not None else None)
            target_pane = "adapters"
            output = f"bridge restart -> {adapter or self._runtime_control.get('active_adapter') or 'active'}"
            details = {
                "subject": "bridge",
                "action": "restart",
                "adapter": adapter or self._runtime_control.get("active_adapter") or "active",
            }
        elif command == "clear-fault":
            adapter = args[0] if args else None
            state = self.clear_fault(str(adapter).strip() or None if adapter is not None else None)
            target_pane = "faults"
            output, details = (
                "fault posture cleared",
                {
                    "subject": "fault",
                    "action": "clear",
                    "adapter": adapter or "active",
                },
            )
        elif command == "record-fault":
            level = args[0] if args else "fault"
            adapter = args[1] if len(args) > 1 else None
            state = self.record_fault(
                str(level).strip() or "fault",
                str(adapter).strip() or None if adapter is not None else None,
            )
            target_pane = "faults"
            output, details = (
                f"fault recorded -> {str(level) or 'fault'}",
                {
                    "subject": "fault",
                    "action": "record",
                    "level": str(level) or "fault",
                    "adapter": adapter or "active",
                },
            )
        elif command == "fault-status":
            posture = dict(self._runtime_control.get("fault_posture", {}))
            target_pane = "faults"
            state = self.runtime_control_snapshot()
            current_level = posture.get("level") or "unknown"
            supervisor = posture.get("supervisor") or "unknown"
            adapters = ",".join(posture.get("affected_adapters") or []) or "none"
            output, details = (
                f"fault level={current_level}"
                f" supervisor={supervisor}"
                f" adapters={adapters}",
                {
                    "subject": "fault",
                    "action": "status",
                    "level": current_level,
                    "supervisor": supervisor,
                    "adapters": adapters,
                },
            )
        elif command == "scheduler-status":
            scheduler = self.scheduler_snapshot(session_metadata=self._active_session_metadata())
            target_pane = "runtime"
            state = self.runtime_control_snapshot()
            queues = list(scheduler.get("queues", []))
            active_runtime = scheduler.get("active_runtime", {})
            active_adapter = active_runtime.get("adapter") if isinstance(active_runtime, dict) else "none"
            output = (
                f"scheduler policy={scheduler.get('policy') or 'unknown'}"
                f" queues={len(queues)}"
                f" active_runtime={active_adapter or 'none'}"
            )
            details = {
                "subject": "scheduler",
                "action": "status",
                "policy": scheduler.get("policy") or "unknown",
                "queues": len(queues),
                "foreground_depth": next((q.get("depth") for q in queues if q.get("id") == "foreground"), 0),
                "goal_depth": next((q.get("depth") for q in queues if q.get("id") == "goal_background"), 0),
            }
        elif command == "lane-status":
            lanes = self.execution_lanes(session_metadata=self._active_session_metadata())
            target_pane = "runtime"
            state = self.runtime_control_snapshot()
            lead = lanes[0] if lanes else {}
            output, details = (
                f"lanes count={len(lanes)}"
                f" lead={lead.get('id', 'none')}"
                f" state={lead.get('state', 'unknown')}",
                {
                    "subject": "lane",
                    "action": "status",
                    "count": len(lanes),
                    "lead": lead.get("id", "none"),
                    "lead_mode": lead.get("mode", "unknown"),
                    "lead_state": lead.get("state", "unknown"),
                },
            )
        elif command == "lane-list":
            lanes = self.execution_lanes(session_metadata=self._active_session_metadata())
            target_pane = "runtime"
            state = self.runtime_control_snapshot()
            output, details = (
                f"lanes count={len(lanes)}",
                {
                    "subject": "lane",
                    "action": "list",
                    "count": len(lanes),
                    "items": ", ".join(str(lane.get("id") or "unknown") for lane in lanes) or "none",
                },
            )
        elif command == "maintenance-status":
            maintenance = dict(self._runtime_control.get("maintenance_mode", {}))
            gate = dict(self._runtime_control.get("execution_gate", {}))
            target_pane = "control_plane"
            state = self.runtime_control_snapshot()
            enabled = "on" if maintenance.get("enabled") else "off"
            output = (
                f"maintenance enabled={enabled}"
                f" gate={gate.get('state') or 'unknown'}"
            )
            details = {
                "subject": "maintenance",
                "action": "status",
                "enabled": enabled,
                "reason": maintenance.get("reason") or "none",
                "gate": gate.get("state") or "unknown",
            }
        elif command == "worker-status":
            workers = self.worker_snapshot(session_metadata=self._active_session_metadata())
            target_pane = "runtime"
            state = self.runtime_control_snapshot()
            lead = workers[0] if workers else {}
            output, details = (
                f"workers count={len(workers)}"
                f" lead={lead.get('id', 'none')}"
                f" state={lead.get('state', 'unknown')}",
                {
                    "subject": "worker",
                    "action": "status",
                    "count": len(workers),
                    "lead": lead.get("id", "none"),
                    "lead_kind": lead.get("kind", "unknown"),
                    "lead_state": lead.get("state", "unknown"),
                },
            )
        elif command == "worker-list":
            workers = self.worker_snapshot(session_metadata=self._active_session_metadata())
            target_pane = "runtime"
            state = self.runtime_control_snapshot()
            output, details = (
                f"workers count={len(workers)}",
                {
                    "subject": "worker",
                    "action": "list",
                    "count": len(workers),
                    "items": ", ".join(str(worker.get("id") or "unknown") for worker in workers) or "none",
                },
            )
        elif command == "event-status":
            event_rows = [dict(row) for row in self._event_log]
            target_pane = "runtime"
            state = self.runtime_control_snapshot()
            head = event_rows[0] if event_rows else {}
            output, details = (
                f"events count={len(event_rows)}"
                f" latest={head.get('type', 'none')}"
                f" state={head.get('state', 'idle')}",
                {
                    "subject": "event",
                    "action": "status",
                    "count": len(event_rows),
                    "latest": head.get("type", "none"),
                    "state": head.get("state", "idle"),
                    "items": ", ".join(str(row.get("type") or "event") for row in event_rows[:6]) or "none",
                },
            )
        elif command == "event-tail":
            event_rows = [dict(row) for row in self._event_log]
            limit = 5
            if args:
                try:
                    limit = max(1, min(int(args[0]), 12))
                except ValueError as exc:
                    raise ValueError("event tail count must be an integer") from exc
            selected = event_rows[:limit]
            target_pane = "runtime"
            state = self.runtime_control_snapshot()
            output, details = (
                f"event tail count={len(selected)}",
                {
                    "subject": "event",
                    "action": "tail",
                    "count": len(selected),
                    "items": ", ".join(
                        f"{row.get('type', 'event')}:{row.get('state', 'unknown')}"
                        for row in selected
                    ) or "none",
                },
            )
        elif command == "session-status":
            session_key = self._active_session_key or "none"
            status = self._session_status.get(session_key, "idle") if session_key != "none" else "idle"
            latency = self._session_latency.get(session_key)
            metadata = self._active_session_metadata() or {}
            target_pane = "runtime"
            state = self.runtime_control_snapshot()
            goal_blob = goal_state_ws_blob(metadata)
            continuation = "on" if internal_continuation_pending(metadata) else "off"
            latency_value = latency if latency is not None else "n/a"
            output, details = (
                f"session {session_key}"
                f" status={status}"
                f" latency_ms={latency_value}"
                f" continuation={continuation}",
                {
                    "subject": "session",
                    "action": "status",
                    "session": session_key,
                    "status": status,
                    "latency_ms": latency_value,
                    "continuation": continuation,
                    "goal_active": "on" if goal_blob.get("active") else "off",
                },
            )
        elif command == "session-goal":
            metadata = self._active_session_metadata() or {}
            target_pane = "runtime"
            state = self.runtime_control_snapshot()
            goal_blob = goal_state_ws_blob(metadata)
            active = "on" if goal_blob.get("active") else "off"
            continuation = "on" if internal_continuation_pending(metadata) else "off"
            output, details = (
                f"goal active={active}"
                f" status={goal_blob.get('status') or 'idle'}",
                {
                    "subject": "session",
                    "action": "goal",
                    "active": active,
                    "status": goal_blob.get("status") or "idle",
                    "summary": goal_blob.get("ui_summary") or goal_blob.get("objective") or "none",
                    "continuation": continuation,
                },
            )
        elif command == "session-continuation":
            metadata = self._active_session_metadata() or {}
            rounds = int(metadata.get("_sustained_goal_continuation_rounds") or 0) if metadata else 0
            target_pane = "runtime"
            state = self.runtime_control_snapshot()
            pending = "on" if internal_continuation_pending(metadata) else "off"
            goal_active = "on" if sustained_goal_active(metadata) else "off"
            output, details = (
                f"continuation pending={pending}"
                f" rounds={rounds}"
                f" goal_active={goal_active}",
                {
                    "subject": "session",
                    "action": "continuation",
                    "pending": pending,
                    "rounds": rounds,
                    "goal_active": goal_active,
                    "session": self._active_session_key or "none",
                },
            )
        elif command == "goal-reset":
            metadata = self._active_session_metadata()
            if metadata is None:
                raise ValueError("no active session")
            reset_goal_continuation_rounds(metadata)
            target_pane = "runtime"
            state = self.runtime_control_snapshot()
            output = "goal continuation budget reset"
            details = {
                "subject": "goal",
                "action": "reset",
                "continuation": "off",
                "session": self._active_session_key or "none",
            }
        elif command == "kernel-profile":
            profile = self._profile.to_dict()
            target_pane = "control_plane"
            state = self.runtime_control_snapshot()
            output = (
                f"kernel profile name={profile.get('name') or 'unknown'}"
                f" gui={'on' if profile.get('gui_enabled') else 'off'}"
                f" api={'on' if profile.get('api_enabled') else 'off'}"
                f" targets={len(profile.get('runtime_targets') or [])}"
            )
            details = {
                "subject": "kernel",
                "action": "profile",
                "profile": profile.get("name") or "unknown",
                "targets": ", ".join(profile.get("runtime_targets") or []) or "none",
                "languages": ", ".join(profile.get("implementation_languages") or []) or "none",
                "automations": "on" if profile.get("automations_enabled") else "off",
                "memory": "on" if profile.get("memory_enabled") else "off",
            }
        elif command == "kernel-manifest":
            manifest = self.manifest_snapshot()
            identity = dict(manifest.get("identity", {}))
            contracts = dict(manifest.get("contracts", {}))
            target_pane = "control_plane"
            state = self.runtime_control_snapshot()
            output = (
                f"kernel manifest app={identity.get('app_name') or 'unknown'}"
                f" cli={identity.get('cli_name') or 'unknown'}"
                f" adapters={len(manifest.get('runtime_adapters') or [])}"
                f" modules={len(manifest.get('runtime_modules') or [])}"
            )
            details = {
                "subject": "kernel",
                "action": "manifest",
                "app": identity.get("app_name") or "unknown",
                "cli": identity.get("cli_name") or "unknown",
                "manifest_version": contracts.get("manifest_version") or 0,
                "event_version": contracts.get("event_version") or 0,
                "snapshot_version": contracts.get("snapshot_version") or 0,
            }
        elif command == "runtime-topology":
            topology = self.runtime_topology_snapshot(session_metadata=self._active_session_metadata())
            scheduler = dict(topology.get("scheduler", {}))
            workers = list(topology.get("workers", []))
            target_pane = "runtime"
            state = self.runtime_control_snapshot()
            output = (
                f"runtime topology adapters={len(topology.get('adapters', []))}"
                f" modules={len(topology.get('modules', []))}"
                f" lanes={len(topology.get('execution_lanes', []))}"
                f" workers={len(workers)}"
            )
            details = {
                "subject": "topology",
                "action": "runtime",
                "preferred_lane": scheduler.get("preferred_lane") or "interactive",
                "dispatch_handoff": scheduler.get("dispatch_handoff_lane") or "none",
                "adapters": ", ".join(str(row.get("name") or "unknown") for row in topology.get("adapters", [])) or "none",
                "modules": ", ".join(str(row.get("name") or "unknown") for row in topology.get("modules", [])) or "none",
                "lanes": ", ".join(str(row.get("id") or "lane") for row in topology.get("execution_lanes", [])) or "none",
            }
        elif command == "embedded-topology":
            topology = self.embedded_topology_snapshot()
            board = dict(topology.get("board", {}))
            target_pane = "runtime"
            state = self.runtime_control_snapshot()
            output = (
                f"embedded topology attached={'yes' if board.get('attached') else 'no'}"
                f" transport={board.get('transport') or board.get('preferred_transport') or 'unset'}"
                f" target={board.get('target') or 'host'}"
            )
            details = {
                "subject": "topology",
                "action": "embedded",
                "attached": "yes" if board.get("attached") else "no",
                "port": board.get("port") or "none",
                "transport": board.get("transport") or board.get("preferred_transport") or "unset",
                "target": board.get("target") or "host",
                "runtime_mode": board.get("runtime_mode") or "userland",
                "available_ports": ", ".join(board.get("available_ports") or []) or "none",
            }
        elif command == "workspace-status":
            workspace = self._workspace_root()
            target_pane = "workspace"
            state = self.runtime_control_snapshot()
            output = f"workspace {workspace.name} path={workspace}"
            details = {
                "subject": "workspace",
                "action": "status",
                "name": workspace.name or "workspace",
                "path": str(workspace),
                "session": self._active_session_key or "none",
            }
        elif command == "workspace-scope":
            workspace = self._workspace_root()
            repo = self._repo_root()
            target_pane = "workspace"
            state = self.runtime_control_snapshot()
            output = (
                f"workspace scope root={workspace}"
                f" repo={'attached' if repo is not None else 'detached'}"
            )
            details = {
                "subject": "workspace",
                "action": "scope",
                "path": str(workspace),
                "repo_root": str(repo) if repo is not None else "none",
                "restrict_mode": "workspace",
            }
        elif command == "workspace-modules":
            workspace = self._workspace_root()
            modules = [
                str(row.get("name") or "unknown")
                for row in self._runtime_modules
                if str(row.get("status") or "") == "enabled"
            ]
            target_pane = "workspace"
            state = self.runtime_control_snapshot()
            output = f"workspace modules count={len(modules)} root={workspace.name or 'workspace'}"
            details = {
                "subject": "workspace",
                "action": "modules",
                "root": str(workspace),
                "count": len(modules),
                "items": ", ".join(modules) or "none",
            }
        elif command == "workspace-focus-module":
            if not args:
                raise ValueError("missing module")
            module_name = " ".join(args).strip()
            workspace = self._workspace_root()
            state = self.focus_runtime_module(module_name)
            target_pane = "modules"
            output = f"workspace {workspace.name or 'workspace'} module focus -> {module_name}"
            details = {
                "subject": "workspace",
                "action": "focus-module",
                "root": str(workspace),
                "module": module_name,
            }
        elif command == "repo-status":
            repo = self._repo_root()
            workspace = self._workspace_root()
            target_pane = "workspace"
            state = self.runtime_control_snapshot()
            output = (
                f"repo {'attached' if repo is not None else 'missing'}"
                f" root={repo if repo is not None else workspace}"
            )
            details = {
                "subject": "repo",
                "action": "status",
                "attached": repo is not None,
                "root": str(repo) if repo is not None else str(workspace),
                "workspace": str(workspace),
            }
        elif command == "repo-root":
            repo = self._repo_root()
            if repo is None:
                raise ValueError("repo root unavailable")
            target_pane = "workspace"
            state = self.runtime_control_snapshot()
            output = f"repo root -> {repo}"
            details = {
                "subject": "repo",
                "action": "root",
                "root": str(repo),
                "name": repo.name or "repo",
            }
        elif command == "repo-tools":
            repo = self._repo_root()
            workspace = self._workspace_root()
            tools = list(self._profile.tools)
            families = sorted({tool_contract_family(tool) for tool in tools})
            family_counts = tool_contract_family_counts(tools)
            target_pane = "workspace"
            state = self.runtime_control_snapshot()
            output = (
                f"repo tools count={len(tools)}"
                f" root={(repo if repo is not None else workspace).name or 'workspace'}"
                f" families={','.join(f'{family}:{family_counts[family]}' for family in sorted(family_counts)) or 'none'}"
            )
            details = {
                "subject": "repo",
                "action": "tools",
                "root": str(repo) if repo is not None else str(workspace),
                "count": len(tools),
                "items": ", ".join(str(tool) for tool in tools) or "none",
                "families": ", ".join(families) or "none",
                "family_counts": ", ".join(
                    f"{family}:{family_counts[family]}" for family in sorted(family_counts)
                ) or "none",
            }
        elif command == "repo-prepare-tool":
            if not args:
                raise ValueError("missing tool")
            tool_name = " ".join(args).strip()
            if tool_name not in self._profile.tools:
                raise ValueError(f"unknown tool contract: {tool_name}")
            tool_family = tool_contract_family(tool_name)
            repo = self._repo_root()
            workspace = self._workspace_root()
            self._record_kernel_event(
                "tool_contract_prepared",
                state="ready",
                message=(
                    f"{tool_name} [{tool_family}] prepared for "
                    f"{(repo if repo is not None else workspace).name or 'workspace'}"
                ),
            )
            target_pane = "runtime"
            state = self.runtime_control_snapshot()
            output = f"tool contract prepared -> {tool_name} [{tool_family}]"
            details = {
                "subject": "repo",
                "action": "prepare-tool",
                "tool": tool_name,
                "family": tool_family,
                "root": str(repo) if repo is not None else str(workspace),
                "status": "ready",
            }
        elif command == "tool-inspect":
            if not args:
                raise ValueError("missing tool")
            tool_name = " ".join(args).strip()
            if tool_name not in self._profile.tools:
                raise ValueError(f"unknown tool contract: {tool_name}")
            tool_family = tool_contract_family(tool_name)
            repo = self._repo_root()
            workspace = self._workspace_root()
            target_pane = "runtime"
            state = self.runtime_control_snapshot()
            output = f"tool {tool_name} contract available [{tool_family}]"
            details = {
                "subject": "tool",
                "action": "inspect",
                "tool": tool_name,
                "family": tool_family,
                "root": str(repo) if repo is not None else str(workspace),
                "workspace": str(workspace),
            }
        elif command == "tool-dispatch":
            if not args:
                raise ValueError("missing tool")
            tool_name = " ".join(args).strip()
            if tool_name not in self._profile.tools:
                raise ValueError(f"unknown tool contract: {tool_name}")
            tool_family = tool_contract_family(tool_name)
            repo = self._repo_root()
            workspace = self._workspace_root()
            active_module = str(
                self._runtime_control.get("module_focus")
                or (self._runtime_modules[0].get("name") if self._runtime_modules else "session_state")
            )
            self._dispatch_queue.insert(
                0,
                {
                    "tool": tool_name,
                    "family": tool_family,
                    "module": active_module,
                    "root": str(repo) if repo is not None else str(workspace),
                    "status": "queued",
                    "lifecycle": "queued",
                },
            )
            self._dispatch_queue = self._dispatch_queue[:12]
            self._record_kernel_event(
                "tool_dispatch_requested",
                state="queued",
                message=(
                    f"{tool_name} [{tool_family}] dispatched via {active_module}"
                    f" in {(repo if repo is not None else workspace).name or 'workspace'}"
                ),
            )
            target_pane = "runtime"
            state = self.runtime_control_snapshot()
            output = f"tool dispatched -> {tool_name} [{tool_family}]"
            details = {
                "subject": "tool",
                "action": "dispatch",
                "tool": tool_name,
                "family": tool_family,
                "module": active_module,
                "root": str(repo) if repo is not None else str(workspace),
                "status": "queued",
            }
        elif command == "tool-queue":
            target_pane = "runtime"
            state = self.runtime_control_snapshot()
            queue_snapshot = self._dispatch_queue_snapshot()
            output = f"tool queue depth={len(self._dispatch_queue)}"
            details = {
                "subject": "tool",
                "action": "queue",
                "count": queue_snapshot["queue_depth"],
                "priority": queue_snapshot["priority"],
                "handoff": queue_snapshot["handoff"],
                "items": queue_snapshot["items"],
                "lifecycle": queue_snapshot["lifecycle"],
                "roots": queue_snapshot["roots"],
            }
        elif command == "tool-clear-queue":
            cleared = len(self._dispatch_queue)
            self._dispatch_queue = []
            self._record_kernel_event(
                "tool_dispatch_queue_cleared",
                state="ok",
                message=f"cleared {cleared} queued tool dispatch(es)",
            )
            target_pane = "runtime"
            state = self.runtime_control_snapshot()
            output = "tool queue cleared"
            details = {
                "subject": "tool",
                "action": "clear-queue",
                "cleared": cleared,
            }
        elif command == "tool-prioritize":
            for row in self._dispatch_queue:
                row["lifecycle"] = "prioritized"
            self._scheduler_state = prioritize_lane(
                self._scheduler_state,
                lane="interactive",
            )
            self._scheduler_state["dispatch_priority"] = True
            self._record_kernel_event(
                "tool_dispatch_prioritized",
                state="ok",
                message="scheduler priority shifted toward tool dispatch queue",
            )
            target_pane = "runtime"
            state = self.runtime_control_snapshot()
            queue_snapshot = self._dispatch_queue_snapshot()
            output = "tool dispatch queue prioritized"
            details = {
                "subject": "tool",
                "action": "prioritize",
                "count": queue_snapshot["queue_depth"],
                "preferred_lane": "interactive",
                "priority": queue_snapshot["priority"],
                "handoff": queue_snapshot["handoff"],
                "items": queue_snapshot["items"],
            }
        elif command == "tool-drain":
            drained = min(len(self._dispatch_queue), 3)
            for row in self._dispatch_queue[:drained]:
                row["lifecycle"] = "drained"
            self._dispatch_queue = self._dispatch_queue[drained:]
            self._scheduler_state["dispatch_priority"] = False
            self._scheduler_state["dispatch_handoff_lane"] = None
            self._record_kernel_event(
                "tool_dispatch_drained",
                state="ok",
                message=f"drained {drained} queued tool dispatch(es)",
            )
            target_pane = "runtime"
            state = self.runtime_control_snapshot()
            queue_snapshot = self._dispatch_queue_snapshot()
            output = "tool dispatch queue drained"
            details = {
                "subject": "tool",
                "action": "drain",
                "drained": drained,
                "remaining": queue_snapshot["queue_depth"],
                "items": queue_snapshot["items"],
                "lifecycle": queue_snapshot["lifecycle"],
            }
        elif command == "tool-delegate-goal":
            for row in self._dispatch_queue:
                row["lifecycle"] = "delegated_goal"
            self._scheduler_state = prioritize_lane(
                self._scheduler_state,
                lane="sustained_goal",
            )
            self._scheduler_state["dispatch_handoff_lane"] = "sustained_goal"
            self._record_kernel_event(
                "tool_dispatch_goal_handoff",
                state="queued",
                message="tool dispatch queue handed to sustained goal lane",
            )
            target_pane = "runtime"
            state = self.runtime_control_snapshot()
            queue_snapshot = self._dispatch_queue_snapshot()
            output = "tool dispatch queue delegated to goal lane"
            details = {
                "subject": "tool",
                "action": "delegate-goal",
                "count": queue_snapshot["queue_depth"],
                "lane": "sustained_goal",
                "handoff": queue_snapshot["handoff"],
                "items": queue_snapshot["items"],
            }
        elif command == "tool-delegate-subagent":
            for row in self._dispatch_queue:
                row["lifecycle"] = "delegated_subagent"
            self._scheduler_state = prioritize_lane(
                self._scheduler_state,
                lane="subagent",
            )
            self._scheduler_state["dispatch_handoff_lane"] = "subagent"
            self._record_kernel_event(
                "tool_dispatch_subagent_handoff",
                state="queued",
                message="tool dispatch queue handed to subagent lane",
            )
            target_pane = "runtime"
            state = self.runtime_control_snapshot()
            queue_snapshot = self._dispatch_queue_snapshot()
            output = "tool dispatch queue delegated to subagent lane"
            details = {
                "subject": "tool",
                "action": "delegate-subagent",
                "count": queue_snapshot["queue_depth"],
                "lane": "subagent",
                "handoff": queue_snapshot["handoff"],
                "items": queue_snapshot["items"],
            }
        elif command == "tool-complete":
            completed = min(len(self._dispatch_queue), 1)
            if completed:
                self._dispatch_queue[0]["lifecycle"] = "completed"
            self._dispatch_queue = self._dispatch_queue[completed:]
            if not self._dispatch_queue:
                self._scheduler_state["dispatch_priority"] = False
                self._scheduler_state["dispatch_handoff_lane"] = None
            self._record_kernel_event(
                "tool_dispatch_completed",
                state="ok",
                message=f"completed {completed} queued tool dispatch(es)",
            )
            target_pane = "runtime"
            state = self.runtime_control_snapshot()
            queue_snapshot = self._dispatch_queue_snapshot()
            output = "tool dispatch marked completed"
            details = {
                "subject": "tool",
                "action": "complete",
                "completed": completed,
                "remaining": queue_snapshot["queue_depth"],
                "items": queue_snapshot["items"],
                "lifecycle": queue_snapshot["lifecycle"],
            }
        elif command == "tool-fail":
            failed = min(len(self._dispatch_queue), 1)
            if failed:
                self._dispatch_queue[0]["lifecycle"] = "failed"
            self._dispatch_queue = self._dispatch_queue[failed:]
            if not self._dispatch_queue:
                self._scheduler_state["dispatch_priority"] = False
                self._scheduler_state["dispatch_handoff_lane"] = None
            self._record_kernel_event(
                "tool_dispatch_failed",
                state="fault",
                message=f"failed {failed} queued tool dispatch(es)",
            )
            target_pane = "faults"
            state = self.runtime_control_snapshot()
            queue_snapshot = self._dispatch_queue_snapshot()
            output = "tool dispatch marked failed"
            details = {
                "subject": "tool",
                "action": "fail",
                "failed": failed,
                "remaining": queue_snapshot["queue_depth"],
                "items": queue_snapshot["items"],
                "lifecycle": queue_snapshot["lifecycle"],
            }
        elif command == "tool-status":
            queue_snapshot = self._dispatch_queue_snapshot()
            target_pane = "runtime"
            state = self.runtime_control_snapshot()
            output = (
                f"tool orchestration queue={queue_snapshot['queue_depth']}"
                f" priority={queue_snapshot['priority']}"
                f" handoff={queue_snapshot['handoff']}"
            )
            details = {
                "subject": "tool",
                "action": "status",
                "queue_depth": queue_snapshot["queue_depth"],
                "priority": queue_snapshot["priority"],
                "handoff": queue_snapshot["handoff"],
                "items": queue_snapshot["items"],
                "lifecycle": queue_snapshot["lifecycle"],
                "roots": queue_snapshot["roots"],
            }
        elif command == "pause-runtime":
            state = self.pause_runtime(" ".join(args).strip() or None)
            target_pane = "runtime"
            output = "runtime paused"
            details = {"subject": "runtime", "action": "pause", "reason": " ".join(args).strip() or "operator-paused"}
        elif command == "resume-runtime":
            state = self.resume_runtime()
            target_pane = "runtime"
            output = "runtime resumed"
            details = {"subject": "runtime", "action": "resume"}
        elif command == "degrade-runtime":
            state = self.degrade_runtime(" ".join(args).strip() or None)
            target_pane = "runtime"
            output = "runtime degraded"
            details = {"subject": "runtime", "action": "degrade", "reason": " ".join(args).strip() or "fault-containment"}
        elif command == "runtime-status":
            gate = dict(self._runtime_control.get("execution_gate", {}))
            maintenance = dict(self._runtime_control.get("maintenance_mode", {}))
            active_adapter = str(self._runtime_control.get("active_adapter") or "unset")
            target_pane = "runtime"
            state = self.runtime_control_snapshot()
            output = (
                f"runtime gate={gate.get('state') or 'unknown'}"
                f" reason={gate.get('reason') or 'none'}"
                f" adapter={active_adapter}"
                f" maintenance={'on' if maintenance.get('enabled') else 'off'}"
            )
            details = {
                "subject": "runtime",
                "action": "status",
                "gate": gate.get("state") or "unknown",
                "reason": gate.get("reason") or "none",
                "adapter": active_adapter,
                "maintenance": "on" if maintenance.get("enabled") else "off",
            }
        elif command == "runtime-gate":
            gate = dict(self._runtime_control.get("execution_gate", {}))
            maintenance = dict(self._runtime_control.get("maintenance_mode", {}))
            target_pane = "runtime"
            state = self.runtime_control_snapshot()
            output = (
                f"runtime gate={gate.get('state') or 'unknown'}"
                f" maintenance={'on' if maintenance.get('enabled') else 'off'}"
            )
            details = {
                "subject": "runtime",
                "action": "gate",
                "gate": gate.get("state") or "unknown",
                "reason": gate.get("reason") or "none",
                "maintenance": "on" if maintenance.get("enabled") else "off",
                "maintenance_reason": maintenance.get("reason") or "none",
            }
        elif command == "runtime-health":
            active_adapter = str(self._runtime_control.get("active_adapter") or "unset")
            bridge = next(
                (row for row in self._runtime_bridges if str(row.get("adapter") or "") == active_adapter),
                None,
            )
            gate = dict(self._runtime_control.get("execution_gate", {}))
            target_pane = "runtime"
            state = self.runtime_control_snapshot()
            output = (
                f"runtime health adapter={active_adapter}"
                f" bridge={bridge.get('health') if isinstance(bridge, dict) else 'unknown'}"
                f" gate={gate.get('state') or 'unknown'}"
            )
            details = {
                "subject": "runtime",
                "action": "health",
                "adapter": active_adapter,
                "bridge_health": bridge.get("health") if isinstance(bridge, dict) else "unknown",
                "bridge_status": bridge.get("status") if isinstance(bridge, dict) else "unknown",
                "gate": gate.get("state") or "unknown",
                "reason": gate.get("reason") or "none",
            }
        elif command == "runtime-orchestration":
            scheduler = self.scheduler_snapshot(session_metadata=self._active_session_metadata())
            lanes = self.execution_lanes(session_metadata=self._active_session_metadata())
            workers = self.worker_snapshot(session_metadata=self._active_session_metadata())
            dispatch_queue = next(
                (queue for queue in list(scheduler.get("queues", [])) if queue.get("id") == "tool_dispatch"),
                {},
            )
            target_pane = "runtime"
            state = self.runtime_control_snapshot()
            output = (
                f"orchestration lane={scheduler.get('preferred_lane') or 'interactive'}"
                f" dispatch={dispatch_queue.get('state') or 'ready'}"
                f" depth={dispatch_queue.get('depth') or 0}"
                f" workers={len(workers)}"
            )
            details = {
                "subject": "runtime",
                "action": "orchestration",
                "preferred_lane": scheduler.get("preferred_lane") or "interactive",
                "dispatch_state": dispatch_queue.get("state") or "ready",
                "dispatch_depth": dispatch_queue.get("depth") or 0,
                "handoff": scheduler.get("dispatch_handoff_lane") or "none",
                "lanes": ", ".join(str(lane.get("id") or "lane") for lane in lanes) or "none",
                "workers": len(workers),
            }
        elif command == "runtime-queues":
            scheduler = self.scheduler_snapshot(session_metadata=self._active_session_metadata())
            queues = list(scheduler.get("queues", []))
            target_pane = "runtime"
            state = self.runtime_control_snapshot()
            output = (
                f"runtime queues count={len(queues)}"
                f" foreground={next((q.get('depth') for q in queues if q.get('id') == 'foreground'), 0)}"
            )
            details = {
                "subject": "runtime",
                "action": "queues",
                "count": len(queues),
                "foreground_depth": next((q.get("depth") for q in queues if q.get("id") == "foreground"), 0),
                "goal_depth": next((q.get("depth") for q in queues if q.get("id") == "goal_background"), 0),
                "automation_depth": next((q.get("depth") for q in queues if q.get("id") == "automation"), 0),
            }
        elif command == "runtime-adapters":
            adapters = [str(row.get("name") or "unknown") for row in self._runtime_adapters]
            target_pane = "runtime"
            state = self.runtime_control_snapshot()
            output = (
                f"runtime adapters count={len(adapters)}"
                f" active={self._runtime_control.get('active_adapter') or 'unset'}"
            )
            details = {
                "subject": "runtime",
                "action": "adapters",
                "count": len(adapters),
                "active": self._runtime_control.get("active_adapter") or "unset",
                "items": ", ".join(adapters) or "none",
            }
        elif command == "runtime-bridges":
            bridges = [str(row.get("adapter") or "unknown") for row in self._runtime_bridges]
            healthy = sum(1 for row in self._runtime_bridges if str(row.get("health") or "") == "ready")
            target_pane = "runtime"
            state = self.runtime_control_snapshot()
            output = f"runtime bridges count={len(bridges)} ready={healthy}"
            details = {
                "subject": "runtime",
                "action": "bridges",
                "count": len(bridges),
                "ready": healthy,
                "items": ", ".join(bridges) or "none",
            }
        elif command == "drain-background":
            state = self.drain_background()
            target_pane = "runtime"
            output = "background drain requested"
            details = {"subject": "runtime", "action": "drain-background"}
        elif command == "prioritize-goal-lane":
            state = self.prioritize_goal_lane()
            target_pane = "runtime"
            output = "goal lane prioritized"
            details = {"subject": "lane", "action": "prioritize-goal"}
        elif command == "enter-maintenance":
            state = self.enter_maintenance(" ".join(args).strip() or None)
            target_pane = "control_plane"
            output = "maintenance enabled"
            details = {"subject": "maintenance", "action": "enter", "reason": " ".join(args).strip() or "operator-maintenance-window"}
        elif command == "exit-maintenance":
            state = self.exit_maintenance()
            target_pane = "control_plane"
            output = "maintenance cleared"
            details = {"subject": "maintenance", "action": "exit"}
        else:
            raise ValueError(f"unknown operator command: {raw}")
        action_result = {
            "command": raw,
            "target_pane": target_pane,
            "ok": True,
            "status": details.get("status") or "ok",
            "code": details.get("code", 0),
            "subject": details.get("subject"),
            "action": details.get("action"),
            "output": output,
            "details": details,
        }
        return {
            "command": raw,
            "ok": True,
            "target_pane": target_pane,
            "output": output,
            "runtime_control": state,
            "details": details,
            "action_result": action_result,
        }

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
        subagent_rows = self._subagent_snapshot(self._active_session_key)
        if subagent_rows:
            snapshot["snapshot"]["subagent_workers"] = len(subagent_rows)
        board_snapshot = self._board_runtime_snapshot(board)
        native_snapshot = self._native_runtime_snapshot()
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
        sustained_state = "active" if goal_blob.get("active") else "idle"
        sustained_summary = (
            str(goal_blob.get("ui_summary") or goal_blob.get("objective") or "").strip()
            if goal_blob.get("active")
            else "Long-running objective slices with internal continuation support."
        )
        if continuation:
            sustained_state = "continuing"
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
                        [f"dispatch:{item['label']}:{item['lifecycle']}" for item in dispatch_items[:3]]
                        if dispatch_handoff_lane == "sustained_goal" and dispatch_depth
                        else []
                    ),
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
                        [f"dispatch:{item['label']}:{item['lifecycle']}" for item in dispatch_items[:3]]
                        if dispatch_handoff_lane == "subagent" and dispatch_depth
                        else [row["label"] for row in subagent_rows[:4]]
                    ),
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
                        f"{item['label']}:{item['lifecycle']}"
                        for item in dispatch_items[:4]
                    ],
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
    ) -> None:
        self._event_log = append_kernel_event(
            self._event_log,
            action=action,
            state=state,
            message=message,
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
            self._native_recent_commands = [dict(row) for row in recent_commands[:8]]
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
            "recent_commands": [dict(row) for row in self._native_recent_commands[:8]],
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
        items: list[str] = []
        roots: list[str] = []
        queue_items: list[dict[str, Any]] = []
        for row in self._dispatch_queue:
            lifecycle = str(row.get("lifecycle") or row.get("status") or "queued")
            lifecycle_counts[lifecycle] = lifecycle_counts.get(lifecycle, 0) + 1
        for row in self._dispatch_queue[:limit]:
            tool = str(row.get("tool") or "unknown")
            module = str(row.get("module") or "runtime")
            lifecycle = str(row.get("lifecycle") or row.get("status") or "queued")
            items.append(f"{tool}@{module}:{lifecycle}")
            root = str(row.get("root") or "").strip()
            if root:
                roots.append(root)
            queue_items.append(
                {
                    "tool": tool,
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
        return {
            "queue_depth": len(self._dispatch_queue),
            "priority": "on" if dispatch_priority else "off",
            "handoff": dispatch_handoff_lane,
            "items": ", ".join(items) or "none",
            "lifecycle": ", ".join(
                f"{name}:{count}" for name, count in lifecycle_counts.items()
            ) or "none",
            "roots": ", ".join(roots[:limit]) or "none",
            "queue_items": queue_items,
            "root_items": roots[:limit],
            "lifecycle_rows": lifecycle_rows,
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
