from __future__ import annotations

import pytest

from mira.agent.subagent import SubagentManager
from mira.bus.queue import MessageBus


@pytest.mark.parametrize("policy", ["task_only", "default", "full"])
def test_subagent_memory_prompt_redacts_parent_session_and_history_path(tmp_path, policy: str) -> None:
    manager = SubagentManager(workspace=tmp_path, bus=MessageBus(), max_tool_result_chars=1000)

    prompt = manager._build_subagent_prompt(
        workspace=tmp_path,
        session_key="cli:secret-session",
        memory_policy=policy,
        inherited_memory_layers=manager._memory_layers_for_policy(policy),
    )

    assert "cli:secret-session" not in prompt
    assert "history.jsonl" not in prompt
    assert "Effective memory view" in prompt
    assert "parent_session=" in prompt


@pytest.mark.asyncio
async def test_subagent_file_tools_cannot_read_agent_history(tmp_path) -> None:
    history = tmp_path / "memory" / "history.jsonl"
    history.parent.mkdir()
    history.write_text("secret history")
    project = tmp_path / "project"
    project.mkdir()
    manager = SubagentManager(workspace=tmp_path, bus=MessageBus(), max_tool_result_chars=1000)
    tools = manager._build_tools(workspace=project)

    result = await tools.execute("read_file", {"path": str(history)})

    assert "Error" in str(result)
    assert "secret history" not in str(result)
