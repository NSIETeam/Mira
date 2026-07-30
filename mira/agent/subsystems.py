"""Factory helpers for AgentLoop-owned subsystems."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mira.agent.autocompact import AutoCompact
from mira.agent.context import ContextBuilder
from mira.agent.maturity import VirtualContextManager
from mira.agent.memory import Consolidator
from mira.agent.runner import AgentRunner
from mira.agent.subagent import SubagentManager
from mira.agent.tools.exec_session import ExecSessionManager
from mira.agent.tools.file_state import FileStateStore
from mira.agent.tools.registry import ToolRegistry
from mira.bus.queue import MessageBus
from mira.execution_gate import ExecutionGate
from mira.session.goal_state import runner_wall_llm_timeout_s
from mira.session.manager import SessionManager


@dataclass(slots=True)
class AgentLoopSubsystems:
    """Subsystem objects owned by one AgentLoop instance."""

    context: ContextBuilder
    sessions: SessionManager
    tools: ToolRegistry
    file_state_store: FileStateStore
    exec_session_manager: ExecSessionManager
    runner: AgentRunner
    subagents: SubagentManager
    virtual_context_manager: VirtualContextManager
    consolidator: Consolidator
    auto_compact: AutoCompact


def create_agent_loop_subsystems(
    *,
    workspace: Path,
    bus: MessageBus,
    tools_config: Any,
    max_tool_result_chars: int,
    restrict_to_workspace: bool,
    disabled_skills: list[str] | None,
    max_iterations: int,
    max_concurrent_subagents: int | None,
    fail_on_tool_error: bool | None,
    execution_gate: ExecutionGate,
    session_manager: SessionManager | None,
    timezone: str | None,
    consolidation_ratio: float,
    unified_session: bool,
    session_ttl_minutes: int,
) -> AgentLoopSubsystems:
    """Build the concrete subsystems that AgentLoop composes."""
    context = ContextBuilder(workspace, timezone=timezone, disabled_skills=disabled_skills)
    sessions = session_manager or SessionManager(workspace)
    sessions.set_file_cap_archiver(context.memory.raw_archive)
    tools = ToolRegistry()
    file_state_store = FileStateStore()
    exec_session_manager = ExecSessionManager()
    runner = AgentRunner()
    subagents = SubagentManager(
        workspace=workspace,
        bus=bus,
        tools_config=tools_config,
        max_tool_result_chars=max_tool_result_chars,
        restrict_to_workspace=restrict_to_workspace,
        disabled_skills=disabled_skills,
        max_iterations=max_iterations,
        max_concurrent_subagents=max_concurrent_subagents,
        fail_on_tool_error=fail_on_tool_error,
        execution_gate=execution_gate,
        llm_wall_timeout_for_session=lambda sk: runner_wall_llm_timeout_s(sessions, sk),
    )
    consolidator = Consolidator(
        store=context.memory,
        sessions=sessions,
        build_messages=context.build_messages,
        get_tool_definitions=tools.get_definitions,
        consolidation_ratio=consolidation_ratio,
        unified_session=unified_session,
    )
    auto_compact = AutoCompact(
        sessions=sessions,
        consolidator=consolidator,
        session_ttl_minutes=session_ttl_minutes,
    )
    return AgentLoopSubsystems(
        context=context,
        sessions=sessions,
        tools=tools,
        file_state_store=file_state_store,
        exec_session_manager=exec_session_manager,
        runner=runner,
        subagents=subagents,
        virtual_context_manager=VirtualContextManager(),
        consolidator=consolidator,
        auto_compact=auto_compact,
    )
