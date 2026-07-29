"""OS-backed secret references for provider and runtime credentials."""

from __future__ import annotations

import os
import platform
import re
import subprocess
from dataclasses import dataclass

SECRET_REF_PREFIX = "mira-secret:v1:"
_SAFE_PART = re.compile(r"[^A-Za-z0-9_.-]+")


@dataclass(frozen=True)
class SecretRef:
    scope: str
    name: str
    field: str

    @property
    def account(self) -> str:
        return f"{self.scope}.{self.name}.{self.field}"

    def serialize(self) -> str:
        return f"{SECRET_REF_PREFIX}{self.scope}:{self.name}:{self.field}"


class CredentialStore:
    service = "Mira"

    def available(self) -> bool:
        return False

    def get(self, ref: SecretRef) -> str | None:
        raise NotImplementedError

    def set(self, ref: SecretRef, value: str) -> None:
        raise NotImplementedError

    def delete(self, ref: SecretRef) -> None:
        raise NotImplementedError


class MacOSKeychainStore(CredentialStore):
    def available(self) -> bool:
        return platform.system() == "Darwin"

    def get(self, ref: SecretRef) -> str | None:
        proc = subprocess.run(
            ["security", "find-generic-password", "-s", self.service, "-a", ref.account, "-w"],
            check=False,
            capture_output=True,
            text=True,
        )
        return proc.stdout.rstrip("\n") if proc.returncode == 0 else None

    def set(self, ref: SecretRef, value: str) -> None:
        subprocess.run(
            [
                "security",
                "add-generic-password",
                "-U",
                "-s",
                self.service,
                "-a",
                ref.account,
                "-w",
                value,
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    def delete(self, ref: SecretRef) -> None:
        subprocess.run(
            ["security", "delete-generic-password", "-s", self.service, "-a", ref.account],
            check=False,
            capture_output=True,
            text=True,
        )


class DisabledCredentialStore(CredentialStore):
    pass


def make_secret_ref(scope: str, name: str, field: str) -> SecretRef:
    return SecretRef(_safe(scope), _safe(name), _safe(field))


def parse_secret_ref(value: str) -> SecretRef | None:
    if not isinstance(value, str) or not value.startswith(SECRET_REF_PREFIX):
        return None
    parts = value[len(SECRET_REF_PREFIX):].split(":")
    if len(parts) != 3 or not all(parts):
        return None
    return SecretRef(parts[0], parts[1], parts[2])


def resolve_secret_ref(value: str, store: CredentialStore | None = None) -> str:
    ref = parse_secret_ref(value)
    if not ref:
        return value
    active_store = store or system_credential_store()
    secret = active_store.get(ref) if active_store.available() else None
    return secret or ""


def store_secret_value(
    scope: str,
    name: str,
    field: str,
    value: str | None,
    store: CredentialStore | None = None,
) -> str | None:
    if not value or parse_secret_ref(value) or value.startswith("${"):
        return value
    active_store = store or system_credential_store()
    if not active_store.available():
        return value
    ref = make_secret_ref(scope, name, field)
    active_store.set(ref, value)
    return ref.serialize()


def system_credential_store() -> CredentialStore:
    if os.environ.get("MIRA_SECRET_STORE", "").lower() in {"0", "off", "false", "disabled"}:
        return DisabledCredentialStore()
    if platform.system() == "Darwin":
        return MacOSKeychainStore()
    return DisabledCredentialStore()


def _safe(value: str) -> str:
    return _SAFE_PART.sub("_", value.strip())[:120] or "default"
