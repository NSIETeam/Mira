import json

from mira.config.loader import load_config, save_config
from mira.config.schema import Config
from mira.security import credential_store


class MemoryStore(credential_store.CredentialStore):
    def __init__(self):
        self.values = {}

    def available(self):
        return True

    def get(self, ref):
        return self.values.get(ref.account)

    def set(self, ref, value):
        self.values[ref.account] = value

    def delete(self, ref):
        self.values.pop(ref.account, None)


def test_save_config_moves_provider_and_api_keys_to_secret_refs(tmp_path, monkeypatch):
    store = MemoryStore()
    monkeypatch.setattr(credential_store, "system_credential_store", lambda: store)

    path = tmp_path / "config.json"
    config = Config.model_validate({
        "api": {"apiKey": "runtime-secret"},
        "providers": {"groq": {"apiKey": "provider-secret"}},
    })

    save_config(config, path)

    saved_text = path.read_text(encoding="utf-8")
    saved = json.loads(saved_text)
    assert saved["api"]["apiKey"].startswith(credential_store.SECRET_REF_PREFIX)
    assert saved["providers"]["groq"]["apiKey"].startswith(credential_store.SECRET_REF_PREFIX)
    assert "runtime-secret" not in saved_text
    assert "provider-secret" not in saved_text

    loaded = load_config(path)
    assert loaded.api.api_key == "runtime-secret"
    assert loaded.providers.groq.api_key == "provider-secret"


def test_env_refs_are_not_migrated_to_secret_store(tmp_path, monkeypatch):
    store = MemoryStore()
    monkeypatch.setattr(credential_store, "system_credential_store", lambda: store)

    path = tmp_path / "config.json"
    config = Config.model_validate({"providers": {"groq": {"apiKey": "${GROQ_API_KEY}"}}})

    save_config(config, path)

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["providers"]["groq"]["apiKey"] == "${GROQ_API_KEY}"
