"""Mira kernel profile namespace forwarding to nanobot.kernel.profile."""

from nanobot.kernel.profile import *  # noqa: F401,F403
from nanobot.kernel.profile import KernelProfile, get_profile, list_profiles

__all__ = ["KernelProfile", "get_profile", "list_profiles"]
