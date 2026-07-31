from __future__ import annotations

from mira.agent.turn_persistence import persist_subagent_followup, save_turn_messages
from mira.bus.events import InboundMessage
from mira.session.manager import Session


def test_save_turn_messages_drops_orphan_tool_result_without_agent_loop() -> None:
    session = Session(key="test:persistence")
    session.add_message("user", "hi")

    save_turn_messages(
        session,
        [
            {"role": "tool", "tool_call_id": "call_ghost", "name": "exec", "content": "boo"},
            {"role": "assistant", "content": "done"},
        ],
        skip=0,
        max_tool_result_chars=1000,
    )

    assert [message["role"] for message in session.messages] == ["user", "assistant"]
    assert session.messages[-1]["content"] == "done"


def test_persist_subagent_followup_dedupes_task_id_without_agent_loop() -> None:
    session = Session(key="test:subagent-followup")
    msg = InboundMessage(
        channel="system",
        sender_id="subagent",
        chat_id="test:subagent-followup",
        content="subagent result",
        metadata={"subagent_task_id": "task-1"},
    )

    assert persist_subagent_followup(session, msg) is True
    assert persist_subagent_followup(session, msg) is False
    assert [message["content"] for message in session.messages] == ["subagent result"]
