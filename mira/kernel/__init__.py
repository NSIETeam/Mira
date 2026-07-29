"""Stable Mira kernel surface for GUI and external clients.

The existing codebase exposes many powerful internals, but mature agent shells
benefit from a narrow contract:

- one app object that owns runtime construction;
- one normalized event model that GUI code can render directly;
- raw internals still available underneath for advanced integrations.

This package is that contract. It does not replace the current runtime; it
stabilizes the boundary around it.
"""

from .app import KernelApp, active_kernel_app, build_kernel_manifest, register_kernel_loop
from .embedded_plane import build_board_snapshot, build_embedded_topology
from .events import (
    EXECUTION_LIFECYCLE_STATES,
    EXECUTION_SNAPSHOT_STATUSES,
    KERNEL_EVENT_ACTIONS,
    KERNEL_EVENT_STATES,
    KERNEL_EVENT_TYPES,
    ExecutionLifecycleState,
    ExecutionSnapshot,
    ExecutionStatus,
    KernelEvent,
    KernelEventAction,
    KernelEventState,
    KernelEventType,
    merge_snapshot_with_session_metadata,
    normalize_stream_event,
    snapshot_from_run_result,
)
from .execution_plane import build_execution_lanes
from .module_registry import KernelModuleDescriptor, list_kernel_modules
from .native_bridge import (
    NativeBridgeSnapshot,
    dispatch_native_bridge_command,
    snapshot_native_bridge,
)
from .observability import (
    KERNEL_EVENT_LOG_LIMIT,
    append_kernel_event,
    build_diagnostics_snapshot,
)
from .profile import (
    KernelProfile,
    automation_customer_profile,
    desktop_customer_profile,
    get_profile,
    list_profiles,
    lite_customer_profile,
    register_profile,
)
from .runtime_adapter import RuntimeAdapterDescriptor, list_runtime_adapters
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
    build_runtime_control_state,
    clone_runtime_control_state,
    set_active_adapter,
    set_execution_gate,
    set_fault_level,
    set_maintenance_mode,
    set_module_focus,
)
from .runtime_topology import build_runtime_topology
from .scheduler import (
    build_scheduler_state,
    clone_scheduler_state,
    prioritize_lane,
    request_background_drain,
)
from .shell import (
    ShellDescriptor,
    default_engineering_shell,
    get_shell,
    list_shells,
    register_shell,
    review_shell,
    single_execution_shell,
)
from .worker_plane import build_worker_registry, project_worker_registry

ExecutionKernel = KernelApp

__all__ = [
    "KernelApp",
    "ExecutionKernel",
    "ExecutionSnapshot",
    "ExecutionLifecycleState",
    "ExecutionStatus",
    "EXECUTION_LIFECYCLE_STATES",
    "KernelEventAction",
    "KernelEventState",
    "KERNEL_EVENT_TYPES",
    "KERNEL_EVENT_ACTIONS",
    "KERNEL_EVENT_STATES",
    "EXECUTION_SNAPSHOT_STATUSES",
    "build_kernel_manifest",
    "active_kernel_app",
    "register_kernel_loop",
    "build_execution_lanes",
    "KERNEL_EVENT_LOG_LIMIT",
    "append_kernel_event",
    "build_diagnostics_snapshot",
    "NativeBridgeSnapshot",
    "dispatch_native_bridge_command",
    "snapshot_native_bridge",
    "build_worker_registry",
    "project_worker_registry",
    "build_runtime_topology",
    "build_board_snapshot",
    "build_embedded_topology",
    "merge_snapshot_with_session_metadata",
    "KernelEvent",
    "KernelEventType",
    "KernelProfile",
    "ShellDescriptor",
    "KernelModuleDescriptor",
    "RuntimeAdapterDescriptor",
    "lite_customer_profile",
    "desktop_customer_profile",
    "automation_customer_profile",
    "register_profile",
    "get_profile",
    "list_profiles",
    "list_kernel_modules",
    "list_runtime_adapters",
    "default_engineering_shell",
    "single_execution_shell",
    "review_shell",
    "register_shell",
    "get_shell",
    "list_shells",
    "build_runtime_bridges",
    "clone_runtime_bridges",
    "activate_runtime_bridge",
    "mark_bridge_fault",
    "clear_bridge_fault",
    "restart_runtime_bridge",
    "set_bridge_maintenance",
    "build_runtime_control_state",
    "clone_runtime_control_state",
    "set_active_adapter",
    "set_execution_gate",
    "set_fault_level",
    "set_maintenance_mode",
    "set_module_focus",
    "normalize_stream_event",
    "snapshot_from_run_result",
    "build_scheduler_state",
    "clone_scheduler_state",
    "prioritize_lane",
    "request_background_drain",
]
