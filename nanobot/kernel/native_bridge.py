"""Native bridge adapter that folds Rust/C kernel signals into the Mira shell contract."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MODULE_CAPACITY = 64
MESSAGE_CAPACITY = 240


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


@dataclass(slots=True)
class NativeBridgeSnapshot:
    queue_depth: int
    events: list[dict[str, Any]]
    module_states: dict[str, dict[str, Any]]
    artifact: str | None


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _library_candidates() -> list[Path]:
    root = _project_root()
    names = ["libmira_kernel_bridge.dylib", "libmira_kernel_bridge.so", "mira_kernel_bridge.dll"]
    prefixes = [
        root / "native" / "mira-kernel-bridge" / "target" / "release",
        root / "native" / "mira-kernel-bridge" / "target" / "debug",
    ]
    return [prefix / name for prefix in prefixes for name in names]


def _decode_buffer(raw: Any) -> str:
    return bytes(raw).split(b"\0", 1)[0].decode("utf-8", errors="ignore")


def _event_state(kind: int, code: int) -> str:
    if kind >= 3 or code < 0:
        return "fault"
    if kind == 2:
        return "busy"
    return "ok"


def _module_status(status: int, last_code: int) -> str:
    if status >= 3 or last_code < 0:
        return "fault"
    if status == 2:
        return "busy"
    if status == 1:
        return "ready"
    return "planned"


def _load_library() -> tuple[ctypes.CDLL | None, str | None]:
    root = _project_root()
    for candidate in _library_candidates():
        if not candidate.exists():
            continue
        try:
            return ctypes.CDLL(str(candidate)), str(candidate.relative_to(root))
        except OSError:
            continue
    return None, None


def snapshot_native_bridge() -> NativeBridgeSnapshot | None:
    library, artifact = _load_library()
    if library is None:
        return None
    queue_depth_symbol = getattr(library, "mira_kernel_queue_depth", None)
    poll_symbol = getattr(library, "mira_kernel_poll_event", None)
    read_module_symbol = getattr(library, "mira_kernel_read_module_state", None)
    if queue_depth_symbol is None or poll_symbol is None or read_module_symbol is None:
        return None

    queue_depth_symbol.restype = ctypes.c_size_t
    poll_symbol.argtypes = [ctypes.POINTER(NativeKernelEvent)]
    poll_symbol.restype = ctypes.c_int32
    read_module_symbol.argtypes = [ctypes.c_char_p, ctypes.POINTER(NativeKernelModuleState)]
    read_module_symbol.restype = ctypes.c_int32

    events: list[dict[str, Any]] = []
    module_states: dict[str, dict[str, Any]] = {}
    while True:
        raw_event = NativeKernelEvent()
        result = poll_symbol(ctypes.byref(raw_event))
        if result != 0:
            break
        module_name = _decode_buffer(raw_event.module) or "native"
        message = _decode_buffer(raw_event.message) or f"native event code={raw_event.code}"
        state = _event_state(int(raw_event.kind), int(raw_event.code))
        events.append(
            {
                "id": f"native-{raw_event.timestamp_ms}-{len(events) + 1}",
                "action": f"native::{module_name}",
                "state": state,
                "message": message,
                "code": int(raw_event.code),
                "kind": int(raw_event.kind),
                "module": module_name,
                "timestamp_ms": int(raw_event.timestamp_ms),
                "type": "native_bridge",
            }
        )
        if module_name not in module_states:
            raw_state = NativeKernelModuleState()
            if read_module_symbol(module_name.encode("utf-8"), ctypes.byref(raw_state)) == 0:
                module_states[module_name] = {
                    "status": _module_status(int(raw_state.status), int(raw_state.last_code)),
                    "status_code": int(raw_state.status),
                    "last_code": int(raw_state.last_code),
                    "updated_at_ms": int(raw_state.updated_at_ms),
                }
    return NativeBridgeSnapshot(
        queue_depth=int(queue_depth_symbol()),
        events=events,
        module_states=module_states,
        artifact=artifact,
    )
