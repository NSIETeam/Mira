"""Implementation for the `mira onboard` route."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import typer
from rich.console import Console

from mira import __cli_name__
from mira.config.schema import Config

console = Console()


def onboard_plugins(config_path: Path) -> None:
    """Inject default config for all discovered channels (built-in + plugins)."""
    from mira.channels.contracts import channel_default_config
    from mira.channels.registry import discover_plugins
    from mira.config.loader import merge_missing_defaults

    plugins = discover_plugins()
    if not plugins:
        return

    with open(config_path, encoding="utf-8") as f:
        data = json.load(f)

    channels = data.setdefault("channels", {})
    for name, plugin in plugins.items():
        defaults = channel_default_config(plugin)
        if name not in channels:
            channels[name] = defaults
        else:
            channels[name] = merge_missing_defaults(channels[name], defaults)

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def run_onboard_command(
    *,
    workspace: str | None,
    config: str | None,
    wizard: bool,
    non_interactive_refresh: bool,
    onboard_plugins: Callable[[Path], None],
    sync_workspace_templates: Callable[[Path], None],
    get_workspace_path: Callable[[Path | str | None], Path],
) -> None:
    """Initialize Mira configuration and workspace."""
    from mira.config.loader import get_config_path, load_config, save_config, set_config_path

    explicit_config = config is not None
    if config:
        config_path = Path(config).expanduser().resolve()
        set_config_path(config_path)
        console.print(f"[dim]Using config: {config_path}[/dim]")
    else:
        config_path = get_config_path()

    def _apply_workspace_override(loaded: Config) -> Config:
        if workspace:
            loaded.agents.defaults.workspace = workspace
        return loaded

    if config_path.exists():
        if wizard:
            loaded_config = _apply_workspace_override(load_config(config_path))
        else:
            should_refresh = non_interactive_refresh
            if not non_interactive_refresh:
                console.print(f"[yellow]Config already exists at {config_path}[/yellow]")
                console.print(
                    "  [bold]y[/bold] = overwrite with defaults (existing values will be lost)"
                )
                console.print(
                    "  [bold]N[/bold] = refresh config, keeping existing values and adding new fields"
                )
                if typer.confirm("Overwrite?"):
                    loaded_config = _apply_workspace_override(Config())
                    save_config(loaded_config, config_path)
                    console.print(f"[green][/green] Config reset to defaults at {config_path}")
                else:
                    should_refresh = True

            if should_refresh:
                loaded_config = _apply_workspace_override(load_config(config_path))
                save_config(loaded_config, config_path)
                console.print(
                    f"[green][/green] Config refreshed at {config_path} "
                    "(existing values preserved)"
                )
    else:
        loaded_config = _apply_workspace_override(Config())
        if not wizard:
            save_config(loaded_config, config_path)
            console.print(f"[green][/green] Created config at {config_path}")

    if wizard:
        from mira.cli.onboard import run_onboard

        try:
            result = run_onboard(initial_config=loaded_config)
            if not result.should_save:
                console.print("[yellow]Configuration discarded. No changes were saved.[/yellow]")
                return

            loaded_config = result.config
            save_config(loaded_config, config_path)
            console.print(f"[green][/green] Config saved at {config_path}")
        except Exception as e:
            console.print(f"[red][/red] Error during configuration: {e}")
            console.print("[yellow]Please run 'mira onboard' again to complete setup.[/yellow]")
            raise typer.Exit(1) from e

    onboard_plugins(config_path)

    workspace_path = get_workspace_path(loaded_config.workspace_path)
    if not workspace_path.exists():
        workspace_path.mkdir(parents=True, exist_ok=True)
        console.print(f"[green][/green] Created workspace at {workspace_path}")

    sync_workspace_templates(workspace_path)

    webui_cmd = f"{__cli_name__} webui"
    if explicit_config:
        webui_cmd += f' -c "{config_path}"'

    typer.echo(f"\n mira is ready. Run: {webui_cmd}  (or: {__cli_name__} webui)")
