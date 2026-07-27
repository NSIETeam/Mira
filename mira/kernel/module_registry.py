"""Mira kernel module registry namespace forwarding to nanobot.kernel.module_registry."""

from nanobot.kernel.module_registry import *  # noqa: F401,F403
from nanobot.kernel.module_registry import KernelModuleDescriptor, list_kernel_modules

__all__ = ["KernelModuleDescriptor", "list_kernel_modules"]
