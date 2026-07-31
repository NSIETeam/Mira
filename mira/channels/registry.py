"""Discover channel descriptors and load their runtimes lazily."""

from __future__ import annotations

import pkgutil
from functools import cache
from importlib.metadata import entry_points
from typing import TYPE_CHECKING

from loguru import logger

from mira.channels.plugin import (
    ChannelPlugin,
    has_channel_package,
    load_channel_package,
)

if TYPE_CHECKING:
    from mira.channels.base import BaseChannel


@cache
def _warn_legacy_channel_entry_points() -> None:
    # TODO(v0.3.1): Remove this detection and warning. v0.3.0 is the final
    # migration window for installed legacy channel entry points.
    names = sorted({entry_point.name for entry_point in entry_points(group="mira.channels")})
    if not names:
        return
    logger.warning(
        "Legacy channel entry points were detected but will not be loaded: {}. "
        "The '{}' entry-point group is no longer supported; use a built-in channel or "
        "migrate it into mira/channels/<channel>/.",
        ", ".join(names),
        "mira.channels",
    )


def _channel_package_names() -> list[str]:
    import mira.channels as package

    return [
        name
        for _, name, is_package in pkgutil.iter_modules(package.__path__)
        if is_package and has_channel_package(name)
    ]


def discover_plugins(
    enabled_names: set[str] | None = None,
    *,
    include_archived: bool = False,
) -> dict[str, ChannelPlugin]:
    """Load dependency-free descriptors from self-contained channel packages."""
    _warn_legacy_channel_entry_points()
    plugins: dict[str, ChannelPlugin] = {}
    for name in _channel_package_names():
        if enabled_names is not None and name not in enabled_names:
            continue
        try:
            plugin = load_channel_package(name)
            if plugin is not None:
                if plugin.tier == "archive" and not include_archived:
                    continue
                plugins[name] = plugin
        except Exception as exc:
            logger.warning("Failed to load channel package descriptor '{}': {}", name, exc)
    plugins.update(_discover_external_plugins(enabled_names, existing=set(plugins)))
    return plugins


def _discover_external_plugins(
    enabled_names: set[str] | None,
    *,
    existing: set[str],
) -> dict[str, ChannelPlugin]:
    """Load external channel descriptors registered by plugin packages."""
    plugins: dict[str, ChannelPlugin] = {}
    for group, prefix in (("mira.channel_plugins", ""), ("mira.plugins", "channel-")):
        try:
            eps = entry_points(group=group)
        except Exception as exc:
            logger.debug("Failed to inspect {} entry points: {}", group, exc)
            continue
        for ep in eps:
            if prefix and not ep.name.startswith(prefix):
                continue
            declared_name = ep.name.removeprefix(prefix).replace("-", "_")
            if enabled_names is not None and declared_name not in enabled_names:
                continue
            if declared_name in existing or declared_name in plugins:
                logger.warning("External channel plugin '{}' skipped: name already exists", declared_name)
                continue
            try:
                loaded = ep.load()
                plugin = loaded() if callable(loaded) and not isinstance(loaded, ChannelPlugin) else loaded
                if not isinstance(plugin, ChannelPlugin):
                    raise TypeError("entry point did not resolve to a ChannelPlugin")
                if plugin.name != declared_name:
                    raise TypeError(
                        f"entry point name declares '{declared_name}' but plugin name is '{plugin.name}'"
                    )
                plugins[plugin.name] = plugin
            except Exception as exc:
                logger.warning("Failed to load external channel plugin '{}': {}", ep.name, exc)
    return plugins


def load_channel_plugin(name: str) -> ChannelPlugin:
    """Load one channel package descriptor."""
    try:
        plugin = discover_plugins({name}, include_archived=True).get(name)
    except TypeError:
        # Test and extension monkeypatches may still provide the pre-tier
        # discover_plugins(enabled_names) signature.
        plugin = discover_plugins({name}).get(name)
    if plugin is None:
        raise ImportError(f"Unknown channel: {name}")
    return plugin


def channel_default_enabled(name: str) -> bool:
    """Return the activation default declared by a channel descriptor."""
    try:
        return load_channel_plugin(name).default_enabled
    except ImportError:
        return False


def load_channel_class(name: str) -> type[BaseChannel]:
    """Load the runtime declared by one channel descriptor."""
    return load_channel_plugin(name).load_channel_class()


def discover_enabled(
    enabled_names: set[str],
    *,
    _plugins: dict[str, ChannelPlugin] | None = None,
    warn_import_errors: bool = False,
) -> dict[str, type[BaseChannel]]:
    """Load runtime classes only for enabled descriptors."""
    plugins = _plugins if _plugins is not None else discover_plugins(enabled_names)
    result: dict[str, type[BaseChannel]] = {}
    for name, plugin in plugins.items():
        if name not in enabled_names:
            continue
        try:
            result[name] = plugin.load_channel_class()
        except Exception as exc:
            message = "Enabled channel '{}' runtime is not available: {}"
            if warn_import_errors:
                logger.warning(message, name, exc)
            else:
                logger.debug(message, name, exc)
    return result


def discover_all() -> dict[str, type[BaseChannel]]:
    """Load every available channel runtime."""
    plugins = discover_plugins()
    return discover_enabled(set(plugins), _plugins=plugins)


__all__ = [
    "channel_default_enabled",
    "discover_all",
    "discover_enabled",
    "discover_plugins",
    "load_channel_class",
    "load_channel_plugin",
]
