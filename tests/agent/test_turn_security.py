from __future__ import annotations

from mira.agent.turn_security import (
    capability_policy_for_metadata,
    record_capability_audit_event,
)
from mira.kernel.acl import CapabilityAuditEvent
from mira.session.manager import Session


class _Sessions:
    def __init__(self) -> None:
        self.saved: list[str] = []

    def save(self, session: Session) -> None:
        self.saved.append(session.key)


def test_capability_policy_for_metadata_accepts_agent_capabilities_without_agent_loop() -> None:
    policy = capability_policy_for_metadata(
        {
            "agent_capabilities": {
                "/fs/read": {"allow": ["/repo/*"], "deny": ["/repo/private/*"]},
                "/shell/exec": {"deny": "*"},
            }
        },
        sender_id="king",
    )

    assert policy is not None
    assert policy.agent == "king"
    assert set(policy.rules) == {"/fs/read", "/shell/exec"}


def test_record_capability_audit_event_bounds_and_saves_without_agent_loop() -> None:
    session = Session(key="cli:audit")
    session.metadata["capability_audit_log"] = [
        {"agent": "old", "capability": "/fs/read", "target": str(index)}
        for index in range(200)
    ]
    sessions = _Sessions()

    record_capability_audit_event(
        session,
        CapabilityAuditEvent(
            agent="king",
            capability="/fs/write",
            target="/repo/app.py",
            decision="deny",
            reason="target is outside allow list",
        ),
        sessions=sessions,  # type: ignore[arg-type]
    )

    audit_log = session.metadata["capability_audit_log"]
    assert len(audit_log) == 200
    assert audit_log[0]["target"] == "1"
    assert audit_log[-1]["agent"] == "king"
    assert audit_log[-1]["capability"] == "/fs/write"
    assert audit_log[-1]["decision"] == "deny"
    assert audit_log[-1]["timestamp"]
    assert sessions.saved == ["cli:audit"]
