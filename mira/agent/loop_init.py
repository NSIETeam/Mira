"""Initializer for AgentLoop's composed runtime objects."""

from __future__ import annotations

import asyncio
import os
import time
from typing import TYPE_CHECKING, Any

from loguru import logger

from mira.agent.build_turn import BuildTurnHandler
from mira.agent.command_turn import CommandTurnHandler
from mira.agent.context import ContextBuilder
from mira.agent.cron_turns import CronTurnCoordinator
from mira.agent.loop_config import AgentLoopConfig
from mira.agent.memory import Consolidator
from mira.agent.model_runtime import ModelRuntimeResolver
from mira.agent.process_lifecycle import TurnProcessLifecycle
from mira.agent.respond_turn import RespondTurnHandler
from mira.agent.run_turn import RunTurnHandler
from mira.agent.save_turn import SaveTurnHandler
from mira.agent.subagent import SubagentManager
from mira.agent.subsystems import create_agent_loop_subsystems
from mira.agent.turn_delivery import TurnDeliveryFactory
from mira.bus.events import InboundMessage
from mira.bus.runtime_events import RuntimeEventBus
from mira.command import CommandRouter, register_builtin_commands
from mira.config.schema import AgentDefaults, ToolsConfig
from mira.execution_gate import ExecutionGate
from mira.security.workspace_access import WorkspaceScopeResolver
from mira.session.manager import SessionManager
from mira.triggers.local_turns import LocalTriggerTurnCoordinator
from mira.utils.llm_runtime import LLMRuntime

if TYPE_CHECKING:
    from mira.agent.loop import AgentLoop
    from mira.agent.tools.mcp import MCPConnection
    from mira.runtime_context import RuntimeContextProvider


def initialize_agent_loop(loop: AgentLoop, config: AgentLoopConfig) -> None:
    """Populate an AgentLoop instance from its composition config."""
    from mira.agent import loop as loop_module

    bus = config.bus
    provider = config.provider
    workspace = config.workspace
    model = config.model
    max_iterations = config.max_iterations
    max_concurrent_subagents = config.max_concurrent_subagents
    context_window_tokens = config.context_window_tokens
    context_block_limit = config.context_block_limit
    max_tool_result_chars = config.max_tool_result_chars
    fail_on_tool_error = config.fail_on_tool_error
    provider_retry_mode = config.provider_retry_mode
    tool_hint_max_length = config.tool_hint_max_length
    cron_service = config.cron_service
    restrict_to_workspace = config.restrict_to_workspace
    session_manager = config.session_manager
    mcp_servers = config.mcp_servers
    channels_config = config.channels_config
    timezone = config.timezone
    session_ttl_minutes = config.session_ttl_minutes
    consolidation_ratio = config.consolidation_ratio
    hooks = config.hooks
    hook_factories = config.hook_factories
    unified_session = config.unified_session
    disabled_skills = config.disabled_skills
    tools_config = config.tools_config
    modules_config = config.modules_config
    security_config = config.security_config
    image_generation_provider_config = config.image_generation_provider_config
    image_generation_provider_configs = config.image_generation_provider_configs
    provider_snapshot_loader = config.provider_snapshot_loader
    provider_signature = config.provider_signature
    model_presets = config.model_presets
    preset_catalog_loader = config.preset_catalog_loader
    model_preset = config.model_preset
    preset_snapshot_loader = config.preset_snapshot_loader
    runtime_events = config.runtime_events
    turn_delivery_factory = config.turn_delivery_factory
    runtime_model_publisher = config.runtime_model_publisher
    restart_mode = config.restart_mode
    local_trigger_store = config.local_trigger_store
    idle_compact_check_interval_seconds = config.idle_compact_check_interval_seconds
    execution_gate = config.execution_gate
    _tc = tools_config or ToolsConfig()
    defaults = AgentDefaults()
    loop.bus = bus
    if turn_delivery_factory is not None:
        if turn_delivery_factory.bus is not bus:
            raise ValueError("turn delivery factory must use the agent message bus")
        if runtime_events is not None and turn_delivery_factory.runtime_events is not runtime_events:
            raise ValueError("turn delivery factory must use the agent runtime event bus")
        loop.turn_delivery_factory = turn_delivery_factory
        loop.runtime_events = turn_delivery_factory.runtime_events
    else:
        loop.runtime_events = runtime_events or RuntimeEventBus()
        loop.turn_delivery_factory = TurnDeliveryFactory(bus, loop.runtime_events)
    loop.runtime_event_publisher = loop.turn_delivery_factory.runtime_event_publisher
    loop.channels_config = channels_config
    loop.execution_gate = execution_gate or ExecutionGate()
    loop.restart_mode = restart_mode
    loop._runtime_model_publisher = runtime_model_publisher
    loop.workspace = workspace
    initial_model = model or provider.get_default_model()
    loop.max_iterations = (
        max_iterations if max_iterations is not None else defaults.max_tool_iterations
    )
    initial_context_window = (
        context_window_tokens if context_window_tokens is not None else defaults.context_window_tokens
    )
    configured_presets = model_presets or {}
    loop.runtime_resolver = ModelRuntimeResolver(
        LLMRuntime.capture(
            provider,
            initial_model,
            context_window_tokens=initial_context_window,
            snapshot_signature=provider_signature,
        ),
        model_presets=configured_presets,
        preset_catalog_loader=preset_catalog_loader,
        configured_default_preset=model_preset,
        provider_snapshot_loader=provider_snapshot_loader,
        preset_snapshot_loader=preset_snapshot_loader,
    )
    loop.context_block_limit = context_block_limit
    loop.max_tool_result_chars = (
        max_tool_result_chars if max_tool_result_chars is not None else defaults.max_tool_result_chars
    )
    loop.provider_retry_mode = provider_retry_mode
    loop.tool_hint_max_length = (
        tool_hint_max_length if tool_hint_max_length is not None else defaults.tool_hint_max_length
    )
    loop.tools_config = _tc
    loop.modules_config = modules_config
    loop.security_config = security_config
    loop.web_config = _tc.web
    loop.exec_config = _tc.exec
    loop._image_generation_provider_configs = dict(image_generation_provider_configs or {})
    if (
        image_generation_provider_config is not None
        and "openrouter" not in loop._image_generation_provider_configs
    ):
        loop._image_generation_provider_configs["openrouter"] = image_generation_provider_config
    loop.cron_service = cron_service
    loop.local_trigger_store = local_trigger_store
    loop.restrict_to_workspace = restrict_to_workspace
    loop.workspace_scopes = WorkspaceScopeResolver(
        default_workspace=workspace,
        default_restrict_to_workspace=restrict_to_workspace,
    )
    loop._start_time = time.time()
    loop._last_usage: dict[str, int] = {}
    loop._extra_hooks = hooks or []
    loop._hook_factories = hook_factories or []

    subsystems = create_agent_loop_subsystems(
        workspace=workspace,
        bus=bus,
        tools_config=_tc,
        max_tool_result_chars=loop.max_tool_result_chars,
        restrict_to_workspace=restrict_to_workspace,
        disabled_skills=disabled_skills,
        max_iterations=loop.max_iterations,
        max_concurrent_subagents=max_concurrent_subagents,
        fail_on_tool_error=fail_on_tool_error,
        execution_gate=loop.execution_gate,
        session_manager=session_manager,
        timezone=timezone,
        consolidation_ratio=consolidation_ratio,
        unified_session=unified_session,
        session_ttl_minutes=session_ttl_minutes,
        context_builder_cls=getattr(loop_module, "ContextBuilder", ContextBuilder),
        session_manager_cls=getattr(loop_module, "SessionManager", SessionManager),
        subagent_manager_cls=getattr(loop_module, "SubagentManager", SubagentManager),
        consolidator_cls=getattr(loop_module, "Consolidator", Consolidator),
    )
    loop.context = subsystems.context
    loop.sessions = subsystems.sessions
    loop.tools = subsystems.tools
    loop._file_state_store = subsystems.file_state_store
    loop._exec_session_manager = subsystems.exec_session_manager
    loop.runner = subsystems.runner
    loop.subagents = subsystems.subagents
    loop._virtual_context_manager = subsystems.virtual_context_manager
    loop.process_table = subsystems.process_table
    loop.turn_processes = TurnProcessLifecycle(
        sessions=loop.sessions,
        tools=loop.tools,
        process_table=loop.process_table,
        model_hint=lambda: loop.model_preset or loop.model,
        token_usage=lambda: loop._last_usage,
    )
    loop._unified_session = unified_session
    loop._running = False
    loop._mcp_servers = mcp_servers or {}
    loop._mcp_stacks: dict[str, MCPConnection] = {}
    loop._mcp_connecting = False
    loop._runtime_context_providers: list[RuntimeContextProvider] = []
    loop._active_tasks: dict[str, list[asyncio.Task[None]]] = {}
    loop._background_tasks: list[asyncio.Task[None]] = []
    loop._session_locks: dict[str, asyncio.Lock] = {}
    loop._pending_queues: dict[str, asyncio.Queue[InboundMessage]] = {}
    loop._deferred_automation_turns: dict[str, list[InboundMessage]] = {}
    loop._cron_turns = CronTurnCoordinator(
        publish_inbound=loop.bus.publish_inbound,
        dispatch=loop._dispatch,
        is_running=lambda: loop._running,
        deferred_queues=loop._deferred_automation_turns,
    )
    loop._local_trigger_turns = LocalTriggerTurnCoordinator(
        publish_inbound=loop.bus.publish_inbound,
        dispatch=loop._dispatch,
        is_running=lambda: loop._running,
        deferred_queues=loop._deferred_automation_turns,
    )
    loop._automation_turn_coordinators = (
        ("cron", loop._cron_turns),
        ("local trigger", loop._local_trigger_turns),
    )
    max_concurrent_requests = int(os.environ.get("mira_MAX_CONCURRENT_REQUESTS", "3"))
    loop._concurrency_gate = (
        asyncio.Semaphore(max_concurrent_requests) if max_concurrent_requests > 0 else None
    )
    loop.consolidator = subsystems.consolidator
    loop._memory_consolidators: dict[str, Consolidator] = {}
    loop.auto_compact = subsystems.auto_compact
    loop._idle_compact_check_interval_s = idle_compact_check_interval_seconds
    loop._next_idle_compact_check_at = time.monotonic()
    if model_preset:
        loop.set_model_preset(model_preset, publish_update=False)
    loop._register_default_tools(provider_snapshot_loader=provider_snapshot_loader)
    loop._runtime_vars: dict[str, Any] = {}
    loop._current_iteration = 0
    loop.commands = CommandRouter()
    register_builtin_commands(loop.commands)
    loop.command_turns = CommandTurnHandler(
        commands=loop.commands,
        loop=loop,
        persist_user_message=loop._persist_user_message_early,
        save_session=loop.sessions.save,
        clear_pending_user_turn=loop._clear_pending_user_turn,
    )
    loop.build_turns = BuildTurnHandler(loop)
    loop.run_turns = RunTurnHandler(loop)
    loop.save_turns = SaveTurnHandler(loop)
    loop.respond_turns = RespondTurnHandler(loop._assemble_outbound_for_context)
    try:
        from mira.kernel.app import register_kernel_loop

        register_kernel_loop(loop)
    except (ImportError, TypeError, ValueError, RuntimeError):
        logger.debug("kernel loop registration skipped", exc_info=True)
