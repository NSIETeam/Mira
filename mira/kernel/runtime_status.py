"""Shared runtime probe status normalization for Mira kernel bridges."""

from __future__ import annotations

from typing import Any


def runtime_health(status: object) -> str:
    state = str(status or "planned")
    if state == "ready":
        return "ready"
    if state == "planned":
        return "planned"
    return "fault"


def runtime_probe_payload(
    *,
    status: object,
    artifact: str | None,
    manifest: object,
    runtime_mode: object,
    abi: object,
    status_symbol: object,
    runtime: object = None,
    version: object = None,
    queue_depth: object = None,
    module_count: object = None,
    capabilities: object = None,
    module_states: object = None,
    error: object = None,
) -> dict[str, Any]:
    health = runtime_health(status)
    payload = {
        "health": health,
        "artifact": artifact,
        "manifest": manifest,
        "runtime_mode": runtime_mode,
        "abi": abi,
        "status_symbol": status_symbol,
        "last_error": None if health != "fault" else str(error or "runtime probe fault"),
    }
    if runtime is not None:
        payload["runtime"] = runtime
    if version is not None:
        payload["version"] = version
    if queue_depth is not None:
        payload["queue_depth"] = queue_depth
    if module_count is not None:
        payload["module_count"] = module_count
    if capabilities is not None:
        payload["capabilities"] = capabilities
    if module_states is not None:
        payload["module_states"] = module_states
    return payload
