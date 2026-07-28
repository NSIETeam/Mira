"""Stable runtime-control contract for the Mira kernel surface."""

from __future__ import annotations

from copy import deepcopy

from mira.kernel.profile import KernelProfile


def build_runtime_control_state(
    profile: KernelProfile,
    *,
    default_adapter: str,
    module_names: list[str],
) -> dict[str, object]:
    embedded_target = "embedded" if "embedded-lab" in profile.runtime_targets else "desktop"
    preferred_transport = "serial" if embedded_target == "embedded" else "in_process"
    return {
        "active_adapter": default_adapter,
        "adapter_failover_order": [
            default_adapter,
            "rust-ffi",
            "c-serial-bridge",
        ],
        "module_focus": module_names[0] if module_names else None,
        "board": {
            "attached": False,
            "health": "planned",
            "transport": None,
            "port": None,
            "target": embedded_target,
            "preferred_transport": preferred_transport,
            "runtime_mode": None,
            "bridge_artifact": None,
            "last_error": None,
        },
        "fault_posture": {
            "supervisor": "userspace-kernel-loop",
            "restart_policy": "operator-confirmed",
            "last_level": "clear",
        },
        "execution_gate": {
            "state": "open",
            "reason": "operator-ready",
        },
        "maintenance_mode": {
            "enabled": False,
            "reason": None,
        },
    }


def clone_runtime_control_state(state: dict[str, object]) -> dict[str, object]:
    return deepcopy(state)


def set_active_adapter(
    state: dict[str, object],
    *,
    adapter_name: str,
    adapter_names: list[str],
) -> dict[str, object]:
    next_state = clone_runtime_control_state(state)
    if adapter_name not in adapter_names:
        raise ValueError(f"Unknown adapter: {adapter_name}")
    next_state["active_adapter"] = adapter_name
    failover = [adapter_name, *[name for name in adapter_names if name != adapter_name]]
    next_state["adapter_failover_order"] = failover
    return next_state


def set_module_focus(
    state: dict[str, object],
    *,
    module_name: str,
    module_names: list[str],
) -> dict[str, object]:
    next_state = clone_runtime_control_state(state)
    if module_name not in module_names:
        raise ValueError(f"Unknown module: {module_name}")
    next_state["module_focus"] = module_name
    return next_state


def attach_board(
    state: dict[str, object],
    *,
    transport: str | None = None,
    port: str | None = None,
) -> dict[str, object]:
    next_state = clone_runtime_control_state(state)
    board = dict(next_state.get("board", {}))
    preferred_transport = board.get("preferred_transport")
    board["attached"] = True
    board["health"] = "ready"
    board["transport"] = transport or preferred_transport or "serial"
    board["port"] = port or ("kernel://local" if board["transport"] == "in_process" else "/dev/tty.mira")
    board["last_error"] = None
    next_state["board"] = board
    return next_state


def detach_board(state: dict[str, object]) -> dict[str, object]:
    next_state = clone_runtime_control_state(state)
    board = dict(next_state.get("board", {}))
    board["attached"] = False
    board["health"] = "planned"
    board["transport"] = None
    board["port"] = None
    board["runtime_mode"] = None
    board["bridge_artifact"] = None
    board["last_error"] = None
    next_state["board"] = board
    return next_state


def set_fault_level(
    state: dict[str, object],
    *,
    level: str,
) -> dict[str, object]:
    next_state = clone_runtime_control_state(state)
    posture = dict(next_state.get("fault_posture", {}))
    posture["last_level"] = level
    next_state["fault_posture"] = posture
    return next_state


def set_execution_gate(
    state: dict[str, object],
    *,
    gate_state: str,
    reason: str | None = None,
) -> dict[str, object]:
    if gate_state not in {"open", "paused", "degraded"}:
        raise ValueError(f"Unknown execution gate: {gate_state}")
    next_state = clone_runtime_control_state(state)
    next_state["execution_gate"] = {
        "state": gate_state,
        "reason": reason or ("operator-ready" if gate_state == "open" else "operator-requested"),
    }
    return next_state


def set_maintenance_mode(
    state: dict[str, object],
    *,
    enabled: bool,
    reason: str | None = None,
) -> dict[str, object]:
    next_state = clone_runtime_control_state(state)
    next_state["maintenance_mode"] = {
        "enabled": enabled,
        "reason": reason if enabled else None,
    }
    return next_state
