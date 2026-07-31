"""Agent runner execution wrapper used by the turn handlers."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import AbstractContextManager, ExitStack
from typing import Any

from mira.agent.hook import AgentHook, AgentTurnHookFactory
from mira.agent.pending_injections import PendingInjectionDrainer
from mira.agent.runner import _MAX_INJECTIONS_PER_TURN, AgentRunSpec
from mira.agent.tools.context import RequestContext, bind_request_context, reset_request_context
from mira.agent.tools.file_state import bind_file_states, reset_file_states
from mira.agent.tools.registry import ToolRegistry
from mira.agent.turn_hooks import AgentTurnHookSpec, build_agent_turn_hook
from mira.bus.events import InboundMessage
from mira.security.workspace_access import (
    bind_workspace_scope,
    reset_workspace_scope,
)
from mira.session import turn_continuation
from mira.session.goal_state import (
    goal_state_runtime_lines,
    runner_wall_llm_timeout_s,
    sustained_goal_active,
)
from mira.session.manager import Session
from mira.utils.llm_runtime import LLMRuntime
from mira.utils.logging import session_logger


async def run_agent_iteration_loop(
    loop: Any,
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
    """Run the provider/tool iteration loop for one turn."""
    loop._sync_subagent_runtime_limits()

    async def _checkpoint(payload: dict[str, Any]) -> None:
        if session is None:
            return
        loop._set_runtime_checkpoint(session, payload)
        runtime_snapshots = loop._runtime_vars.setdefault("session_checkpoints", {})
        runtime_snapshots[session.key] = dict(payload)

    active_session_key = session.key if session else session_key
    effective_scope = loop.workspace_scopes.for_turn(
        channel=channel,
        message_metadata=metadata,
        session_metadata=session.metadata if session is not None else None,
    )
    effective_tools = tools or loop.tools
    request_ctx = request_context or RequestContext(
        channel=channel,
        chat_id=chat_id,
        message_id=message_id,
        session_key=active_session_key,
        original_user_text=original_user_text,
        runtime=runtime,
        metadata=dict(metadata or {}),
        workspace=effective_scope.project_path,
        policy=loop._policy_for_metadata(metadata),
        capability_policy=loop._capability_policy_for_metadata(
            metadata,
            sender_id=metadata.get("sender_id") if isinstance(metadata, dict) else None,
        ),
        capability_audit_sink=(
            (lambda event: loop._record_capability_audit_event(session, event))
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
        workspace_scopes=loop.workspace_scopes,
        build_user_content=loop.context._build_user_content,
        prepare_message_media=loop._prepare_message_media,
        resolve_runtime_context=loop._resolve_runtime_context_for_request,
        get_running_subagents=loop.subagents.get_running_count_by_session,
    )

    async def _drain_pending(
        *,
        limit: int = _MAX_INJECTIONS_PER_TURN,
    ) -> list[dict[str, Any]]:
        return await pending_injections.drain(limit=limit)

    file_state_token = bind_file_states(loop._file_state_store.for_session(active_session_key))
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
        hook = build_agent_turn_hook(
            AgentTurnHookSpec(
                on_progress=on_progress,
                on_stream=on_stream,
                on_stream_end=on_stream_end,
                channel=channel,
                chat_id=chat_id,
                message_id=message_id,
                metadata=metadata,
                session_key=active_session_key,
                workspace=effective_scope.project_path,
                tool_hint_max_length=loop.tool_hint_max_length,
                on_iteration=lambda iteration: setattr(loop, "_current_iteration", iteration),
                registered_hook_factories=loop._hook_factories,
                turn_hook_factories=list(hook_factories or []),
                registered_hooks=loop._extra_hooks,
                turn_hooks=list(hooks or []),
                ephemeral=ephemeral,
                run_extra_hooks_for_ephemeral=run_extra_hooks_for_ephemeral,
            )
        )
        result = await loop.runner.run(
            AgentRunSpec(
                initial_messages=initial_messages,
                tools=effective_tools,
                runtime=runtime,
                max_iterations=loop.max_iterations,
                max_tool_result_chars=loop.max_tool_result_chars,
                hook=hook,
                error_message="Sorry, I encountered an error calling the AI model.",
                concurrent_tools=True,
                workspace=effective_scope.project_path,
                session_key=session.key if session else None,
                context_block_limit=loop.context_block_limit,
                provider_retry_mode=loop.provider_retry_mode,
                progress_callback=on_progress,
                stream_progress_deltas=on_stream is not None,
                retry_wait_callback=on_retry_wait,
                checkpoint_callback=_checkpoint,
                injection_callback=_drain_pending,
                # Sustained goals may legitimately exceed MIRA_LLM_TIMEOUT_S; idle stall
                # is still capped by MIRA_STREAM_IDLE_TIMEOUT_S in streaming providers.
                llm_timeout_s=runner_wall_llm_timeout_s(
                    loop.sessions,
                    session.key if session is not None else session_key,
                    metadata=session_metadata,
                    message_metadata=metadata,
                ),
                goal_active_predicate=(
                    lambda: sustained_goal_active(session.metadata)
                    if session is not None
                    else False
                ),
                goal_continue_message=_goal_continue,
                execution_gate=loop.execution_gate,
                finalize_on_max_iterations=turn_continuation.should_finalize_on_max_iterations(
                    pending_queue_available=pending_queue is not None and session is not None,
                    session_metadata=session_metadata,
                    message_metadata=metadata,
                ),
            )
        )
    finally:
        turn_scope_stack.close()
        reset_workspace_scope(workspace_token)
        reset_request_context(request_token)
        reset_file_states(file_state_token)

    loop._last_usage = result.usage
    if result.stop_reason == "max_iterations":
        session_logger(active_session_key).warning(
            "Max iterations ({}) reached",
            loop.max_iterations,
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

    return (
        result.final_content,
        result.tools_used,
        result.messages,
        result.stop_reason,
        result.had_injections,
    )
