from __future__ import annotations

from mira.agent.memory import MemoryStore


def test_memory_audit_reports_confidence_conflicts_and_rollback(tmp_path) -> None:
    store = MemoryStore(tmp_path)
    store.memory_file.write_text(
        "[confidence:high] stable fact\n"
        "[confidence:low] weak fact\n"
        "[source:meeting] sourced fact\n"
        "[conflict] older value disagrees\n"
        "[rollback] remove bad memory\n",
        encoding="utf-8",
    )

    audit = store.memory_audit(tmp_path)
    governance = audit["auto_memory"]["governance"]

    assert governance["confidence_counts"] == {"high": 1, "medium": 0, "low": 1}
    assert governance["source_hint_count"] == 1
    assert governance["conflict_count"] == 1
    assert governance["rollback_hint_count"] == 1
    assert governance["review_required"] is True
