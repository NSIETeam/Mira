"""User-initiated desktop-safe version checker for Mira releases."""

from __future__ import annotations

import hashlib
import logging
import platform
import time
from typing import Any

import httpx
from packaging.version import InvalidVersion, Version

from mira import __version__

logger = logging.getLogger(__name__)

_GITHUB_LATEST_RELEASE_URL = "https://api.github.com/repos/NSIETeam/Mira/releases/latest"
_PYPI_URL = "https://pypi.org/pypi/mira-ai/json"
_CACHE_TTL_S = 300

_cache: tuple[float, dict[str, Any] | None] = (0.0, None)


def check_for_update() -> dict[str, Any] | None:
    """Return newer release metadata, without sending workspace state."""
    global _cache
    now = time.monotonic()
    cached_at, cached_payload = _cache
    if cached_at > 0 and now - cached_at < _CACHE_TTL_S:
        return cached_payload

    payload = _check_github_release() or _check_pypi_release()
    _cache = (now, payload)
    return payload


def verify_artifact_sha256(path: str, expected_sha256: str) -> bool:
    expected = expected_sha256.strip().lower()
    if len(expected) != 64:
        return False
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest() == expected


def _check_github_release() -> dict[str, Any] | None:
    try:
        resp = httpx.get(_GITHUB_LATEST_RELEASE_URL, timeout=5.0, follow_redirects=True)
        resp.raise_for_status()
        release = resp.json()
    except Exception:
        logger.debug("GitHub release version check failed", exc_info=True)
        return None

    latest = _normalize_release_version(release.get("tag_name") or release.get("name"))
    if not _is_newer(latest, __version__):
        return None
    artifact = _select_desktop_artifact(release.get("assets") or [])
    return {
        "currentVersion": __version__,
        "latestVersion": latest,
        "releaseUrl": release.get("html_url"),
        "notes": _release_notes(release.get("body")),
        "installMode": "verified-download" if artifact and artifact.get("sha256") else "manual",
        "artifact": artifact,
        "privacy": "No workspace files, prompts, messages, or tool outputs are sent during update checks.",
    }


def _check_pypi_release() -> dict[str, Any] | None:
    try:
        resp = httpx.get(_PYPI_URL, timeout=5.0, follow_redirects=True)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        logger.debug("PyPI version check failed", exc_info=True)
        return None

    latest = data.get("info", {}).get("version")
    if not _is_newer(latest, __version__):
        return None
    artifact = _select_pypi_artifact(data.get("releases", {}).get(latest, []))
    return {
        "currentVersion": __version__,
        "latestVersion": latest,
        "releaseUrl": data.get("info", {}).get("project_url") or "https://pypi.org/project/mira-ai/",
        "pypiUrl": "https://pypi.org/project/mira-ai/",
        "notes": (
            "Python package update is available. Desktop installers stay manual unless a "
            "signed installer asset with SHA-256 checksums is published."
        ),
        "installMode": "manual",
        "artifact": artifact,
        "privacy": "No workspace files, prompts, messages, or tool outputs are sent during update checks.",
    }


def _is_newer(latest: str | None, current: str) -> bool:
    if not latest:
        return False
    try:
        return Version(_normalize_release_version(latest)) > Version(_normalize_release_version(current))
    except InvalidVersion:
        return latest != current


def _normalize_release_version(value: Any) -> str:
    text = str(value or "").strip()
    return text[1:] if text.startswith("v") else text


def _release_notes(value: Any) -> str:
    notes = str(value or "").strip()
    return notes if len(notes) <= 1200 else notes[:1200].rstrip() + "..."


def _desktop_suffixes() -> tuple[str, ...]:
    system = platform.system().lower()
    if system == "darwin":
        return (".dmg", ".pkg", ".zip")
    if system == "windows":
        return (".exe", ".msi", ".zip")
    return (".appimage", ".deb", ".rpm", ".tar.gz")


def _select_desktop_artifact(assets: list[dict[str, Any]]) -> dict[str, Any] | None:
    hashes = _asset_hashes(assets)
    for asset in assets:
        name = str(asset.get("name") or "")
        lower = name.lower()
        if not any(lower.endswith(suffix) for suffix in _desktop_suffixes()):
            continue
        return {
            "name": name,
            "downloadUrl": asset.get("browser_download_url"),
            "sizeBytes": asset.get("size"),
            "sha256": hashes.get(name),
            "verified": bool(hashes.get(name)),
        }
    return None


def _select_pypi_artifact(files: list[dict[str, Any]]) -> dict[str, Any] | None:
    for file_info in files:
        name = str(file_info.get("filename") or "")
        digest = (file_info.get("digests") or {}).get("sha256")
        if name and digest:
            return {
                "name": name,
                "downloadUrl": file_info.get("url"),
                "sizeBytes": file_info.get("size"),
                "sha256": digest,
                "verified": True,
            }
    return None


def _asset_hashes(assets: list[dict[str, Any]]) -> dict[str, str]:
    checksum_asset = next(
        (
            asset
            for asset in assets
            if str(asset.get("name") or "").lower() in {"sha256sums.txt", "sha256sum.txt"}
        ),
        None,
    )
    url = checksum_asset.get("browser_download_url") if checksum_asset else None
    if not url:
        return {}
    try:
        resp = httpx.get(url, timeout=5.0, follow_redirects=True)
        resp.raise_for_status()
    except Exception:
        logger.debug("release checksum fetch failed", exc_info=True)
        return {}

    hashes: dict[str, str] = {}
    for line in resp.text.splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) != 2:
            continue
        digest, filename = parts
        filename = filename.lstrip("*")
        if len(digest) == 64:
            hashes[filename] = digest.lower()
    return hashes
