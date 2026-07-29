"""Deployment profiles for a lightweight but mature customer-facing kernel.

The goal is not another orchestration layer. The goal is to make kernel shape
explicit so customer delivery can stay lean:

- choose a narrow capability set;
- keep GUI optional;
- keep long-running/runtime-heavy surfaces opt-in;
- describe the profile in one place for packaging and product decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True, slots=True)
class KernelProfile:
    """Named capability bundle for customer-facing deployments."""

    name: str
    description: str
    channels: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    features: tuple[str, ...] = ()
    runtime_targets: tuple[str, ...] = ()
    implementation_languages: tuple[str, ...] = ()
    gui_enabled: bool = True
    api_enabled: bool = False
    automations_enabled: bool = False
    memory_enabled: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "channels": list(self.channels),
            "tools": list(self.tools),
            "features": list(self.features),
            "runtime_targets": list(self.runtime_targets),
            "implementation_languages": list(self.implementation_languages),
            "gui_enabled": self.gui_enabled,
            "api_enabled": self.api_enabled,
            "automations_enabled": self.automations_enabled,
            "memory_enabled": self.memory_enabled,
        }


def lite_customer_profile() -> KernelProfile:
    """Smallest mature profile suitable for customized client delivery."""
    return KernelProfile(
        name="lite-customer",
        description=(
            "Lean customer kernel with core chat, file, shell, approval, and session memory."
        ),
        channels=("webui", "cli"),
        tools=("filesystem", "shell", "apply_patch", "search"),
        features=("session_state", "approvals", "event_stream"),
        runtime_targets=("desktop",),
        implementation_languages=("python",),
        gui_enabled=True,
        api_enabled=False,
        automations_enabled=False,
        memory_enabled=True,
    )


def desktop_customer_profile() -> KernelProfile:
    """Balanced profile for desktop delivery with GUI and diagnostics."""
    return KernelProfile(
        name="desktop-customer",
        description="Desktop-oriented kernel profile with GUI, logs, and runtime controls.",
        channels=("webui", "cli"),
        tools=("filesystem", "shell", "apply_patch", "search", "self"),
        features=("session_state", "approvals", "event_stream", "diagnostics"),
        runtime_targets=("desktop", "workstation"),
        implementation_languages=("python",),
        gui_enabled=True,
        api_enabled=False,
        automations_enabled=False,
        memory_enabled=True,
    )


def automation_customer_profile() -> KernelProfile:
    """Extended profile when the client needs scheduled or background workflows."""
    return KernelProfile(
        name="automation-customer",
        description="Customer kernel with automations enabled for long-running workflows.",
        channels=("webui", "cli", "websocket"),
        tools=("filesystem", "shell", "apply_patch", "search", "cron"),
        features=("session_state", "approvals", "event_stream", "automations"),
        runtime_targets=("desktop", "server"),
        implementation_languages=("python",),
        gui_enabled=True,
        api_enabled=True,
        automations_enabled=True,
        memory_enabled=True,
    )


def mira_studio_profile() -> KernelProfile:
    """Otto-grade engineering profile for Mira-branded execution."""
    return KernelProfile(
        name="mira-studio",
        description=(
            "Mira studio profile with desktop orchestration, diagnostics, automation, "
            "CLI app integration, and supervised subagent workflows."
        ),
        channels=("webui", "cli", "websocket"),
        tools=(
            "filesystem",
            "shell",
            "apply_patch",
            "search",
            "self",
            "cron",
            "cli_apps",
            "spawn",
        ),
        features=(
            "session_state",
            "approvals",
            "event_stream",
            "diagnostics",
            "automations",
            "subagents",
            "virtual_context",
            "agent_roles",
            "tool_middleware",
            "multimodal_contract",
            "workspace_controls",
            "cli_apps",
        ),
        runtime_targets=("desktop", "server", "operator-console"),
        implementation_languages=("python", "rust"),
        gui_enabled=True,
        api_enabled=True,
        automations_enabled=True,
        memory_enabled=True,
    )


def mira_embedded_lab_profile() -> KernelProfile:
    """Experimental profile for embedded-control and firmware-adjacent runtimes."""
    return KernelProfile(
        name="mira-embedded-lab",
        description=(
            "Experimental Mira profile for constrained runtimes, diagnostics, automation "
            "pipelines, and operator-supervised embedded control loops."
        ),
        channels=("webui", "cli", "websocket"),
        tools=(
            "filesystem",
            "shell",
            "apply_patch",
            "search",
            "self",
            "spawn",
        ),
        features=(
            "session_state",
            "approvals",
            "event_stream",
            "diagnostics",
            "subagents",
            "workspace_controls",
            "embedded_ops",
            "firmware_lab",
        ),
        runtime_targets=("embedded-lab", "operator-console", "firmware-control"),
        implementation_languages=("rust", "c", "python"),
        gui_enabled=True,
        api_enabled=True,
        automations_enabled=True,
        memory_enabled=True,
    )


KernelProfileFactory = Callable[[], KernelProfile]

_PROFILE_FACTORIES: dict[str, KernelProfileFactory] = {
    "lite-customer": lite_customer_profile,
    "desktop-customer": desktop_customer_profile,
    "automation-customer": automation_customer_profile,
    "mira-studio": mira_studio_profile,
    "mira-embedded-lab": mira_embedded_lab_profile,
}


def get_profile(name: str | None) -> KernelProfile:
    registry_name = (name or "mira-studio").strip() or "mira-studio"
    try:
        return _PROFILE_FACTORIES[registry_name]()
    except KeyError as exc:
        raise KeyError(f"unknown kernel profile: {registry_name}") from exc


def list_profiles() -> list[dict[str, object]]:
    profiles: list[dict[str, object]] = []
    for registry_name, factory in _PROFILE_FACTORIES.items():
        profile = factory()
        item = profile.to_dict()
        item["registry_name"] = registry_name
        profiles.append(item)
    return profiles


def register_profile(name: str, factory: KernelProfileFactory) -> None:
    registry_name = name.strip()
    if not registry_name:
        raise ValueError("profile registry name must not be empty")
    _PROFILE_FACTORIES[registry_name] = factory
