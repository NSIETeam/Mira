from __future__ import annotations

import asyncio

import pytest

from mira.agent.loop import AgentLoop, AgentLoopConfig
from mira.agent.maturity import (
    ToolMiddlewareStack,
    VirtualContextManager,
    apply_agent_role_to_task,
    list_agent_role_profiles,
    normalize_media_contract,
    parse_workflow_dsl,
)
from mira.agent.subsystems import create_agent_loop_subsystems
from mira.agent.tools.base import ToolResult
from mira.bus.events import InboundMessage, OutboundMessage
from mira.bus.queue import MessageBus
from mira.config.schema import ModuleConfig, ModulesConfig
from mira.execution_gate import ExecutionGate
from mira.kernel.acl import CapabilityAuditEvent
from mira.providers.base import ToolCallRequest
from mira.session.manager import SessionManager
from tests.agent.conftest import make_provider


def test_agent_role_profiles_are_small_and_actionable():
    names = {row["name"] for row in list_agent_role_profiles()}

    assert {"implementer", "reviewer", "researcher", "doctor"} <= names
    assert "review subagent" in apply_agent_role_to_task("check this", "reviewer")


def test_virtual_context_pages_old_messages_into_breadcrumb():
    messages = [{"role": "user", "content": f"message {index} " * 40} for index in range(12)]

    page = VirtualContextManager().page(messages, budget_tokens=80)

    assert page.paged_count > 0
    assert page.kept_messages[0]["metadata"]["virtual_context"] is True
    assert "older message" in page.kept_messages[0]["content"]


def test_virtual_context_explain_is_user_visible():
    messages = [{"role": "user", "content": f"message {index} " * 40} for index in range(12)]

    explanation = VirtualContextManager().explain(messages, budget_tokens=80)

    assert explanation["strategy"] == "deterministic_tail_window"
    assert explanation["paged_messages"] > 0
    assert "breadcrumb" in explanation["reason"]


def test_multimodal_contract_normalizes_files_and_images():
    parts = normalize_media_contract("look", ["/tmp/a.png", {"kind": "audio", "source": "clip.wav"}])

    assert parts[0] == {"type": "text", "text": "look"}
    assert parts[1]["kind"] == "image"
    assert parts[2]["kind"] == "audio"


def test_workflow_dsl_validates_dependency_graph():
    steps = parse_workflow_dsl({
        "steps": [
            {"id": "scan", "task": "scan repo", "role": "researcher"},
            {"id": "fix", "task": "apply fix", "depends_on": ["scan"]},
        ]
    })

    assert [step.step_id for step in steps] == ["scan", "fix"]
    with pytest.raises(ValueError, match="unknown"):
        parse_workflow_dsl({"steps": [{"id": "fix", "task": "x", "depends_on": ["missing"]}]})


class _BlockingMiddleware:
    async def before_execute(self, tool_call, tool, params):
        return ToolResult.error(f"blocked {tool_call.name}")

    async def after_execute(self, tool_call, tool, params, result):
        raise AssertionError("after should not run")

    async def on_error(self, tool_call, tool, params, error):
        raise AssertionError("error should not run")


def test_tool_middleware_stack_can_fail_closed_before_execution():
    stack = ToolMiddlewareStack([_BlockingMiddleware()])
    tool_call = ToolCallRequest(id="1", name="exec", arguments={})

    result = asyncio.run(stack.before_execute(tool_call, None, {}))

    assert "blocked exec" in str(result)


def test_optional_maturity_tools_are_disabled_by_default(tmp_path):
    loop = AgentLoop(
        bus=MessageBus(),
        provider=make_provider(spec=False),
        workspace=tmp_path,
        modules_config=ModulesConfig(),
    )

    assert "computer_use" not in loop.tools.tool_names
    assert "workflow_dsl" not in loop.tools.tool_names


def test_agent_loop_accepts_parameter_object(tmp_path):
    bus = MessageBus()
    provider = make_provider(spec=False)

    loop = AgentLoop.from_loop_config(
        AgentLoopConfig(
            bus=bus,
            provider=provider,
            workspace=tmp_path,
            model="test-model",
            restrict_to_workspace=True,
        )
    )

    assert loop.bus is bus
    assert loop.provider is provider
    assert loop.model == "test-model"
    assert loop.loop_config.restrict_to_workspace is True


def test_agent_loop_subsystem_factory_uses_supplied_session_manager(tmp_path):
    sessions = SessionManager(tmp_path)

    subsystems = create_agent_loop_subsystems(
        workspace=tmp_path,
        bus=MessageBus(),
        tools_config=None,
        max_tool_result_chars=4096,
        restrict_to_workspace=True,
        disabled_skills=None,
        max_iterations=4,
        max_concurrent_subagents=1,
        fail_on_tool_error=None,
        execution_gate=ExecutionGate(),
        session_manager=sessions,
        timezone=None,
        consolidation_ratio=0.5,
        unified_session=False,
        session_ttl_minutes=0,
    )

    assert subsystems.sessions is sessions
    assert subsystems.consolidator.sessions is sessions
    assert subsystems.auto_compact.sessions is sessions
    assert subsystems.tools.tool_names == []
    assert subsystems.process_table.list() == []


def test_agent_loop_builds_capability_policy_from_metadata(tmp_path):
    loop = AgentLoop(
        bus=MessageBus(),
        provider=make_provider(spec=False),
        workspace=tmp_path,
    )

    policy = loop._capability_policy_for_metadata(
        {
            "agent_capabilities": {
                "/fs/read": {"allow": ["/repo/*"], "deny": ["/repo/private/*"]},
                "/shell/exec": {"deny": ["*"]},
            }
        },
        sender_id="king",
    )

    assert policy is not None
    assert set(policy.rules) == {"/fs/read", "/shell/exec"}


def test_agent_loop_persists_capability_audit_event_to_session(tmp_path):
    loop = AgentLoop(
        bus=MessageBus(),
        provider=make_provider(spec=False),
        workspace=tmp_path,
    )
    session = loop.sessions.get_or_create("cli:audit")

    loop._record_capability_audit_event(
        session,
        CapabilityAuditEvent(
            agent="king",
            capability="/fs/write",
            target="/repo/app.py",
            decision="deny",
            reason="target is outside allow list",
        ),
    )

    audit_log = loop.sessions.get_or_create("cli:audit").metadata["capability_audit_log"]
    assert audit_log[-1]["agent"] == "king"
    assert audit_log[-1]["capability"] == "/fs/write"
    assert audit_log[-1]["target"] == "/repo/app.py"
    assert audit_log[-1]["decision"] == "deny"
    assert audit_log[-1]["reason"] == "target is outside allow list"
    assert audit_log[-1]["timestamp"]


@pytest.mark.asyncio
async def test_dispatch_records_completed_agent_process(tmp_path, monkeypatch):
    loop = AgentLoop(
        bus=MessageBus(),
        provider=make_provider(spec=False),
        workspace=tmp_path,
    )

    async def fake_process_message(*args, **kwargs):
        session = loop.sessions.get_or_create("cli:process")
        session.add_message("user", "run task")
        session.add_message("assistant", "done")
        loop.sessions.save(session)
        return OutboundMessage(channel="cli", chat_id="process", content="done")

    monkeypatch.setattr(loop, "_process_message", fake_process_message)

    await loop._dispatch(InboundMessage(channel="cli", chat_id="process", sender_id="king", content="run task"))

    session = loop.sessions.get_or_create("cli:process")
    snapshot = session.metadata["agent_process"]
    assert snapshot["status"] == "terminated"
    assert snapshot["stopped_reason"] == "completed"
    assert snapshot["user"] == "king"
    assert snapshot["context"]["history_window"][-1]["content"] == "done"


@pytest.mark.asyncio
async def test_dispatch_records_cancelled_agent_process_for_context_swap(tmp_path, monkeypatch):
    loop = AgentLoop(
        bus=MessageBus(),
        provider=make_provider(spec=False),
        workspace=tmp_path,
    )

    async def fake_process_message(*args, **kwargs):
        session = loop.sessions.get_or_create("cli:cancel")
        session.add_message("user", "long task")
        loop.sessions.save(session)
        raise asyncio.CancelledError()

    monkeypatch.setattr(loop, "_process_message", fake_process_message)

    with pytest.raises(asyncio.CancelledError):
        await loop._dispatch(
            InboundMessage(channel="cli", chat_id="cancel", sender_id="king", content="long task")
        )

    session = loop.sessions.get_or_create("cli:cancel")
    snapshot = session.metadata["agent_process"]
    assert snapshot["status"] == "stopped"
    assert snapshot["stopped_reason"] == "cancelled"
    assert snapshot["context"]["history_window"][-1]["content"] == "long task"


def test_optional_workflow_dsl_tool_mounts_when_enabled(tmp_path):
    loop = AgentLoop(
        bus=MessageBus(),
        provider=make_provider(spec=False),
        workspace=tmp_path,
        modules_config=ModulesConfig(registry={"workflow_dsl": ModuleConfig(enabled=True)}),
    )

    assert "workflow_dsl" in loop.tools.tool_names


def test_virtual_context_pages_real_agent_loop_history(tmp_path):
    loop = AgentLoop(
        bus=MessageBus(),
        provider=make_provider(spec=False),
        workspace=tmp_path,
    )
    history = [{"role": "user", "content": f"message {index} " * 40} for index in range(12)]

    paged = loop._page_virtual_context_history(history, budget_tokens=80, session_key="cli:direct")

    assert paged[0]["metadata"]["virtual_context"] is True
    assert "older message" in paged[0]["content"]
