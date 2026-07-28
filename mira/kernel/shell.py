"""Shell-facing descriptors for a generic execution kernel.

The kernel should be reusable across many shells. Shell-specific customization
must stay declarative and thin so product surfaces can vary without mutating
core runtime behavior.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable

ShellMode = str
HOST_CONTRACT_SCHEMA = "mira.host/v1"
HOST_CONTRACT_VERSION = 1


def _host_contract(
    *,
    mode: str,
    show_sidebar_chrome: bool,
    show_search_dialog: bool,
    allow_utility_surface: bool,
    allow_execution_fork: bool,
    allow_workspace_controls: bool,
    allow_runtime_model_controls: bool,
    allow_kernel_console: bool,
    allow_privileged_runtime_controls: bool,
    allow_composer: bool,
    read_only_execution: bool,
    privilege_role: str,
    privilege_can_elevate: bool,
) -> dict[str, object]:
    return {
        "schema": HOST_CONTRACT_SCHEMA,
        "version": HOST_CONTRACT_VERSION,
        "mode": mode,
        "chrome": {
            "showSidebarChrome": show_sidebar_chrome,
            "showSearchDialog": show_search_dialog,
        },
        "surfaces": {
            "allowUtilitySurface": allow_utility_surface,
            "allowWorkspaceControls": allow_workspace_controls,
            "allowRuntimeModelControls": allow_runtime_model_controls,
            "allowKernelConsole": allow_kernel_console,
            "allowPrivilegedRuntimeControls": allow_privileged_runtime_controls,
        },
        "actions": {
            "allowExecutionFork": allow_execution_fork,
        },
        "composer": {
            "allowComposer": allow_composer,
            "readOnlyExecution": read_only_execution,
        },
        "privilege": {
            "role": privilege_role,
            "canElevate": privilege_can_elevate,
        },
    }


def _runtime_privilege() -> tuple[str, bool]:
    geteuid = getattr(os, "geteuid", None)
    if callable(geteuid):
        uid = int(geteuid())
        return ("root" if uid == 0 else "user", uid != 0)
    return ("user", False)


def _shell_metadata(**entries: str) -> dict[str, str]:
    return {
        "host_contract_schema": HOST_CONTRACT_SCHEMA,
        "host_contract_version": str(HOST_CONTRACT_VERSION),
        **entries,
    }


@dataclass(frozen=True, slots=True)
class ShellDescriptor:
    """Minimal shell contract layered on top of the execution kernel."""

    name: str = "mira-shell"
    display_name: str = "Mira"
    description: str = "General-purpose engineering shell for the Mira execution kernel."
    theme: str = "engineering"
    supports_threads: bool = True
    supports_file_activity: bool = True
    supports_approvals: bool = True
    supports_runtime_controls: bool = True
    host_contract: dict[str, object] = field(default_factory=dict)
    metadata: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "theme": self.theme,
            "supports_threads": self.supports_threads,
            "supports_file_activity": self.supports_file_activity,
            "supports_approvals": self.supports_approvals,
            "supports_runtime_controls": self.supports_runtime_controls,
            "host_contract": dict(self.host_contract),
            "metadata": dict(self.metadata),
        }


def default_engineering_shell() -> ShellDescriptor:
    """Default shell for a mature, generic execution layer."""
    privilege_role, privilege_can_elevate = _runtime_privilege()
    return ShellDescriptor(
        name="engineering-shell",
        host_contract=_host_contract(
            mode="engineering",
            show_sidebar_chrome=True,
            show_search_dialog=True,
            allow_utility_surface=True,
            allow_execution_fork=True,
            allow_workspace_controls=True,
            allow_runtime_model_controls=True,
            allow_kernel_console=True,
            allow_privileged_runtime_controls=True,
            allow_composer=True,
            read_only_execution=False,
            privilege_role=privilege_role,
            privilege_can_elevate=privilege_can_elevate,
        ),
        metadata=_shell_metadata(posture="engineering"),
    )


def single_execution_shell() -> ShellDescriptor:
    """Single-workbench shell without thread-management affordances."""
    privilege_role, privilege_can_elevate = _runtime_privilege()
    return ShellDescriptor(
        name="single-execution",
        display_name="Mira Workbench",
        description="Focused single-execution shell on top of the Mira execution kernel.",
        theme="workbench",
        supports_threads=False,
        supports_file_activity=True,
        supports_approvals=True,
        supports_runtime_controls=True,
        host_contract=_host_contract(
            mode="single-execution",
            show_sidebar_chrome=False,
            show_search_dialog=False,
            allow_utility_surface=False,
            allow_execution_fork=False,
            allow_workspace_controls=False,
            allow_runtime_model_controls=False,
            allow_kernel_console=True,
            allow_privileged_runtime_controls=True,
            allow_composer=True,
            read_only_execution=False,
            privilege_role=privilege_role,
            privilege_can_elevate=privilege_can_elevate,
        ),
        metadata=_shell_metadata(posture="single-execution"),
    )


def review_shell() -> ShellDescriptor:
    """Read-heavy review shell that suppresses runtime tuning during analysis."""
    privilege_role, privilege_can_elevate = _runtime_privilege()
    return ShellDescriptor(
        name="review",
        display_name="Mira Review",
        description="Review-oriented shell for code inspection, traces, and approvals.",
        theme="review",
        supports_threads=True,
        supports_file_activity=True,
        supports_approvals=True,
        supports_runtime_controls=False,
        host_contract=_host_contract(
            mode="review",
            show_sidebar_chrome=False,
            show_search_dialog=False,
            allow_utility_surface=True,
            allow_execution_fork=False,
            allow_workspace_controls=False,
            allow_runtime_model_controls=False,
            allow_kernel_console=True,
            allow_privileged_runtime_controls=False,
            allow_composer=False,
            read_only_execution=True,
            privilege_role=privilege_role,
            privilege_can_elevate=privilege_can_elevate,
        ),
        metadata=_shell_metadata(posture="review"),
    )


ShellFactory = Callable[[], ShellDescriptor]

_SHELL_FACTORIES: dict[str, ShellFactory] = {
    "engineering": default_engineering_shell,
    "single-execution": single_execution_shell,
    "review": review_shell,
}


def register_shell(name: str, factory: ShellFactory) -> None:
    """Register a shell factory under a stable name."""
    normalized = name.strip().lower()
    if not normalized:
        raise ValueError("shell name must not be empty")
    _SHELL_FACTORIES[normalized] = factory


def get_shell(name: str | None) -> ShellDescriptor:
    """Resolve a shell descriptor by name, defaulting to engineering."""
    normalized = (name or "engineering").strip().lower()
    factory = _SHELL_FACTORIES.get(normalized, default_engineering_shell)
    return factory()


def list_shells() -> list[dict[str, object]]:
    """List known shell descriptors for selection UIs and packaging."""
    items: list[dict[str, object]] = []
    for name in sorted(_SHELL_FACTORIES):
        descriptor = _SHELL_FACTORIES[name]()
        row = descriptor.to_dict()
        row["registry_name"] = name
        items.append(row)
    return items
