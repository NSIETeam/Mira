from pathlib import Path

from mira.session.manager import Session, SessionManager
from mira.session.recovery import (
    PENDING_USER_TURN_KEY,
    RUNTIME_CHECKPOINT_KEY,
    recover_interrupted_sessions,
)


def test_recover_interrupted_sessions_materializes_runtime_checkpoint(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    session = Session(
        key="webui:test",
        metadata={
            RUNTIME_CHECKPOINT_KEY: {
                "assistant_message": {
                    "role": "assistant",
                    "content": "working",
                    "tool_calls": [
                        {
                            "id": "call_done",
                            "type": "function",
                            "function": {"name": "read_file", "arguments": "{}"},
                        },
                        {
                            "id": "call_pending",
                            "type": "function",
                            "function": {"name": "exec", "arguments": "{}"},
                        },
                    ],
                },
                "completed_tool_results": [
                    {
                        "role": "tool",
                        "tool_call_id": "call_done",
                        "name": "read_file",
                        "content": "ok",
                    }
                ],
                "pending_tool_calls": [
                    {
                        "id": "call_pending",
                        "type": "function",
                        "function": {"name": "exec", "arguments": "{}"},
                    }
                ],
            },
            PENDING_USER_TURN_KEY: True,
        },
    )
    manager.save(session, fsync=True)

    results = recover_interrupted_sessions(manager)

    assert [result.session_key for result in results] == ["webui:test"]
    recovered = manager.read_session_file("webui:test")
    assert recovered is not None
    assert RUNTIME_CHECKPOINT_KEY not in recovered["metadata"]
    assert PENDING_USER_TURN_KEY not in recovered["metadata"]
    assert recovered["messages"][0]["role"] == "assistant"
    assert recovered["messages"][1]["tool_call_id"] == "call_done"
    assert recovered["messages"][2]["tool_call_id"] == "call_pending"
    assert "interrupted before this tool finished" in recovered["messages"][2]["content"].lower()


def test_recover_interrupted_sessions_closes_pending_user_turn(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    session = Session(
        key="webui:pending",
        messages=[{"role": "user", "content": "hello"}],
        metadata={PENDING_USER_TURN_KEY: True},
    )
    manager.save(session, fsync=True)

    results = recover_interrupted_sessions(manager)

    assert [result.session_key for result in results] == ["webui:pending"]
    recovered = manager.read_session_file("webui:pending")
    assert recovered is not None
    assert PENDING_USER_TURN_KEY not in recovered["metadata"]
    assert recovered["messages"][-1]["role"] == "assistant"
    assert "interrupted before a response" in recovered["messages"][-1]["content"].lower()
