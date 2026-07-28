"""Stable embedded/board contract for the Mira kernel surface."""

from __future__ import annotations

from typing import Any


def build_board_snapshot(
    *,
    attached: bool,
    health: str | None,
    transport: str | None,
    port: str | None,
    target: str | None,
    preferred_transport: str | None,
    runtime_mode: str | None = None,
    bridge_artifact: str | None = None,
    last_error: str | None = None,
    available_ports: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "attached": attached,
        "health": health,
        "transport": transport,
        "port": port,
        "target": target,
        "preferred_transport": preferred_transport,
        "runtime_mode": runtime_mode,
        "bridge_artifact": bridge_artifact,
        "last_error": last_error,
        "available_ports": list(available_ports or []),
    }


def build_embedded_topology(
    *,
    board: dict[str, Any],
    transports: list[str],
    active_adapter: str | None,
) -> dict[str, Any]:
    return {
        "board": dict(board),
        "transports": list(transports),
        "active_adapter": active_adapter,
    }
