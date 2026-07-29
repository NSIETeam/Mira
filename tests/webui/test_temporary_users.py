from __future__ import annotations

import os
import time

from mira.webui.users import WebUITemporaryUserManager


def test_temporary_user_manager_audits_and_cleans_stale_users(tmp_path):
    manager = WebUITemporaryUserManager(tmp_path)
    manager.ensure("alice", group="growth")
    stale_root = tmp_path / "alice"
    old = time.time() - 48 * 3600
    os.utime(stale_root, (old, old))

    payload = manager.active_users_payload(ttl_hours=24)
    alice = next(row for row in payload["users"] if row["id"] == "alice")
    assert alice["stale"] is True
    assert payload["groups"][0]["id"] == "growth"

    result = manager.cleanup_stale(ttl_hours=24)
    assert result["removed"] == ["alice"]
    assert not stale_root.exists()
