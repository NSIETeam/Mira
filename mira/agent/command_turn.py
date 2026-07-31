"""Slash-command turn handling for the agent loop state machine."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from mira.agent.turn_context import TurnContext, TurnKind
from mira.command import CommandContext, CommandRouter
from mira.session.automation_turns import automation_history_overrides
from mira.session.manager import Session


@dataclass(frozen=True)
class CommandTurnResult:
    event: str
    input_persisted_early: bool = False


class CommandTurnHandler:
    """Handle the command branch of a user turn without owning the full loop."""

    def __init__(
        self,
        *,
        commands: CommandRouter,
        loop: Any,
        persist_user_message: Callable[..., bool],
        save_session: Callable[[Session], None],
        clear_pending_user_turn: Callable[[Session], None],
    ) -> None:
        self.commands = commands
        self.loop = loop
        self.persist_user_message = persist_user_message
        self.save_session = save_session
        self.clear_pending_user_turn = clear_pending_user_turn

    async def handle(self, ctx: TurnContext, session: Session) -> CommandTurnResult:
        if ctx.kind is TurnKind.SYSTEM:
            return CommandTurnResult(event="dispatch")

        raw = ctx.msg.content.strip()
        _, automation_metadata = automation_history_overrides(ctx.msg.metadata)
        is_user_turn = (
            ctx.original_user_text is not None
            and not automation_metadata
            and ctx.msg.channel != "system"
            and ctx.msg.sender_id != "subagent"
        )
        cmd_ctx = CommandContext(
            msg=ctx.msg,
            session=ctx.session,
            key=ctx.session_key,
            raw=raw,
            loop=self.loop,
            runtime=ctx.runtime,
            is_user_turn=is_user_turn,
            turn_scopes=ctx.turn_scopes,
        )
        result = await self.commands.dispatch(cmd_ctx)
        if result is None:
            return CommandTurnResult(event="dispatch")

        ctx.outbound = result
        if cmd_ctx.raw.lower() == "/new":
            return CommandTurnResult(event="shortcut")

        input_persisted_early = self.persist_user_message(ctx.msg, session, _command=True)
        session.add_message("assistant", result.content, _command=True)
        self.save_session(session)
        self.clear_pending_user_turn(session)
        return CommandTurnResult(
            event="shortcut",
            input_persisted_early=input_persisted_early,
        )
