"""Save-state persistence orchestration for an agent turn."""

from __future__ import annotations

import time
from functools import partial
from typing import Any

from mira.agent.turn_context import TurnContext, TurnKind
from mira.session import turn_continuation
from mira.session.manager import Session, replay_max_messages_for_context
from mira.utils.llm_runtime import LLMRuntime
from mira.utils.runtime import EMPTY_FINAL_RESPONSE_MESSAGE


class SaveTurnHandler:
    """Persist a completed turn and clear in-flight recovery metadata."""

    def __init__(self, loop: Any) -> None:
        self.loop = loop

    async def handle(
        self,
        ctx: TurnContext,
        *,
        session: Session,
        runtime: LLMRuntime,
    ) -> str:
        turn_continuation.prepare_save_boundary(ctx)

        if (
            ctx.kind is TurnKind.USER
            and (ctx.final_content is None or not ctx.final_content.strip())
            and not ctx.suppress_response
        ):
            ctx.final_content = EMPTY_FINAL_RESPONSE_MESSAGE

        latency_started_at = (
            ctx.visible_run_started_at
            if (
                ctx.kind is TurnKind.SYSTEM
                or turn_continuation.internal_continuation_inbound(ctx.msg.metadata)
            )
            and ctx.visible_run_started_at is not None
            else ctx.turn_wall_started_at
        )
        ctx.turn_latency_ms = max(0, int((time.time() - latency_started_at) * 1000))
        self.loop._save_turn(
            session,
            ctx.all_messages,
            ctx.save_skip,
            turn_latency_ms=ctx.turn_latency_ms,
        )
        ctx.delivery.record_latency(ctx.turn_latency_ms)
        if not ctx.ephemeral:
            session.enforce_file_cap(
                on_archive=partial(
                    self.loop._memory_store_for_metadata(session.metadata).raw_archive,
                    session_key=ctx.session_key,
                )
            )
            self.loop._schedule_background(
                self.loop._consolidator_for_metadata(
                    session.metadata
                ).maybe_consolidate_by_tokens(
                    session,
                    runtime=runtime,
                    replay_max_messages=replay_max_messages_for_context(
                        runtime.context_window_tokens
                    ),
                )
            )
        self.loop._clear_pending_user_turn(session)
        self.loop._clear_runtime_checkpoint(session)
        self.loop.sessions.save(session)
        return "ok"
