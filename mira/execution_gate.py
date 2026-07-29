"""Authoritative execution gate shared by the kernel, loop, and runner."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ExecutionGateSnapshot:
    state: str = "open"
    reason: str = "operator-ready"
    actor: str = "system"
    correlation_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    updated_at: float = field(default_factory=time.time)
    permits_turns: bool = True
    permits_tools: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "reason": self.reason,
            "actor": self.actor,
            "correlation_id": self.correlation_id,
            "updated_at": self.updated_at,
            "permits_turns": self.permits_turns,
            "permits_tools": self.permits_tools,
        }


class ExecutionGateClosedError(RuntimeError):
    """Raised when execution reaches a closed gate boundary."""

    def __init__(self, snapshot: ExecutionGateSnapshot, *, boundary: str) -> None:
        self.snapshot = snapshot
        self.boundary = boundary
        super().__init__(
            f"execution gate is {snapshot.state} at {boundary}: {snapshot.reason}"
        )


class ExecutionGate:
    """One mutable execution-plane gate for turn admission and tool execution."""

    def __init__(self) -> None:
        self._snapshot = ExecutionGateSnapshot()
        self._condition = asyncio.Condition()

    @property
    def snapshot(self) -> ExecutionGateSnapshot:
        return self._snapshot

    def snapshot_dict(self) -> dict[str, Any]:
        return self._snapshot.to_dict()

    def set_state(
        self,
        state: str,
        *,
        reason: str | None = None,
        actor: str = "operator",
        correlation_id: str | None = None,
    ) -> ExecutionGateSnapshot:
        if state not in {"open", "paused", "maintenance", "degraded"}:
            raise ValueError(f"unknown execution gate state: {state}")
        self._snapshot = ExecutionGateSnapshot(
            state=state,
            reason=reason or ("operator-ready" if state == "open" else "operator-requested"),
            actor=actor,
            correlation_id=correlation_id or uuid.uuid4().hex,
            permits_turns=state in {"open", "degraded"},
            permits_tools=state == "open",
        )
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return self._snapshot
        loop.create_task(self._notify_all())
        return self._snapshot

    async def _notify_all(self) -> None:
        async with self._condition:
            self._condition.notify_all()

    async def wait_for_turn_admission(self) -> ExecutionGateSnapshot:
        async with self._condition:
            while not self._snapshot.permits_turns:
                await self._condition.wait()
            return self._snapshot

    def assert_tools_allowed(self) -> ExecutionGateSnapshot:
        snapshot = self._snapshot
        if not snapshot.permits_tools:
            raise ExecutionGateClosedError(snapshot, boundary="pre-tool")
        return snapshot


DEFAULT_EXECUTION_GATE = ExecutionGate()
