"""Implementation for the `mira webui` route."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

from mira import __app_name__, __cli_name__
from mira.config.paths import get_workspace_path
from mira.config.schema import Config
from mira.webui.build import BuildMode

console = Console()


@dataclass(frozen=True)
class WebUICommandDeps:
    ensure_interactive_tty_mode: Callable[[], None]
    resolve_webui_config_path: Callable[[str | None], Path]
    sync_workspace_templates: Callable[..., None]
    confirm_webui_action: Callable[..., None]
    load_webui_setup_config: Callable[[Path], Config]
    provider_setup_error: Callable[[Config], str | None]
    run_quick_start_for_webui: Callable[..., Config]
    ensure_local_webui_channel: Callable[..., tuple[bool, bool]]
    warn_webui_bind_scope: Callable[[Config], None]
    webui_browser_url: Callable[..., str]
    load_runtime_config: Callable[[str | None, str | None], Config]
    webui_display_url: Callable[[str], str]
    gateway_health_url: Callable[[str, int], str]
    gateway_health_bind_note: Callable[[str], str]
    webui_build_mode_for_interactive: Callable[..., BuildMode]
    prepare_webui_bundle_for_gateway: Callable[..., None]
    gateway_instance_command: Callable[..., str]
    open_webui_browser: Callable[..., None]
    gateway_health_ready: Callable[..., bool]
    webui_endpoint_reachable: Callable[..., bool]
    attach_to_background_gateway: Callable[[Any], None]
    tcp_endpoint_reachable: Callable[..., bool]
    host_for_local_browser: Callable[[str], str]
    print_foreground_port_conflict: Callable[..., None]
    print_webui_foreground_lifecycle: Callable[..., None]
    run_gateway: Callable[..., None]


def run_webui_command(
    *,
    port: int | None,
    gateway_port: int | None,
    workspace: str | None,
    config: str | None,
    background: bool,
    no_open: bool,
    yes: bool,
    user: str | None,
    group: str | None,
    deps: WebUICommandDeps,
) -> None:
    """Prepare the local WebUI, start the gateway, and open the browser workbench."""
    from mira.config.loader import resolve_config_env_vars, save_config
    from mira.gateway import GatewayRuntime, GatewayRuntimePaths, GatewayStartOptions

    deps.ensure_interactive_tty_mode()
    config_path = deps.resolve_webui_config_path(config)
    created_config = not config_path.exists()
    if created_config:
        console.print(f"[yellow]No config found at {config_path}.[/yellow]")
        deps.confirm_webui_action("Create a Mira config and workspace now?", yes=yes)

    setup_config = deps.load_webui_setup_config(config_path)
    if workspace:
        setup_config.agents.defaults.workspace = workspace

    try:
        resolved_setup_config = resolve_config_env_vars(setup_config.model_copy(deep=True))
    except ValueError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(1) from exc

    provider_error = deps.provider_setup_error(resolved_setup_config)
    settings_setup_error = provider_error if provider_error and created_config else None
    if settings_setup_error:
        console.print(f"[yellow]Model setup is incomplete: {provider_error}[/yellow]")
        console.print("Configure a provider and model in WebUI Settings → Models.")
        if background:
            console.print(
                "[red]First-time WebUI setup must run in the foreground. "
                f"Run `{__cli_name__} webui` without --background.[/red]"
            )
            raise typer.Exit(1)
    elif provider_error:
        console.print(f"[dim]Provider check: {provider_error}[/dim]")
        setup_config = deps.run_quick_start_for_webui(setup_config, yes=yes)
        if workspace:
            setup_config.agents.defaults.workspace = workspace

    try:
        changed_webui, generated_bootstrap_secret = deps.ensure_local_webui_channel(
            setup_config,
            port=port,
            yes=yes,
        )
        deps.warn_webui_bind_scope(setup_config)
        webui_url = deps.webui_browser_url(setup_config, user=user, group=group)
    except ValueError as exc:
        console.print(f"[red]Error: invalid WebUI channel config: {exc}[/red]")
        raise typer.Exit(1) from exc

    if created_config or provider_error or changed_webui or workspace:
        save_config(setup_config, config_path)
        console.print(f"[green][/green] Saved config: {config_path}")

    workspace_path = get_workspace_path(setup_config.workspace_path)
    workspace_path.mkdir(parents=True, exist_ok=True)
    deps.sync_workspace_templates(workspace_path)

    runtime_config = deps.load_runtime_config(str(config_path), workspace)
    effective_gateway_port = gateway_port if gateway_port is not None else runtime_config.gateway.port

    console.print()
    console.print(f"WebUI: [cyan]{deps.webui_display_url(webui_url)}[/cyan]")
    gateway_health_url = deps.gateway_health_url(
        runtime_config.gateway.host,
        effective_gateway_port,
    )
    console.print(
        f"Gateway health: [cyan]{gateway_health_url}[/cyan]"
        f"{deps.gateway_health_bind_note(runtime_config.gateway.host)}"
    )
    if no_open:
        console.print("[dim]Browser opening disabled by --no-open.[/dim]")
        if generated_bootstrap_secret:
            console.print(
                "[yellow]A WebUI bootstrap secret was generated and saved in this config.[/yellow]"
            )
            console.print(
                "[dim]Open the WebUI and enter channels.websocket.tokenIssueSecret from "
                f"{config_path}, or rerun without --no-open to open the authenticated URL.[/dim]"
            )

    webui_bundle_mode = deps.webui_build_mode_for_interactive(yes=yes)

    config_arg = str(config_path)
    workspace_arg = str(Path(workspace).expanduser().resolve(strict=False)) if workspace else None
    runtime = GatewayRuntime(
        paths=GatewayRuntimePaths.for_instance(
            data_dir=config_path.parent,
            workspace=workspace_arg,
            config_path=config_arg,
        )
    )
    start_options = GatewayStartOptions(
        port=effective_gateway_port,
        workspace=workspace_arg,
        config_path=config_arg,
    )

    if background:
        deps.prepare_webui_bundle_for_gateway(runtime_config, mode=webui_bundle_mode)
        result = runtime.start_background(start_options)
        restarted = False
        restart_attempted = False
        if not result.ok and result.message == "gateway_already_running" and changed_webui:
            restart_attempted = True
            console.print("[yellow]WebUI config changed; restarting the background gateway.[/yellow]")
            result = runtime.restart(start_options, timeout_s=20)
            restarted = result.ok
        if not result.ok and (restart_attempted or result.message != "gateway_already_running"):
            action = "restarted" if restart_attempted else "started"
            console.print(f"[yellow]Gateway was not {action}: {result.message}[/yellow]")
            console.print(f"Logs: {result.status.log_path}")
            raise typer.Exit(1)
        if restarted:
            console.print("[green]Gateway restarted in the background.[/green]")
        elif result.ok:
            console.print("[green]Gateway started in the background.[/green]")
        else:
            console.print("[yellow]Gateway is already running in the background.[/yellow]")
        console.print(
            "Manage this instance: "
            f"[cyan]{deps.gateway_instance_command('status', config_path=config_path, workspace=workspace)}[/cyan]"
        )
        console.print(
            "View logs: "
            f"[cyan]{deps.gateway_instance_command('logs', config_path=config_path, workspace=workspace)}[/cyan]"
        )
        console.print("[dim]Closing the browser does not stop channels or automations.[/dim]")
        console.print(
            f"Stop {__app_name__}: "
            f"[cyan]{deps.gateway_instance_command('stop', config_path=config_path, workspace=workspace)}[/cyan]"
        )
        if not no_open:
            deps.open_webui_browser(webui_url)
        return

    gateway_ready = deps.gateway_health_ready(runtime_config.gateway.host, effective_gateway_port)
    webui_ready = deps.webui_endpoint_reachable(webui_url)
    if gateway_ready and webui_ready:
        console.print("[yellow]Gateway is already running; attaching to the existing WebUI.[/yellow]")
        console.print(
            "Restart the gateway if you need it to pick up local source changes: "
            f"[cyan]{deps.gateway_instance_command('restart', config_path=config_path, workspace=workspace)}[/cyan]"
        )
        if not no_open:
            deps.open_webui_browser(webui_url, wait=False)
        if runtime.status().running:
            deps.attach_to_background_gateway(runtime)
        else:
            console.print(
                "[yellow]This gateway is controlled by another foreground command. "
                "Stop it from that terminal.[/yellow]"
            )
        return

    gateway_port_taken = gateway_ready or deps.tcp_endpoint_reachable(
        deps.host_for_local_browser(runtime_config.gateway.host),
        effective_gateway_port,
    )
    webui_port_taken = webui_ready
    if gateway_port_taken or webui_port_taken:
        deps.print_foreground_port_conflict(
            webui_url=webui_url,
            gateway_host=runtime_config.gateway.host,
            gateway_port=effective_gateway_port,
        )
        raise typer.Exit(1)

    deps.print_webui_foreground_lifecycle(attached=False)
    deps.run_gateway(
        runtime_config,
        port=effective_gateway_port,
        open_browser_url=None if no_open else webui_url,
        webui_bundle_mode=webui_bundle_mode,
        unconfigured_provider_error=settings_setup_error,
    )
