from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from mira.kernel.app import KernelApp, build_kernel_manifest
from mira.kernel.profile import lite_customer_profile
from mira.kernel.shell import default_engineering_shell, desktop_customer_shell

SNAPSHOT_DIR = Path(__file__).parent / "snapshots"


def _stable_json(value: dict[str, Any]) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def _assert_snapshot(name: str, value: dict[str, Any]) -> None:
    assert _stable_json(value) == (SNAPSHOT_DIR / name).read_text(encoding="utf-8")


def _normalize_privilege(contract: dict[str, Any]) -> dict[str, Any]:
    normalized = json.loads(json.dumps(contract))
    privilege = normalized.get("privilege")
    if isinstance(privilege, dict):
        normalized["privilege"] = {key: "<runtime>" for key in privilege}
    return normalized


def _normalize_shell_descriptor(descriptor: dict[str, Any]) -> dict[str, Any]:
    normalized = json.loads(json.dumps(descriptor))
    host_contract = normalized.get("host_contract")
    if isinstance(host_contract, dict):
        normalized["host_contract"] = _normalize_privilege(host_contract)
    return normalized


def test_kernel_manifest_v1_golden_snapshot() -> None:
    manifest = build_kernel_manifest(
        profile=lite_customer_profile(),
        shell=desktop_customer_shell(),
        runtime_capabilities={"restart_engine": True},
    )

    _assert_snapshot(
        "manifest_v1.json",
        {
            "contracts": manifest["contracts"],
            "identity": manifest["identity"],
            "capabilities": {
                key: manifest["capabilities"][key]
                for key in sorted(manifest["capabilities"])
            },
            "targets": manifest["targets"],
            "operator_action_ids": manifest["operator_console"]["actions"],
            "session_action_ids": [
                row["id"] for row in manifest["session_controls"]["actions"]
            ],
            "worker_action_ids": [
                row["id"] for row in manifest["worker_controls"]["actions"]
            ],
        },
    )


def test_host_contract_v1_golden_snapshot() -> None:
    _assert_snapshot(
        "host_contract_v1.json",
        _normalize_privilege(default_engineering_shell().host_contract),
    )


def test_desktop_shell_descriptor_v1_golden_snapshot() -> None:
    _assert_snapshot(
        "shell_descriptor_desktop_v1.json",
        _normalize_shell_descriptor(desktop_customer_shell().to_dict()),
    )


def test_kernel_runtime_snapshot_v1_golden_snapshot() -> None:
    app = KernelApp(
        SimpleNamespace(_loop=None),
        profile=lite_customer_profile(),
        shell=desktop_customer_shell(),
    )
    runtime = app.manifest_snapshot()

    _assert_snapshot(
        "kernel_runtime_snapshot_v1.json",
        {
            "contracts": runtime["contracts"],
            "runtime_adapters": [row["name"] for row in runtime["runtime_adapters"]],
            "runtime_bridges": [row["adapter"] for row in runtime["runtime_bridges"]],
            "runtime_modules": [row["name"] for row in runtime["runtime_modules"]],
            "runtime_control": {
                "active_adapter": runtime["runtime_control"]["active_adapter"],
                "execution_gate": runtime["runtime_control"]["execution_gate"]["state"],
                "module_focus": runtime["runtime_control"]["module_focus"],
            },
            "diagnostics": {
                "active_adapter": runtime["diagnostics"]["snapshot"]["active_adapter"],
                "dispatch_queue_state": runtime["diagnostics"]["snapshot"][
                    "dispatch_queue_state"
                ],
                "execution_gate": runtime["diagnostics"]["snapshot"]["execution_gate"],
                "module_count": runtime["diagnostics"]["snapshot"]["module_count"],
            },
            "event_actions": [row["action"] for row in runtime["event_log"]],
        },
    )
