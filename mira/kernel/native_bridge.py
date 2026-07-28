"""Native bridge adapter that folds Rust/C kernel signals into the Mira shell contract."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from typing import Any

from .paths import KERNEL_PROJECT_ROOT


MODULE_CAPACITY = 64
MESSAGE_CAPACITY = 240
COMMAND_CAPACITY = 96


class NativeKernelEvent(ctypes.Structure):
    _fields_ = [
        ("kind", ctypes.c_uint32),
        ("code", ctypes.c_int32),
        ("timestamp_ms", ctypes.c_uint64),
        ("module", ctypes.c_uint8 * MODULE_CAPACITY),
        ("message", ctypes.c_uint8 * MESSAGE_CAPACITY),
    ]


class NativeKernelModuleState(ctypes.Structure):
    _fields_ = [
        ("name", ctypes.c_uint8 * MODULE_CAPACITY),
        ("status", ctypes.c_uint32),
        ("last_code", ctypes.c_int32),
        ("updated_at_ms", ctypes.c_uint64),
    ]


class NativeKernelCommand(ctypes.Structure):
    _fields_ = [
        ("issued_at_ms", ctypes.c_uint64),
        ("updated_at_ms", ctypes.c_uint64),
        ("status", ctypes.c_uint32),
        ("code", ctypes.c_int32),
        ("target", ctypes.c_uint8 * MODULE_CAPACITY),
        ("action", ctypes.c_uint8 * MODULE_CAPACITY),
        ("value", ctypes.c_uint8 * COMMAND_CAPACITY),
    ]


@dataclass(slots=True)
class NativeBridgeSnapshot:
    queue_depth: int
    command_depth: int
    module_count: int
    events: list[dict[str, Any]]
    recent_commands: list[dict[str, Any]]
    module_states: dict[str, dict[str, Any]]
    last_command: dict[str, Any] | None
    artifact: str | None


def _library_candidates() -> list[Any]:
    root = KERNEL_PROJECT_ROOT
    names = ["libmira_kernel_bridge.dylib", "libmira_kernel_bridge.so", "mira_kernel_bridge.dll"]
    prefixes = [
        root / "native" / "mira-kernel-bridge" / "target" / "release",
        root / "native" / "mira-kernel-bridge" / "target" / "debug",
    ]
    return [prefix / name for prefix in prefixes for name in names]


def _decode_buffer(raw: Any) -> str:
    return bytes(raw).split(b"\0", 1)[0].decode("utf-8", errors="ignore")


def _native_command_text(target: str, action: str, value: str = "") -> str:
    command = f"native replay {target} {action}".strip()
    return f"{command} {value}".strip() if value else command


def _native_phase_state(
    state: int,
    *,
    code: int,
    ready_state: int | None = None,
    active_state: int = 2,
    active_label: str = "busy",
    idle_label: str = "planned",
) -> str:
    if state >= 3 or code < 0:
        return "fault"
    if state == active_state:
        return active_label
    if ready_state is not None and state == ready_state:
        return "ready"
    return idle_label


def _load_library() -> tuple[ctypes.CDLL | None, str | None]:
    root = KERNEL_PROJECT_ROOT
    for candidate in _library_candidates():
        if not candidate.exists():
            continue
        try:
            return ctypes.CDLL(str(candidate)), str(candidate.relative_to(root))
        except OSError:
            continue
    return None, None


def _native_command_actions(target: str, action: str, value: str) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = [
        {
            "id": "native_status",
            "label": "inspect native",
            "pane": "adapters",
            "command": "native status",
        },
        {
            "id": "native_modules",
            "label": "native modules",
            "pane": "modules",
            "command": "native modules",
        },
    ]
    if target and target != "none":
        actions.append(
            {
                "id": "focus_recent_target",
                "label": "focus target",
                "pane": "modules",
                "command": f"native focus {target}",
            }
        )
    if target and target != "none" and action and action != "none":
        replay_command = f"native replay {target} {action}"
        if value:
            replay_command = f"{replay_command} {value}"
        actions.append(
            {
                "id": "replay_recent_command",
                "label": "replay command",
                "pane": "adapters",
                "command": replay_command,
            }
        )
    return actions


def _last_command_actions(target: str, action: str) -> list[dict[str, Any]]:
    actions = [
        {
            "id": "native_status",
            "label": "inspect native",
            "pane": "adapters",
            "command": "native status",
        },
        {
            "id": "native_last_command",
            "label": "last command",
            "pane": "adapters",
            "command": "native last-command",
        },
        {
            "id": "native_modules",
            "label": "native modules",
            "pane": "modules",
            "command": "native modules",
        },
    ]
    if target and target != "none":
        actions.extend(
            [
                {
                    "id": "focus_last_target",
                    "label": "focus last target",
                    "pane": "modules",
                    "command": f"native focus {target}",
                },
                {
                    "id": "open_last_target",
                    "label": "open target",
                    "pane": "modules",
                    "command": f"module show {target}",
                },
            ]
        )
    if target and target != "none" and action and action != "none":
        actions.append(
            {
                "id": "replay_last",
                "label": "replay last",
                "pane": "adapters",
                "command": "native replay-last",
            }
        )
    return actions


def _native_status_route() -> list[dict[str, Any]]:
    return [
        {
            "id": "inspect_native",
            "label": "route",
            "pane": "adapters",
            "command": "native status",
        }
    ]


def _native_module_actions(module_name: str) -> list[dict[str, Any]]:
    return [
        {
            "id": "inspect_native_module",
            "label": "inspect",
            "pane": "modules",
            "command": f"native inspect {module_name}",
        }
    ]


def _native_event_row(raw_event: NativeKernelEvent) -> dict[str, Any]:
    module_name = _decode_buffer(raw_event.module) or "native"
    return {
        "id": f"native-{raw_event.timestamp_ms}-{module_name}-{int(raw_event.kind)}-{int(raw_event.code)}",
        "action": f"native::{module_name}",
        "state": _native_phase_state(
            int(raw_event.kind),
            code=int(raw_event.code),
            active_label="busy",
            idle_label="ok",
        ),
        "message": _decode_buffer(raw_event.message) or f"native event code={raw_event.code}",
        "code": int(raw_event.code),
        "kind": int(raw_event.kind),
        "module": module_name,
        "timestamp_ms": int(raw_event.timestamp_ms),
        "type": "native_bridge",
        "actions": _native_status_route(),
    }


def _native_command_row(
    raw_command: NativeKernelCommand,
    *,
    artifact: str | None,
    queue_depth: int,
    last_command: bool = False,
) -> dict[str, Any]:
    target = _decode_buffer(raw_command.target) or "none"
    action = _decode_buffer(raw_command.action) or "none"
    value = _decode_buffer(raw_command.value)
    command_text = _native_command_text(target, action, value)
    return {
        "target": target,
        "action": action,
        "command": command_text,
        "summary": f"{target}:{action}",
        "value": value,
        "status": _native_phase_state(
            int(raw_command.status),
            code=int(raw_command.code),
            ready_state=1,
            active_label="queued",
        ),
        "code": int(raw_command.code),
        "queue_depth": queue_depth,
        "artifact": artifact,
        "updated_at_ms": int(raw_command.updated_at_ms or raw_command.issued_at_ms),
        "actions": (
            _last_command_actions(target, action)
            if last_command
            else _native_command_actions(target, action, value)
        ),
    }


def _native_module_row(raw_state: NativeKernelModuleState) -> tuple[str | None, dict[str, Any] | None]:
    module_name = _decode_buffer(raw_state.name)
    if not module_name:
        return None, None
    return module_name, {
        "status": _native_phase_state(
            int(raw_state.status),
            code=int(raw_state.last_code),
            ready_state=1,
            active_label="busy",
        ),
        "status_code": int(raw_state.status),
        "last_code": int(raw_state.last_code),
        "updated_at_ms": int(raw_state.updated_at_ms),
        "actions": _native_module_actions(module_name),
    }


def _native_dispatch_row(
    *,
    ok: bool,
    status: str,
    health: str,
    code: int,
    artifact: str | None,
    target: str,
    action: str,
    value: str,
    queue_depth: int = 0,
    error: str | None = None,
) -> dict[str, Any]:
    command_text = _native_command_text(target, action, value)
    return {
        "ok": ok,
        "status": status,
        "health": health,
        "code": code,
        "artifact": artifact,
        "target": target,
        "action": action,
        "command": command_text,
        "summary": f"{target}:{action}",
        "value": value,
        "queue_depth": queue_depth,
        "updated_at_ms": None,
        "error": error,
    }


def snapshot_native_bridge() -> NativeBridgeSnapshot | None:
    library, artifact = _load_library()
    if library is None:
        return None
    queue_depth_symbol = getattr(library, "mira_kernel_queue_depth", None)
    recent_event_count_symbol = getattr(library, "mira_kernel_recent_event_count", None)
    command_depth_symbol = getattr(library, "mira_kernel_command_depth", None)
    recent_command_count_symbol = getattr(library, "mira_kernel_recent_command_count", None)
    module_count_symbol = getattr(library, "mira_kernel_module_count", None)
    poll_symbol = getattr(library, "mira_kernel_poll_event", None)
    read_recent_event_at_symbol = getattr(library, "mira_kernel_read_recent_event_at", None)
    read_module_at_symbol = getattr(library, "mira_kernel_read_module_state_at", None)
    read_last_command_symbol = getattr(library, "mira_kernel_read_last_command", None)
    read_recent_command_at_symbol = getattr(library, "mira_kernel_read_recent_command_at", None)
    if (
        queue_depth_symbol is None
        or recent_event_count_symbol is None
        or command_depth_symbol is None
        or recent_command_count_symbol is None
        or module_count_symbol is None
        or poll_symbol is None
        or read_recent_event_at_symbol is None
        or read_module_at_symbol is None
        or read_last_command_symbol is None
        or read_recent_command_at_symbol is None
    ):
        return None

    queue_depth_symbol.restype = ctypes.c_size_t
    recent_event_count_symbol.restype = ctypes.c_size_t
    command_depth_symbol.restype = ctypes.c_size_t
    recent_command_count_symbol.restype = ctypes.c_size_t
    module_count_symbol.restype = ctypes.c_size_t
    poll_symbol.argtypes = [ctypes.POINTER(NativeKernelEvent)]
    poll_symbol.restype = ctypes.c_int32
    read_recent_event_at_symbol.argtypes = [ctypes.c_size_t, ctypes.POINTER(NativeKernelEvent)]
    read_recent_event_at_symbol.restype = ctypes.c_int32
    read_module_at_symbol.argtypes = [ctypes.c_size_t, ctypes.POINTER(NativeKernelModuleState)]
    read_module_at_symbol.restype = ctypes.c_int32
    read_last_command_symbol.argtypes = [ctypes.POINTER(NativeKernelCommand)]
    read_last_command_symbol.restype = ctypes.c_int32
    read_recent_command_at_symbol.argtypes = [ctypes.c_size_t, ctypes.POINTER(NativeKernelCommand)]
    read_recent_command_at_symbol.restype = ctypes.c_int32

    events: list[dict[str, Any]] = []
    recent_commands: list[dict[str, Any]] = []
    seen_event_ids: set[str] = set()
    module_states: dict[str, dict[str, Any]] = {}
    command_depth = int(command_depth_symbol())
    recent_event_count = int(recent_event_count_symbol())
    for index in range(recent_event_count):
        raw_event = NativeKernelEvent()
        if read_recent_event_at_symbol(index, ctypes.byref(raw_event)) != 0:
            continue
        event_row = _native_event_row(raw_event)
        event_id = str(event_row["id"])
        if event_id in seen_event_ids:
            continue
        seen_event_ids.add(event_id)
        events.append(event_row)
    while True:
        raw_event = NativeKernelEvent()
        result = poll_symbol(ctypes.byref(raw_event))
        if result != 0:
            break
        event_row = _native_event_row(raw_event)
        event_id = str(event_row["id"])
        if event_id in seen_event_ids:
            continue
        seen_event_ids.add(event_id)
        events.append(event_row)
    recent_command_count = int(recent_command_count_symbol())
    for index in range(recent_command_count):
        raw_command = NativeKernelCommand()
        if read_recent_command_at_symbol(index, ctypes.byref(raw_command)) != 0:
            continue
        recent_commands.append(
            _native_command_row(
                raw_command,
                artifact=artifact,
                queue_depth=command_depth,
            )
        )
    module_count = int(module_count_symbol())
    for index in range(module_count):
        raw_state = NativeKernelModuleState()
        if read_module_at_symbol(index, ctypes.byref(raw_state)) != 0:
            continue
        module_name, module_row = _native_module_row(raw_state)
        if not module_name or module_row is None:
            continue
        module_states[module_name] = module_row
    last_command: dict[str, Any] | None = None
    raw_command = NativeKernelCommand()
    if read_last_command_symbol(ctypes.byref(raw_command)) == 0:
        last_command = _native_command_row(
            raw_command,
            artifact=artifact,
            queue_depth=command_depth,
            last_command=True,
        )
    return NativeBridgeSnapshot(
        queue_depth=int(queue_depth_symbol()),
        command_depth=command_depth,
        module_count=module_count,
        events=events,
        recent_commands=recent_commands,
        module_states=module_states,
        last_command=last_command,
        artifact=artifact,
    )


def dispatch_native_bridge_command(
    *,
    target: str,
    action: str,
    value: str = "",
) -> dict[str, Any]:
    library, artifact = _load_library()
    if library is None:
        return _native_dispatch_row(
            ok=False,
            status="unavailable",
            health="fault",
            code=-1,
            artifact=None,
            target=target,
            action=action,
            value=value,
            error="native bridge library not built",
        )
    submit_symbol = getattr(library, "mira_kernel_submit_command", None)
    depth_symbol = getattr(library, "mira_kernel_command_depth", None)
    if submit_symbol is None or depth_symbol is None:
        return _native_dispatch_row(
            ok=False,
            status="unsupported",
            health="fault",
            code=-2,
            artifact=artifact,
            target=target,
            action=action,
            value=value,
            error="native command surface unavailable",
        )
    submit_symbol.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p]
    submit_symbol.restype = ctypes.c_int32
    depth_symbol.restype = ctypes.c_size_t
    code = int(
        submit_symbol(
            target.encode("utf-8"),
            action.encode("utf-8"),
            value.encode("utf-8"),
        )
    )
    return _native_dispatch_row(
        ok=code == 0,
        status="queued" if code == 0 else "fault",
        health="ready" if code == 0 else "fault",
        code=code,
        artifact=artifact,
        target=target,
        action=action,
        value=value,
        queue_depth=int(depth_symbol()),
        error=None if code == 0 else f"native command failed with code {code}",
    )
