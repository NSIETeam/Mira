from __future__ import annotations

from types import SimpleNamespace

from mira.webui.gateway_tokens import GatewayTokenStore
from mira.webui.users import WebUITemporaryUserManager


def _request(token: str):
    return SimpleNamespace(headers={"Authorization": f"Bearer {token}"}, path="/api/sessions")


def test_temporary_user_creates_isolated_workspace(tmp_path):
    users = WebUITemporaryUserManager(tmp_path / "users")

    alice = users.ensure("Alice Smith")
    bob = users.ensure("bob")

    assert alice.user_id == "alice-smith"
    assert bob.user_id == "bob"
    assert alice.workspace != bob.workspace
    assert alice.workspace.exists()
    assert users.scoped_chat_id("alice", "chat-1") == "u:alice:chat-1"
    assert users.session_key_allowed("alice", "websocket:u:alice:chat-1")
    assert not users.session_key_allowed("alice", "websocket:u:bob:chat-1")


def test_gateway_tokens_bind_api_and_websocket_tokens_to_user():
    store = GatewayTokenStore()

    ws_token = store.issue_token(60, audience="webui", user_id="alice")
    api_token = store.issue_api_token(60, user_id="alice")

    assert store.take_issued_token(ws_token) == ("webui", "alice")
    assert store.api_token_user(_request(api_token)) == "alice"
