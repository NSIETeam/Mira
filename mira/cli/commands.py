"""Mira CLI entry forwarding to nanobot CLI commands."""

from nanobot.cli.commands import *  # noqa: F401,F403
from nanobot.cli.commands import app

__all__ = ["app"]
