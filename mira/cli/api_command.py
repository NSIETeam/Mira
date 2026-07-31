"""OpenAI-compatible API server CLI command implementation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import typer
from loguru import logger
from rich.console import Console

from mira import __app_name__, __logo__
from mira.config.schema import Config


@dataclass(frozen=True, slots=True)
class ServeCommandDeps:
    """Runtime dependencies for the API server command."""

    agent_loop_cls: Callable[[], Any]
    bus_cls: Callable[[], Any]
    session_manager_cls: Callable[[Any], Any]
    load_runtime_config: Callable[[str | None, str | None], Config]
    sync_workspace_templates: Callable[[Any], None]
    set_mira_logs: Callable[[bool], None]
    create_file_edit_activity_hook: Callable[..., Any]
    image_gen_provider_configs: Callable[[Config], dict[str, Any]]
    model_display: Callable[[Config], tuple[str, str]]
    is_loopback_host: Callable[[str], bool]


def run_serve_command(
    *,
    port: int | None,
    host: str | None,
    timeout: float | None,
    verbose: bool,
    workspace: str | None,
    config_path_arg: str | None,
    console: Console,
    deps: ServeCommandDeps,
) -> None:
    """Start the OpenAI-compatible API server (/v1/chat/completions)."""
    try:
        from aiohttp import web
    except ImportError:
        console.print("[red]aiohttp is required. Install with: mira plugins enable api[/red]")
        raise typer.Exit(1)

    from mira.api.server import create_app

    deps.set_mira_logs(verbose)

    runtime_config = deps.load_runtime_config(config_path_arg, workspace)
    api_cfg = runtime_config.api
    host = host if host is not None else api_cfg.host
    port = port if port is not None else api_cfg.port
    timeout = timeout if timeout is not None else api_cfg.timeout
    api_key = api_cfg.api_key.strip() if api_cfg.api_key else ""
    if not deps.is_loopback_host(host) and not api_key:
        console.print(
            f"[red]Error: host {host} is available beyond this device but api_key is not set. "
            "Set api.api_key in config to prevent unauthenticated access.[/red]"
        )
        raise typer.Exit(1)
    deps.sync_workspace_templates(runtime_config.workspace_path)
    bus = deps.bus_cls()
    session_manager = deps.session_manager_cls(runtime_config.workspace_path)
    try:
        agent_loop = deps.agent_loop_cls().from_config(
            runtime_config,
            bus,
            session_manager=session_manager,
            image_generation_provider_configs=deps.image_gen_provider_configs(runtime_config),
            hook_factories=[deps.create_file_edit_activity_hook],
        )
    except ValueError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(1) from exc

    model_name, preset_tag = deps.model_display(runtime_config)
    console.print(f"{__logo__} Starting {__app_name__} gateway")
    console.print(f"  [cyan]Endpoint[/cyan] : http://{host}:{port}/v1/chat/completions")
    console.print(f"  [cyan]Model[/cyan]    : {model_name}{preset_tag}")
    console.print("  [cyan]Session[/cyan]  : api:default")
    console.print(f"  [cyan]Timeout[/cyan]  : {timeout}s")
    if not deps.is_loopback_host(host):
        console.print(
            "[yellow]API is available beyond this device "
            "(authentication required).[/yellow]"
        )
    console.print()

    api_app = create_app(
        agent_loop,
        model_name=model_name,
        request_timeout=timeout,
        api_key=api_key,
    )

    async def on_startup(_app):
        await agent_loop._connect_mcp()

    async def on_cleanup(_app):
        await agent_loop.close_mcp()

    api_app.on_startup.append(on_startup)
    api_app.on_cleanup.append(on_cleanup)

    web.run_app(api_app, host=host, port=port, print=lambda msg: logger.info(msg))
