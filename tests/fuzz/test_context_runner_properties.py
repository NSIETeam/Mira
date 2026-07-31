from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from mira.agent.context_governance import ContextGovernanceConfig, ContextGovernor
from mira.agent.runner import AgentRunner

_ROLE = st.sampled_from(["user", "assistant", "tool", "system", "", "invalid"])
_MODEL_ROLES = {"user", "assistant", "tool", "system"}
_TEXT = st.text(max_size=2_000)
_CONTENT = st.one_of(_TEXT, st.none(), st.lists(st.dictionaries(st.text(max_size=20), _TEXT, max_size=4), max_size=8))
_MESSAGE = st.fixed_dictionaries(
    {
        "role": _ROLE,
        "content": _CONTENT,
    },
    optional={
        "tool_call_id": st.text(max_size=64),
        "tool_calls": st.lists(
            st.dictionaries(st.text(max_size=20), st.one_of(_TEXT, st.none()), max_size=4),
            max_size=5,
        ),
    },
)


def _config(tmp_path: Path) -> ContextGovernanceConfig:
    return ContextGovernanceConfig(
        provider=SimpleNamespace(generation=SimpleNamespace(max_tokens=256)),
        model="fuzz",
        tools=SimpleNamespace(get_definitions=lambda: []),
        workspace=tmp_path,
        session_key="fuzz:session",
        max_tool_result_chars=512,
        context_window_tokens=16_000,
        context_block_limit=12_000,
        max_tokens=256,
    )


@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(messages=st.lists(_MESSAGE, max_size=40))
def test_context_governor_prepare_for_model_never_crashes(tmp_path: Path, messages: list[dict[str, Any]]) -> None:
    result = ContextGovernor().prepare_for_model(_config(tmp_path), messages, set())

    assert isinstance(result, list)
    assert all(isinstance(message, dict) for message in result)
    assert all(message.get("role") in _MODEL_ROLES for message in result)


@settings(max_examples=100, deadline=None)
@given(messages=st.lists(_MESSAGE, max_size=60))
def test_context_governor_output_has_no_orphan_tool_results(messages: list[dict[str, Any]]) -> None:
    result = ContextGovernor.drop_orphan_tool_results(messages)
    assistant_call_ids = {
        call.get("id")
        for message in result
        for call in (message.get("tool_calls") or [])
        if isinstance(call, dict)
    }

    for message in result:
        if message.get("role") == "tool":
            assert message.get("tool_call_id") in assistant_call_ids


@settings(max_examples=100, deadline=None)
@given(messages=st.lists(_MESSAGE, max_size=60))
def test_context_governor_backfill_balances_valid_tool_calls(messages: list[dict[str, Any]]) -> None:
    result = ContextGovernor.backfill_missing_tool_results(messages)
    tool_result_ids = {
        message.get("tool_call_id")
        for message in result
        if message.get("role") == "tool"
    }

    for message in result:
        if message.get("role") != "assistant":
            continue
        for call in message.get("tool_calls") or []:
            if isinstance(call, dict) and call.get("id"):
                assert call.get("id") in tool_result_ids


@settings(max_examples=100, deadline=None)
@given(left=_CONTENT, right=_CONTENT)
def test_agent_runner_merge_content_preserves_nonempty_inputs(left: Any, right: Any) -> None:
    result = AgentRunner._merge_message_content(left, right)

    assert isinstance(result, (str, list))
    if isinstance(result, list):
        assert all(isinstance(block, dict) for block in result)


@settings(max_examples=100, deadline=None)
@given(
    base=st.lists(_MESSAGE, max_size=20),
    injections=st.lists(_MESSAGE, max_size=20),
)
def test_agent_runner_append_injections_preserves_message_list(base: list[dict[str, Any]], injections: list[dict[str, Any]]) -> None:
    messages = [dict(message) for message in base]

    AgentRunner._append_injected_messages(messages, [dict(message) for message in injections])

    assert isinstance(messages, list)
    assert all(isinstance(message, dict) for message in messages)
