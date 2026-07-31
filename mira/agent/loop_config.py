"""Construction config for :class:`mira.agent.loop.AgentLoop`."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mira.agent import model_presets as preset_helpers
from mira.agent.turn_delivery import TurnDeliveryFactory
from mira.bus.queue import MessageBus
from mira.bus.runtime_events import RuntimeEventBus
from mira.config.schema import ModelPresetConfig
from mira.execution_gate import ExecutionGate
from mira.providers.base import LLMProvider
from mira.providers.factory import ProviderSnapshot

if TYPE_CHECKING:
    from mira.agent.hook import AgentHook, AgentTurnHookFactory
    from mira.config.schema import ChannelsConfig, ProviderConfig, ToolsConfig
    from mira.cron.service import CronService
    from mira.session.manager import SessionManager


@dataclass(slots=True)
class AgentLoopConfig:
    """Construction parameters for the composition-kernel migration path."""

    bus: MessageBus
    provider: LLMProvider
    workspace: Path
    model: str | None = None
    max_iterations: int | None = None
    max_concurrent_subagents: int | None = None
    context_window_tokens: int | None = None
    context_block_limit: int | None = None
    max_tool_result_chars: int | None = None
    fail_on_tool_error: bool | None = None
    provider_retry_mode: str = "standard"
    tool_hint_max_length: int | None = None
    cron_service: CronService | None = None
    restrict_to_workspace: bool = False
    session_manager: SessionManager | None = None
    mcp_servers: dict[str, Any] | None = None
    channels_config: ChannelsConfig | None = None
    timezone: str | None = None
    session_ttl_minutes: int = 0
    consolidation_ratio: float = 0.5
    hooks: list[AgentHook] | None = None
    hook_factories: list[AgentTurnHookFactory] | None = None
    unified_session: bool = False
    disabled_skills: list[str] | None = None
    tools_config: ToolsConfig | None = None
    modules_config: Any | None = None
    security_config: Any | None = None
    image_generation_provider_config: ProviderConfig | None = None
    image_generation_provider_configs: dict[str, ProviderConfig] | None = None
    provider_snapshot_loader: Callable[..., ProviderSnapshot] | None = None
    provider_signature: tuple[object, ...] | None = None
    model_presets: dict[str, ModelPresetConfig] | None = None
    preset_catalog_loader: preset_helpers.PresetCatalogLoader | None = None
    model_preset: str | None = None
    preset_snapshot_loader: preset_helpers.PresetSnapshotLoader | None = None
    runtime_events: RuntimeEventBus | None = None
    turn_delivery_factory: TurnDeliveryFactory | None = None
    runtime_model_publisher: Callable[[str, str | None], None] | None = None
    restart_mode: str = "auto"
    local_trigger_store: Any | None = None
    idle_compact_check_interval_seconds: int = 0
    execution_gate: ExecutionGate | None = None

    def to_kwargs(self) -> dict[str, Any]:
        return {field.name: getattr(self, field.name) for field in dataclasses.fields(self)}


def agent_loop_config_from_legacy_kwargs(legacy: dict[str, Any]) -> AgentLoopConfig:
    """Normalize legacy ``AgentLoop(**kwargs)`` callers into one config object."""
    field_names = {field.name for field in dataclasses.fields(AgentLoopConfig)}
    unknown = sorted(set(legacy) - field_names)
    if unknown:
        raise TypeError(f"Unexpected AgentLoop argument(s): {', '.join(unknown)}")
    missing = [name for name in ("bus", "provider", "workspace") if name not in legacy]
    if missing:
        raise TypeError(f"Missing required AgentLoop argument(s): {', '.join(missing)}")
    return AgentLoopConfig(**legacy)


def agent_loop_config_from_legacy_args(
    args: tuple[Any, ...],
    legacy: dict[str, Any],
) -> AgentLoopConfig:
    """Normalize legacy positional/keyword construction into one config object."""
    positional_names = ("bus", "provider", "workspace")
    if len(args) > len(positional_names):
        raise TypeError(f"AgentLoop expected at most 3 positional arguments, got {len(args)}")
    for name, value in zip(positional_names, args, strict=False):
        if name in legacy:
            raise TypeError(f"AgentLoop got multiple values for argument '{name}'")
        legacy[name] = value
    return agent_loop_config_from_legacy_kwargs(legacy)


__all__ = [
    "AgentLoopConfig",
    "agent_loop_config_from_legacy_args",
    "agent_loop_config_from_legacy_kwargs",
]
