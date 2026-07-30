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
            name="virtual_context",
            display_name="Virtual Context",
            category="memory",
            status=_status("virtual_context", profile, configured),
            kind="memory",
            dependencies=("session_state",),
            memory_cost_mb=2,
            summary="Pages old turns into compact breadcrumbs instead of keeping every token live.",
        ),
        KernelModuleDescriptor(
            name="agent_roles",
            display_name="Agent Roles",
            category="execution",
            status=_status("agent_roles", profile, configured),
            kind="runtime",
            dependencies=("subagents",),
            memory_cost_mb=1,
            summary="Named subagent profiles such as implementer, reviewer, researcher, and doctor.",
        ),
        KernelModuleDescriptor(
            name="tool_middleware",
            display_name="Tool Middleware",
            category="safety",
            status=_status("tool_middleware", profile, configured),
            kind="runtime",
            dependencies=("approvals",),
            memory_cost_mb=1,
            summary="Before/after/error hooks around tool execution for policy and observability.",
        ),
        KernelModuleDescriptor(
            name="multimodal_contract",
            display_name="Multimodal Contract",
            category="io",
            status=_status("multimodal_contract", profile, configured),
            kind="runtime",
            memory_cost_mb=1,
            summary="Stable media part contract for images, files, audio, and future model routing.",
        ),
        KernelModuleDescriptor(
            name="workflow_dsl",
            display_name="Workflow DSL",
            category="workflow",
            status=_status("workflow_dsl", profile, configured),
            kind="runtime",
            lazy=True,
            enabled_by_default=False,
            dependencies=("subagents", "agent_roles"),
            memory_cost_mb=2,
            summary="Small declarative workflow contract; no visual-builder dependency.",
        ),
        KernelModuleDescriptor(
            name="computer_use",
            display_name="Computer Use",
            category="tool",
            status=_status("computer_use", profile, configured),
            kind="tool",
            lazy=True,
            enabled_by_default=False,
            dependencies=("workspace_controls", "approvals"),
            memory_cost_mb=6,
            summary="Optional desktop-control mount point for trusted local sessions.",
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
            name="external_runtime_ops",
            display_name="External Runtime Ops",
            category="runtime",
            status=_status("external_runtime_ops", profile, configured),
            kind="runtime",
            dependencies=("diagnostics",),
            memory_cost_mb=12,
            operator_actions=("inspect_modules", "inspect_faults"),
            summary="Operator-facing runtime bridge inspection for external runtimes.",
        ),
        KernelModuleDescriptor(
            name="bridge_lab",
            display_name="Bridge Lab",
            category="runtime",
            status=_status("bridge_lab", profile, configured),
            kind="runtime",
            dependencies=("external_runtime_ops",),
            memory_cost_mb=24,
            operator_actions=("restart_bridge", "inspect_faults"),
            summary="Runtime bridge validation surface for adapters and fault loops.",
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
