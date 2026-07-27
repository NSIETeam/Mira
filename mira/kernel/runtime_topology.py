"""Mira runtime-topology namespace forwarding to nanobot.kernel.runtime_topology."""

from nanobot.kernel.runtime_topology import *  # noqa: F401,F403
from nanobot.kernel.runtime_topology import build_runtime_topology

__all__ = ["build_runtime_topology"]
