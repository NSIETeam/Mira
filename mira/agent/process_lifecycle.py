"""Agent process lifecycle helpers for one message turn."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mira.agent.tools.registry import ToolRegistry
from mira.bus.events import InboundMessage
from mira.session.manager import SessionManager

if TYPE_CHECKING:
    from mira.kernel.process import AgentProcess, ProcessTable


@dataclass(slots=True)
class TurnProcessLifecycle:
    """Map an admitted turn onto the kernel process table."""

    sessions: SessionManager
    tools: ToolRegistry
    process_table: ProcessTable
    model_hint: Callable[[], str | None]
    token_usage: Callable[[], Mapping[str, int]]

    def spawn(self, msg: InboundMessage) -> AgentProcess:
        """Register one admitted turn as an agent process."""
        from mira.kernel.process import AgentContextSpace

        context = AgentContextSpace(tool_caps=frozenset(self.tools.tool_names))
        return self.process_table.spawn(
            user=msg.sender_id or "unknown",
            goal=msg.content[:200],
            context=context,
            priority="interactive",
            model_hint=self.model_hint(),
        )

    def complete(
        self,
        process: AgentProcess | None,
        session_key: str,
        *,
        reason: str,
    ) -> None:
        """Mark a turn process complete and persist its last snapshot."""
        if process is None:
            return
        self._refresh_context(process, session_key)
        self.process_table.kill(process.pid, reason=reason)
        self._persist_snapshot(process, session_key)

    def stop_for_swap(
        self,
        process: AgentProcess | None,
        session_key: str,
        *,
        reason: str,
    ) -> None:
        """Stop a process when an interrupted turn has preserved resumable state."""
        if process is None:
            return
        self._refresh_context(process, session_key)
        self.process_table.stop_for_swap(process.pid, reason=reason)
        self._persist_snapshot(process, session_key)

    def _refresh_context(self, process: AgentProcess, session_key: str) -> None:
        session = self.sessions.get_or_create(session_key)
        get_history = getattr(session, "get_history", None)
        if callable(get_history):
            history = get_history(max_messages=32)
        else:
            history = list(getattr(session, "messages", []))[-32:]
        process.context.history_window = history
        process.context.tool_caps = frozenset(self.tools.tool_names)
        process.tokens_consumed = sum(self.token_usage().values())

    def _persist_snapshot(self, process: AgentProcess, session_key: str) -> None:
        session = self.sessions.get_or_create(session_key)
        session.metadata["agent_process"] = process.snapshot()
        self.sessions.save(session)
