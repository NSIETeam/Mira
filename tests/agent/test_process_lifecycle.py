from __future__ import annotations

from mira.agent.process_lifecycle import TurnProcessLifecycle
from mira.agent.tools.registry import ToolRegistry
from mira.bus.events import InboundMessage
from mira.kernel.process import ProcessTable
from mira.session.manager import SessionManager


def test_turn_process_lifecycle_persists_completed_snapshot(tmp_path) -> None:
    sessions = SessionManager(tmp_path)
    session = sessions.get_or_create("cli:task")
    session.add_message("user", "do work")
    session.add_message("assistant", "done")
    sessions.save(session)
    lifecycle = TurnProcessLifecycle(
        sessions=sessions,
        tools=ToolRegistry(),
        process_table=ProcessTable(),
        model_hint=lambda: "test/model",
        token_usage=lambda: {"input": 11, "output": 7},
    )

    process = lifecycle.spawn(
        InboundMessage(channel="cli", chat_id="task", sender_id="king", content="do work")
    )
    lifecycle.complete(process, "cli:task", reason="completed")

    snapshot = sessions.get_or_create("cli:task").metadata["agent_process"]
    assert snapshot["status"] == "terminated"
    assert snapshot["stopped_reason"] == "completed"
    assert snapshot["model_hint"] == "test/model"
    assert snapshot["tokens_consumed"] == 18
    assert snapshot["context"]["history_window"][-1]["content"] == "done"
