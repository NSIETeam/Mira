"""Deployment profiles for a lightweight but mature customer-facing kernel.

The goal is not another orchestration layer. The goal is to make kernel shape
explicit so customer delivery can stay lean:

- choose a narrow capability set;
- keep GUI optional;
- keep long-running/runtime-heavy surfaces opt-in;
- describe the profile in one place for packaging and product decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class KernelProfile:
    """Named capability bundle for customer-facing deployments."""

    name: str
    description: str
    channels: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    features: tuple[str, ...] = ()
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
        gui_enabled=True,
        api_enabled=True,
        automations_enabled=True,
        memory_enabled=True,
    )
