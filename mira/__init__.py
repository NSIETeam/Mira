"""
Mira - A lightweight execution kernel and AI agent framework
"""

import tomllib
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path


def _read_pyproject_version() -> str | None:
    """Read the source-tree version when package metadata is unavailable."""
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    if not pyproject.exists():
        return None
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    return data.get("project", {}).get("version")


def _resolve_version() -> str:
    try:
        return _pkg_version("mira")
    except PackageNotFoundError:
        # Source checkouts often import mira without installed dist-info.
        return _read_pyproject_version() or "0.3.0"


__version__ = _resolve_version()
__logo__ = ""
__app_name__ = "Mira"
__cli_name__ = "mira"
__legacy_cli_name__ = "mira"

_LAZY_EXPORTS = {
    "ExecutionKernel": ".kernel",
    "KernelApp": ".kernel",
    "KernelEvent": ".kernel",
    "KernelEventType": ".kernel",
    "KernelProfile": ".kernel",
    "ShellDescriptor": ".kernel",
    "default_engineering_shell": ".kernel",
    "normalize_stream_event": ".kernel",
    "mira": ".mira",
    "RunStream": ".mira",
    "RunResult": ".mira",
    "SessionInfo": ".mira",
    "SessionSnapshot": ".mira",
    "STREAM_EVENT_REASONING_COMPLETED": ".mira",
    "STREAM_EVENT_REASONING_DELTA": ".mira",
    "STREAM_EVENT_RUN_COMPLETED": ".mira",
    "STREAM_EVENT_RUN_FAILED": ".mira",
    "STREAM_EVENT_RUN_STARTED": ".mira",
    "STREAM_EVENT_TEXT_COMPLETED": ".mira",
    "STREAM_EVENT_TEXT_DELTA": ".mira",
    "STREAM_EVENT_TOOL_COMPLETED": ".mira",
    "STREAM_EVENT_TOOL_FAILED": ".mira",
    "STREAM_EVENT_TOOL_STARTED": ".mira",
    "STREAM_EVENT_TYPES": ".mira",
    "StreamEvent": ".mira",
    "StreamEventType": ".mira",
}


def __getattr__(name: str):
    module_path = _LAZY_EXPORTS.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module
    mod = import_module(module_path, __name__)
    val = getattr(mod, name)
    globals()[name] = val
    return val


__all__ = [
    "__app_name__",
    "__cli_name__",
    "__legacy_cli_name__",
    "ExecutionKernel",
    "KernelApp",
    "KernelEvent",
    "KernelEventType",
    "KernelProfile",
    "ShellDescriptor",
    "default_engineering_shell",
    "normalize_stream_event",
    "mira",
    "RunResult",
    "RunStream",
    "SessionInfo",
    "SessionSnapshot",
    "STREAM_EVENT_REASONING_COMPLETED",
    "STREAM_EVENT_REASONING_DELTA",
    "STREAM_EVENT_RUN_COMPLETED",
    "STREAM_EVENT_RUN_FAILED",
    "STREAM_EVENT_RUN_STARTED",
    "STREAM_EVENT_TEXT_COMPLETED",
    "STREAM_EVENT_TEXT_DELTA",
    "STREAM_EVENT_TOOL_COMPLETED",
    "STREAM_EVENT_TOOL_FAILED",
    "STREAM_EVENT_TOOL_STARTED",
    "STREAM_EVENT_TYPES",
    "StreamEvent",
    "StreamEventType",
]
