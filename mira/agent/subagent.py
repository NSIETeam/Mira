"""Subagent manager for background task execution."""

import asyncio
import json
import os
import tempfile
import time
import uuid
import warnings
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from mira.agent.hook import AgentHook, AgentHookContext
from mira.agent.maturity import apply_agent_role_to_task, resolve_agent_role_profile
from mira.agent.memory import MemoryStore
from mira.agent.runner import AgentRunner, AgentRunResult, AgentRunSpec
from mira.agent.tools.base import ToolResult
from mira.agent.tools.context import (
    RequestContext,
    ToolContext,
    bind_request_context,
    current_request_context,
    reset_request_context,
)
from mira.agent.tools.exec_session import ExecSessionManager
from mira.agent.tools.file_state import FileStates
from mira.agent.tools.loader import ToolLoader
from mira.agent.tools.registry import ToolRegistry
from mira.bus.events import InboundMessage
from mira.bus.queue import MessageBus
from mira.config.schema import AgentDefaults, ToolsConfig
from mira.execution_gate import ExecutionGate
from mira.providers.base import LLMProvider
from mira.security.workspace_access import (
    WorkspaceScope,
    bind_workspace_scope,
    reset_workspace_scope,
    workspace_sandbox_status,
)
from mira.utils.llm_runtime import LLMRuntime
from mira.utils.prompt_templates import render_template


@dataclass(frozen=True, slots=True)
class MemoryView:
    policy: str
    effective_layers: tuple[str, ...]
    parent_session_visible: bool
    history_log_visible: bool
    provenance: tuple[str, ...]

    def summary(self) -> str:
        layers = ", ".join(self.effective_layers) if self.effective_layers else "none"
        provenance = ", ".join(self.provenance) if self.provenance else "task only"
        return (
            f"policy={self.policy}; layers={layers}; "
            f"parent_session={'visible' if self.parent_session_visible else 'hidden'}; "
            f"history_log={'visible' if self.history_log_visible else 'hidden'}; "
            f"provenance={provenance}"
        )


@dataclass(slots=True)
class SubagentStatus:
    """Real-time status of a running subagent."""

    task_id: str
    label: str
    task_description: str
    started_at: float          # time.monotonic()
    phase: str = "initializing"  # initializing | awaiting_tools | tools_completed | final_response | done | error
    iteration: int = 0
    tool_events: list[dict[str, str]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    stop_reason: str | None = None
    error: str | None = None
    memory_policy: str = "default"
    inherited_memory_layers: list[str] = field(default_factory=list)
    role: str = "default"


@dataclass(slots=True)
class PendingSubagent:
    """Queued subagent request awaiting an execution slot."""

    task_id: str
    task: str
    label: str
    origin: dict[str, str]
    runtime: LLMRuntime
    origin_message_id: str | None = None
    workspace_scope: WorkspaceScope | None = None
    temperature: float | None = None
    queued_at: float = field(default_factory=time.monotonic)
    weight: int = 1
    memory_policy: str = "default"
    inherited_memory_layers: list[str] = field(default_factory=list)
    role: str = "default"


class _SubagentHook(AgentHook):
    """Hook for subagent execution — logs tool calls and updates status."""

    def __init__(self, task_id: str, status: SubagentStatus | None = None) -> None:
        super().__init__()
        self._task_id = task_id
        self._status = status

    async def before_execute_tools(self, context: AgentHookContext) -> None:
        for tool_call in context.tool_calls:
            args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
            logger.debug(
                "Subagent [{}] executing: {} with arguments: {}",
                self._task_id, tool_call.name, args_str,
            )

    async def after_iteration(self, context: AgentHookContext) -> None:
        if self._status is None:
            return
        self._status.iteration = context.iteration
        self._status.tool_events = list(context.tool_events)
        self._status.usage = dict(context.usage)
        if context.error:
            self._status.error = str(context.error)


class SubagentManager:
    """Manages background subagent execution."""

    _DEFAULT_SUBAGENT_MEMORY_MB = 10
    _DEFAULT_QUEUE_FACTOR = 4
    _DEFAULT_MEMORY_POLICY = "default"
    _SESSION_LOAD_PENALTY = 5.0
    _HOT_QUEUE_WEIGHT_THRESHOLD = 4
    _WARM_QUEUE_WEIGHT_THRESHOLD = 2
    _COLD_TO_WARM_PROMOTION_S = 15.0
    _WARM_TO_HOT_PROMOTION_S = 30.0
    _MEMORY_POLICY_LAYERS = {
        "task_only": [],
        "default": [
            "repo_instructions",
            "user_overlay",
            "topic_memory",
            "knowledge_graph",
        ],
        "full": [
            "repo_instructions",
            "user_overlay",
            "topic_memory",
            "knowledge_graph",
            "session_scratchpad",
        ],
    }

    @staticmethod
    def _host_memory_mb() -> int | None:
        try:
            page_size = os.sysconf("SC_PAGE_SIZE")
            page_count = os.sysconf("SC_PHYS_PAGES")
        except (AttributeError, ValueError, OSError):
            return None
        if not isinstance(page_size, int) or not isinstance(page_count, int):
            return None
        total_bytes = page_size * page_count
        if total_bytes <= 0:
            return None
        return total_bytes // (1024 * 1024)

    @classmethod
    def _recommended_concurrency(cls) -> int:
        cpu = os.cpu_count() or 2
        if cpu <= 2:
            cpu_limit = 1
        elif cpu <= 4:
            cpu_limit = 2
        elif cpu <= 8:
            cpu_limit = 3
        else:
            cpu_limit = 4
        memory_mb = cls._host_memory_mb()
        if memory_mb is None:
            return cpu_limit
        reserve_mb = 512
        available_mb = max(memory_mb - reserve_mb, cls._DEFAULT_SUBAGENT_MEMORY_MB)
        memory_limit = max(1, available_mb // cls._DEFAULT_SUBAGENT_MEMORY_MB)
        return max(1, min(cpu_limit, memory_limit))

    @classmethod
    def _recommended_queue_limit(cls, concurrency: int) -> int:
        base = max(1, concurrency) * cls._DEFAULT_QUEUE_FACTOR
        memory_mb = cls._host_memory_mb()
        if memory_mb is None:
            return base
        reserve_mb = 512
        available_mb = max(memory_mb - reserve_mb, cls._DEFAULT_SUBAGENT_MEMORY_MB)
        memory_budget_tasks = max(1, available_mb // cls._DEFAULT_SUBAGENT_MEMORY_MB)
        return max(concurrency, min(base, memory_budget_tasks))

    @classmethod
    def _recommended_session_queue_limit(cls, concurrency: int) -> int:
        if concurrency <= 1:
            return 1
        return max(1, min(max(2, concurrency), concurrency * 2))

    @classmethod
    def _recommended_session_running_limit(cls, concurrency: int) -> int:
        return max(1, concurrency)

    @classmethod
    def _normalize_memory_policy(cls, memory_policy: str | None) -> str:
        normalized = str(memory_policy or cls._DEFAULT_MEMORY_POLICY).strip().lower()
        if normalized == "auto":
            return cls._DEFAULT_MEMORY_POLICY
        if normalized not in cls._MEMORY_POLICY_LAYERS:
            return cls._DEFAULT_MEMORY_POLICY
        return normalized

    @classmethod
    def _memory_layers_for_policy(cls, memory_policy: str | None) -> list[str]:
        normalized = cls._normalize_memory_policy(memory_policy)
        return list(cls._MEMORY_POLICY_LAYERS.get(normalized, cls._MEMORY_POLICY_LAYERS[cls._DEFAULT_MEMORY_POLICY]))

    @classmethod
    def _memory_view_for_policy(cls, memory_policy: str | None) -> MemoryView:
        normalized = cls._normalize_memory_policy(memory_policy)
        layers = tuple(cls._memory_layers_for_policy(normalized))
        full = normalized == "full"
        return MemoryView(
            policy=normalized,
            effective_layers=layers,
            parent_session_visible=full,
            history_log_visible=full,
            provenance=tuple(layer for layer in layers if layer != "session_scratchpad"),
        )

    @classmethod
    def _host_strategy_profile(cls) -> str:
        cpu = os.cpu_count() or 2
        memory_mb = cls._host_memory_mb() or 0
        if cpu <= 2 or (memory_mb and memory_mb < 4096):
            return "conservative"
        if cpu >= 8 and memory_mb >= 16384:
            return "throughput_shared"
        return "balanced_shared"

    @classmethod
    def _host_strategy_reason(cls) -> str:
        cpu = os.cpu_count() or 2
        memory_mb = cls._host_memory_mb()
        strategy = cls._host_strategy_profile()
        memory_label = f"{memory_mb}MB" if memory_mb is not None else "unknown-memory"
        if strategy == "conservative":
            return f"low host headroom cpu={cpu} memory={memory_label}"
        if strategy == "throughput_shared":
            return f"high shared capacity cpu={cpu} memory={memory_label}"
        return f"mixed shared host cpu={cpu} memory={memory_label}"

    def __init__(
        self,
        provider: LLMProvider | None = None,
        workspace: Path | None = None,
        bus: MessageBus | None = None,
        max_tool_result_chars: int | None = None,
        model: str | None = None,
        tools_config: ToolsConfig | None = None,
        restrict_to_workspace: bool = False,
        disabled_skills: list[str] | None = None,
        max_iterations: int | None = None,
        max_concurrent_subagents: int | None = None,
        fail_on_tool_error: bool | None = None,
        execution_gate: ExecutionGate | None = None,
        llm_wall_timeout_for_session: Callable[[str | None], float | None] | None = None,
    ):
        if workspace is None:
            raise TypeError("SubagentManager.__init__() missing required argument: 'workspace'")
        if not isinstance(workspace, Path):
            try:
                workspace = Path(workspace)
            except TypeError:
                workspace = Path(tempfile.mkdtemp(prefix="mira-subagent-"))
        if bus is None:
            raise TypeError("SubagentManager.__init__() missing required argument: 'bus'")
        if max_tool_result_chars is None:
            raise TypeError(
                "SubagentManager.__init__() missing required argument: 'max_tool_result_chars'"
            )
        if model is not None and provider is None:
            raise TypeError("SubagentManager model compatibility argument requires provider")

        defaults = AgentDefaults()
        self._compat_runtime: LLMRuntime | None = None
        if provider is not None:
            warnings.warn(
                "SubagentManager provider/model constructor arguments are deprecated; "
                "pass runtime=... to spawn() instead",
                DeprecationWarning,
                stacklevel=2,
            )
            self._compat_runtime = LLMRuntime.capture(
                provider,
                model or provider.get_default_model(),
                context_window_tokens=defaults.context_window_tokens,
            )
        from mira.config.schema import ensure_tool_config_refs

        ensure_tool_config_refs()
        self.workspace = workspace
        self.bus = bus
        self.tools_config = tools_config or ToolsConfig()
        self.max_tool_result_chars = max_tool_result_chars
        self.restrict_to_workspace = restrict_to_workspace
        self.disabled_skills = set(disabled_skills or [])
        self.max_iterations = (
            max_iterations
            if max_iterations is not None
            else defaults.max_tool_iterations
        )
        configured_subagents = (
            max_concurrent_subagents
            if max_concurrent_subagents is not None
            else defaults.max_concurrent_subagents
        )
        self.max_concurrent_subagents = (
            configured_subagents
            if configured_subagents > 0
            else self._recommended_concurrency()
        )
        self.subagent_memory_mb = self._DEFAULT_SUBAGENT_MEMORY_MB
        self.max_pending_subagents = self._recommended_queue_limit(self.max_concurrent_subagents)
        self.max_pending_subagents_per_session = self._recommended_session_queue_limit(
            self.max_concurrent_subagents
        )
        self.max_running_subagents_per_session = self._recommended_session_running_limit(
            self.max_concurrent_subagents
        )
        self.fail_on_tool_error = (
            fail_on_tool_error
            if fail_on_tool_error is not None
            else defaults.fail_on_tool_error
        )
        self.runner = AgentRunner()
        self._exec_session_manager = ExecSessionManager()
        self.execution_gate = execution_gate or ExecutionGate()
        self._llm_wall_timeout_for_session = llm_wall_timeout_for_session
        self._running_tasks: dict[str, asyncio.Task[str]] = {}
        self._task_statuses: dict[str, SubagentStatus] = {}
        self._session_tasks: dict[str, set[str]] = {}  # session_key -> {task_id, ...}
        self._pending_hot: list[PendingSubagent] = []
        self._pending_warm: list[PendingSubagent] = []
        self._pending_cold: list[PendingSubagent] = []
        self._dispatch_lock = asyncio.Lock()

    def set_provider(self, provider: LLMProvider, model: str) -> None:
        """Update the deprecated runtime source used by legacy ``spawn`` calls."""
        warnings.warn(
            "SubagentManager.set_provider() is deprecated; pass runtime=... to spawn() instead",
            DeprecationWarning,
            stacklevel=2,
        )
        context_window_tokens = (
            self._compat_runtime.context_window_tokens
            if self._compat_runtime is not None
            else AgentDefaults().context_window_tokens
        )
        self._compat_runtime = LLMRuntime.capture(
            provider,
            model,
            context_window_tokens=context_window_tokens,
        )

    def _compat_spawn_runtime(self) -> LLMRuntime:
        runtime = self._compat_runtime
        if runtime is None:
            raise TypeError(
                "SubagentManager.spawn() missing required keyword-only argument: 'runtime'"
            )
        warnings.warn(
            "SubagentManager.spawn() without runtime is deprecated; pass runtime=... explicitly",
            DeprecationWarning,
            stacklevel=3,
        )
        return LLMRuntime.capture(
            runtime.provider,
            runtime.model,
            context_window_tokens=runtime.context_window_tokens,
        )

    def _subagent_tools_config(self) -> ToolsConfig:
        """Build a ToolsConfig scoped for subagent use."""
        return ToolsConfig(
            exec=self.tools_config.exec,
            web=self.tools_config.web,
            file=self.tools_config.file,
            restrict_to_workspace=True,
        )

    def _build_tools(
        self,
        workspace: Path | None = None,
        tools_config: ToolsConfig | None = None,
    ) -> ToolRegistry:
        """Build an isolated subagent tool registry via ToolLoader."""
        root = self.workspace if workspace is None else workspace
        registry = ToolRegistry()
        cfg = tools_config if tools_config is not None else self._subagent_tools_config()
        ctx = ToolContext(
            config=cfg,
            workspace=str(root.resolve()),
            exec_session_manager=self._exec_session_manager,
            file_state_store=FileStates(),
            workspace_sandbox=workspace_sandbox_status(
                restrict_to_workspace=cfg.restrict_to_workspace,
                workspace=root,
            ),
        )
        ToolLoader().load(ctx, registry, scope="subagent")
        return registry

    async def spawn(
        self,
        task: str,
        label: str | None = None,
        origin_channel: str = "cli",
        origin_chat_id: str = "direct",
        session_key: str | None = None,
        origin_message_id: str | None = None,
        temperature: float | None = None,
        workspace_scope: WorkspaceScope | None = None,
        weight: int = 1,
        memory_policy: str | None = None,
        role: str | None = None,
        *,
        runtime: LLMRuntime | None = None,
    ) -> str:
        """Spawn a subagent to execute a task in the background."""
        if runtime is None:
            runtime = self._compat_spawn_runtime()
        if temperature is not None:
            runtime = runtime.with_generation_overrides(temperature=temperature)
        task_id = str(uuid.uuid4())[:8]
        display_label = label or task[:30] + ("..." if len(task) > 30 else "")
        origin = {"channel": origin_channel, "chat_id": origin_chat_id}
        if session_key is not None:
            origin["session_key"] = session_key
        resolved_memory_policy = self._normalize_memory_policy(memory_policy)
        role_profile = resolve_agent_role_profile(role)
        if role_profile is not None and memory_policy in {None, "auto"}:
            resolved_memory_policy = role_profile.default_memory_policy
        resolved_role = role_profile.name if role_profile is not None else "default"
        inherited_memory_layers = self._memory_layers_for_policy(resolved_memory_policy)

        status = SubagentStatus(
            task_id=task_id,
            label=display_label,
            task_description=task,
            started_at=time.monotonic(),
            memory_policy=resolved_memory_policy,
            inherited_memory_layers=inherited_memory_layers,
            role=resolved_role,
        )
        self._task_statuses[task_id] = status
        pending = PendingSubagent(
            task_id=task_id,
            task=task,
            label=display_label,
            origin=origin,
            runtime=runtime,
            origin_message_id=origin_message_id,
            workspace_scope=workspace_scope,
            temperature=temperature,
            weight=max(1, weight),
            memory_policy=resolved_memory_policy,
            inherited_memory_layers=inherited_memory_layers,
            role=resolved_role,
        )
        if not await self._enqueue_or_start(pending, status):
            if status.phase == "error":
                error_detail = status.error or "shared queue rejected the request"
                session_key = origin.get("session_key")
                session_queue = self._pending_count_for_session(session_key)
                session_fragment = (
                    f", session queued: {session_queue}/{self.max_pending_subagents_per_session}"
                    if session_key
                    else ""
                )
                return (
                    f"Subagent [{display_label}] rejected. {error_detail}. "
                    f"Running: {len(self._running_tasks)}/{self.max_concurrent_subagents}, "
                    f"queued: {self._pending_count()}/{self.max_pending_subagents}"
                    f"{session_fragment}."
                )
            queued = self._pending_count()
            session_key = origin.get("session_key")
            running_for_session = (
                self.get_running_count_by_session(session_key)
                if session_key
                else 0
            )
            session_reason = (
                f" Session running limit active: {running_for_session}/{self.max_running_subagents_per_session}."
                if session_key and running_for_session >= self.max_running_subagents_per_session
                else ""
            )
            logger.info("Queued subagent [{}]: {}", task_id, display_label)
            return (
                f"Subagent [{display_label}] queued (id: {task_id}). "
                f"It will start automatically when a shared execution slot is free. "
                f"Queue depth: {queued}. Memory policy: {resolved_memory_policy}."
                f"{session_reason}"
            )

        logger.info("Spawned subagent [{}]: {}", task_id, display_label)
        return (
            f"Subagent [{display_label}] started (id: {task_id}). "
            f"Memory policy: {resolved_memory_policy}. I'll notify you when it completes."
        )

    async def _enqueue_or_start(
        self,
        pending: PendingSubagent,
        status: SubagentStatus,
    ) -> bool:
        async with self._dispatch_lock:
            session_key = pending.origin.get("session_key")
            if (
                session_key
                    and self._running_count_by_session(session_key)
                >= self.max_running_subagents_per_session
            ):
                if self._pending_count() >= self.max_pending_subagents:
                    status.phase = "error"
                    status.error = (
                        "queued-subagent limit reached; host is saturated and the shared queue is full"
                    )
                    self._task_statuses.pop(pending.task_id, None)
                    return False
                status.phase = "queued"
                self._push_pending(pending)
                if session_key:
                    self._session_tasks.setdefault(session_key, set()).add(pending.task_id)
                return False
            if len(self._running_tasks) >= self.max_concurrent_subagents:
                if self._pending_count() >= self.max_pending_subagents:
                    status.phase = "error"
                    status.error = (
                        "queued-subagent limit reached; host is saturated and the shared queue is full"
                    )
                    self._task_statuses.pop(pending.task_id, None)
                    return False
                session_key = pending.origin.get("session_key")
                if (
                    session_key
                    and self._pending_count_for_session(session_key)
                    >= self.max_pending_subagents_per_session
                ):
                    status.phase = "error"
                    status.error = (
                        "session queued-subagent limit reached; this session already occupies "
                        "its fair share of the shared queue"
                    )
                    self._task_statuses.pop(pending.task_id, None)
                    return False
                status.phase = "queued"
                self._push_pending(pending)
                if session_key:
                    self._session_tasks.setdefault(session_key, set()).add(pending.task_id)
                return False
            self._start_pending_locked(pending, status)
            return True

    def _start_pending_locked(
        self,
        pending: PendingSubagent,
        status: SubagentStatus,
    ) -> None:
        session_key = pending.origin.get("session_key")
        bg_task = asyncio.create_task(
            self._run_subagent(
                pending.task_id,
                pending.task,
                pending.label,
                pending.origin,
                status,
                pending.runtime,
                pending.origin_message_id,
                pending.workspace_scope,
                pending.memory_policy,
                pending.inherited_memory_layers,
                pending.role,
            )
        )
        self._running_tasks[pending.task_id] = bg_task
        status.phase = "initializing"
        if session_key:
            self._session_tasks.setdefault(session_key, set()).add(pending.task_id)

        task_id = pending.task_id
        def _cleanup(_: asyncio.Task[str]) -> None:
            self._running_tasks.pop(task_id, None)
            if session_key and (ids := self._session_tasks.get(session_key)):
                ids.discard(task_id)
                if not ids:
                    del self._session_tasks[session_key]
            self._task_statuses.pop(task_id, None)
            asyncio.create_task(self._dispatch_pending())
        bg_task.add_done_callback(_cleanup)

    async def _dispatch_pending(self) -> None:
        async with self._dispatch_lock:
            while self._pending_count() and len(self._running_tasks) < self.max_concurrent_subagents:
                self._promote_pending_locked()
                deferred: list[PendingSubagent] = []
                pending: PendingSubagent | None = None
                while True:
                    candidate = self._pop_next_pending_locked()
                    if candidate is None:
                        break
                    session_key = candidate.origin.get("session_key")
                    if (
                        session_key
                        and self.get_running_count_by_session(session_key)
                        >= self.max_running_subagents_per_session
                    ):
                        deferred.append(candidate)
                        continue
                    pending = candidate
                    break
                for item in deferred:
                    self._push_pending(item)
                if pending is None:
                    break
                status = self._task_statuses.get(pending.task_id)
                if status is None:
                    continue
                self._start_pending_locked(pending, status)

    def _pick_next_pending_index(self, queue: list[PendingSubagent]) -> int:
        best_index = 0
        best_score = float("-inf")
        now = time.monotonic()
        for index, pending in enumerate(queue):
            age = max(now - pending.queued_at, 0.0)
            session_key = pending.origin.get("session_key")
            session_load = self._running_count_by_session(session_key) + self._pending_count_for_session(session_key)
            fairness_penalty = max(0, session_load - 1) * self._SESSION_LOAD_PENALTY
            score = (age * max(1, pending.weight)) - fairness_penalty
            if score > best_score:
                best_score = score
                best_index = index
        return best_index

    def _pending_count(self) -> int:
        return len(self._pending_hot) + len(self._pending_warm) + len(self._pending_cold)

    def _pending_count_for_session(self, session_key: str | None) -> int:
        if not session_key:
            return 0
        total = 0
        for pending in [*self._pending_hot, *self._pending_warm, *self._pending_cold]:
            if pending.origin.get("session_key") == session_key:
                total += 1
        return total

    def _pending_sessions_summary(self, limit: int = 3) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for pending in [*self._pending_hot, *self._pending_warm, *self._pending_cold]:
            session_key = str(pending.origin.get("session_key") or "").strip()
            if not session_key:
                continue
            counts[session_key] = counts.get(session_key, 0) + 1
        return [
            {"session_key": session_key, "queued": count}
            for session_key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
        ]

    def _running_sessions_summary(self, limit: int = 3) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for session_key in sorted(self._session_tasks.keys()):
            running = self.get_running_count_by_session(session_key)
            if running <= 0:
                continue
            rows.append({
                "session_key": session_key,
                "running": running,
            })
        rows.sort(key=lambda item: (-int(item["running"]), str(item["session_key"])))
        return rows[:limit]

    def _session_load_summary(self, limit: int = 3) -> list[dict[str, Any]]:
        session_keys = {
            str(pending.origin.get("session_key") or "").strip()
            for pending in [*self._pending_hot, *self._pending_warm, *self._pending_cold]
        }
        session_keys.update(self._session_tasks.keys())
        rows: list[dict[str, Any]] = []
        for session_key in session_keys:
            if not session_key:
                continue
            running = self.get_running_count_by_session(session_key)
            queued = self._pending_count_for_session(session_key)
            total = running + queued
            if total <= 0:
                continue
            rows.append({
                "session_key": session_key,
                "running": running,
                "queued": queued,
                "total": total,
                "running_limited": running >= self.max_running_subagents_per_session,
            })
        rows.sort(key=lambda item: (-int(item["total"]), str(item["session_key"])))
        return rows[:limit]

    def _push_pending(self, pending: PendingSubagent) -> None:
        if pending.weight >= self._HOT_QUEUE_WEIGHT_THRESHOLD:
            self._pending_hot.append(pending)
        elif pending.weight >= self._WARM_QUEUE_WEIGHT_THRESHOLD:
            self._pending_warm.append(pending)
        else:
            self._pending_cold.append(pending)

    def _promote_pending_locked(self) -> None:
        now = time.monotonic()
        keep_cold: list[PendingSubagent] = []
        for pending in self._pending_cold:
            age = max(now - pending.queued_at, 0.0)
            if age >= self._COLD_TO_WARM_PROMOTION_S:
                self._pending_warm.append(pending)
            else:
                keep_cold.append(pending)
        self._pending_cold = keep_cold

        keep_warm: list[PendingSubagent] = []
        for pending in self._pending_warm:
            age = max(now - pending.queued_at, 0.0)
            if age >= self._WARM_TO_HOT_PROMOTION_S:
                self._pending_hot.append(pending)
            else:
                keep_warm.append(pending)
        self._pending_warm = keep_warm

    def _pop_next_pending_locked(self) -> PendingSubagent | None:
        if self._pending_hot:
            index = self._pick_next_pending_index(self._pending_hot)
            return self._pending_hot.pop(index)
        if self._pending_warm:
            index = self._pick_next_pending_index(self._pending_warm)
            return self._pending_warm.pop(index)
        if self._pending_cold:
            index = self._pick_next_pending_index(self._pending_cold)
            return self._pending_cold.pop(index)
        return None

    async def run_inline(
        self,
        task: str,
        label: str | None = None,
        origin_channel: str = "cli",
        origin_chat_id: str = "direct",
        session_key: str | None = None,
        origin_message_id: str | None = None,
        temperature: float | None = None,
        workspace_scope: WorkspaceScope | None = None,
        memory_policy: str | None = None,
        role: str | None = None,
        *,
        runtime: LLMRuntime | None = None,
    ) -> str:
        """Run a subagent synchronously and return its result to the caller."""
        if runtime is None:
            runtime = self._compat_spawn_runtime()
        if temperature is not None:
            runtime = runtime.with_generation_overrides(temperature=temperature)
        task_id = str(uuid.uuid4())[:8]
        display_label = label or task[:30] + ("..." if len(task) > 30 else "")
        origin = {
            "channel": origin_channel,
            "chat_id": origin_chat_id,
        }
        if session_key is not None:
            origin["session_key"] = session_key
        resolved_memory_policy = self._normalize_memory_policy(memory_policy)
        role_profile = resolve_agent_role_profile(role)
        if role_profile is not None and memory_policy in {None, "auto"}:
            resolved_memory_policy = role_profile.default_memory_policy
        resolved_role = role_profile.name if role_profile is not None else "default"
        inherited_memory_layers = self._memory_layers_for_policy(resolved_memory_policy)
        status = SubagentStatus(
            task_id=task_id,
            label=display_label,
            task_description=task,
            started_at=time.monotonic(),
            memory_policy=resolved_memory_policy,
            inherited_memory_layers=inherited_memory_layers,
            role=resolved_role,
        )
        running_for_session = self._running_count_by_session(session_key) if session_key else 0
        if len(self._running_tasks) >= self.max_concurrent_subagents:
            self._task_statuses.pop(task_id, None)
            return ToolResult.error(
                "Cannot run inline subagent: concurrency limit reached; shared running limit reached "
                f"({len(self._running_tasks)}/{self.max_concurrent_subagents})."
            )
        if session_key and running_for_session >= self.max_running_subagents_per_session:
            self._task_statuses.pop(task_id, None)
            return ToolResult.error(
                "Cannot run inline subagent: session running limit reached "
                f"({running_for_session}/{self.max_running_subagents_per_session})."
            )
        self._task_statuses[task_id] = status
        logger.info("Running inline subagent [{}]: {}", task_id, display_label)
        inline_task = asyncio.create_task(
            self._run_subagent(
                task_id,
                task,
                display_label,
                origin,
                status,
                runtime,
                origin_message_id,
                workspace_scope,
                resolved_memory_policy,
                inherited_memory_layers,
                resolved_role,
                announce=False,
            )
        )
        self._running_tasks[task_id] = inline_task
        if session_key:
            self._session_tasks.setdefault(session_key, set()).add(task_id)
        try:
            result = await inline_task
            if status.phase == "error" or status.stop_reason in {"error", "tool_error"}:
                return ToolResult.error(result)
            return result
        finally:
            self._running_tasks.pop(task_id, None)
            self._task_statuses.pop(task_id, None)
            if session_key and (ids := self._session_tasks.get(session_key)):
                ids.discard(task_id)
                if not ids:
                    del self._session_tasks[session_key]

    async def _run_subagent(
        self,
        task_id: str,
        task: str,
        label: str,
        origin: dict[str, str],
        status: SubagentStatus,
        runtime: LLMRuntime,
        origin_message_id: str | None = None,
        workspace_scope: WorkspaceScope | None = None,
        memory_policy: str = _DEFAULT_MEMORY_POLICY,
        inherited_memory_layers: list[str] | None = None,
        role: str = "default",
        *,
        announce: bool = True,
    ) -> str:
        """Execute the subagent task and announce the result."""
        logger.info("Subagent [{}] starting task: {}", task_id, label)

        async def _on_checkpoint(payload: dict[str, Any]) -> None:
            status.phase = payload.get("phase", status.phase)
            status.iteration = payload.get("iteration", status.iteration)

        try:
            root = workspace_scope.project_path if workspace_scope is not None else self.workspace
            cfg = None
            if workspace_scope is not None:
                cfg = self._subagent_tools_config()
                cfg.restrict_to_workspace = workspace_scope.restrict_to_workspace
            # Construct from the agent workspace; the bound scope below supplies the project cwd.
            sess_key = origin.get("session_key")
            tools = self._build_tools(tools_config=cfg)
            system_prompt = self._build_subagent_prompt(
                workspace=root,
                session_key=sess_key,
                memory_policy=memory_policy,
                inherited_memory_layers=inherited_memory_layers or [],
            )
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": apply_agent_role_to_task(task, role)},
            ]

            llm_timeout = (
                self._llm_wall_timeout_for_session(sess_key)
                if self._llm_wall_timeout_for_session
                else None
            )
            parent_ctx = current_request_context()
            request_token = bind_request_context(RequestContext(
                channel=origin["channel"],
                chat_id=origin["chat_id"],
                message_id=origin_message_id,
                session_key=sess_key,
                runtime=runtime,
                policy=getattr(parent_ctx, "policy", None),
            ))
            token = bind_workspace_scope(workspace_scope) if workspace_scope is not None else None
            try:
                result = await self.runner.run(AgentRunSpec(
                    initial_messages=messages,
                    tools=tools,
                    runtime=runtime,
                    max_iterations=self.max_iterations,
                    max_tool_result_chars=self.max_tool_result_chars,
                    hook=_SubagentHook(task_id, status),
                    max_iterations_message="Task completed but no final response was generated.",
                    finalize_on_max_iterations=False,
                    error_message=None,
                    fail_on_tool_error=self.fail_on_tool_error,
                    checkpoint_callback=_on_checkpoint,
                    session_key=sess_key,
                    workspace=root,
                    llm_timeout_s=llm_timeout,
                    execution_gate=self.execution_gate,
                ))
            finally:
                if token is not None:
                    reset_workspace_scope(token)
                try:
                    reset_request_context(request_token)
                except ValueError:
                    logger.debug("Subagent [{}] request context already detached", task_id)
            status.phase = "done"
            status.stop_reason = result.stop_reason

            if result.stop_reason == "tool_error":
                status.tool_events = list(result.tool_events)
                final_result = self._format_partial_progress(result)
                final_status = "error"
            elif result.stop_reason == "error":
                final_result = result.error or "Error: subagent execution failed."
                final_status = "error"
            else:
                final_result = result.final_content or "Task completed but no final response was generated."
                final_status = "ok"
                logger.info("Subagent [{}] completed successfully", task_id)
            if announce:
                await self._announce_result(
                    task_id,
                    label,
                    task,
                    final_result,
                    origin,
                    final_status,
                    origin_message_id,
                )
            MemoryStore(self.workspace).write_subagent_memory(
                session_key=sess_key,
                task_id=task_id,
                label=label,
                memory_policy=memory_policy,
                inherited_memory_layers=inherited_memory_layers or [],
                task=task,
                result=final_result,
                status=final_status,
            )
            return final_result

        except Exception as e:
            status.phase = "error"
            status.error = str(e)
            logger.exception("Subagent [{}] failed", task_id)
            final_result = f"Error: {e}"
            MemoryStore(self.workspace).write_subagent_memory(
                session_key=origin.get("session_key"),
                task_id=task_id,
                label=label,
                memory_policy=memory_policy,
                inherited_memory_layers=inherited_memory_layers or [],
                task=task,
                result=final_result,
                status="error",
            )
            if announce:
                await self._announce_result(
                    task_id,
                    label,
                    task,
                    final_result,
                    origin,
                    "error",
                    origin_message_id,
                )
            return final_result

    async def _announce_result(
        self,
        task_id: str,
        label: str,
        task: str,
        result: str,
        origin: dict[str, str],
        status: str,
        origin_message_id: str | None = None,
    ) -> None:
        """Announce the subagent result to the main agent via the message bus."""
        status_text = "completed successfully" if status == "ok" else "failed"

        announce_content = render_template(
            "agent/subagent_announce.md",
            label=label,
            status_text=status_text,
            task=task,
            result=result,
        )

        # Inject as system message to trigger main agent.
        # Use session_key_override to align with the main agent's effective
        # session key (which accounts for unified sessions) so the result is
        # routed to the correct pending queue (mid-turn injection) instead of
        # being dispatched as a competing independent task.
        override = origin.get("session_key") or f"{origin['channel']}:{origin['chat_id']}"
        metadata: dict[str, Any] = {
            "injected_event": "subagent_result",
            "subagent_task_id": task_id,
        }
        if origin_message_id:
            metadata["origin_message_id"] = origin_message_id
        msg = InboundMessage(
            channel="system",
            sender_id="subagent",
            chat_id=f"{origin['channel']}:{origin['chat_id']}",
            content=announce_content,
            session_key_override=override,
            metadata=metadata,
        )

        await self.bus.publish_inbound(msg)
        logger.debug("Subagent [{}] announced result to {}:{}", task_id, origin['channel'], origin['chat_id'])

    @staticmethod
    def _format_partial_progress(result: AgentRunResult) -> str:
        completed = [e for e in result.tool_events if e["status"] == "ok"]
        failure = next((e for e in reversed(result.tool_events) if e["status"] == "error"), None)
        lines: list[str] = []
        if completed:
            lines.append("Completed steps:")
            for event in completed[-3:]:
                lines.append(f"- {event['name']}: {event['detail']}")
        if failure:
            if lines:
                lines.append("")
            lines.append("Failure:")
            lines.append(f"- {failure['name']}: {failure['detail']}")
        if result.error and not failure:
            if lines:
                lines.append("")
            lines.append("Failure:")
            lines.append(f"- {result.error}")
        return "\n".join(lines) or (result.error or "Error: subagent execution failed.")

    def _build_subagent_prompt(
        self,
        workspace: Path | None = None,
        session_key: str | None = None,
        memory_policy: str = _DEFAULT_MEMORY_POLICY,
        inherited_memory_layers: list[str] | None = None,
        role: str = "default",
    ) -> str:
        """Build a focused system prompt for the subagent."""
        from mira.agent.skills import SkillsLoader

        agent_workspace = self.workspace.expanduser().resolve()
        project_workspace = workspace.expanduser().resolve() if workspace else agent_workspace
        memory_view = self._memory_view_for_policy(memory_policy)
        skills_summary = SkillsLoader(
            self.workspace,
            disabled_skills=self.disabled_skills,
        ).build_skills_summary()
        return render_template(
            "agent/subagent_system.md",
            workspace=str(project_workspace),
            agent_workspace=str(agent_workspace),
            memory_view=memory_view.summary(),
            history_log=str(agent_workspace / "memory" / "history.jsonl"),
            history_log_visible=session_key is None,
            parent_session_ref="[redacted]" if memory_view.parent_session_visible and session_key else "",
            memory_policy=memory_policy,
            inherited_memory_layers=", ".join(inherited_memory_layers or []) or "none",
            subagent_role=role,
            skills_summary=skills_summary or "",
        )

    async def cancel_by_session(self, session_key: str) -> int:
        """Cancel all subagents for the given session. Returns count cancelled."""
        queued_ids = {
            pending.task_id
            for pending in [*self._pending_hot, *self._pending_warm, *self._pending_cold]
            if pending.origin.get("session_key") == session_key
        }
        if queued_ids:
            self._pending_hot = [
                pending for pending in self._pending_hot
                if pending.task_id not in queued_ids
            ]
            self._pending_warm = [
                pending for pending in self._pending_warm
                if pending.task_id not in queued_ids
            ]
            self._pending_cold = [
                pending for pending in self._pending_cold
                if pending.task_id not in queued_ids
            ]
            for task_id in queued_ids:
                self._task_statuses.pop(task_id, None)
            if session_key in self._session_tasks:
                self._session_tasks[session_key].difference_update(queued_ids)
                if not self._session_tasks[session_key]:
                    del self._session_tasks[session_key]
        tasks = [self._running_tasks[tid] for tid in self._session_tasks.get(session_key, [])
                 if tid in self._running_tasks and not self._running_tasks[tid].done()]
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await self._exec_session_manager.terminate_by_owner(session_key)
        return len(tasks) + len(queued_ids)

    async def close(self) -> None:
        """Cancel running subagents and close their shared exec sessions."""
        self._pending_hot.clear()
        self._pending_warm.clear()
        self._pending_cold.clear()
        tasks = [task for task in self._running_tasks.values() if not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await self._exec_session_manager.close_all()

    def get_running_count(self) -> int:
        """Return the number of active subagents, including queued requests."""
        running = sum(1 for task in self._running_tasks.values() if not task.done())
        queued = self._pending_count() if running else 0
        return running + queued

    def get_running_count_by_session(self, session_key: str) -> int:
        """Return active subagents for a session, including queued requests."""
        tids = self._session_tasks.get(session_key, set())
        queued = {
            pending.task_id
            for pending in [*self._pending_hot, *self._pending_warm, *self._pending_cold]
            if pending.origin.get("session_key") == session_key
        }
        running = {
            tid
            for tid in tids
            if tid in self._running_tasks and not self._running_tasks[tid].done()
        }
        return len(running | (queued if running else set()))

    def _running_count_by_session(self, session_key: str | None) -> int:
        if not session_key:
            return 0
        tids = self._session_tasks.get(session_key, set())
        return sum(
            1 for tid in tids
            if tid in self._running_tasks and not self._running_tasks[tid].done()
        )

    def status_snapshot(self, session_key: str | None = None) -> list[dict[str, Any]]:
        """Project running subagents into an operator-facing snapshot."""
        task_ids = (
            sorted(self._session_tasks.get(session_key, set()))
            if session_key is not None
            else sorted(self._task_statuses.keys())
        )
        rows: list[dict[str, Any]] = []
        for task_id in task_ids:
            status = self._task_statuses.get(task_id)
            if status is None:
                continue
            rows.append(
                {
                    "task_id": status.task_id,
                    "label": status.label,
                    "task_description": status.task_description,
                    "phase": status.phase,
                    "iteration": status.iteration,
                    "tool_events": [dict(event) for event in list(status.tool_events)[-4:]],
                    "usage": dict(status.usage),
                    "stop_reason": status.stop_reason,
                    "error": status.error,
                    "queued": status.phase == "queued",
                    "memory_policy": status.memory_policy,
                    "inherited_memory_layers": list(status.inherited_memory_layers),
                }
            )
        return rows

    def scheduler_snapshot(self) -> dict[str, Any]:
        """Return lightweight scheduler pressure indicators."""
        running = len(self._running_tasks)
        running_limit = self.max_concurrent_subagents
        queued = self._pending_count()
        queue_limit = self.max_pending_subagents
        if queue_limit > 0 and queued >= queue_limit:
            pressure = "saturated"
        elif queued > running_limit:
            pressure = "busy"
        else:
            pressure = "steady"
        return {
            "running": running,
            "running_limit": running_limit,
            "queued": queued,
            "queued_hot": len(self._pending_hot),
            "queued_warm": len(self._pending_warm),
            "queued_cold": len(self._pending_cold),
            "queue_limit": queue_limit,
            "session_queue_limit": self.max_pending_subagents_per_session,
            "session_running_limit": self.max_running_subagents_per_session,
            "fair_share_bias": "session_load_penalty",
            "fair_share_penalty": self._SESSION_LOAD_PENALTY,
            "running_sessions": self._running_sessions_summary(),
            "queued_sessions": self._pending_sessions_summary(),
            "session_loads": self._session_load_summary(),
            "pressure": pressure,
            "estimated_subagent_memory_mb": self.subagent_memory_mb,
            "host_memory_mb": self._host_memory_mb(),
            "default_memory_policy": self._DEFAULT_MEMORY_POLICY,
            "default_inherited_memory_layers": self._memory_layers_for_policy(self._DEFAULT_MEMORY_POLICY),
            "recommended_concurrency": self._recommended_concurrency(),
            "plan_first_default": True,
            "parallelism_mode": "lightweight",
            "host_strategy_profile": self._host_strategy_profile(),
            "host_strategy_reason": self._host_strategy_reason(),
            "queue_policy": "weighted_hot_warm_cold",
            "queue_promotions": {
                "cold_to_warm_s": self._COLD_TO_WARM_PROMOTION_S,
                "warm_to_hot_s": self._WARM_TO_HOT_PROMOTION_S,
                "hot_weight_threshold": self._HOT_QUEUE_WEIGHT_THRESHOLD,
                "warm_weight_threshold": self._WARM_QUEUE_WEIGHT_THRESHOLD,
            },
        }
