"""Kernel-oriented runtime facade.

`mira` remains the full SDK surface. `KernelApp` narrows that surface for
products that want a stable mature-agent boundary: a small kernel API under a
thin GUI.
"""

from __future__ import annotations

from typing import Any

from mira.agent.loop import AgentLoop
from mira.config.schema import Config
from mira.execution_gate import ExecutionGate
from mira.mira import mira
from mira.providers.image_generation import image_gen_provider_configs

from . import manifest as _manifest
from .actions import (
    _adapter_actions as _adapter_actions,
)
from .actions import (
    _bridge_actions as _bridge_actions,
)
from .actions import (
    _fault_posture_actions as _fault_posture_actions,
)
from .actions import (
    _merge_module_native_state as _merge_module_native_state,
)
from .actions import (
    _module_actions as _module_actions,
)
from .actions import (
    _native_module_actions as _native_module_actions,
)
from .actions import (
    _session_control_actions as _session_control_actions,
)
from .actions import (
    _worker_control_actions as _worker_control_actions,
)
from .authorization import KernelAuthorizer
from .manifest import (
    _build_scheduler_state,
)
from .manifest import (
    _copy_rows as _copy_rows,
)
from .manifest import (
    build_kernel_manifest as build_kernel_manifest,
)
from .module_registry import list_kernel_modules
from .native_bridge import dispatch_native_bridge_command as dispatch_native_bridge_command
from .profile import KernelProfile, lite_customer_profile
from .runtime_adapter import list_runtime_adapters
from .runtime_bridge import build_runtime_bridges
from .runtime_control import build_runtime_control_state
from .runtime_methods import KernelAppRuntimeMixin
from .session_projection import KernelSessionProjector
from .shell import ShellDescriptor, default_engineering_shell

KERNEL_MANIFEST_VERSION = _manifest.KERNEL_MANIFEST_VERSION
KERNEL_EVENT_CONTRACT_VERSION = _manifest.KERNEL_EVENT_CONTRACT_VERSION
KERNEL_SNAPSHOT_CONTRACT_VERSION = _manifest.KERNEL_SNAPSHOT_CONTRACT_VERSION
_SHARED_KERNEL_APP: KernelApp | None = None



def active_kernel_app() -> KernelApp | None:
    return _SHARED_KERNEL_APP


def register_kernel_loop(
    loop: AgentLoop,
    *,
    config: Config | None = None,
    profile: KernelProfile | None = None,
    shell: ShellDescriptor | None = None,
) -> KernelApp:
    global _SHARED_KERNEL_APP
    if _SHARED_KERNEL_APP is not None:
        _SHARED_KERNEL_APP.attach_loop(loop)
        return _SHARED_KERNEL_APP
    _SHARED_KERNEL_APP = KernelApp.from_loop(
        loop,
        config=config,
        profile=profile,
        shell=shell,
    )
    return _SHARED_KERNEL_APP


class KernelApp(KernelAppRuntimeMixin):
    """Thin kernel wrapper around the existing agent loop."""

    def __init__(
        self,
        bot: mira,
        *,
        config: Config | None = None,
        profile: KernelProfile | None = None,
        shell: ShellDescriptor | None = None,
    ) -> None:
        self._bot = bot
        self._config = config
        self._profile = profile or lite_customer_profile()
        self._shell = shell or default_engineering_shell()
        self._loop: AgentLoop | None = getattr(bot, "_loop", None)
        self._execution_gate: ExecutionGate = getattr(self._loop, "execution_gate", None) or ExecutionGate()
        self._authorizer = KernelAuthorizer()
        self._runtime_adapters = list_runtime_adapters()
        self._runtime_modules = list_kernel_modules(self._profile)
        default_adapter = "python-inprocess"
        self._runtime_bridges = build_runtime_bridges(
            self._runtime_adapters,
            active_adapter=default_adapter,
        )
        self._runtime_control = build_runtime_control_state(
            self._profile,
            default_adapter=default_adapter,
            module_names=[str(module["name"]) for module in self._runtime_modules],
        )
        self._scheduler_state = _build_scheduler_state()
        self._event_log: list[dict[str, Any]] = []
        self._native_module_states: dict[str, dict[str, Any]] = {}
        self._native_bridge_artifact: str | None = None
        self._native_recent_commands: list[dict[str, Any]] = []
        self._native_last_command: dict[str, Any] | None = None
        self._reset_native_command_state()
        self._dispatch_queue: list[dict[str, Any]] = []
        self._session_metadata: dict[str, dict[str, Any]] = {}
        self._session_status: dict[str, str] = {}
        self._session_runtime: dict[str, dict[str, Any]] = {}
        self._session_latency: dict[str, int | None] = {}
        self._active_session_key: str | None = None
        self._runtime_subscription_attached = False
        self._checkpoint_signatures: dict[str, tuple[Any, ...]] = {}
        self._subagent_signatures: dict[str, tuple[Any, ...]] = {}
        self._session_projector = KernelSessionProjector(self)
        self._attach_runtime_bus()
        self._record_kernel_event(
            "kernel_boot",
            state="ready",
            message=f"{self._profile.name} profile initialized",
        )

    @classmethod
    def build_loop(
        cls,
        config: Config,
    ) -> AgentLoop:
        """Expose loop construction behind the kernel namespace."""
        from mira.agent.hooks import create_file_edit_activity_hook

        return AgentLoop.from_config(
            config,
            image_generation_provider_configs=image_gen_provider_configs(config),
            hook_factories=[create_file_edit_activity_hook],
        )


KernelApp.execute_operator_command.__module__ = __name__
