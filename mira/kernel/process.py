"""Agent process table primitives."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from itertools import count
from typing import Any, Literal

AgentProcessStatus = Literal["running", "waiting", "stopped", "terminated"]
AgentPriority = Literal["background", "interactive", "critical"]


@dataclass(slots=True)
class AgentContextSpace:
    """Virtual context address space for one agent process."""

    system_prompt: str = ""
    history_window: list[dict[str, Any]] = field(default_factory=list)
    memory_map: tuple[str, ...] = ()
    tool_caps: frozenset[str] = frozenset()

    def snapshot(self) -> dict[str, Any]:
        return {
            "system_prompt": self.system_prompt,
            "history_window": deepcopy(self.history_window),
            "memory_map": list(self.memory_map),
            "tool_caps": sorted(self.tool_caps),
        }


@dataclass(slots=True)
class AgentProcess:
    """One running or restorable agent process."""

    pid: str
    user: str
    goal: str
    context: AgentContextSpace = field(default_factory=AgentContextSpace)
    priority: AgentPriority = "interactive"
    model_hint: str = "auto"
    status: AgentProcessStatus = "waiting"
    tokens_consumed: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    stopped_reason: str = ""

    def snapshot(self) -> dict[str, Any]:
        return {
            "pid": self.pid,
            "user": self.user,
            "goal": self.goal,
            "priority": self.priority,
            "model_hint": self.model_hint,
            "status": self.status,
            "tokens_consumed": self.tokens_consumed,
            "context": self.context.snapshot(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "stopped_reason": self.stopped_reason,
        }


class ProcessTable:
    """In-memory process table for local agent process management."""

    def __init__(self, *, pid_prefix: str = "agent") -> None:
        self._pid_prefix = pid_prefix
        self._counter = count(1)
        self._processes: dict[str, AgentProcess] = {}

    def spawn(
        self,
        *,
        user: str,
        goal: str,
        context: AgentContextSpace | None = None,
        priority: AgentPriority = "interactive",
        model_hint: str = "auto",
    ) -> AgentProcess:
        pid = f"{self._pid_prefix}-{next(self._counter):04x}"
        process = AgentProcess(
            pid=pid,
            user=user,
            goal=goal,
            context=context or AgentContextSpace(),
            priority=priority,
            model_hint=model_hint,
            status="running",
        )
        self._processes[pid] = process
        return process

    def get(self, pid: str) -> AgentProcess | None:
        return self._processes.get(pid)

    def list(self) -> list[AgentProcess]:
        return sorted(self._processes.values(), key=lambda process: process.created_at)

    def kill(self, pid: str, *, reason: str = "terminated") -> dict[str, Any]:
        process = self._require(pid)
        process.status = "terminated"
        process.stopped_reason = reason
        process.updated_at = datetime.now()
        return process.snapshot()

    def stop_for_swap(self, pid: str, *, reason: str = "context switch") -> dict[str, Any]:
        process = self._require(pid)
        process.status = "stopped"
        process.stopped_reason = reason
        process.updated_at = datetime.now()
        return process.snapshot()

    def resume(self, pid: str) -> AgentProcess:
        process = self._require(pid)
        process.status = "running"
        process.stopped_reason = ""
        process.updated_at = datetime.now()
        return process

    def fork(
        self,
        pid: str,
        *,
        user: str | None = None,
        role: str | None = None,
    ) -> AgentProcess:
        source = self._require(pid)
        child_context = AgentContextSpace(
            system_prompt=source.context.system_prompt,
            history_window=deepcopy(source.context.history_window),
            memory_map=tuple(source.context.memory_map),
            tool_caps=frozenset(source.context.tool_caps),
        )
        child = self.spawn(
            user=user or source.user,
            goal=f"{source.goal} ({role})" if role else source.goal,
            context=child_context,
            priority=source.priority,
            model_hint=source.model_hint,
        )
        return child

    def _require(self, pid: str) -> AgentProcess:
        process = self._processes.get(pid)
        if process is None:
            raise KeyError(f"unknown agent process: {pid}")
        return process
