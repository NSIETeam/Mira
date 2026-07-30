from __future__ import annotations

import asyncio

import pytest

from mira.agent.loop import AgentLoop
from mira.agent.maturity import (
    ToolMiddlewareStack,
    apply_agent_role_to_task,
    list_agent_role_profiles,
    normalize_media_contract,
    parse_workflow_dsl,
    VirtualContextManager,
)
from mira.agent.tools.base import ToolResult
from mira.bus.queue import MessageBus
from mira.config.schema import ModuleConfig, ModulesConfig
from mira.providers.base import ToolCallRequest
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
