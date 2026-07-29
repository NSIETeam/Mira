from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_dockerfile_declares_and_consumes_mira_channels() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "ARG MIRA_CHANNELS=whatsapp" in dockerfile
    assert "selected_channels=\"${MIRA_CHANNELS:-${NANOBOT_CHANNELS:-whatsapp}}\"" in dockerfile
    assert "scripts.install_channel_dependencies \"$channel\"" in dockerfile


def test_compose_passes_canonical_channel_build_arg() -> None:
    compose = (ROOT / "docker-compose.yml").read_text()
    assert "MIRA_CHANNELS: ${MIRA_CHANNELS:-whatsapp}" in compose
    assert "mira_CHANNELS" not in compose
