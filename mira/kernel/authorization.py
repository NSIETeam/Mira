"""Server-side authorization for privileged kernel controls."""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class KernelPrincipal:
    role: str
    elevated: bool = False
    elevation_id: str | None = None
    expires_at: float | None = None
    scopes: frozenset[str] = field(default_factory=frozenset)

    @property
    def root(self) -> bool:
        return self.role == "root"

    def allows(self, action: str) -> bool:
        if self.root:
            return True
        if not self.elevated:
            return False
        if self.expires_at is not None and self.expires_at <= time.time():
            return False
        return "*" in self.scopes or action in self.scopes


def process_principal() -> KernelPrincipal:
    geteuid = getattr(os, "geteuid", None)
    if callable(geteuid) and int(geteuid()) == 0:
        return KernelPrincipal(role="root")
    return KernelPrincipal(role="user")


class KernelAuthorizer:
    """Default-deny privileged-action checker owned by the server process."""

    def __init__(self, principal: KernelPrincipal | None = None) -> None:
        self._base_principal = principal or process_principal()
        self._elevation: KernelPrincipal | None = None
        self.audit_log: list[dict[str, Any]] = []

    @property
    def principal(self) -> KernelPrincipal:
        elevated = self._elevation
        if elevated is not None and elevated.allows("*"):
            return elevated
        if elevated is not None and elevated.expires_at is not None and elevated.expires_at > time.time():
            return elevated
        self._elevation = None
        return self._base_principal

    def grant_elevation(
        self,
        *,
        scopes: set[str] | None = None,
        ttl_seconds: int = 300,
    ) -> KernelPrincipal:
        scope_set = frozenset(scopes or {"*"})
        principal = KernelPrincipal(
            role=self._base_principal.role,
            elevated=True,
            elevation_id=uuid.uuid4().hex,
            expires_at=time.time() + max(1, ttl_seconds),
            scopes=scope_set,
        )
        self._elevation = principal
        self._audit("grant", "*", True, "elevation granted")
        return principal

    def revoke_elevation(self) -> None:
        self._elevation = None
        self._audit("revoke", "*", True, "elevation revoked")

    def assert_allowed(self, action: str, *, raw: str | None = None) -> None:
        principal = self.principal
        allowed = principal.allows(action)
        self._audit("use", action, allowed, raw or action)
        if not allowed:
            raise PermissionError(f"operator action requires elevated server authorization: {raw or action}")

    def _audit(self, event: str, action: str, allowed: bool, detail: str) -> None:
        self.audit_log.append({
            "event": event,
            "action": action,
            "allowed": allowed,
            "role": self.principal.role if event != "grant" else self._base_principal.role,
            "detail": _redact(detail),
            "at": time.time(),
        })


def _redact(value: str) -> str:
    if not value:
        return value
    lowered = value.lower()
    if "key=" in lowered or "token=" in lowered or "secret=" in lowered or "sk-" in lowered:
        return "[redacted]"
    return value
