"""Build-state preparation for an agent turn."""

from __future__ import annotations

from typing import Any

from mira.agent.tools.message import MessageTool
from mira.agent.turn_context import TurnContext, TurnKind
from mira.session.manager import Session, replay_max_messages_for_context
from mira.utils.logging import turn_logger


class BuildTurnHandler:
    """Prepare runtime, replay history, tools, and initial prompt messages."""

    def __init__(self, loop: Any) -> None:
        self.loop = loop

    async def handle(self, ctx: TurnContext, session: Session) -> str:
        runtime = ctx.runtime
        if runtime is None:
            runtime = self.loop.runtime_for_session(session)
            ctx.runtime = runtime
        if ctx.on_runtime_admitted is not None:
            await ctx.on_runtime_admitted(runtime)

        replay_max_messages = replay_max_messages_for_context(runtime.context_window_tokens)
        if not ctx.ephemeral:
            await self.loop._consolidator_for_metadata(
                session.metadata
            ).maybe_consolidate_by_tokens(
                session,
                runtime=runtime,
                replay_max_messages=replay_max_messages,
            )
        is_subagent = ctx.kind is TurnKind.SYSTEM and ctx.msg.sender_id == "subagent"

        if ctx.kind is TurnKind.USER and (message_tool := self.loop.tools.get("message")):
            if isinstance(message_tool, MessageTool):
                message_tool.start_turn()

        hist_kwargs: dict[str, Any] = {
            "max_messages": replay_max_messages,
            "max_tokens": self.loop._replay_token_budget(runtime),
            "extend_to_user": is_subagent,
        }
        ctx.history = session.get_history(**hist_kwargs)
        ctx.history = self.loop._page_virtual_context_history(
            ctx.history,
            budget_tokens=hist_kwargs["max_tokens"],
            session_key=ctx.session_key,
        )
        if is_subagent:
            if self.loop._persist_subagent_followup(session, ctx.msg):
                turn_logger(ctx.session_key, ctx.turn_id).debug(
                    "Subagent result persisted for session {}",
                    ctx.session_key,
                )
                self.loop.sessions.save(session)
            ctx.input_persisted_early = True
        ctx.delivery.record_runtime(ctx.runtime)

        ctx.tools = self.loop._tools_for_metadata(session.metadata)
        ctx.request_context = self.loop._request_context_for_turn(ctx)
        if ctx.kind is TurnKind.USER:
            ctx.runtime_context_blocks = await self.loop._resolve_runtime_context_for_turn(ctx)
        ctx.initial_messages = self.loop._build_initial_messages(ctx)
        if ctx.kind is TurnKind.USER:
            ctx.input_persisted_early = self.loop._persist_user_message_early(
                ctx.msg,
                session,
                runtime_context_blocks=ctx.runtime_context_blocks,
            )

        if ctx.on_progress is None:
            ctx.on_progress = ctx.delivery.progress_callback()
        if ctx.on_retry_wait is None:
            ctx.on_retry_wait = ctx.delivery.retry_wait_callback()

        return "ok"
