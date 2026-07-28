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
    error: object = None,
) -> dict[str, Any]:
    health = runtime_health(status)
    return {
        "health": health,
        "artifact": artifact,
        "manifest": manifest,
        "runtime_mode": runtime_mode,
        "abi": abi,
        "status_symbol": status_symbol,
        "last_error": None if health != "fault" else str(error or "runtime probe fault"),
    }
