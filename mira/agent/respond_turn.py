"""Respond-state outbound assembly for an agent turn."""

from __future__ import annotations

from collections.abc import Callable

from mira.agent.turn_context import TurnContext, TurnKind
from mira.bus.events import OutboundMessage

AssembleOutbound = Callable[
    [TurnContext],
    OutboundMessage | None,
]


class RespondTurnHandler:
    """Create the final outbound message for a completed turn."""

    def __init__(self, assemble_outbound: AssembleOutbound) -> None:
        self.assemble_outbound = assemble_outbound

    async def handle(self, ctx: TurnContext) -> str:
        if ctx.suppress_response:
            ctx.outbound = None
            return "ok"
        if ctx.kind is TurnKind.SYSTEM:
            ctx.outbound = ctx.delivery.background_response(
                ctx.final_content,
                stop_reason=ctx.stop_reason,
                streamed=ctx.streamed_content,
                latency_ms=ctx.turn_latency_ms,
            )
            return "ok"

        ctx.outbound = self.assemble_outbound(ctx)
        if ctx.ephemeral and ctx.outbound is not None:
            ctx.outbound.metadata["_stop_reason"] = ctx.stop_reason
        return "ok"
