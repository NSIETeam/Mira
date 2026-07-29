from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from mira.agent.runner import AgentRunner, AgentRunSpec
from mira.execution_gate import ExecutionGate
from mira.providers.base import ToolCallRequest
from mira.utils.llm_runtime import LLMRuntime


def _runtime() -> LLMRuntime:
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    return LLMRuntime.capture(provider, "test-model", context_window_tokens=4096)


@pytest.mark.asyncio
async def test_execution_gate_paused_holds_admission_until_resume() -> None:
    gate = ExecutionGate()
    gate.set_state("paused", reason="maintenance")
    admitted = asyncio.create_task(gate.wait_for_turn_admission())

    await asyncio.sleep(0)
    assert not admitted.done()

    opened = gate.set_state("open", reason="ready")
    snapshot = await asyncio.wait_for(admitted, timeout=1)

    assert snapshot.correlation_id == opened.correlation_id
    assert snapshot.permits_turns is True
    assert snapshot.permits_tools is True


@pytest.mark.asyncio
async def test_degraded_gate_blocks_tool_before_registry_execution() -> None:
    gate = ExecutionGate()
    gate.set_state("degraded", reason="fault containment")
    tools = MagicMock()
    tools.prepare_call.return_value = (None, {}, None)
    tools.execute = AsyncMock(return_value="should not run")

    result, event, error = await AgentRunner()._run_tool(
        AgentRunSpec(
            initial_messages=[],
            tools=tools,
            runtime=_runtime(),
            max_iterations=1,
            max_tool_result_chars=1000,
            execution_gate=gate,
        ),
        ToolCallRequest(id="call-1", name="demo", arguments={}),
        {},
        {},
    )

    assert "execution gate is degraded" in str(result)
    assert event["status"] == "error"
    assert error is not None
    tools.execute.assert_not_awaited()
