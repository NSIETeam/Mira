"""Bridge stub state for non-Python execution backends."""

from __future__ import annotations

from copy import deepcopy
import json

from .paths import KERNEL_PROJECT_ROOT
from .runtime_probe import probe_runtime_bridge
from .runtime_status import runtime_probe_payload


def _manifest_probe(adapter: dict[str, object]) -> dict[str, object] | None:
    manifest = str(adapter.get("runtime_manifest") or "")
    if not manifest:
        return None
    manifest_path = KERNEL_PROJECT_ROOT / manifest
    if not manifest_path.exists():
        return None
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return runtime_probe_payload(
            status="fault",
            artifact=manifest,
            manifest=manifest,
            runtime_mode=None,
            abi=adapter.get("abi"),
            status_symbol=adapter.get("status_symbol"),
            error="invalid runtime manifest",
        )
    payload = runtime_probe_payload(
        status=raw.get("status"),
        artifact=manifest,
        manifest=manifest,
        runtime_mode=raw.get("mode"),
        abi=raw.get("abi") or adapter.get("abi"),
        status_symbol=raw.get("status_symbol") or adapter.get("status_symbol"),
        runtime=raw.get("runtime"),
        version=raw.get("version"),
        queue_depth=raw.get("queue_depth"),
        module_count=raw.get("module_count"),
        capabilities=raw.get("capabilities"),
        error=raw.get("error") or "runtime manifest fault",
    )
    payload["kernel_surface"] = raw.get("kernel_surface")
    payload["free_symbol"] = raw.get("free_symbol")
    payload["attach_symbol"] = raw.get("attach_symbol")
    return payload


def _artifact_status(adapter: dict[str, object]) -> tuple[str, str, dict[str, object] | None]:
    live_probe = probe_runtime_bridge(adapter)
    if live_probe is not None:
        return str(live_probe.get("health") or "planned"), str(live_probe.get("artifact") or ""), live_probe
    probe = _manifest_probe(adapter)
    if probe is not None:
        return str(probe.get("health") or "planned"), str(probe.get("artifact") or ""), probe
    artifact = str(adapter.get("bootstrap_artifact") or "")
    if not artifact:
        return "stub", "", None
    artifact_path = KERNEL_PROJECT_ROOT / artifact
    if artifact_path.exists():
        return "ready", artifact, None
    return "planned", artifact, None


def build_runtime_bridges(
    adapters: list[dict[str, object]],
    *,
    active_adapter: str,
) -> list[dict[str, object]]:
    bridges: list[dict[str, object]] = []
    for adapter in adapters:
        name = str(adapter.get("name", ""))
        transport = str(adapter.get("transport", ""))
        language = str(adapter.get("implementation_language", ""))
        status = "active" if name == active_adapter else "standby"
        health, artifact, probe = _artifact_status(adapter)
        if name == "python-inprocess":
            entrypoint = "python://kernel.loop"
        elif name == "rust-ffi":
            entrypoint = f"ffi://{artifact or 'mira.runtime.rust'}"
        else:
            entrypoint = f"serial://{artifact or 'mira.bridge'}"
        bridges.append(
            {
                "adapter": name,
                "backend_kind": f"{language}-{transport}",
                "status": status,
                "health": health,
                "entrypoint": entrypoint,
                "manifest": (probe or {}).get("manifest", adapter.get("runtime_manifest")),
                "abi": (probe or {}).get("abi", adapter.get("abi")),
                "status_symbol": (probe or {}).get("status_symbol", adapter.get("status_symbol")),
                "kernel_surface": (probe or {}).get("kernel_surface"),
                "free_symbol": (probe or {}).get("free_symbol"),
                "attach_symbol": (probe or {}).get("attach_symbol"),
                "runtime": (probe or {}).get("runtime"),
                "version": (probe or {}).get("version"),
                "queue_depth": (probe or {}).get("queue_depth"),
                "module_count": (probe or {}).get("module_count"),
                "capabilities": (probe or {}).get("capabilities"),
                "runtime_mode": (probe or {}).get("runtime_mode"),
                "runtime_stage": adapter.get("runtime_stage"),
                "build_hint": adapter.get("build_hint"),
                "board_capable": "board_io" in list(adapter.get("capabilities", [])),
                "last_error": (probe or {}).get("last_error"),
            }
        )
    return bridges


def clone_runtime_bridges(bridges: list[dict[str, object]]) -> list[dict[str, object]]:
    return deepcopy(bridges)


def activate_runtime_bridge(
    bridges: list[dict[str, object]],
    *,
    adapter_name: str,
) -> list[dict[str, object]]:
    next_bridges = clone_runtime_bridges(bridges)
    found = False
    for bridge in next_bridges:
        if bridge.get("adapter") == adapter_name:
            bridge["status"] = "active"
            bridge["health"] = (
                "ready"
                if adapter_name == "python-inprocess"
                else ("maintenance" if bridge.get("health") == "maintenance" else "ready")
            )
            bridge["last_error"] = None
            found = True
        elif bridge.get("status") == "active":
            bridge["status"] = "standby"
    if not found:
        raise ValueError(f"Unknown bridge adapter: {adapter_name}")
    return next_bridges


def mark_bridge_fault(
    bridges: list[dict[str, object]],
    *,
    adapter_name: str,
    error: str,
) -> list[dict[str, object]]:
    next_bridges = clone_runtime_bridges(bridges)
    for bridge in next_bridges:
        if bridge.get("adapter") == adapter_name:
            bridge["health"] = "fault"
            bridge["last_error"] = error
            return next_bridges
    raise ValueError(f"Unknown bridge adapter: {adapter_name}")


def clear_bridge_fault(
    bridges: list[dict[str, object]],
    *,
    adapter_name: str,
) -> list[dict[str, object]]:
    next_bridges = clone_runtime_bridges(bridges)
    for bridge in next_bridges:
        if bridge.get("adapter") == adapter_name:
            bridge["health"] = "ready"
            bridge["last_error"] = None
            return next_bridges
    raise ValueError(f"Unknown bridge adapter: {adapter_name}")


def restart_runtime_bridge(
    bridges: list[dict[str, object]],
    *,
    adapter_name: str,
) -> list[dict[str, object]]:
    next_bridges = clone_runtime_bridges(bridges)
    for bridge in next_bridges:
        if bridge.get("adapter") == adapter_name:
            bridge["status"] = "active"
            bridge["health"] = "ready"
            bridge["last_error"] = None
            return next_bridges
    raise ValueError(f"Unknown bridge adapter: {adapter_name}")


def set_bridge_maintenance(
    bridges: list[dict[str, object]],
    *,
    adapter_name: str | None = None,
    enabled: bool,
    reason: str | None = None,
) -> list[dict[str, object]]:
    next_bridges = clone_runtime_bridges(bridges)
    matched = False
    for bridge in next_bridges:
        if adapter_name is not None and bridge.get("adapter") != adapter_name:
            continue
        bridge["status"] = "maintenance" if enabled else "standby"
        bridge["last_error"] = reason if enabled else None
        if bridge.get("health") != "fault":
            bridge["health"] = "maintenance" if enabled else (
                "ready"
            )
        matched = True
    if not matched:
        raise ValueError(f"Unknown bridge adapter: {adapter_name}")
    return next_bridges
