"""Channel and optional-feature CLI command registration."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from mira import __logo__
from mira import optional_features as feature_support
from mira.config.schema import Config


def register_channel_plugin_commands(
    app: typer.Typer,
    *,
    console: Console,
    load_inspection_config: Callable[..., tuple[Path, Config]],
    print_enable_options: Callable[..., None],
    set_mira_logs: Callable[[bool], None],
) -> None:
    channels_app = typer.Typer(help="Manage channels")
    app.add_typer(channels_app, name="channels")

    @channels_app.command("status")
    def channels_status(
        config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
    ) -> None:
        """Show channel status."""
        from mira.channels.registry import discover_all

        _, loaded = load_inspection_config(config=config)

        table = Table(title="Channel Status")
        table.add_column("Channel", style="cyan")
        table.add_column("Enabled")

        for name, cls in sorted(discover_all().items()):
            section = getattr(loaded.channels, name, None)
            if section is None:
                enabled = False
            elif isinstance(section, dict):
                enabled = section.get("enabled", False)
            else:
                enabled = getattr(section, "enabled", False)
            table.add_row(
                cls.display_name,
                "[green]\u2713[/green]" if enabled else "[dim]\u2717[/dim]",
            )

        console.print(table)

    @channels_app.command("login")
    def channels_login(
        channel_name: str = typer.Argument(..., help="Channel name (e.g. weixin, whatsapp)"),
        force: bool = typer.Option(
            False,
            "--force",
            "-f",
            help="Force re-authentication even if already logged in",
        ),
        config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
    ) -> None:
        """Authenticate with a channel via QR code or other interactive login."""
        from mira.channels.registry import discover_all

        _, loaded = load_inspection_config(config=config)
        channel_cfg = getattr(loaded.channels, channel_name, None) or {}

        all_channels = discover_all()
        if channel_name not in all_channels:
            available = ", ".join(all_channels.keys())
            console.print(f"[red]Unknown channel: {channel_name}[/red]  Available: {available}")
            raise typer.Exit(1)

        console.print(f"{__logo__} {all_channels[channel_name].display_name} Login\n")

        channel_cls = all_channels[channel_name]
        channel = channel_cls(channel_cfg, bus=None)

        success = asyncio.run(channel.login(force=force))
        if not success:
            raise typer.Exit(1)

    plugins_app = typer.Typer(help="Manage optional Mira features")
    app.add_typer(plugins_app, name="plugins")

    @plugins_app.command("list")
    def plugins_list(
        config_path: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
    ) -> None:
        """List optional Mira features."""
        from mira.channels.registry import discover_plugins
        from mira.config.loader import load_config, set_config_path

        resolved_config_path = Path(config_path).expanduser().resolve() if config_path else None
        if resolved_config_path is not None:
            set_config_path(resolved_config_path)

        print_enable_options(
            feature_support.optional_dependency_groups(),
            discover_plugins(),
            load_config(resolved_config_path),
        )

    @plugins_app.command("enable")
    def plugins_enable(
        name: str = typer.Argument(..., help="Feature name (e.g. weixin, matrix, bedrock)"),
        config_path: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
        logs: bool = typer.Option(
            False,
            "--logs/--no-logs",
            help="Show optional package install logs",
        ),
    ) -> None:
        """Enable a Mira feature."""
        from mira.config.loader import get_config_path, set_config_path

        resolved_config_path = Path(config_path).expanduser().resolve() if config_path else None
        if resolved_config_path is not None:
            set_config_path(resolved_config_path)
        resolved_config_path = resolved_config_path or get_config_path()
        set_mira_logs(logs)

        try:
            payload = feature_support.enable_optional_feature(
                name,
                config_path=resolved_config_path,
                runner=feature_support.run_install_command,
            )
        except feature_support.OptionalFeatureError as exc:
            console.print(f"[red]{escape(exc.message)}[/red]")
            raise typer.Exit(1) from exc

        message = payload.get("last_action", {}).get("message") or f"Enabled feature '{name}'"
        console.print(f"[green]{escape(message)}[/green]")

    @plugins_app.command("disable")
    def plugins_disable(
        name: str = typer.Argument(..., help="Channel name (e.g. telegram, matrix, slack)"),
        config_path: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
    ) -> None:
        """Disable a Mira channel feature."""
        from mira.config.loader import get_config_path, set_config_path

        resolved_config_path = Path(config_path).expanduser().resolve() if config_path else None
        if resolved_config_path is not None:
            set_config_path(resolved_config_path)
        resolved_config_path = resolved_config_path or get_config_path()

        try:
            payload = feature_support.disable_optional_feature(name, config_path=resolved_config_path)
        except feature_support.OptionalFeatureError as exc:
            console.print(f"[red]{escape(exc.message)}[/red]")
            raise typer.Exit(1) from exc

        message = payload.get("last_action", {}).get("message") or f"Disabled channel '{name}'"
        console.print(f"[green]{escape(message)}[/green] in {resolved_config_path}")
