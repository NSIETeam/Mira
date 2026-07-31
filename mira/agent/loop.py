"""Agent loop: the core processing engine."""

from __future__ import annotations

import asyncio
import dataclasses
import time
from collections.abc import Awaitable, Callable, Coroutine, Mapping
from contextlib import AbstractContextManager, ExitStack, suppress
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from loguru import logger

from mira.agent import context as agent_context
from mira.agent import model_presets as preset_helpers
from mira.agent.automation_turns import publish_next_deferred_turn
from mira.agent.context import ContextBuilder
from mira.agent.dispatch_turn import dispatch_inbound_turn
from mira.agent.hook import AgentHook, AgentTurnHookFactory
from mira.agent.loop_config import AgentLoopConfig, agent_loop_config_from_legacy_args
from mira.agent.loop_init import initialize_agent_loop
from mira.agent.memory import Consolidator, MemoryStore
from mira.agent.pending_injections import PendingInjectionDrainer
from mira.agent.process_message import process_inbound_message
from mira.agent.runner import _MAX_INJECTIONS_PER_TURN, AgentRunSpec
from mira.agent.subagent import SubagentManager
from mira.agent.tools.context import RequestContext, bind_request_context, reset_request_context
from mira.agent.tools.file_state import bind_file_states, reset_file_states
from mira.agent.tools.message import MessageTool
from mira.agent.tools.registry import ToolRegistry
from mira.agent.tools.runtime_state import RuntimeState
from mira.agent.tools.self import MyTool
from mira.agent.turn_context import (
    TurnContext,
    TurnKind,
    TurnState,
)
from mira.agent.turn_delivery import (
    TurnDelivery,
)
from mira.agent.turn_delivery import TurnRoute as TurnRoute
from mira.agent.turn_hooks import AgentTurnHookSpec, build_agent_turn_hook
from mira.agent.turn_persistence import (
    persist_subagent_followup,
    sanitize_persisted_blocks,
    save_turn_messages,
)
from mira.agent.turn_security import (
    capability_policy_for_metadata,
    policy_for_metadata,
    record_capability_audit_event,
    tools_for_metadata,
)
from mira.bus.events import InboundMessage, OutboundMessage
from mira.bus.outbound_events import StreamedResponseEvent
from mira.bus.queue import MessageBus
from mira.bus.runtime_events import (
    RuntimeEventPublisher,
    ensure_runtime_event_publisher,
)
from mira.command import CommandContext
from mira.config.schema import ModelPresetConfig
from mira.providers.base import LLMProvider
from mira.providers.factory import ProviderSnapshot
from mira.runtime_context import (
    RUNTIME_CONTEXT_HISTORY_META,
    RuntimeContextBlock,
    RuntimeContextProvider,
    append_runtime_context,
    resolve_runtime_context,
    runtime_context_blocks_from_metadata,
)
from mira.security.workspace_access import (
    bind_workspace_scope,
    reset_workspace_scope,
)
from mira.session import turn_continuation
from mira.session.automation_turns import automation_history_overrides
from mira.session.goal_state import (
    goal_state_runtime_lines,
    runner_wall_llm_timeout_s,
    sustained_goal_active,
)
from mira.session.keys import UNIFIED_SESSION_KEY, remember_last_channel
from mira.session.manager import Session, SessionManager
from mira.session.model_selection import (
    SESSION_MODEL_PRESET_METADATA_KEY,
    model_preset_from_metadata,
)
from mira.session.recovery import (
    PENDING_USER_TURN_KEY,
    RUNTIME_CHECKPOINT_KEY,
    restore_pending_user_turn,
    restore_runtime_checkpoint,
)
from mira.utils.cancellation import task_is_cancelling
from mira.utils.document import extract_documents, reference_non_image_attachments
from mira.utils.llm_runtime import LLMRuntime
from mira.utils.logging import session_logger, turn_logger
from mira.webui.users import (
    WEBUI_GROUP_METADATA_KEY,
    WEBUI_MEMORY_WORKSPACE_METADATA_KEY,
    WEBUI_USER_METADATA_KEY,
)

_LEGACY_PATCH_TARGETS = (ContextBuilder, SessionManager, SubagentManager, Consolidator)

if TYPE_CHECKING:
    from mira.agent.autocompact import AutoCompact
    from mira.agent.build_turn import BuildTurnHandler
    from mira.agent.command_turn import CommandTurnHandler
    from mira.agent.cron_turns import CronTurnCoordinator
    from mira.agent.maturity import VirtualContextManager
    from mira.agent.model_runtime import ModelRuntimeResolver
    from mira.agent.process_lifecycle import TurnProcessLifecycle
    from mira.agent.respond_turn import RespondTurnHandler
    from mira.agent.run_turn import RunTurnHandler
    from mira.agent.save_turn import SaveTurnHandler
    from mira.agent.tools.exec_session import ExecSessionManager
    from mira.agent.tools.file_state import FileStateStore
    from mira.agent.turn_delivery import TurnDeliveryFactory
    from mira.bus.runtime_events import RuntimeEventBus
    from mira.command import CommandRouter
    from mira.config.schema import (
        ChannelsConfig,
        ModulesConfig,
        SecurityConfig,
        ToolsConfig,
    )
    from mira.execution_gate import ExecutionGate
    from mira.security.workspace_access import WorkspaceScopeResolver
    from mira.triggers.local_turns import LocalTriggerTurnCoordinator


def _ctx_logger(ctx: TurnContext) -> Any:
    return turn_logger(ctx.session_key, ctx.turn_id)


def _ctx_session(ctx: TurnContext) -> Session:
    if ctx.session is None:
        raise RuntimeError("Turn session is not available")
    return ctx.session


def _ctx_runtime(ctx: TurnContext) -> LLMRuntime:
    if ctx.runtime is None:
        raise RuntimeError("Turn runtime is not available")
    return ctx.runtime


class AgentLoop:
    """
    The agent loop is the core processing engine.

    It:
    1. Receives messages from the bus
    2. Builds context with history, memory, skills
    3. Calls the LLM
    4. Executes tool calls
    5. Sends responses back
    """

    bus: MessageBus
    loop_config: AgentLoopConfig
    turn_delivery_factory: TurnDeliveryFactory
    runtime_events: RuntimeEventBus
    runtime_event_publisher: RuntimeEventPublisher
    channels_config: ChannelsConfig | None
    execution_gate: ExecutionGate
    restart_mode: str
    workspace: Path
    max_iterations: int
    runtime_resolver: ModelRuntimeResolver
    context_block_limit: int | None
    max_tool_result_chars: int
    provider_retry_mode: str
    tool_hint_max_length: int
    tools_config: ToolsConfig
    modules_config: ModulesConfig | None
    security_config: SecurityConfig | None
    web_config: Any
    exec_config: Any
    cron_service: Any | None
    local_trigger_store: Any | None
    restrict_to_workspace: bool
    workspace_scopes: WorkspaceScopeResolver
    context: ContextBuilder
    sessions: SessionManager
    tools: ToolRegistry
    runner: Any
    subagents: SubagentManager
    process_table: Any
    turn_processes: TurnProcessLifecycle
    consolidator: Consolidator
    auto_compact: AutoCompact
    commands: CommandRouter
    command_turns: CommandTurnHandler
    build_turns: BuildTurnHandler
    run_turns: RunTurnHandler
    save_turns: SaveTurnHandler
    respond_turns: RespondTurnHandler
    _runtime_model_publisher: Callable[[str, str | None], None] | None
    _image_generation_provider_configs: dict[str, Any]
    _start_time: float
    _last_usage: dict[str, int]
    _extra_hooks: list[AgentHook]
    _hook_factories: list[AgentTurnHookFactory]
    _file_state_store: FileStateStore
    _exec_session_manager: ExecSessionManager
    _virtual_context_manager: VirtualContextManager
    _unified_session: bool
    _running: bool
    _mcp_servers: Mapping[str, Any]
    _mcp_stacks: dict[str, Any]
    _mcp_connecting: bool
    _runtime_context_providers: list[RuntimeContextProvider]
    _active_tasks: dict[str, list[asyncio.Task[None]]]
    _background_tasks: list[asyncio.Task[None]]
    _session_locks: dict[str, asyncio.Lock]
    _pending_queues: dict[str, asyncio.Queue[InboundMessage]]
    _deferred_automation_turns: dict[str, list[InboundMessage]]
    _cron_turns: CronTurnCoordinator
    _local_trigger_turns: LocalTriggerTurnCoordinator
    _automation_turn_coordinators: tuple[tuple[str, Any], tuple[str, Any]]
    _concurrency_gate: asyncio.Semaphore | None
    _memory_consolidators: dict[str, Consolidator]
    _idle_compact_check_interval_s: float
    _next_idle_compact_check_at: float
    _runtime_vars: dict[str, Any]
    _current_iteration: int

    @property
    def current_iteration(self) -> int:
        return self._current_iteration

    @property
    def tool_names(self) -> list[str]:
        return self.tools.tool_names

    @property
    def provider(self) -> LLMProvider:
        """Provider selected for future turn admissions."""
        return self.runtime_resolver.runtime.provider

    @property
    def model(self) -> str:
        """Model selected for future turn admissions."""
        return self.runtime_resolver.runtime.model

    @property
    def context_window_tokens(self) -> int:
        """Context limit selected for future turn admissions."""
        return self.runtime_resolver.runtime.context_window_tokens

    @property
    def workspace_sandbox(self) -> Any:
        """Current workspace sandbox status exposed to the runtime state tool."""
        return self.workspace_scopes.sandbox_status

    @property
    def model_presets(self) -> Mapping[str, ModelPresetConfig]:
        """Configured model presets exposed for selection and display."""
        return self.runtime_resolver.model_presets

    @property
    def model_preset(self) -> str | None:
        return self.runtime_resolver.model_preset

    @model_preset.setter
    def model_preset(self, name: str | None) -> None:
        self.set_model_preset(name)

    def llm_runtime(self) -> LLMRuntime:
        """Resolve the immutable default used to admit the next turn."""
        previous = self.runtime_resolver.runtime
        runtime = self.runtime_resolver.admit()
        if (
            runtime.model != previous.model
            or runtime.model_preset != previous.model_preset
            or runtime.snapshot_signature != previous.snapshot_signature
        ):
            self._publish_runtime_selection(runtime)
        return runtime

    _RUNTIME_CHECKPOINT_KEY = RUNTIME_CHECKPOINT_KEY
    _PENDING_USER_TURN_KEY = PENDING_USER_TURN_KEY

    # Event-driven state transition table.
    # Handlers return an event string; the driver looks up the next state here.
    _TRANSITIONS: dict[tuple[TurnState, str], TurnState] = {
        (TurnState.RESTORE, "ok"): TurnState.COMPACT,
        (TurnState.COMPACT, "ok"): TurnState.COMMAND,
        (TurnState.COMMAND, "dispatch"): TurnState.BUILD,
        (TurnState.COMMAND, "shortcut"): TurnState.DONE,
        (TurnState.BUILD, "ok"): TurnState.RUN,
        (TurnState.RUN, "ok"): TurnState.SAVE,
        (TurnState.SAVE, "ok"): TurnState.RESPOND,
        (TurnState.RESPOND, "ok"): TurnState.DONE,
    }

    def __init__(
        self,
        *args: Any,
        config: AgentLoopConfig | None = None,
        **legacy: Any,
    ):
        from mira.config.schema import ensure_tool_config_refs

        ensure_tool_config_refs()
        if config is None:
            config = agent_loop_config_from_legacy_args(args, legacy)
        elif args:
            raise TypeError("AgentLoop accepts either config=AgentLoopConfig or legacy args, not both")
        elif legacy:
            raise TypeError("AgentLoop accepts either config=AgentLoopConfig or legacy kwargs, not both")
        self.loop_config = config
        initialize_agent_loop(self, config)

    @classmethod
    def from_loop_config(cls, config: AgentLoopConfig) -> AgentLoop:
        """Create a loop from one parameter object while legacy kwargs migrate."""
        return cls(config=config)

    def _memory_workspace_from_metadata(self, metadata: Mapping[str, Any] | None) -> Path | None:
        if not isinstance(metadata, Mapping):
            return None
        raw = metadata.get(WEBUI_MEMORY_WORKSPACE_METADATA_KEY)
        if not isinstance(raw, str) or not raw.strip():
            return None
        return Path(raw).expanduser().resolve(strict=False)

    def _memory_store_for_metadata(self, metadata: Mapping[str, Any] | None) -> MemoryStore:
        return self.context.memory_for_workspace(self._memory_workspace_from_metadata(metadata))

    def _consolidator_for_metadata(self, metadata: Mapping[str, Any] | None) -> Consolidator:
        workspace = self._memory_workspace_from_metadata(metadata)
        if workspace is None:
            return self.consolidator
        key = str(workspace)
        cached = self._memory_consolidators.get(key)
        if cached is None:
            cached = Consolidator(
                store=self.context.memory_for_workspace(workspace),
                sessions=self.sessions,
                build_messages=self.context.build_messages,
                get_tool_definitions=self.tools.get_definitions,
                consolidation_ratio=self.consolidator.consolidation_ratio,
                unified_session=self._unified_session,
            )
            self._memory_consolidators[key] = cached
        return cached

    def _page_virtual_context_history(
        self,
        history: list[dict[str, Any]],
        *,
        budget_tokens: int,
        session_key: str,
    ) -> list[dict[str, Any]]:
        if not history or not self._module_enabled("virtual_context", default=True):
            return history
        page = self._virtual_context_manager.page(history, budget_tokens=budget_tokens)
        if page.paged_count:
            logger.debug(
                "Virtual context paged {} message(s) for session {}",
                page.paged_count,
                session_key,
            )
        return page.kept_messages

    def _persist_webui_identity_metadata(self, session: Session, msg: InboundMessage) -> None:
        metadata = msg.metadata if isinstance(msg.metadata, dict) else {}
        for key in (
            WEBUI_USER_METADATA_KEY,
            WEBUI_GROUP_METADATA_KEY,
            WEBUI_MEMORY_WORKSPACE_METADATA_KEY,
        ):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                session.metadata[key] = value

    def _tools_for_metadata(self, metadata: Mapping[str, Any] | None) -> ToolRegistry:
        return tools_for_metadata(
            metadata,
            tools=self.tools,
            security_config=self.security_config,
        )

    def _policy_for_metadata(self, metadata: Mapping[str, Any] | None) -> Any | None:
        return policy_for_metadata(metadata, security_config=self.security_config)

    def _capability_policy_for_metadata(
        self,
        metadata: Mapping[str, Any] | None,
        *,
        sender_id: str | None,
    ) -> Any | None:
        return capability_policy_for_metadata(metadata, sender_id=sender_id)

    def _record_capability_audit_event(self, session: Session, event: Any) -> None:
        record_capability_audit_event(session, event, sessions=self.sessions)

    def _module_enabled(self, name: str, *, default: bool = True) -> bool:
        is_enabled = getattr(self.modules_config, "is_enabled", None)
        return bool(is_enabled(name, default=default)) if callable(is_enabled) else default

    @classmethod
    def from_config(
        cls,
        config: Any,
        bus: MessageBus | None = None,
        **extra: Any,
    ) -> AgentLoop:
        """Create an AgentLoop from config with the common parameter set.

        Extra keyword arguments are forwarded to ``AgentLoop.__init__``,
        allowing callers to override or extend the standard config-derived
        parameters (e.g. ``cron_service``, ``session_manager``).
        """
        from mira.providers.factory import make_provider

        if bus is None:
            bus = MessageBus()
        defaults = config.agents.defaults
        provider = extra.pop("provider", None) or make_provider(config)
        resolved = config.resolve_preset()
        model = extra.pop("model", None) or resolved.model
        context_window_tokens = extra.pop("context_window_tokens", None) or resolved.context_window_tokens
        provider_snapshot_loader = extra.pop("provider_snapshot_loader", None)
        preset_snapshot_loader = extra.pop("preset_snapshot_loader", None) or preset_helpers.make_preset_snapshot_loader(
            config,
            provider_snapshot_loader,
        )
        return cls(
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

    def _sync_subagent_runtime_limits(self) -> None:
        """Keep subagent runtime limits aligned with mutable loop settings."""
        self.subagents.max_iterations = self.max_iterations

    def invalidate_runtime_config(self) -> None:
        """Invalidate runtime config and notify clients to refresh its catalog."""
        self.runtime_resolver.invalidate()
        self._publish_runtime_selection(self.runtime_resolver.runtime)

    def runtime_for_session(
        self,
        session: Session,
        *,
        recover_removed: bool = True,
    ) -> LLMRuntime:
        """Resolve the immutable runtime selected by one session."""
        name = model_preset_from_metadata(session.metadata)
        if name is None:
            return self.llm_runtime()
        try:
            return self.runtime_resolver.resolve_preset(name)
        except KeyError:
            if not recover_removed or name in self.runtime_resolver.model_presets:
                raise
            session_logger(session.key).warning(
                "Session '{}' references removed model preset '{}'; falling back to default",
                session.key,
                name,
            )
            session.metadata.pop(SESSION_MODEL_PRESET_METADATA_KEY, None)
            self.sessions.save(session)
            return self.llm_runtime()

    def set_session_model_preset(
        self,
        session_key: str,
        name: str,
    ) -> LLMRuntime:
        """Validate and persist one session's preset selection."""
        runtime = self.runtime_resolver.resolve_preset(name)
        session = self.sessions.get_or_create(session_key)
        session.metadata[SESSION_MODEL_PRESET_METADATA_KEY] = runtime.model_preset
        self.sessions.save(session)
        return runtime

    def _publish_runtime_selection(
        self,
        runtime: LLMRuntime,
        *,
        publish_update: bool = True,
    ) -> None:
        if not publish_update:
            return
        if self._runtime_model_publisher is not None:
            self._runtime_model_publisher(runtime.model, runtime.model_preset)
        self._runtime_events().runtime_model_changed(
            runtime.model,
            runtime.model_preset,
        )

    def set_model_preset(
        self,
        name: str | None,
        *,
        publish_update: bool = True,
    ) -> LLMRuntime:
        """Select a named default runtime for future turns."""
        old_model = self.model
        runtime = self.runtime_resolver.select_preset(name)
        self._publish_runtime_selection(runtime, publish_update=publish_update)
        session_logger(None).info(
            "Runtime model switched for next turn: {} -> {}",
            old_model,
            runtime.model,
        )
        return runtime

    def set_runtime_model(self, model: str) -> LLMRuntime:
        """Select a model on the current provider for future turns."""
        return self.runtime_resolver.select_model(model)

    def set_runtime_context_window(self, context_window_tokens: int) -> LLMRuntime:
        """Select a context limit for future turns."""
        return self.runtime_resolver.select_context_window(context_window_tokens)

    def _register_default_tools(
        self,
        *,
        provider_snapshot_loader: Callable[..., ProviderSnapshot] | None,
    ) -> None:
        """Register the default set of tools via plugin loader."""
        from mira.agent.tools.context import ToolContext
        from mira.agent.tools.loader import ToolLoader

        ctx = ToolContext(
            config=self.tools_config,
            modules=self.modules_config,
            workspace=str(self.workspace),
            bus=self.bus,
            subagent_manager=self.subagents,
            cron_service=self.cron_service,
            exec_session_manager=self._exec_session_manager,
            sessions=self.sessions,
            provider_snapshot_loader=provider_snapshot_loader,
            image_generation_provider_configs=self._image_generation_provider_configs,
            timezone=self.context.timezone or "UTC",
            workspace_sandbox=self.workspace_scopes.sandbox_status,
            runtime_events=self.runtime_events,
        )
        loader = ToolLoader()
        registered = loader.load(ctx, self.tools)

        # MyTool needs runtime state reference — manual registration
        if self.tools_config.my.enable:
            self.tools.register(
                MyTool(
                    runtime_state=cast(RuntimeState, self),
                    modify_allowed=self.tools_config.my.allow_set,
                )
            )
            registered.append("my")

        for name in list(self.tools.tool_names):
            if not self._module_enabled(name, default=True):
                self.tools.unregister(name)
                if name in registered:
                    registered.remove(name)

        session_logger(None).info("Registered {} tools: {}", len(registered), registered)

    async def _connect_mcp(self) -> None:
        """Connect configured MCP servers."""
        await agent_context.connect_mcp(self, self.tools)

    def register_runtime_context_provider(
        self,
        provider: RuntimeContextProvider,
    ) -> None:
        """Register a provider resolved once before each inbound model turn."""
        if provider not in self._runtime_context_providers:
            self._runtime_context_providers.append(provider)

    def _runtime_events(self) -> RuntimeEventPublisher:
        return ensure_runtime_event_publisher(self)

    async def submit_cron_turn(self, msg: InboundMessage) -> OutboundMessage | None:
        return await self._cron_turns.submit(msg)

    async def submit_local_trigger_turn(self, msg: InboundMessage) -> OutboundMessage | None:
        return await self._local_trigger_turns.submit(msg)

    def pending_cron_job_ids_for_session(self, session_key: str) -> set[str]:
        return self._cron_turns.pending_job_ids_for_session(session_key)

    def pending_local_trigger_ids_for_session(self, session_key: str) -> set[str]:
        return self._local_trigger_turns.pending_trigger_ids_for_session(session_key)

    async def _publish_next_deferred_automation_turn(self, session_key: str) -> None:
        await publish_next_deferred_turn(
            deferred_queues=self._deferred_automation_turns,
            publish_inbound=self.bus.publish_inbound,
            session_key=session_key,
        )

    def _persist_user_message_early(
        self,
        msg: InboundMessage,
        session: Session,
        runtime_context_blocks: list[RuntimeContextBlock] | None = None,
        **kwargs: Any,
    ) -> bool:
        """Persist the triggering user message before the turn starts.

        Returns True if the message was persisted.
        """
        if not turn_continuation.should_persist_user_message(msg.metadata):
            return False
        media_paths = [p for p in (msg.media or []) if isinstance(p, str) and p]
        has_text = isinstance(msg.content, str) and msg.content.strip()
        if has_text or media_paths or runtime_context_blocks:
            extra: dict[str, Any] = ({"media": list(media_paths)} if media_paths else {}) | agent_context.session_extra(msg.metadata)
            extra.update(kwargs)
            text = msg.content if isinstance(msg.content, str) else ""
            text_override, automation_extra = automation_history_overrides(msg.metadata)
            if text_override is not None:
                text = text_override
            extra.update(automation_extra)
            text, runtime_context_meta = append_runtime_context(
                text,
                runtime_context_blocks or (),
            )
            if runtime_context_meta is not None:
                extra[RUNTIME_CONTEXT_HISTORY_META] = runtime_context_meta
            session.add_message("user", text, **extra)
            self._mark_pending_user_turn(session)
            self.sessions.save(session)
            return True
        return False

    def _build_initial_messages(self, ctx: TurnContext) -> list[dict[str, Any]]:
        """Build the initial message list for the LLM turn."""
        assert ctx.session is not None
        scope = self.workspace_scopes.for_message(ctx.msg, ctx.session.metadata)
        return self.context.build_messages(
            history=ctx.history,
            current_message=ctx.msg.content,
            media=ctx.msg.media if ctx.kind is TurnKind.USER and ctx.msg.media else None,
            channel=ctx.delivery.route.channel,
            chat_id=str(
                ctx.msg.metadata.get("context_chat_id") or ctx.delivery.route.chat_id
            ),
            current_role="user",
            sender_id=ctx.msg.sender_id,
            session_summary=ctx.pending_summary,
            session_metadata=ctx.session.metadata,
            workspace=scope.project_path,
            runtime_context_blocks=ctx.runtime_context_blocks,
            include_memory_recent_history=not ctx.ephemeral,
            session_key=ctx.session.key,
            unified_session=self._unified_session,
            memory_workspace=self._memory_workspace_from_metadata(ctx.session.metadata),
        )

    def _request_context_for_turn(self, ctx: TurnContext) -> RequestContext:
        assert ctx.session is not None
        session = ctx.session
        scope = self.workspace_scopes.for_turn(
            channel=ctx.delivery.route.channel,
            message_metadata=ctx.msg.metadata,
            session_metadata=session.metadata,
        )
        return RequestContext(
            channel=ctx.delivery.route.channel,
            chat_id=ctx.delivery.route.chat_id,
            message_id=ctx.msg.metadata.get("message_id"),
            session_key=ctx.session_key,
            original_user_text=ctx.original_user_text,
            runtime=ctx.runtime,
            metadata=dict(ctx.msg.metadata or {}),
            sender_id=ctx.msg.sender_id,
            turn_id=ctx.turn_id,
            workspace=scope.project_path,
            policy=self._policy_for_metadata(ctx.msg.metadata),
            capability_policy=self._capability_policy_for_metadata(
                ctx.msg.metadata,
                sender_id=ctx.msg.sender_id,
            ),
            capability_audit_sink=lambda event: self._record_capability_audit_event(
                session,
                event,
            ),
        )

    async def _resolve_runtime_context_for_turn(
        self,
        ctx: TurnContext,
    ) -> list[RuntimeContextBlock]:
        assert ctx.request_context is not None
        return await self._resolve_runtime_context_for_request(
            ctx.request_context,
            ctx.tools or self.tools,
        )

    async def _resolve_runtime_context_for_request(
        self,
        request: RequestContext,
        tools: ToolRegistry,
    ) -> list[RuntimeContextBlock]:
        providers = [
            *tools.get_runtime_context_providers(),
            *self._runtime_context_providers,
        ]
        blocks = runtime_context_blocks_from_metadata(request.metadata)
        blocks.extend(await resolve_runtime_context(providers, request))
        return blocks

    async def _dispatch_command_inline(
        self,
        msg: InboundMessage,
        key: str,
        raw: str,
        dispatch_fn: Callable[[CommandContext], Awaitable[OutboundMessage | None]],
    ) -> None:
        """Dispatch a command directly from the run() loop and publish the result."""
        ctx = CommandContext(msg=msg, session=None, key=key, raw=raw, loop=self)
        result = await dispatch_fn(ctx)
        if result:
            await self.bus.publish_outbound(result)
        else:
            session_logger(key).warning("Command '{}' matched but dispatch returned None", raw)

    async def _cancel_active_tasks(self, key: str) -> int:
        """Cancel and await all active tasks and subagents for *key*.

        Returns the total number of cancelled tasks + subagents.
        """
        tasks = self._active_tasks.pop(key, [])
        cancelled = sum(1 for t in tasks if not t.done() and t.cancel())
        for t in tasks:
            with suppress(asyncio.CancelledError, Exception):
                await t
        sub_cancelled = await self.subagents.cancel_by_session(key)
        return cancelled + sub_cancelled

    def _effective_session_key(self, msg: InboundMessage) -> str:
        """Return the session key used for task routing and mid-turn injections."""
        if self._unified_session and not msg.session_key_override:
            return UNIFIED_SESSION_KEY
        return msg.session_key

    def _remember_unified_session_route(
        self,
        session: Session,
        msg: InboundMessage,
        *,
        is_user_turn: bool,
    ) -> None:
        """Remember the latest user-facing route for unified-session delivery."""
        if (
            not self._unified_session
            or session.key != UNIFIED_SESSION_KEY
            or not is_user_turn
            or msg.channel in {"cli", "system"}
            or msg.sender_id == "subagent"
        ):
            return
        _, automation_metadata = automation_history_overrides(msg.metadata)
        if automation_metadata:
            return
        remember_last_channel(session.metadata, msg.channel, msg.chat_id)

    @staticmethod
    def _replay_token_budget(runtime: LLMRuntime) -> int:
        """Derive a token budget for session history replay from the context window."""
        if runtime.context_window_tokens <= 0:
            return 0
        max_output = runtime.generation.max_tokens
        try:
            reserved_output = int(max_output)
        except (TypeError, ValueError):
            reserved_output = 4096
        budget = runtime.context_window_tokens - max(1, reserved_output) - 1024
        return budget if budget > 0 else max(128, runtime.context_window_tokens // 2)

    async def _run_agent_loop(
        self,
        initial_messages: list[dict[str, Any]],
        on_progress: Callable[..., Awaitable[None]] | None = None,
        on_stream: Callable[[str], Awaitable[None]] | None = None,
        on_stream_end: Callable[..., Awaitable[None]] | None = None,
        on_retry_wait: Callable[[str], Awaitable[None]] | None = None,
        *,
        runtime: LLMRuntime,
        session: Session | None = None,
        channel: str = "cli",
        chat_id: str = "direct",
        message_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        session_key: str | None = None,
        original_user_text: str | None = None,
        pending_queue: asyncio.Queue[InboundMessage] | None = None,
        ephemeral: bool = False,
        run_extra_hooks_for_ephemeral: bool = False,
        hooks: list[AgentHook] | None = None,
        hook_factories: list[AgentTurnHookFactory] | None = None,
        turn_scopes: list[AbstractContextManager[Any]] | None = None,
        tools: ToolRegistry | None = None,
        request_context: RequestContext | None = None,
    ) -> tuple[str | None, list[str], list[dict[str, Any]], str, bool]:
        """Run the agent iteration loop.

        *on_stream*: called with each content delta during streaming.
        *on_stream_end(resuming, merge_next)*: called when a streaming session finishes.
        ``resuming=True`` means the active turn continues. ``merge_next=True`` means
        the next text segment belongs to the same user-visible assistant message.

        Returns (final_content, tools_used, messages, stop_reason, had_injections).
        """
        self._sync_subagent_runtime_limits()

        async def _checkpoint(payload: dict[str, Any]) -> None:
            if session is None:
                return
            self._set_runtime_checkpoint(session, payload)
            runtime_snapshots = self._runtime_vars.setdefault("session_checkpoints", {})
            runtime_snapshots[session.key] = dict(payload)

        active_session_key = session.key if session else session_key
        effective_scope = self.workspace_scopes.for_turn(
            channel=channel,
            message_metadata=metadata,
            session_metadata=session.metadata if session is not None else None,
        )
        effective_tools = tools or self.tools
        request_ctx = request_context or RequestContext(
            channel=channel,
            chat_id=chat_id,
            message_id=message_id,
            session_key=active_session_key,
            original_user_text=original_user_text,
            runtime=runtime,
            metadata=dict(metadata or {}),
            workspace=effective_scope.project_path,
            policy=self._policy_for_metadata(metadata),
            capability_policy=self._capability_policy_for_metadata(
                metadata,
                sender_id=metadata.get("sender_id") if isinstance(metadata, dict) else None,
            ),
            capability_audit_sink=(
                (lambda event: self._record_capability_audit_event(session, event))
                if session is not None
                else None
            ),
        )
        pending_injections = PendingInjectionDrainer(
            pending_queue=pending_queue,
            session=session,
            active_session_key=active_session_key,
            runtime=runtime,
            request_turn_id=str(request_ctx.turn_id or ""),
            effective_tools=effective_tools,
            workspace_scopes=self.workspace_scopes,
            build_user_content=self.context._build_user_content,
            prepare_message_media=self._prepare_message_media,
            resolve_runtime_context=self._resolve_runtime_context_for_request,
            get_running_subagents=self.subagents.get_running_count_by_session,
        )

        async def _drain_pending(*, limit: int = _MAX_INJECTIONS_PER_TURN) -> list[dict[str, Any]]:
            return await pending_injections.drain(limit=limit)

        file_state_token = bind_file_states(self._file_state_store.for_session(active_session_key))
        request_token = bind_request_context(request_ctx)
        workspace_token = bind_workspace_scope(effective_scope)
        turn_scope_stack = ExitStack()
        # Compute lazily because create_goal may create goal metadata during this run.
        def _goal_continue() -> str | None:
            _goal_lines = goal_state_runtime_lines(session.metadata if session is not None else None)
            if not _goal_lines:
                return None
            return (
                "You have an active sustained goal:\n\n"
                + "\n".join(_goal_lines)
                + "\n\nPlease continue working toward the objective using your tools, "
                "or call update_goal with action='complete' if the work is truly finished."
            )

        session_metadata = session.metadata if session is not None else None
        try:
            for scope in turn_scopes or ():
                turn_scope_stack.enter_context(scope)
            hook = build_agent_turn_hook(AgentTurnHookSpec(
                on_progress=on_progress,
                on_stream=on_stream,
                on_stream_end=on_stream_end,
                channel=channel,
                chat_id=chat_id,
                message_id=message_id,
                metadata=metadata,
                session_key=active_session_key,
                workspace=effective_scope.project_path,
                tool_hint_max_length=self.tool_hint_max_length,
                on_iteration=lambda iteration: setattr(self, "_current_iteration", iteration),
                registered_hook_factories=self._hook_factories,
                turn_hook_factories=list(hook_factories or []),
                registered_hooks=self._extra_hooks,
                turn_hooks=list(hooks or []),
                ephemeral=ephemeral,
                run_extra_hooks_for_ephemeral=run_extra_hooks_for_ephemeral,
            ))
            result = await self.runner.run(AgentRunSpec(
                initial_messages=initial_messages,
                tools=effective_tools,
                runtime=runtime,
                max_iterations=self.max_iterations,
                max_tool_result_chars=self.max_tool_result_chars,
                hook=hook,
                error_message="Sorry, I encountered an error calling the AI model.",
                concurrent_tools=True,
                workspace=effective_scope.project_path,
                session_key=session.key if session else None,
                context_block_limit=self.context_block_limit,
                provider_retry_mode=self.provider_retry_mode,
                progress_callback=on_progress,
                stream_progress_deltas=on_stream is not None,
                retry_wait_callback=on_retry_wait,
                checkpoint_callback=_checkpoint,
                injection_callback=_drain_pending,
                # Sustained goals may legitimately exceed mira_LLM_TIMEOUT_S; idle stall
                # is still capped by mira_STREAM_IDLE_TIMEOUT_S in streaming providers.
                llm_timeout_s=runner_wall_llm_timeout_s(
                    self.sessions,
                    session.key if session is not None else session_key,
                    metadata=session_metadata,
                    message_metadata=metadata,
                ),
                goal_active_predicate=lambda: sustained_goal_active(session.metadata) if session is not None else False,
                goal_continue_message=_goal_continue,
                execution_gate=self.execution_gate,
                finalize_on_max_iterations=turn_continuation.should_finalize_on_max_iterations(
                    pending_queue_available=pending_queue is not None and session is not None,
                    session_metadata=session_metadata,
                    message_metadata=metadata,
                ),
            ))
        finally:
            turn_scope_stack.close()
            reset_workspace_scope(workspace_token)
            reset_request_context(request_token)
            reset_file_states(file_state_token)
        self._last_usage = result.usage
        if result.stop_reason == "max_iterations":
            session_logger(active_session_key).warning(
                "Max iterations ({}) reached",
                self.max_iterations,
            )
            should_stream = turn_continuation.should_stream_budget_response(
                stop_reason=result.stop_reason,
                pending_queue_available=pending_queue is not None and session is not None,
                session_metadata=session_metadata,
                message_metadata=metadata,
            )
            # Push final content through stream so streaming channels (e.g. Feishu)
            # update the card instead of leaving it empty.
            if on_stream and on_stream_end and should_stream:
                stream_content = (
                    result.pending_stream_content
                    if result.pending_stream_content is not None
                    else result.final_content or ""
                )
                await on_stream(stream_content)
                await on_stream_end(resuming=False)
        elif result.stop_reason == "error":
            session_logger(active_session_key).error(
                "LLM returned error: {}",
                (result.final_content or "")[:200],
            )
        return result.final_content, result.tools_used, result.messages, result.stop_reason, result.had_injections

    def _check_expired_sessions_if_due(self) -> None:
        """Scan idle sessions no more often than the configured interval."""
        now = time.monotonic()
        if now < self._next_idle_compact_check_at:
            return
        self._next_idle_compact_check_at = now + self._idle_compact_check_interval_s
        self.auto_compact.check_expired(
            self._schedule_background,
            self.runtime_for_session,
            active_session_keys=self._pending_queues.keys(),
        )

    async def run(self) -> None:
        """Run the agent loop, dispatching messages as tasks to stay responsive to /stop."""
        self._running = True
        try:
            await self._connect_mcp()
            session_logger(None).info("Agent loop started")

            while self._running:
                try:
                    msg = await asyncio.wait_for(self.bus.consume_inbound(), timeout=1.0)
                except TimeoutError:
                    self._check_expired_sessions_if_due()
                    continue
                except asyncio.CancelledError:
                    # Preserve real task cancellation so shutdown can complete cleanly.
                    # Only ignore non-task CancelledError signals that may leak from integrations.
                    if not self._running or task_is_cancelling():
                        raise
                    logger.warning(
                        "Ignoring leaked CancelledError while consuming inbound messages"
                    )
                    continue
                except BaseException as e:
                    if isinstance(e, (KeyboardInterrupt, SystemExit)):
                        raise
                    session_logger(None).warning(
                        "Error consuming inbound message: {}, continuing...",
                        e,
                    )
                    continue

                raw = msg.content.strip()
                effective_key = self._effective_session_key(msg)
                if await agent_context.handle_runtime_control(self, msg, self.tools):
                    continue
                if self.commands.is_priority(raw):
                    await self._dispatch_command_inline(
                        msg, effective_key, raw,
                        self.commands.dispatch_priority,
                    )
                    continue
                deferred = False
                for label, coordinator in self._automation_turn_coordinators:
                    if coordinator.defer_if_active(
                        msg,
                        session_key=effective_key,
                        active_session_keys=self._pending_queues.keys(),
                    ):
                        session_logger(effective_key).info(
                            "Deferred {} turn for active session {}",
                            label,
                            effective_key,
                        )
                        deferred = True
                        break
                if deferred:
                    continue
                # If this session already has an active pending queue (i.e. a task
                # is processing this session), route the message there for mid-turn
                # injection instead of creating a competing task.
                if effective_key in self._pending_queues:
                    # Non-priority commands must not be queued for injection;
                    # dispatch them directly (same pattern as priority commands).
                    if self.commands.is_dispatchable_command(raw):
                        await self._dispatch_command_inline(
                            msg, effective_key, raw,
                            self.commands.dispatch,
                        )
                        continue
                    pending_msg = msg
                    if effective_key != msg.session_key:
                        pending_msg = dataclasses.replace(
                            msg,
                            session_key_override=effective_key,
                        )
                    try:
                        self._pending_queues[effective_key].put_nowait(pending_msg)
                    except asyncio.QueueFull:
                        session_logger(effective_key).warning(
                            "Pending queue full for session {}, falling back to queued task",
                            effective_key,
                        )
                    else:
                        session_logger(effective_key).info(
                            "Routed follow-up message to pending queue for session {}",
                            effective_key,
                        )
                        continue
                # Compute the effective session key before dispatching
                # This ensures /stop command can find tasks correctly when unified session is enabled
                task = asyncio.create_task(self._dispatch(msg))
                self._active_tasks.setdefault(effective_key, []).append(task)
                task.add_done_callback(partial(self._forget_active_task, session_key=effective_key))
        finally:
            # MCP stdio transports use AnyIO cancel scopes; close them from the task that opened them.
            await self.close_mcp()

    async def _dispatch(self, msg: InboundMessage) -> None:
        """Process a message: per-session serial, cross-session concurrent."""
        await dispatch_inbound_turn(self, msg)

    async def close_mcp(self) -> None:
        """Drain background work, stop exec sessions, then close MCP connections."""
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
            self._background_tasks.clear()
        errors: list[BaseException] = []
        cleanup_steps = (
            self.subagents.close,
            self._exec_session_manager.close_all,
            lambda: agent_context.close_mcp(self),
        )
        for cleanup in cleanup_steps:
            try:
                await cleanup()
            except BaseException as exc:
                errors.append(exc)
        if len(errors) == 1:
            raise errors[0]
        if errors:
            raise BaseExceptionGroup("failed to close agent resources", errors)

    def _forget_active_task(self, task: asyncio.Task[None], *, session_key: str) -> None:
        tasks = self._active_tasks.get(session_key, [])
        if task in tasks:
            tasks.remove(task)

    def _schedule_background(self, coro: Coroutine[Any, Any, None]) -> None:
        """Schedule a coroutine as a tracked background task (drained on shutdown)."""
        task = asyncio.create_task(coro)
        self._background_tasks.append(task)
        task.add_done_callback(self._background_tasks.remove)

    def stop(self) -> None:
        """Stop the agent loop."""
        self._running = False
        session_logger(None).info("Agent loop stopping")

    async def _process_message(
        self,
        msg: InboundMessage,
        session_key: str | None = None,
        on_progress: Callable[..., Awaitable[None]] | None = None,
        on_stream: Callable[[str], Awaitable[None]] | None = None,
        on_stream_end: Callable[..., Awaitable[None]] | None = None,
        pending_queue: asyncio.Queue[InboundMessage] | None = None,
        ephemeral: bool = False,
        run_extra_hooks_for_ephemeral: bool = False,
        hooks: list[AgentHook] | None = None,
        hook_factories: list[AgentTurnHookFactory] | None = None,
        tools: ToolRegistry | None = None,
        runtime: LLMRuntime | None = None,
        delivery: TurnDelivery | None = None,
        on_runtime_admitted: Callable[[LLMRuntime], Awaitable[None]] | None = None,
    ) -> OutboundMessage | None:
        return await process_inbound_message(
            self,
            msg,
            session_key=session_key,
            on_progress=on_progress,
            on_stream=on_stream,
            on_stream_end=on_stream_end,
            pending_queue=pending_queue,
            ephemeral=ephemeral,
            run_extra_hooks_for_ephemeral=run_extra_hooks_for_ephemeral,
            hooks=hooks,
            hook_factories=hook_factories,
            tools=tools,
            runtime=runtime,
            delivery=delivery,
            on_runtime_admitted=on_runtime_admitted,
        )

    def _assemble_outbound(
        self,
        msg: InboundMessage,
        final_content: str,
        all_msgs: list[dict[str, Any]],
        stop_reason: str,
        had_injections: bool,
        streamed_content: bool,
        *,
        turn_latency_ms: int | None = None,
    ) -> OutboundMessage | None:
        """Assemble the final outbound message from turn results."""
        # MessageTool suppression
        if (mt := self.tools.get("message")) and isinstance(mt, MessageTool) and mt._sent_in_turn:
            if not had_injections or stop_reason == "empty_final_response":
                return None

        preview = final_content[:120] + "..." if len(final_content) > 120 else final_content
        meta = dict(msg.metadata or {})
        session_logger(msg.session_key).info(
            "Response to {}:{}: {}",
            msg.channel,
            msg.sender_id,
            preview,
        )

        event = None
        if streamed_content and stop_reason not in {"error", "tool_error"}:
            event = StreamedResponseEvent()
        if turn_latency_ms is not None:
            meta["latency_ms"] = int(turn_latency_ms)

        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=final_content,
            event=event,
            metadata=meta,
        )

    def _assemble_outbound_for_context(self, ctx: TurnContext) -> OutboundMessage | None:
        return self._assemble_outbound(
            ctx.msg,
            ctx.final_content or "",
            ctx.all_messages,
            ctx.stop_reason,
            ctx.had_injections,
            ctx.streamed_content,
            turn_latency_ms=ctx.turn_latency_ms,
        )

    async def _state_restore(self, ctx: TurnContext) -> str:
        """Restore checkpoint / pending user turn; extract documents."""
        msg = ctx.msg

        if ctx.kind is TurnKind.USER and msg.media:
            new_content, image_only = self._prepare_message_media(msg.content, msg.media)
            ctx.msg = dataclasses.replace(msg, content=new_content, media=image_only)
            msg = ctx.msg

        preview = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
        if ctx.kind is TurnKind.SYSTEM:
            _ctx_logger(ctx).info("Processing system message from {}", msg.sender_id)
        else:
            _ctx_logger(ctx).info(
                "Processing message from {}:{}: {}",
                msg.channel,
                msg.sender_id,
                preview,
            )

        # Session is already fetched by the caller (_process_message) but
        # ensure it exists in case this handler is invoked independently.
        if ctx.session is None:
            ctx.session = self.sessions.get_or_create(ctx.session_key)
        self._remember_unified_session_route(
            ctx.session,
            msg,
            is_user_turn=ctx.original_user_text is not None,
        )
        await ctx.delivery.started()
        if ctx.kind is TurnKind.USER:
            self.workspace_scopes.persist_message_scope(ctx.session, msg)
            self._persist_webui_identity_metadata(ctx.session, msg)

        if self._restore_runtime_checkpoint(ctx.session):
            self.sessions.save(ctx.session)
        if self._restore_pending_user_turn(ctx.session):
            self.sessions.save(ctx.session)

        return "ok"

    def _prepare_message_media(self, content: str, media: list[str]) -> tuple[str, list[str]]:
        if self._should_extract_document_text():
            return extract_documents(content, media)
        return reference_non_image_attachments(content, media)

    def _should_extract_document_text(self) -> bool:
        if self.channels_config is None:
            return True
        return self.channels_config.extract_document_text

    async def _state_compact(self, ctx: TurnContext) -> str:
        ctx.session, pending = self.auto_compact.prepare_session(_ctx_session(ctx), ctx.session_key)
        ctx.pending_summary = pending
        return "ok"

    async def _state_command(self, ctx: TurnContext) -> str:
        result = await self.command_turns.handle(ctx, _ctx_session(ctx))
        ctx.input_persisted_early = result.input_persisted_early
        return result.event

    async def _state_build(self, ctx: TurnContext) -> str:
        return await self.build_turns.handle(ctx, _ctx_session(ctx))

    async def _state_run(self, ctx: TurnContext) -> str:
        return await self.run_turns.handle(
            ctx,
            runtime=_ctx_runtime(ctx),
            session=_ctx_session(ctx),
        )

    async def _state_save(self, ctx: TurnContext) -> str:
        return await self.save_turns.handle(
            ctx,
            session=_ctx_session(ctx),
            runtime=_ctx_runtime(ctx),
        )

    async def _state_respond(self, ctx: TurnContext) -> str:
        return await self.respond_turns.handle(ctx)

    def _sanitize_persisted_blocks(
        self,
        content: list[dict[str, Any]],
        *,
        should_truncate_text: bool = False,
    ) -> list[dict[str, Any]]:
        return sanitize_persisted_blocks(
            content,
            max_tool_result_chars=self.max_tool_result_chars,
            should_truncate_text=should_truncate_text,
        )

    def _save_turn(
        self,
        session: Session,
        messages: list[dict[str, Any]],
        skip: int,
        *,
        turn_latency_ms: int | None = None,
    ) -> None:
        save_turn_messages(
            session,
            messages,
            skip,
            max_tool_result_chars=self.max_tool_result_chars,
            turn_latency_ms=turn_latency_ms,
        )

    def _persist_subagent_followup(self, session: Session, msg: InboundMessage) -> bool:
        return persist_subagent_followup(session, msg)

    def _set_runtime_checkpoint(self, session: Session, payload: dict[str, Any]) -> None:
        """Persist the latest in-flight turn state into session metadata."""
        session.metadata[self._RUNTIME_CHECKPOINT_KEY] = payload
        self.sessions.save(session)

    def _mark_pending_user_turn(self, session: Session) -> None:
        session.metadata[self._PENDING_USER_TURN_KEY] = True

    def _clear_pending_user_turn(self, session: Session) -> None:
        session.metadata.pop(self._PENDING_USER_TURN_KEY, None)

    def _clear_runtime_checkpoint(self, session: Session) -> None:
        if self._RUNTIME_CHECKPOINT_KEY in session.metadata:
            session.metadata.pop(self._RUNTIME_CHECKPOINT_KEY, None)

    @staticmethod
    def _checkpoint_message_key(message: dict[str, Any]) -> tuple[Any, ...]:
        return (
            message.get("role"),
            message.get("content"),
            message.get("tool_call_id"),
            message.get("name"),
            message.get("tool_calls"),
            message.get("reasoning_content"),
            message.get("thinking_blocks"),
        )

    def _restore_runtime_checkpoint(self, session: Session) -> bool:
        """Materialize an unfinished turn into session history before a new request."""
        return restore_runtime_checkpoint(session)

    def _restore_pending_user_turn(self, session: Session) -> bool:
        """Close a turn that only persisted the user message before crashing."""
        return restore_pending_user_turn(session)

    async def process_direct(
        self,
        content: str,
        session_key: str = "cli:direct",
        channel: str = "cli",
        chat_id: str = "direct",
        sender_id: str = "user",
        media: list[str] | None = None,
        on_progress: Callable[..., Awaitable[None]] | None = None,
        on_stream: Callable[[str], Awaitable[None]] | None = None,
        on_stream_end: Callable[..., Awaitable[None]] | None = None,
        ephemeral: bool = False,
        _run_extra_hooks_for_ephemeral: bool = False,
        hooks: list[AgentHook] | None = None,
        hook_factories: list[AgentTurnHookFactory] | None = None,
        tools: ToolRegistry | None = None,
        persist_user_message: bool = True,
        runtime: LLMRuntime | None = None,
        on_runtime_admitted: Callable[[LLMRuntime], Awaitable[None]] | None = None,
    ) -> OutboundMessage | None:
        """Process an external message directly and return the outbound payload."""
        if channel == "system":
            raise ValueError("channel 'system' is reserved for internal messages")
        await self._connect_mcp()
        metadata: dict[str, Any] = {}
        if not persist_user_message:
            metadata[turn_continuation.SKIP_USER_PERSIST_META] = True
        msg = InboundMessage(
            channel=channel, sender_id=sender_id, chat_id=chat_id,
            content=content, media=media or [], metadata=metadata,
        )
        # Share the dispatch lock so direct calls serialize with bus turns.
        lock = self._session_locks.setdefault(session_key, asyncio.Lock())
        try:
            async with lock:
                kwargs: dict[str, Any] = {
                    "session_key": session_key,
                    "on_progress": on_progress,
                    "on_stream": on_stream,
                    "on_stream_end": on_stream_end,
                    "ephemeral": ephemeral,
                }
                if _run_extra_hooks_for_ephemeral:
                    kwargs["run_extra_hooks_for_ephemeral"] = True
                if hooks is not None:
                    kwargs["hooks"] = hooks
                if hook_factories is not None:
                    kwargs["hook_factories"] = hook_factories
                if tools is not None:
                    kwargs["tools"] = tools
                if runtime is not None:
                    kwargs["runtime"] = runtime
                if on_runtime_admitted is not None:
                    kwargs["on_runtime_admitted"] = on_runtime_admitted
                return await self._process_message(
                    msg,
                    **kwargs,
                )
        finally:
            await self._runtime_events().run_status_changed(msg, session_key, "idle")
            self._runtime_events().clear_turn(session_key)
