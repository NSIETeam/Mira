"""Runtime adapter registry for Mira execution targets.

The Python agent loop remains the default implementation today, but the kernel
should expose a stable adapter contract so other runtimes can be attached over
time: Rust workers, C/firmware bridges, serial targets, and board-level
operator loops.
"""

from __future__ import annotations

from dataclasses import dataclass

from .paths import KERNEL_PROJECT_ROOT


def _runtime_manifest_exists(path: str | None) -> bool:
    if not path:
        return False
    return (KERNEL_PROJECT_ROOT / path).exists()


def _runtime_stage(manifest_path: str | None, bootstrap_artifact: str | None) -> str:
    if _runtime_manifest_exists(manifest_path):
        return "manifested"
    if bootstrap_artifact and (KERNEL_PROJECT_ROOT / bootstrap_artifact).exists():
        return "skeleton"
    return "planned"


@dataclass(frozen=True, slots=True)
class RuntimeAdapterDescriptor:
    name: str
    display_name: str
    implementation_language: str
    transport: str
    target_class: str
    maturity: str = "experimental"
    capabilities: tuple[str, ...] = ()
    operator_actions: tuple[str, ...] = ()
    notes: str = ""
    enabled_by_default: bool = False
    runtime_root: str | None = None
    bootstrap_artifact: str | None = None
    runtime_manifest: str | None = None
    abi: str | None = None
    status_symbol: str | None = None
    runtime_stage: str = "planned"
    build_hint: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "implementation_language": self.implementation_language,
            "transport": self.transport,
            "target_class": self.target_class,
            "maturity": self.maturity,
            "capabilities": list(self.capabilities),
            "operator_actions": list(self.operator_actions),
            "notes": self.notes,
            "enabled_by_default": self.enabled_by_default,
            "runtime_root": self.runtime_root,
            "bootstrap_artifact": self.bootstrap_artifact,
            "runtime_manifest": self.runtime_manifest,
            "abi": self.abi,
            "status_symbol": self.status_symbol,
            "runtime_stage": self.runtime_stage,
            "build_hint": self.build_hint,
        }


def list_runtime_adapters() -> list[dict[str, object]]:
    return [
        RuntimeAdapterDescriptor(
            name="python-inprocess",
            display_name="Python In-Process",
            implementation_language="python",
            transport="in_process",
            target_class="desktop",
            maturity="stable",
            capabilities=(
                "task_exec",
                "fault_stream",
                "workspace_sync",
                "diagnostics",
            ),
            operator_actions=(
                "restart_runtime",
                "restart_bridge",
                "open_kernel_settings",
                "inspect_faults",
            ),
            notes="Default Mira runtime hosted inside the current process.",
            enabled_by_default=True,
            runtime_root="mira",
            bootstrap_artifact="mira/agent/loop.py",
            runtime_manifest="mira/kernel/runtime-python.json",
            abi="python",
            status_symbol="kernel.describe",
            runtime_stage=_runtime_stage(
                "mira/kernel/runtime-python.json",
                "mira/agent/loop.py",
            ),
            build_hint="Built into the current Python process; no separate compilation step.",
        ).to_dict(),
        RuntimeAdapterDescriptor(
            name="rust-ffi",
            display_name="Rust FFI Worker",
            implementation_language="rust",
            transport="ffi",
            target_class="operator-console",
            maturity="planned",
            capabilities=(
                "task_exec",
                "fault_stream",
                "module_state",
                "diagnostics",
                "hot_swap_ready",
            ),
            operator_actions=(
                "switch_adapter",
                "restart_bridge",
                "restart_runtime",
                "inspect_modules",
            ),
            notes="Native worker boundary with a stable C ABI for low-latency execution.",
            runtime_root="runtimes/mira-rust",
            bootstrap_artifact="runtimes/mira-rust/src/lib.rs",
            runtime_manifest="runtimes/mira-rust/runtime.json",
            abi="c",
            status_symbol="mira_runtime_status_json",
            runtime_stage=_runtime_stage(
                "runtimes/mira-rust/runtime.json",
                "runtimes/mira-rust/src/lib.rs",
            ),
            build_hint="cd runtimes/mira-rust && cargo build --release",
        ).to_dict(),
        RuntimeAdapterDescriptor(
            name="c-serial-bridge",
            display_name="C Serial Bridge",
            implementation_language="c",
            transport="serial",
            target_class="firmware-control",
            maturity="planned",
            capabilities=(
                "fault_stream",
                "module_state",
                "diagnostics",
                "board_io",
                "firmware_bridge",
            ),
            operator_actions=(
                "attach_board",
                "restart_bridge",
                "inspect_modules",
                "inspect_faults",
            ),
            notes="MCU-facing control loop skeleton for serial and board-side operations.",
            runtime_root="runtimes/mira-c",
            bootstrap_artifact="runtimes/mira-c/src/mira_bridge.c",
            runtime_manifest="runtimes/mira-c/runtime.json",
            abi="c",
            status_symbol="mira_bridge_status_json",
            runtime_stage=_runtime_stage(
                "runtimes/mira-c/runtime.json",
                "runtimes/mira-c/src/mira_bridge.c",
            ),
            build_hint="Compile as a shared bridge or firmware-side stub with the supplied header.",
        ).to_dict(),
    ]
