"""WebUI startup helpers kept out of the thin CLI route module."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.markup import escape

from mira import __app_name__, __cli_name__, __legacy_cli_name__
from mira.config.paths import get_workspace_path
from mira.config.schema import Config
from mira.security.network import is_loopback_host
from mira.utils.helpers import sync_workspace_templates
from mira.webui.build import BuildMode, WebUIBuildError, ensure_webui_bundle

console = Console()


def confirm_webui_action(message: str, *, yes: bool) -> None:
    """Confirm a WebUI first-run mutation or fail clearly in non-interactive shells."""
    if yes:
        return
    if not cli_can_prompt():
        console.print(
            "[red]Error: WebUI setup needs confirmation. Re-run with --yes or use "
            "`mira onboard --wizard`.[/red]"
        )
        raise typer.Exit(1)
    if not typer.confirm(message, default=True):
        console.print("[yellow]WebUI setup cancelled.[/yellow]")
        raise typer.Exit(1)


def cli_can_prompt() -> bool:
    try:
        return sys.stdin.isatty()
    except Exception:
        return False


def webui_build_mode_for_interactive(*, yes: bool = False) -> BuildMode:
    if yes:
        return "auto"
    return "prompt" if cli_can_prompt() else "warn"


def resolve_webui_config_path(config: str | None) -> Path:
    """Resolve the config path used by ``mira webui`` and bind loader state."""
    from mira.config.loader import get_config_path, set_config_path

    if not config:
        return get_config_path()
    config_path = Path(config).expanduser().resolve(strict=False)
    set_config_path(config_path)
    console.print(f"[dim]Using config: {config_path}[/dim]")
    return config_path


def load_webui_setup_config(config_path: Path) -> Config:
    """Load config for first-run mutation without resolving env-var placeholders."""
    from mira.config.loader import load_config

    try:
        return load_config(config_path)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from e


def provider_setup_error(config: Config) -> str | None:
    """Return the provider setup error, or None when the current model can start."""
    from mira.providers.factory import build_provider_snapshot

    try:
        build_provider_snapshot(config)
    except ValueError as exc:
        return str(exc)
    return None


def webui_config_dict(config: Config) -> dict[str, Any]:
    """Return the current WebSocket config as a mutable alias-key dictionary."""
    from mira.channels.websocket.runtime import WebSocketConfig

    current = getattr(config.channels, "websocket", None) or {}
    model = WebSocketConfig.model_validate(current)
    return model.model_dump(by_alias=True, exclude_none=True)


def webui_channel_enabled(config: Config) -> bool:
    from mira.channels.websocket.runtime import WebSocketConfig

    current = getattr(config.channels, "websocket", None) or {}
    return bool(WebSocketConfig.model_validate(current).enabled)


def prepare_webui_bundle_for_gateway(
    config: Config,
    *,
    mode: BuildMode,
    webui_static_dist: bool = True,
) -> None:
    """Refresh or warn about stale bundled WebUI assets before gateway startup."""
    if not webui_static_dist or not webui_channel_enabled(config):
        return

    def _print(message: str) -> None:
        console.print(f"[yellow]{escape(message)}[/yellow]")

    def _confirm(message: str) -> bool:
        return typer.confirm(message, default=True)

    try:
        ensure_webui_bundle(
            mode=mode,
            confirm=_confirm if mode == "prompt" else None,
            output=_print,
        )
    except WebUIBuildError as exc:
        if mode == "warn":
            console.print(f"[yellow]Warning: {escape(str(exc))}[/yellow]")
            return
        console.print(f"[red]Error: {escape(str(exc))}[/red]")
        raise typer.Exit(1) from exc


def host_for_local_browser(host: str) -> str:
    """Map bind hosts to a browser-openable local host."""
    if host in {"0.0.0.0", ""}:
        return "127.0.0.1"
    if host == "::":
        return "[::1]"
    if ":" in host and not host.startswith("["):
        return f"[{host}]"
    return host


def gateway_health_url(host: str, port: int) -> str:
    """Return a health URL that can be opened from this device."""
    return f"http://{host_for_local_browser(host)}:{port}/health"


def gateway_health_bind_note(host: str) -> str:
    """Describe a non-local bind without presenting it as a usable URL."""
    return "" if is_loopback_host(host) else f" [dim](listening on {host})[/dim]"


GATEWAY_HEALTH_MAX_CONNECTIONS = 64
GATEWAY_HEALTH_READ_TIMEOUT_SECONDS = 2.0


def print_gateway_health_endpoint(host: str, port: int) -> None:
    """Print a usable health URL and make non-loopback binds explicit."""
    console.print(
        f"[green][/green] Health endpoint: {gateway_health_url(host, port)}"
        f"{gateway_health_bind_note(host)}"
    )
    if is_loopback_host(host):
        return

    console.print(
        "[yellow]Warning: the unauthenticated health endpoint is listening beyond loopback "
        "and may be reachable from other devices. "
        f"Keep port {port} private or protect it with a firewall or reverse proxy.[/yellow]"
    )


def webui_bootstrap_secret(config: Config) -> str:
    ws_cfg = webui_config_dict(config)
    return str(ws_cfg.get("tokenIssueSecret") or ws_cfg.get("token") or "").strip()


def webui_browser_url(
    config: Config,
    *,
    user: str | None = None,
    group: str | None = None,
) -> str:
    from urllib.parse import quote

    ws_cfg = webui_config_dict(config)
    host = host_for_local_browser(str(ws_cfg.get("host") or "127.0.0.1"))
    port = int(ws_cfg.get("port") or 8765)
    base_url = f"http://{host}:{port}"
    secret = webui_bootstrap_secret(config)
    params: list[str] = []
    if secret:
        params.append(f"bootstrapSecret={quote(secret, safe='')}")
    if user:
        params.append(f"user={quote(user, safe='')}")
    if group:
        params.append(f"group={quote(group, safe='')}")
    return f"{base_url}/#/{'?' + '&'.join(params) if params else ''}"


def webui_display_url(url: str) -> str:
    marker = "bootstrapSecret="
    if marker not in url:
        return url
    prefix, _ = url.split(marker, 1)
    return f"{prefix}{marker}<redacted>"


def ensure_local_webui_channel(
    config: Config,
    *,
    port: int | None,
    yes: bool,
) -> tuple[bool, bool]:
    """Enable the local WebUI channel with safe localhost defaults."""
    from mira.channels.websocket.runtime import WebSocketConfig

    current = getattr(config.channels, "websocket", None) or {}
    model = WebSocketConfig.model_validate(current)
    changed = False
    generated_secret = False

    needs_enable = not model.enabled
    needs_port = port is not None and model.port != port
    needs_secret = not model.token_issue_secret.strip() and not model.token.strip()
    if not needs_enable and not needs_port and not needs_secret:
        return False, False

    target_port = port if port is not None else model.port
    console.print()
    console.print("[bold]Local WebUI setup[/bold]")
    console.print(f"  URL: [cyan]http://127.0.0.1:{target_port}[/cyan]")
    console.print("  Bind: [cyan]127.0.0.1 only[/cyan] (not exposed to your LAN)")
    console.print("  Auth: generated WebUI bootstrap secret stored in config")
    console.print(
        "  LAN access requires an explicit host change plus a WebUI password in config."
    )
    confirm_webui_action("Update the local WebUI channel in this config?", yes=yes)

    if not model.enabled:
        model.enabled = True
        changed = True
    if model.host != "127.0.0.1":
        model.host = "127.0.0.1"
        changed = True
    if port is not None and model.port != port:
        model.port = port
        changed = True
    if not model.websocket_requires_token:
        model.websocket_requires_token = True
        changed = True
    if needs_secret:
        import secrets

        model.token_issue_secret = secrets.token_urlsafe(32)
        changed = True
        generated_secret = True

    setattr(config.channels, "websocket", model.model_dump(by_alias=True, exclude_none=True))
    return changed, generated_secret


def warn_webui_bind_scope(config: Config) -> None:
    ws_cfg = webui_config_dict(config)
    host = str(ws_cfg.get("host") or "127.0.0.1")
    if host in {"127.0.0.1", "localhost", "::1"}:
        return
    console.print(
        "[yellow]Warning: WebUI is configured to bind outside localhost. "
        "Keep tokenIssueSecret set and use this only on trusted networks.[/yellow]"
    )


def wait_for_webui(url: str, *, timeout_s: float = 5.0) -> None:
    """Best-effort wait for the WebUI listener before opening a browser."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if tcp_endpoint_reachable(host, port, timeout_s=0.2):
            return
        time.sleep(0.1)


def tcp_endpoint_reachable(host: str, port: int, *, timeout_s: float = 0.25) -> bool:
    """Return whether a local TCP endpoint accepts connections."""
    import socket

    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def gateway_health_ready(host: str, port: int, *, timeout_s: float = 0.4) -> bool:
    """Return whether the mira gateway health endpoint responds OK."""
    import urllib.error
    import urllib.request

    browser_host = host_for_local_browser(host)
    try:
        with urllib.request.urlopen(
            f"http://{browser_host}:{port}/health",
            timeout=timeout_s,
        ) as response:
            if response.status != 200:
                return False
            body = response.read(1024)
    except (OSError, urllib.error.URLError, TimeoutError, ValueError):
        return False

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    return payload.get("status") == "ok"


def webui_endpoint_reachable(url: str, *, timeout_s: float = 0.25) -> bool:
    """Return whether the WebUI URL's TCP endpoint is already listening."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return tcp_endpoint_reachable(host, port, timeout_s=timeout_s)


def print_foreground_port_conflict(
    *,
    webui_url: str,
    gateway_host: str,
    gateway_port: int,
) -> None:
    console.print(
        "[red]Error: mira cannot start because one of its local ports is already in use.[/red]"
    )
    console.print(f"  WebUI: [cyan]{webui_url}[/cyan]")
    console.print(
        f"  Gateway health: [cyan]http://{host_for_local_browser(gateway_host)}:{gateway_port}/health[/cyan]"
    )
    console.print()
    console.print("If this is an existing Mira instance, use it or stop it first:")
    console.print("  [cyan]mira gateway status[/cyan]")
    console.print("  [cyan]mira gateway stop[/cyan]")
    console.print("Or choose different ports with [cyan]--port[/cyan] and [cyan]--gateway-port[/cyan].")


def open_webui_browser(url: str, *, wait: bool = True) -> None:
    """Open the WebUI in the user's default browser, with a copyable fallback."""
    import webbrowser

    if wait:
        wait_for_webui(url)
    display_url = webui_display_url(url)
    try:
        webbrowser.open(url)
        console.print(
            f"[green][/green] Opened {__app_name__} WebUI: [cyan]{display_url}[/cyan]"
        )
    except Exception as exc:
        console.print(f"[yellow]Could not open browser ({exc}); visit {display_url}[/yellow]")


def print_webui_foreground_lifecycle(*, attached: bool) -> None:
    """Explain how the browser and gateway lifecycles differ."""
    console.print()
    if attached:
        console.print("[green]mira is attached to the existing gateway.[/green]")
    else:
        console.print("[green]mira is running in this terminal.[/green]")
    console.print("[dim]Closing the browser does not stop channels or automations.[/dim]")
    console.print("[dim]Press Ctrl+C here to stop mira.[/dim]")


def attach_to_background_gateway(runtime: Any) -> None:
    """Keep a foreground WebUI command attached to a managed gateway."""
    print_webui_foreground_lifecycle(attached=True)
    try:
        while runtime.status().running:
            time.sleep(0.5)
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopping mira...[/yellow]")
        result = runtime.stop()
        if result.ok or result.message == "gateway_not_running":
            console.print("[green]Gateway stopped.[/green]")
            return
        console.print(f"[red]Gateway could not be stopped: {result.message}[/red]")
        raise typer.Exit(1)

    console.print("[yellow]Gateway stopped.[/yellow]")


def gateway_instance_command(
    subcommand: str,
    *,
    config_path: Path,
    workspace: str | None,
) -> str:
    """Return a copyable gateway command for the same config/workspace instance."""
    import shlex

    parts = [__cli_name__, "gateway", subcommand, "--config", str(config_path)]
    if workspace:
        workspace_path = str(Path(workspace).expanduser().resolve(strict=False))
        parts.extend(["--workspace", workspace_path])
    return " ".join(shlex.quote(part) for part in parts)


def run_quick_start_for_webui(config: Config, *, yes: bool) -> Config:
    """Offer the existing Quick Start flow when provider setup is missing."""
    if yes:
        console.print(
            "[red]Error: provider/model setup is incomplete, and --yes cannot answer "
            f"provider credentials. Run `{__cli_name__} webui` "
            f"interactively or `{__cli_name__} onboard --wizard` "
            f"(compat alias: `{__legacy_cli_name__}`).[/red]"
        )
        raise typer.Exit(1)

    console.print()
    console.print("[yellow]Model provider setup is not ready.[/yellow]")
    console.print("Quick Start will ask for provider, API key/base URL, model, and WebUI password.")
    confirm_webui_action("Run Quick Start now?", yes=False)

    from mira.cli.onboard import run_quick_start_onboard

    try:
        result = run_quick_start_onboard(config)
    except RuntimeError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        console.print("[yellow]Run `mira onboard --wizard` after installing wizard dependencies.[/yellow]")
        raise typer.Exit(1) from exc
    if not result.should_save:
        console.print("[yellow]Quick Start cancelled. No changes were saved.[/yellow]")
        raise typer.Exit(1)
    return result.config


def run_quick_start_templates(config: Config) -> Config:
    workspace_path = get_workspace_path(config.workspace_path)
    workspace_path.mkdir(parents=True, exist_ok=True)
    sync_workspace_templates(workspace_path)
    return config
