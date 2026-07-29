"""Temporary WebUI users for shared gateway deployments."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mira.utils.helpers import ensure_dir, sync_workspace_templates

_USER_ID_RE = re.compile(r"[^A-Za-z0-9_-]+")
_DEFAULT_USER = "default"


@dataclass(frozen=True)
class WebUITemporaryUser:
    user_id: str
    root: Path
    workspace: Path

    def payload(self) -> dict[str, Any]:
        return {
            "id": self.user_id,
            "root": str(self.root),
            "workspace": str(self.workspace),
            "temporary": True,
        }


class WebUITemporaryUserManager:
    """Filesystem-backed temporary user registry."""

    def __init__(self, root: Path) -> None:
        self.root = ensure_dir(root)

    def normalize(self, raw: str | None) -> str:
        user_id = _USER_ID_RE.sub("-", (raw or "").strip()).strip("-_").lower()
        return (user_id or _DEFAULT_USER)[:24]

    def ensure(self, raw: str | None) -> WebUITemporaryUser:
        user_id = self.normalize(raw)
        root = ensure_dir(self.root / user_id)
        workspace = ensure_dir(root / "workspace")
        sync_workspace_templates(workspace, silent=True)
        return WebUITemporaryUser(user_id=user_id, root=root, workspace=workspace)

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
