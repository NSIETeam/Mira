"""Mira kernel shell namespace forwarding to nanobot.kernel.shell."""

from nanobot.kernel.shell import *  # noqa: F401,F403
from nanobot.kernel.shell import ShellDescriptor, default_engineering_shell, get_shell, list_shells

__all__ = ["ShellDescriptor", "default_engineering_shell", "get_shell", "list_shells"]
