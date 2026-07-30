"""Implementation for the `mira desktop` route."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import typer
from loguru import logger
from rich.console import Console

from mira import __app_name__
from mira.config.schema import Config

console = Console()


@dataclass(frozen=True)
class DesktopCommandDeps:
    resolve_webui_config_path: Callable[[str | None], Path]
    load_runtime_config: Callable[[str | None, str | None], Config]
    webui_browser_url: Callable[[Config], str]
    gateway_health_ready: Callable[..., bool]
    webui_endpoint_reachable: Callable[..., bool]
    start_webui: Callable[..., None]


def run_desktop_command(
    *,
    port: int | None,
    gateway_port: int | None,
    workspace: str | None,
    config: str | None,
    yes: bool,
    debug: bool,
    stop_on_close: bool,
    deps: DesktopCommandDeps,
) -> None:
    """Launch the Mira workbench inside a native desktop window."""
    from mira.config.loader import load_config as _load_config_file
    from mira.config.loader import save_config
    from mira.desktop.app import NativeWindowOptions, launch_native_window
    from mira.gateway import GatewayRuntime, GatewayRuntimePaths

    config_path = deps.resolve_webui_config_path(config)
    desktop_config = _load_config_file(config_path)
    if (desktop_config.kernel.shell_name or "").strip() in {"", "engineering"}:
        desktop_config.kernel.shell_name = "desktop-customer"
        save_config(desktop_config, config_path)
    pre_runtime_config = deps.load_runtime_config(str(config_path), workspace)
    pre_gateway_port = gateway_port if gateway_port is not None else pre_runtime_config.gateway.port
    pre_webui_url = deps.webui_browser_url(pre_runtime_config)
    already_running = deps.gateway_health_ready(
        pre_runtime_config.gateway.host,
        pre_gateway_port,
    ) and deps.webui_endpoint_reachable(pre_webui_url)

    deps.start_webui(
        port=port,
        gateway_port=gateway_port,
        workspace=workspace,
        config=config,
        background=True,
        no_open=True,
        yes=yes,
    )

    runtime_config = deps.load_runtime_config(str(config_path), workspace)
    webui_url = deps.webui_browser_url(runtime_config)
    config_arg = str(config_path)
    workspace_arg = str(Path(workspace).expanduser().resolve(strict=False)) if workspace else None
    runtime = GatewayRuntime(
        paths=GatewayRuntimePaths.for_instance(
            data_dir=config_path.parent,
            workspace=workspace_arg,
            config_path=config_arg,
        )
    )

    def _stop_runtime() -> None:
        if not stop_on_close or already_running:
            return
        result = runtime.stop(timeout_s=20)
        if not result.ok and result.message != "gateway_not_running":
            logger.warning("Desktop shell failed to stop background gateway: {}", result.message)

    try:
        launch_native_window(
            NativeWindowOptions(
                url=webui_url,
                title=__app_name__,
                debug=debug,
            ),
            on_closed=_stop_runtime,
        )
    except RuntimeError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(1) from exc
