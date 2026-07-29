"""Kernel module registry for Mira operator surfaces.

This keeps execution features visible as operator-facing modules rather than a
flat feature string list. The console can then inspect modules the way a
kernel operator would inspect subsystems.
"""

from __future__ import annotations

from dataclasses import dataclass

from .profile import KernelProfile


@dataclass(frozen=True, slots=True)
class KernelModuleDescriptor:
    name: str
    display_name: str
    category: str
    status: str
    kind: str = "core"
    lazy: bool = True
    enabled_by_default: bool = True
    memory_cost_mb: int = 0
    dependencies: tuple[str, ...] = ()
    operator_actions: tuple[str, ...] = ()
    summary: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "category": self.category,
            "status": self.status,
            "kind": self.kind,
            "lazy": self.lazy,
            "enabled_by_default": self.enabled_by_default,
            "memory_cost_mb": self.memory_cost_mb,
            "dependencies": list(self.dependencies),
            "operator_actions": list(self.operator_actions),
            "summary": self.summary,
        }


def _status(name: str, profile: KernelProfile, configured: object | None = None) -> str:
    enabled = name in set(profile.features) or name in set(profile.tools) or name in set(profile.channels)
    registry = getattr(configured, "registry", {}) if configured is not None else {}
    module_cfg = registry.get(name) if isinstance(registry, dict) else None
    if module_cfg is not None:
        enabled = bool(getattr(module_cfg, "enabled", enabled))
    elif configured is not None and callable(getattr(configured, "is_enabled", None)):
        enabled = bool(configured.is_enabled(name, default=enabled))
    return "enabled" if enabled else "disabled"


def list_kernel_modules(
    profile: KernelProfile,
    configured: object | None = None,
) -> list[dict[str, object]]:
    rows: list[KernelModuleDescriptor] = [
        KernelModuleDescriptor(
            name="session_state",
            display_name="Session State",
            category="core",
            status=_status("session_state", profile, configured),
            kind="core",
            lazy=False,
            memory_cost_mb=4,
            operator_actions=("inspect_modules",),
            summary="Tracks execution sessions, active turns, and persisted thread state.",
        ),
        KernelModuleDescriptor(
            name="approvals",
            display_name="Approvals",
            category="safety",
            status=_status("approvals", profile, configured),
            kind="core",
            lazy=False,
            memory_cost_mb=1,
            operator_actions=("inspect_faults",),
            summary="Operator approval boundary for actions that require confirmation.",
        ),
        KernelModuleDescriptor(
            name="automations",
            display_name="Automations",
            category="workflow",
            status=_status("automations", profile, configured),
            kind="runtime",
            dependencies=("session_state",),
            memory_cost_mb=8,
            operator_actions=("open_kernel_settings",),
            summary="Scheduled and long-running execution workflows.",
        ),
        KernelModuleDescriptor(
            name="diagnostics",
            display_name="Diagnostics",
            category="observability",
            status=_status("diagnostics", profile, configured),
            kind="diagnostic",
            memory_cost_mb=3,
            operator_actions=("inspect_faults", "open_kernel_settings"),
            summary="Runtime health, operator debug signals, and diagnostic surfacing.",
        ),
        KernelModuleDescriptor(
            name="subagents",
            display_name="Subagents",
            category="execution",
            status=_status("subagents", profile, configured),
            kind="runtime",
            dependencies=("session_state",),
            memory_cost_mb=32,
            operator_actions=("inspect_modules", "restart_runtime"),
            summary="Delegated execution workers for parallel or specialized tasks.",
        ),
        KernelModuleDescriptor(
            name="workspace_controls",
            display_name="Workspace Controls",
            category="io",
            status=_status("workspace_controls", profile, configured),
            kind="core",
            lazy=False,
            memory_cost_mb=2,
            operator_actions=("open_kernel_settings",),
            summary="Project scope, access posture, and workspace attachment controls.",
        ),
        KernelModuleDescriptor(
            name="embedded_ops",
            display_name="Embedded Ops",
            category="embedded",
            status=_status("embedded_ops", profile, configured),
            kind="runtime",
            dependencies=("diagnostics",),
            memory_cost_mb=12,
            operator_actions=("attach_board", "inspect_modules"),
            summary="Operator-facing embedded control loops for constrained runtimes.",
        ),
        KernelModuleDescriptor(
            name="firmware_lab",
            display_name="Firmware Lab",
            category="embedded",
            status=_status("firmware_lab", profile, configured),
            kind="runtime",
            dependencies=("embedded_ops",),
            memory_cost_mb=24,
            operator_actions=("attach_board", "inspect_faults"),
            summary="Firmware experiment surface for boards, bridges, and validation loops.",
        ),
    ]
    for name in sorted(set(profile.channels)):
        rows.append(KernelModuleDescriptor(
            name=name,
            display_name=name.replace("_", " ").title(),
            category="channel",
            status=_status(name, profile, configured),
            kind="channel",
            memory_cost_mb=6,
            summary="Lazy-loadable chat or WebUI ingress module.",
        ))
    for name in sorted(set(profile.tools)):
        rows.append(KernelModuleDescriptor(
            name=name,
            display_name=name.replace("_", " ").title(),
            category="tool",
            status=_status(name, profile, configured),
            kind="tool",
            memory_cost_mb=4 if name != "shell" else 10,
            dependencies=("workspace_controls",) if name in {"filesystem", "shell", "apply_patch"} else (),
            summary="Lazy-loadable agent tool module.",
        ))
    return [row.to_dict() for row in rows]


def module_summary(profile: KernelProfile, configured: object | None = None) -> dict[str, object]:
    rows = list_kernel_modules(profile, configured)
    enabled = [row for row in rows if row["status"] == "enabled"]
    return {
        "profile": profile.name,
        "total": len(rows),
        "enabled": len(enabled),
        "lazy": sum(1 for row in enabled if row.get("lazy")),
        "estimated_memory_cost_mb": sum(int(row.get("memory_cost_mb") or 0) for row in enabled),
        "modules": rows,
    }
