from __future__ import annotations

from loguru import logger

from mira.utils.logging import session_logger, tool_logger, turn_logger


def _capture_extra(write_log) -> dict:
    records = []
    sink_id = logger.add(lambda message: records.append(message.record), format="{message}")
    try:
        write_log()
    finally:
        logger.remove(sink_id)
    assert records
    return records[-1]["extra"]


def test_session_logger_binds_session_key() -> None:
    extra = _capture_extra(lambda: session_logger("websocket:chat").info("hello"))

    assert extra["session_key"] == "websocket:chat"


def test_turn_logger_binds_turn_id() -> None:
    extra = _capture_extra(lambda: turn_logger("websocket:chat", "turn-1").info("hello"))

    assert extra["session_key"] == "websocket:chat"
    assert extra["turn_id"] == "turn-1"


def test_tool_logger_binds_tool_context() -> None:
    extra = _capture_extra(lambda: tool_logger("websocket:chat", "call-1", "exec").info("hello"))

    assert extra["session_key"] == "websocket:chat"
    assert extra["tool_call_id"] == "call-1"
    assert extra["tool_name"] == "exec"
