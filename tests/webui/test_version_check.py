import hashlib

from mira.webui import version_check


class FakeResponse:
    def __init__(self, payload=None, text=""):
        self._payload = payload or {}
        self.text = text

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_github_update_selects_platform_artifact_with_sha256(monkeypatch):
    monkeypatch.setattr(version_check, "__version__", "0.3.0")
    monkeypatch.setattr(version_check.platform, "system", lambda: "Darwin")
    version_check._cache = (0.0, None)

    def fake_get(url, **_kwargs):
        if url.endswith("/releases/latest"):
            return FakeResponse(
                {
                    "tag_name": "v0.4.0",
                    "html_url": "https://github.com/NSIETeam/Mira/releases/tag/v0.4.0",
                    "body": "Desktop release",
                    "assets": [
                        {
                            "name": "Mira-0.4.0.dmg",
                            "browser_download_url": "https://example.test/Mira.dmg",
                            "size": 119_000_000,
                        },
                        {
                            "name": "SHA256SUMS.txt",
                            "browser_download_url": "https://example.test/SHA256SUMS.txt",
                            "size": 80,
                        },
                    ],
                }
            )
        return FakeResponse(text="a" * 64 + "  Mira-0.4.0.dmg\n")

    monkeypatch.setattr(version_check.httpx, "get", fake_get)

    result = version_check.check_for_update()

    assert result is not None
    assert result["latestVersion"] == "0.4.0"
    assert result["installMode"] == "verified-download"
    assert result["artifact"]["name"] == "Mira-0.4.0.dmg"
    assert result["artifact"]["sha256"] == "a" * 64
    assert "workspace" in result["privacy"].lower()


def test_verify_artifact_sha256(tmp_path):
    artifact = tmp_path / "Mira.dmg"
    artifact.write_bytes(b"installer")
    expected = hashlib.sha256(b"installer").hexdigest()

    assert version_check.verify_artifact_sha256(str(artifact), expected)
    assert not version_check.verify_artifact_sha256(str(artifact), "0" * 64)
