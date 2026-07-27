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
    operator_actions: tuple[str, ...] = ()
    summary: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "category": self.category,
            "status": self.status,
            "operator_actions": list(self.operator_actions),
            "summary": self.summary,
        }


def list_kernel_modules(profile: KernelProfile) -> list[dict[str, object]]:
    feature_set = set(profile.features)
    rows: list[KernelModuleDescriptor] = [
        KernelModuleDescriptor(
            name="session_state",
            display_name="Session State",
            category="core",
            status="enabled" if "session_state" in feature_set else "disabled",
            operator_actions=("inspect_modules",),
            summary="Tracks execution sessions, active turns, and persisted thread state.",
        ),
        KernelModuleDescriptor(
            name="approvals",
            display_name="Approvals",
            category="safety",
            status="enabled" if "approvals" in feature_set else "disabled",
            operator_actions=("inspect_faults",),
            summary="Operator approval boundary for actions that require confirmation.",
        ),
        KernelModuleDescriptor(
            name="automations",
            display_name="Automations",
            category="workflow",
            status="enabled" if "automations" in feature_set else "disabled",
            operator_actions=("open_kernel_settings",),
            summary="Scheduled and long-running execution workflows.",
        ),
        KernelModuleDescriptor(
            name="diagnostics",
            display_name="Diagnostics",
            category="observability",
            status="enabled" if "diagnostics" in feature_set else "disabled",
            operator_actions=("inspect_faults", "open_kernel_settings"),
            summary="Runtime health, operator debug signals, and diagnostic surfacing.",
        ),
        KernelModuleDescriptor(
            name="subagents",
            display_name="Subagents",
            category="execution",
            status="enabled" if "subagents" in feature_set else "disabled",
            operator_actions=("inspect_modules", "restart_runtime"),
            summary="Delegated execution workers for parallel or specialized tasks.",
        ),
        KernelModuleDescriptor(
            name="workspace_controls",
            display_name="Workspace Controls",
            category="io",
            status="enabled" if "workspace_controls" in feature_set else "disabled",
            operator_actions=("open_kernel_settings",),
            summary="Project scope, access posture, and workspace attachment controls.",
        ),
        KernelModuleDescriptor(
            name="embedded_ops",
            display_name="Embedded Ops",
            category="embedded",
            status="enabled" if "embedded_ops" in feature_set else "disabled",
            operator_actions=("attach_board", "inspect_modules"),
            summary="Operator-facing embedded control loops for constrained runtimes.",
        ),
        KernelModuleDescriptor(
            name="firmware_lab",
            display_name="Firmware Lab",
            category="embedded",
            status="enabled" if "firmware_lab" in feature_set else "disabled",
            operator_actions=("attach_board", "inspect_faults"),
            summary="Firmware experiment surface for boards, bridges, and validation loops.",
        ),
    ]
    return [row.to_dict() for row in rows]
