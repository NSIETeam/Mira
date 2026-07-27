"""Kernel-oriented runtime facade.

`Nanobot` remains the full SDK surface. `KernelApp` narrows that surface for
products that want a stable mature-agent boundary: a small kernel API under a
thin GUI.
"""

from __future__ import annotations

from pathlib import Path

from nanobot.agent.loop import AgentLoop
from nanobot.config.schema import Config
from nanobot.nanobot import Nanobot, RunResult, RunStream
from nanobot.providers.image_generation import image_gen_provider_configs
from .profile import KernelProfile, lite_customer_profile


class KernelApp:
    """Thin kernel wrapper around the existing agent loop."""

    def __init__(
        self,
        bot: Nanobot,
        *,
        config: Config | None = None,
        profile: KernelProfile | None = None,
    ) -> None:
        self._bot = bot
        self._config = config
        self._profile = profile or lite_customer_profile()

    @property
    def bot(self) -> Nanobot:
        """Expose the underlying bot for advanced integrations."""
        return self._bot

    @property
    def config(self) -> Config | None:
        return self._config

    @property
    def profile(self) -> KernelProfile:
        return self._profile

    @classmethod
    def from_config(
        cls,
        config_path: str | Path | None = None,
        *,
        workspace: str | Path | None = None,
        model: str | None = None,
        model_preset: str | None = None,
        profile: KernelProfile | None = None,
    ) -> KernelApp:
        """Construct a kernel runtime from the standard nanobot config."""
        bot = Nanobot.from_config(
            config_path=config_path,
            workspace=workspace,
            model=model,
            model_preset=model_preset,
        )
        return cls(bot, config=bot._config, profile=profile)

    @classmethod
    def from_loop(
        cls,
        loop: AgentLoop,
        *,
        config: Config | None = None,
        profile: KernelProfile | None = None,
    ) -> KernelApp:
        return cls(Nanobot(loop, config=config), config=config, profile=profile)

    async def run(self, message: str, **kwargs: object) -> RunResult:
        """Single-turn execution via the kernel boundary."""
        return await self._bot.run(message, **kwargs)

    async def run_streamed(self, message: str, **kwargs: object) -> RunStream:
        """Streamed execution for GUI shells.

        Consumers should normalize emitted SDK events with
        `kernel.normalize_stream_event` before rendering them.
        """
        return await self._bot.run_streamed(message, **kwargs)

    @classmethod
    def build_loop(
        cls,
        config: Config,
    ) -> AgentLoop:
        """Expose loop construction behind the kernel namespace."""
        from nanobot.agent.hooks import create_file_edit_activity_hook

        return AgentLoop.from_config(
            config,
            image_generation_provider_configs=image_gen_provider_configs(config),
            hook_factories=[create_file_edit_activity_hook],
        )
