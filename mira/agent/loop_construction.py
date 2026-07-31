"""Construction helpers for AgentLoop."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar, cast

from mira.agent import model_presets as preset_helpers
from mira.agent.tools.context import ToolContext
from mira.agent.tools.loader import ToolLoader
from mira.agent.tools.runtime_state import RuntimeState
from mira.agent.tools.self import MyTool
from mira.bus.queue import MessageBus
from mira.providers import factory as provider_factory
from mira.providers.factory import ProviderSnapshot
from mira.utils.logging import session_logger

LoopT = TypeVar("LoopT")


def agent_loop_from_config(
    loop_cls: type[LoopT],
    config: Any,
    bus: MessageBus | None = None,
    **extra: Any,
) -> LoopT:
    """Create an AgentLoop from config with the common parameter set."""
    if bus is None:
        bus = MessageBus()
    defaults = config.agents.defaults
    provider = extra.pop("provider", None) or provider_factory.make_provider(config)
    resolved = config.resolve_preset()
    model = extra.pop("model", None) or resolved.model
    context_window_tokens = extra.pop("context_window_tokens", None) or resolved.context_window_tokens
    provider_snapshot_loader = extra.pop("provider_snapshot_loader", None)
    preset_snapshot_loader = extra.pop(
        "preset_snapshot_loader",
        None,
    ) or preset_helpers.make_preset_snapshot_loader(
        config,
        provider_snapshot_loader,
    )
    return loop_cls(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        model=model,
        max_iterations=defaults.max_tool_iterations,
        max_concurrent_subagents=defaults.max_concurrent_subagents,
        context_window_tokens=context_window_tokens,
        context_block_limit=defaults.context_block_limit,
        max_tool_result_chars=defaults.max_tool_result_chars,
        fail_on_tool_error=defaults.fail_on_tool_error,
        provider_retry_mode=defaults.provider_retry_mode,
        tool_hint_max_length=defaults.tool_hint_max_length,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        mcp_servers=config.tools.mcp_servers,
        channels_config=config.channels,
        timezone=defaults.timezone,
        unified_session=defaults.unified_session,
        disabled_skills=defaults.disabled_skills,
        session_ttl_minutes=defaults.session_ttl_minutes,
        idle_compact_check_interval_seconds=defaults.idle_compact_check_interval_seconds,
        consolidation_ratio=defaults.consolidation_ratio,
        tools_config=config.tools,
        modules_config=config.modules,
        security_config=config.security,
        model_presets=preset_helpers.configured_model_presets(config),
        model_preset=defaults.model_preset,
        restart_mode=config.gateway.restart_mode,
        provider_snapshot_loader=provider_snapshot_loader,
        preset_snapshot_loader=preset_snapshot_loader,
        **extra,
    )


def register_default_tools(
    loop: Any,
    *,
    provider_snapshot_loader: Callable[..., ProviderSnapshot] | None,
) -> None:
    """Register the default set of tools via plugin loader."""
    ctx = ToolContext(
        config=loop.tools_config,
        modules=loop.modules_config,
        workspace=str(loop.workspace),
        bus=loop.bus,
        subagent_manager=loop.subagents,
        cron_service=loop.cron_service,
        exec_session_manager=loop._exec_session_manager,
        sessions=loop.sessions,
        provider_snapshot_loader=provider_snapshot_loader,
        image_generation_provider_configs=loop._image_generation_provider_configs,
        timezone=loop.context.timezone or "UTC",
        workspace_sandbox=loop.workspace_scopes.sandbox_status,
        runtime_events=loop.runtime_events,
    )
    loader = ToolLoader()
    registered = loader.load(ctx, loop.tools)

    # MyTool needs runtime state reference, so it is wired manually.
    if loop.tools_config.my.enable:
        loop.tools.register(
            MyTool(
                runtime_state=cast(RuntimeState, loop),
                modify_allowed=loop.tools_config.my.allow_set,
            )
        )
        registered.append("my")

    for name in list(loop.tools.tool_names):
        if not loop._module_enabled(name, default=True):
            loop.tools.unregister(name)
            if name in registered:
                registered.remove(name)

    session_logger(None).info("Registered {} tools: {}", len(registered), registered)
