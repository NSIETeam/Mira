"""Token state for the embedded WebUI gateway."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from websockets.http11 import Request as WsRequest

from mira.webui.http_utils import bearer_token, parse_query, query_first

IssuedTokenAudience = Literal["client", "webui"]


@dataclass
class GatewayTokenStore:
    """Own short-lived WebSocket and WebUI API tokens for one gateway process."""

    max_tokens: int = 10_000
    issued_tokens: dict[str, float] = field(default_factory=dict)
    issued_token_audiences: dict[str, IssuedTokenAudience] = field(default_factory=dict)
    issued_token_users: dict[str, str] = field(default_factory=dict)
    api_tokens: dict[str, float] = field(default_factory=dict)
    api_token_users: dict[str, str] = field(default_factory=dict)

    def check_api_token(self, request: WsRequest) -> bool:
        return self.api_token_user(request) is not None

    def api_token_user(self, request: WsRequest) -> str | None:
        self._purge_expired_api_tokens()
        token = bearer_token(request.headers) or query_first(
            parse_query(request.path), "token"
        )
        if not token:
            return None
        expiry = self.api_tokens.get(token)
        if expiry is None or time.monotonic() > expiry:
            self.api_tokens.pop(token, None)
            self.api_token_users.pop(token, None)
            return None
        return self.api_token_users.get(token, "default")

    def can_issue(self, *, include_api_token: bool = False) -> bool:
        self._purge_expired_issued_tokens()
        self._purge_expired_api_tokens()
        if len(self.issued_tokens) >= self.max_tokens:
            return False
        if include_api_token and len(self.api_tokens) >= self.max_tokens:
            return False
        return True

    def issue_token(
        self,
        ttl_s: int | float,
        *,
        audience: IssuedTokenAudience = "client",
        user_id: str = "default",
    ) -> str:
        token_value = f"nbwt_{secrets.token_urlsafe(32)}"
        expiry = time.monotonic() + float(ttl_s)
        self.issued_tokens[token_value] = expiry
        self.issued_token_audiences[token_value] = audience
        self.issued_token_users[token_value] = user_id
        return token_value

    def issue_api_token(self, ttl_s: int | float, *, user_id: str = "default") -> str:
        token_value = f"nbwt_{secrets.token_urlsafe(32)}"
        expiry = time.monotonic() + float(ttl_s)
        self.api_tokens[token_value] = expiry
        self.api_token_users[token_value] = user_id
        return token_value

    def take_issued_token_if_valid(self, token_value: str | None) -> bool:
        return self.take_issued_token_audience(token_value) is not None

    def take_issued_token_audience(
        self,
        token_value: str | None,
    ) -> IssuedTokenAudience | None:
        result = self.take_issued_token(token_value)
        return result[0] if result else None

    def take_issued_token(
        self,
        token_value: str | None,
    ) -> tuple[IssuedTokenAudience, str] | None:
        if not token_value:
            return None
        self._purge_expired_issued_tokens()
        expiry = self.issued_tokens.pop(token_value, None)
        if expiry is None:
            self.issued_token_audiences.pop(token_value, None)
            self.issued_token_users.pop(token_value, None)
            return None
        audience = self.issued_token_audiences.pop(token_value, "client")
        user_id = self.issued_token_users.pop(token_value, "default")
        if time.monotonic() > expiry:
            return None
        return audience, user_id

    def clear(self) -> None:
        self.issued_tokens.clear()
        self.issued_token_audiences.clear()
        self.issued_token_users.clear()
        self.api_tokens.clear()
        self.api_token_users.clear()

    def _purge_expired_api_tokens(self) -> None:
        now = time.monotonic()
        for token_key, expiry in list(self.api_tokens.items()):
            if now > expiry:
                self.api_tokens.pop(token_key, None)
                self.api_token_users.pop(token_key, None)

    def _purge_expired_issued_tokens(self) -> None:
        now = time.monotonic()
        for token_key, expiry in list(self.issued_tokens.items()):
            if now > expiry:
                self.issued_tokens.pop(token_key, None)
                self.issued_token_audiences.pop(token_key, None)
                self.issued_token_users.pop(token_key, None)


def token_response_payload(token: str, expires_in: Any) -> dict[str, Any]:
    return {"token": token, "expires_in": expires_in}
