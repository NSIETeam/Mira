"""Runtime config helpers shared by CLI commands."""

import json
import shutil
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from mira import optional_features as feature_support
from mira.config.schema import Config


def print_enable_options(
    extras: dict[str, list[str] | None],
    channel_plugins: dict[str, Any],
    config: Config,
    *,
    console: Console,
) -> None:
    table = Table(title="Available Features")
    table.add_column("Name", style="cyan")
    table.add_column("Type")
    table.add_column("Enabled")

    for item in sorted(set(channel_plugins) | set(extras)):
        plugin = channel_plugins.get(item)
        is_channel = plugin is not None
        enabled = (
            feature_support.channel_enabled(
                config,
                item,
                plugin,
                default_enabled=plugin.default_enabled,
            )
            if is_channel
            else feature_support.extra_installed(item, extras[item])
        )
        table.add_row(
            item,
            "channel" if is_channel else "feature",
            "[green]yes[/green]" if enabled else "[dim]no[/dim]",
        )

    console.print(table)


def model_display(config: Config) -> tuple[str, str]:
    """Return (resolved_model_name, preset_tag) for display strings."""
    resolved = config.resolve_preset()
    name = config.agents.defaults.model_preset
    tag = f" (preset: {name})" if name else ""
    return resolved.model, tag


def warn_deprecated_config_keys(config_path: Path | None, *, console: Console) -> None:
    """Hint users to remove obsolete keys from their config file."""
    from mira.config.loader import get_config_path

    path = config_path or get_config_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    if "memoryWindow" in raw.get("agents", {}).get("defaults", {}):
        console.print(
            "[dim]Hint: `memoryWindow` in your config is no longer used "
            "and can be safely removed.[/dim]"
        )


def load_runtime_config(
    config: str | None = None,
    workspace: str | None = None,
    *,
    console: Console,
) -> Config:
    """Load config and optionally override the active workspace."""
    from mira.config.loader import load_config, resolve_config_env_vars, set_config_path

    config_path = None
    if config:
        config_path = Path(config).expanduser().resolve()
        if not config_path.exists():
            console.print(f"[red]Error: Config file not found: {config_path}[/red]")
            raise typer.Exit(1)
        set_config_path(config_path)
        console.print(f"[dim]Using config: {config_path}[/dim]")

    try:
        loaded = resolve_config_env_vars(load_config(config_path))
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
    warn_deprecated_config_keys(config_path, console=console)
    if workspace:
        loaded.agents.defaults.workspace = workspace
    return loaded


def load_inspection_config(
    config: str | None = None,
    workspace: str | None = None,
    *,
    console: Console,
) -> tuple[Path, Config]:
    """Load config for diagnostic commands without resolving secret env refs."""
    from mira.config.loader import get_config_path, load_config, set_config_path

    config_path = None
    if config:
        config_path = Path(config).expanduser().resolve(strict=False)
        set_config_path(config_path)
        console.print(f"[dim]Using config: {config_path}[/dim]")

    display_path = config_path or get_config_path()
    try:
        loaded = load_config(config_path)
    except ValueError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(1) from exc
    warn_deprecated_config_keys(display_path, console=console)
    if workspace:
        loaded.agents.defaults.workspace = workspace
    return display_path, loaded


def migrate_cron_store(config: Config) -> None:
    """One-time migration: move legacy global cron store into the workspace."""
    from mira.config.paths import get_cron_dir

    legacy_path = get_cron_dir() / "jobs.json"
    new_path = config.workspace_path / "cron" / "jobs.json"
    if legacy_path.is_file() and not new_path.exists():
        new_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(legacy_path), str(new_path))
