"""Mira package namespace forwarding to the mature kernel/runtime surface."""

from nanobot import *  # noqa: F401,F403
from nanobot import __all__ as _nanobot_all
from mira.kernel import KernelApp, ExecutionKernel
from mira.runtime import Nanobot, RunResult, RunStream, SessionInfo, SessionSnapshot

__all__ = list(_nanobot_all)
for _name in (
    "KernelApp",
    "ExecutionKernel",
    "Nanobot",
    "RunResult",
    "RunStream",
    "SessionInfo",
    "SessionSnapshot",
):
    if _name not in __all__:
        __all__.append(_name)
