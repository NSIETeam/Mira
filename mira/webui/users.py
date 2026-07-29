"""Temporary WebUI users for shared gateway deployments."""

from __future__ import annotations

import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mira.utils.helpers import ensure_dir, sync_workspace_templates

_USER_ID_RE = re.compile(r"[^A-Za-z0-9_-]+")
_DEFAULT_USER = "default"
WEBUI_USER_METADATA_KEY = "webui_user"
WEBUI_GROUP_METADATA_KEY = "webui_group"
WEBUI_MEMORY_WORKSPACE_METADATA_KEY = "memory_workspace"


@dataclass(frozen=True)
class WebUITemporaryUser:
    user_id: str
    group_id: str
    root: Path
    workspace: Path
    memory_workspace: Path

    def payload(self) -> dict[str, Any]:
        return {
            "id": self.user_id,
            "group": self.group_id,
            "root": str(self.root),
            "workspace": str(self.workspace),
            "memory_workspace": str(self.memory_workspace),
            "temporary": True,
        }


class WebUITemporaryUserManager:
    """Filesystem-backed temporary user registry."""

    def __init__(self, root: Path) -> None:
        self.root = ensure_dir(root)

    def normalize(self, raw: str | None) -> str:
        user_id = _USER_ID_RE.sub("-", (raw or "").strip()).strip("-_").lower()
        return (user_id or _DEFAULT_USER)[:24]

    def ensure(self, raw: str | None, *, group: str | None = None) -> WebUITemporaryUser:
        user_id = self.normalize(raw)
        group_id = self.normalize(group)
        root = ensure_dir(self.root / user_id)
        workspace = ensure_dir(root / "workspace")
        memory_workspace = ensure_dir(self.root / "_groups" / group_id)
        sync_workspace_templates(workspace, silent=True)
        sync_workspace_templates(memory_workspace, silent=True)
        return WebUITemporaryUser(
            user_id=user_id,
            group_id=group_id,
            root=root,
            workspace=workspace,
            memory_workspace=memory_workspace,
        )

    def memory_workspace(self, group_id: str | None) -> Path:
        return ensure_dir(self.root / "_groups" / self.normalize(group_id))

    def turn_metadata(self, user_id: str | None, group_id: str | None) -> dict[str, Any]:
        user = self.normalize(user_id)
        group = self.normalize(group_id)
        metadata: dict[str, Any] = {
            WEBUI_USER_METADATA_KEY: user,
            WEBUI_GROUP_METADATA_KEY: group,
        }
        if user != _DEFAULT_USER or group != _DEFAULT_USER:
            metadata[WEBUI_MEMORY_WORKSPACE_METADATA_KEY] = str(self.memory_workspace(group))
        return metadata

    def user_for_chat_id(self, chat_id: str) -> str | None:
        if not chat_id.startswith("u:"):
            return None
        parts = chat_id.split(":", 2)
        if len(parts) != 3:
            return None
        return self.normalize(parts[1])

    def scoped_chat_id(self, user_id: str, chat_id: str) -> str:
        user = self.normalize(user_id)
        if user == _DEFAULT_USER:
            return chat_id
        if self.user_for_chat_id(chat_id) == user:
            return chat_id
        safe_chat = _USER_ID_RE.sub("-", chat_id.strip()).strip("-_")[:36] or "chat"
        return f"u:{user}:{safe_chat}"

    def session_key_allowed(self, user_id: str | None, session_key: str) -> bool:
        if not user_id:
            return False
        user = self.normalize(user_id)
        if user == _DEFAULT_USER:
            return session_key.startswith("websocket:")
        return session_key.startswith(f"websocket:u:{user}:")

    def is_isolated_user(self, user_id: str | None) -> bool:
        return self.normalize(user_id) != _DEFAULT_USER

    def active_users_payload(self, *, ttl_hours: int = 24) -> dict[str, Any]:
        users: list[dict[str, Any]] = []
        for path in sorted(self.root.iterdir()) if self.root.exists() else []:
            if not path.is_dir() or path.name.startswith("_"):
                continue
            stat = path.stat()
            workspace = path / "workspace"
            users.append({
                "id": path.name,
                "root": str(path),
                "workspace": str(workspace),
                "workspace_exists": workspace.exists(),
                "temporary": path.name != _DEFAULT_USER,
                "updated_at": stat.st_mtime,
                "stale": (stat.st_mtime + ttl_hours * 3600) < time.time(),
            })
        groups: list[dict[str, Any]] = []
        groups_root = self.root / "_groups"
        if groups_root.exists():
            for path in sorted(groups_root.iterdir()):
                if path.is_dir():
                    groups.append({"id": path.name, "path": str(path), "bytes": _dir_size(path)})
        return {"users": users, "groups": groups, "ttl_hours": ttl_hours}

    def cleanup_stale(self, *, ttl_hours: int = 24) -> dict[str, Any]:
        removed: list[str] = []
        cutoff = time.time() - ttl_hours * 3600
        for path in sorted(self.root.iterdir()) if self.root.exists() else []:
            if not path.is_dir() or path.name.startswith("_") or path.name == _DEFAULT_USER:
                continue
            try:
                if path.stat().st_mtime >= cutoff:
                    continue
                shutil.rmtree(path)
                removed.append(path.name)
            except OSError:
                continue
        return {"removed": removed, "ttl_hours": ttl_hours}


def _dir_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                continue
    return total
