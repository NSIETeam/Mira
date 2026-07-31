"""Run-state execution for an agent turn."""

from __future__ import annotations

import time
from typing import Any

from mira.agent.turn_context import TurnContext, TurnKind
from mira.session import turn_continuation
from mira.session.manager import Session
from mira.utils.llm_runtime import LLMRuntime


class RunTurnHandler:
    """Call the agent runner and write its result back to the turn context."""

    def __init__(self, loop: Any) -> None:
        self.loop = loop

    async def handle(
        self,
        ctx: TurnContext,
        *,
        runtime: LLMRuntime,
        session: Session,
    ) -> str:
        if ctx.visible_run_started_at is None:
            ctx.visible_run_started_at = time.time()
        await ctx.delivery.running(started_at=ctx.visible_run_started_at)
        result = await self.loop._run_agent_loop(
            ctx.initial_messages,
            runtime=runtime,
            on_progress=ctx.on_progress,
            on_stream=ctx.on_stream,
            on_stream_end=ctx.on_stream_end,
            on_retry_wait=ctx.on_retry_wait,
            session=session,
            channel=ctx.delivery.route.channel,
            chat_id=ctx.delivery.route.chat_id,
            message_id=ctx.msg.metadata.get("message_id"),
            metadata=ctx.msg.metadata,
            session_key=ctx.session_key,
            original_user_text=ctx.original_user_text,
            pending_queue=ctx.pending_queue,
            ephemeral=ctx.ephemeral,
            run_extra_hooks_for_ephemeral=ctx.run_extra_hooks_for_ephemeral,
            hooks=ctx.hooks,
            hook_factories=ctx.hook_factories,
            turn_scopes=ctx.turn_scopes,
            tools=ctx.tools,
            request_context=ctx.request_context,
        )
        final_content, tools_used, all_msgs, stop_reason, had_injections = result
        ctx.final_content = final_content
        ctx.tools_used = tools_used
        ctx.all_messages = all_msgs
        ctx.stop_reason = stop_reason
        ctx.had_injections = had_injections
        if ctx.kind is TurnKind.USER:
            await turn_continuation.maybe_continue_turn(ctx)
        return "ok"
