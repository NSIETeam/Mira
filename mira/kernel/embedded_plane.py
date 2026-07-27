"""Mira embedded-plane namespace forwarding to nanobot.kernel.embedded_plane."""

from nanobot.kernel.embedded_plane import *  # noqa: F401,F403
from nanobot.kernel.embedded_plane import build_board_snapshot, build_embedded_topology

__all__ = ["build_board_snapshot", "build_embedded_topology"]
