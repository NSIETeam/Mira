"""Minimal host-side probing for non-Python Mira runtime bridges."""

from __future__ import annotations

import ctypes
import glob
import json
import sys
from pathlib import Path
from typing import Any

from .paths import KERNEL_PROJECT_ROOT
from .runtime_status import runtime_probe_payload


def _shared_library_candidates(adapter_name: str) -> list[Path]:
    root = KERNEL_PROJECT_ROOT
    if adapter_name == "rust-ffi":
        names = ["libmira_kernel_runtime.dylib", "libmira_kernel_runtime.so", "mira_kernel_runtime.dll"]
        prefixes = [
            root / "runtimes" / "mira-rust" / "target" / "release",
            root / "runtimes" / "mira-rust" / "target" / "debug",
        ]
    elif adapter_name == "c-serial-bridge":
        names = ["libmira_bridge.dylib", "libmira_bridge.so", "mira_bridge.dll"]
        prefixes = [
            root / "runtimes" / "mira-c" / "build",
            root / "runtimes" / "mira-c",
        ]
    else:
        return []
    return [prefix / name for prefix in prefixes for name in names]


def discover_serial_ports() -> list[str]:
    if sys.platform == "darwin":
        patterns = ["/dev/tty.*", "/dev/cu.*"]
    elif sys.platform.startswith("linux"):
        patterns = ["/dev/ttyUSB*", "/dev/ttyACM*", "/dev/ttyS*"]
    elif sys.platform.startswith("win"):
        return [f"COM{i}" for i in range(1, 17)]
    else:
        patterns = ["/dev/tty*"]
    seen: set[str] = set()
    ports: list[str] = []
    for pattern in patterns:
        for path in sorted(glob.glob(pattern)):
            if path in seen:
                continue
            seen.add(path)
            ports.append(path)
    return ports[:16]


def _load_library(candidates: list[Path]) -> tuple[ctypes.CDLL | None, str | None]:
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            return ctypes.CDLL(str(candidate)), str(candidate.relative_to(KERNEL_PROJECT_ROOT))
        except OSError:
            continue
    return None, None


def probe_runtime_bridge(adapter: dict[str, object]) -> dict[str, Any] | None:
    adapter_name = str(adapter.get("name") or "")
    if adapter_name not in {"rust-ffi", "c-serial-bridge"}:
        return None
    status_symbol = str(adapter.get("status_symbol") or "")
    if not status_symbol:
        return None
    library, loaded_path = _load_library(_shared_library_candidates(adapter_name))
    if library is None or not loaded_path:
        return None
    try:
        symbol = getattr(library, status_symbol)
    except AttributeError:
        return runtime_probe_payload(
            status="fault",
            artifact=loaded_path,
            manifest=adapter.get("runtime_manifest"),
            runtime_mode=None,
            abi=adapter.get("abi"),
            status_symbol=status_symbol,
            kernel_surface=adapter.get("kernel_surface"),
            free_symbol=adapter.get("free_symbol"),
            attach_symbol=adapter.get("attach_symbol"),
            runtime=adapter.get("name"),
            error=f"missing status symbol: {status_symbol}",
        )

    if adapter_name == "rust-ffi":
        symbol.restype = ctypes.c_void_p
        free_symbol_name = "mira_runtime_free_json"
        free_symbol = getattr(library, free_symbol_name, None)
        payload_ptr = symbol()
        if not payload_ptr:
            return runtime_probe_payload(
                status="fault",
                artifact=loaded_path,
                manifest=adapter.get("runtime_manifest"),
                runtime_mode=None,
                abi=adapter.get("abi"),
                status_symbol=status_symbol,
                kernel_surface=adapter.get("kernel_surface"),
                free_symbol=adapter.get("free_symbol"),
                attach_symbol=adapter.get("attach_symbol"),
                runtime=adapter.get("name"),
                error="rust runtime returned null status pointer",
            )
        raw_json = ctypes.cast(payload_ptr, ctypes.c_char_p).value
        if free_symbol is not None:
            free_symbol.argtypes = [ctypes.c_void_p]
            free_symbol.restype = None
            free_symbol(payload_ptr)
    else:
        symbol.restype = ctypes.c_char_p
        raw_json = symbol()

    if not raw_json:
        return runtime_probe_payload(
            status="fault",
            artifact=loaded_path,
            manifest=adapter.get("runtime_manifest"),
            runtime_mode=None,
            abi=adapter.get("abi"),
            status_symbol=status_symbol,
            kernel_surface=adapter.get("kernel_surface"),
            free_symbol=adapter.get("free_symbol"),
            attach_symbol=adapter.get("attach_symbol"),
            runtime=adapter.get("name"),
            error="runtime probe returned empty status payload",
        )
    try:
        payload = json.loads(raw_json.decode("utf-8") if isinstance(raw_json, bytes) else str(raw_json))
    except Exception:
        return runtime_probe_payload(
            status="fault",
            artifact=loaded_path,
            manifest=adapter.get("runtime_manifest"),
            runtime_mode=None,
            abi=adapter.get("abi"),
            status_symbol=status_symbol,
            kernel_surface=adapter.get("kernel_surface"),
            free_symbol=adapter.get("free_symbol"),
            attach_symbol=adapter.get("attach_symbol"),
            runtime=adapter.get("name"),
            error="runtime probe returned invalid JSON",
        )
    return runtime_probe_payload(
        status=payload.get("status"),
        artifact=loaded_path,
        manifest=adapter.get("runtime_manifest"),
        runtime_mode=payload.get("mode"),
        abi=payload.get("abi") or adapter.get("abi"),
        status_symbol=status_symbol,
        kernel_surface=payload.get("kernel_surface") or adapter.get("kernel_surface"),
        free_symbol=payload.get("free_symbol") or adapter.get("free_symbol"),
        attach_symbol=payload.get("attach_symbol") or adapter.get("attach_symbol"),
        runtime=payload.get("runtime") or adapter.get("name"),
        version=payload.get("version"),
        queue_depth=payload.get("queue_depth"),
        module_count=payload.get("module_count"),
        updated_at_ms=payload.get("updated_at_ms"),
        capabilities=payload.get("capabilities"),
        module_states=payload.get("module_states"),
        last_command=payload.get("last_command"),
        error=payload.get("error") or "runtime probe fault",
    )


def attach_runtime_board_probe(
    adapter: dict[str, object],
    *,
    transport: str,
    port: str,
) -> dict[str, Any] | None:
    adapter_name = str(adapter.get("name") or "")
    if adapter_name != "c-serial-bridge":
        return None
    library, loaded_path = _load_library(_shared_library_candidates(adapter_name))
    if library is None or not loaded_path:
        return {
            "ok": False,
            "artifact": None,
            "transport": transport,
            "port": port,
            "error": "bridge library not built",
        }
    try:
        attach_symbol = getattr(library, "mira_bridge_attach_board")
    except AttributeError:
        return {
            "ok": False,
            "artifact": loaded_path,
            "transport": transport,
            "port": port,
            "error": "missing board attach symbol",
        }
    attach_symbol.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    attach_symbol.restype = ctypes.c_int
    result = attach_symbol(transport.encode("utf-8"), port.encode("utf-8"))
    return {
        "ok": result == 0,
        "artifact": loaded_path,
        "transport": transport,
        "port": port,
        "error": None if result == 0 else f"bridge attach failed with code {result}",
    }


def board_status_runtime_probe(
    adapter: dict[str, object],
    *,
    transport: str | None,
    port: str | None,
) -> dict[str, Any] | None:
    adapter_name = str(adapter.get("name") or "")
    if adapter_name != "c-serial-bridge":
        return None
    probe = probe_runtime_bridge(adapter)
    if probe is None:
        return None
    return {
        "ok": probe.get("health") == "ready",
        "health": probe.get("health"),
        "artifact": probe.get("artifact"),
        "transport": transport,
        "port": port,
        "runtime_mode": probe.get("runtime_mode"),
        "error": probe.get("last_error"),
    }
