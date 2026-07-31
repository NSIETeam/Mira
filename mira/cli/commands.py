"""CLI commands for Mira."""

import asyncio
import json
import os
import signal
import sys
from collections.abc import Callable, Iterable
from contextlib import suppress
from pathlib import Path
from typing import Any

# Force UTF-8 encoding for Windows console
if sys.platform == "win32":
    if sys.stdout.encoding != "utf-8":
        os.environ["PYTHONIOENCODING"] = "utf-8"
        # Re-open stdout/stderr with UTF-8 encoding
        with suppress(Exception):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Keep console encoding setup before importing CLI UI/logging libraries.
import typer  # noqa: E402
from loguru import logger  # noqa: E402

# Remove default handler and re-add with unified kernel log format
logger.remove()
_log_handler_id = logger.add(
    sys.stderr,
    format=(
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <5}</level> | "
        "<cyan>{extra[channel]}</cyan> | "
        "<level>{message}</level>"
    ),
    level="INFO",
    colorize=None,
    filter=lambda record: record["extra"].setdefault("channel", "-") or True,
)


def _set_mira_logs(enabled: bool) -> None:
    if enabled:
        logger.enable("mira")
    else:
        logger.disable("mira")


from rich.console import Console  # noqa: E402
from rich.table import Table  # noqa: E402

from mira import (  # noqa: E402
    __app_name__,
    __cli_name__,
    __logo__,
    __version__,
)
from mira import optional_features as feature_support  # noqa: E402
from mira.agent.hooks import create_file_edit_activity_hook  # noqa: E402
from mira.agent.loop import AgentLoop  # noqa: E402
from mira.cli import interactive as _interactive  # noqa: E402
from mira.cli import provider_commands as _provider_commands  # noqa: E402
from mira.cli import webui_helpers as _webui_helpers  # noqa: E402
from mira.cli.agent_command import AgentCommandDeps, run_agent_command  # noqa: E402
from mira.cli.api_command import ServeCommandDeps, run_serve_command  # noqa: E402
from mira.cli.channel_plugin_commands import register_channel_plugin_commands  # noqa: E402
from mira.cli.desktop_command import DesktopCommandDeps, run_desktop_command  # noqa: E402
from mira.cli.gateway import create_gateway_app  # noqa: E402
from mira.cli.gateway_runtime import GatewayRuntimeDeps, run_gateway_runtime  # noqa: E402
from mira.cli.kernel_commands import register_kernel_commands  # noqa: E402
from mira.cli.kernel_lifecycle_commands import register_kernel_lifecycle_commands  # noqa: E402
from mira.cli.onboard_command import run_onboard_command  # noqa: E402
from mira.cli.provider_commands import register_provider_commands  # noqa: E402
from mira.cli.stream import StreamRenderer, ThinkingSpinner  # noqa: E402
from mira.cli.system_commands import register_system_commands  # noqa: E402
from mira.cli.trigger_command import run_trigger_command  # noqa: E402
from mira.cli.webui_command import WebUICommandDeps, run_webui_command  # noqa: E402
from mira.config.paths import get_workspace_path  # noqa: E402
from mira.config.schema import Config  # noqa: E402
from mira.security.network import is_loopback_host  # noqa: E402
from mira.session.keys import (  # noqa: E402
    UNIFIED_SESSION_KEY,
    last_channel_from_metadata,
)
from mira.utils.evaluator import evaluate_response, resolve_evaluator_prompt  # noqa: E402
from mira.utils.helpers import (  # noqa: E402
    sync_workspace_templates,
)
from mira.webui.build import (  # noqa: E402
    BuildMode,
)
from mira.webui.sidebar_state import read_webui_sidebar_state  # noqa: E402

time = _webui_helpers.time

_GATEWAY_HEALTH_MAX_CONNECTIONS = _webui_helpers.GATEWAY_HEALTH_MAX_CONNECTIONS
_GATEWAY_HEALTH_READ_TIMEOUT_SECONDS = _webui_helpers.GATEWAY_HEALTH_READ_TIMEOUT_SECONDS
_attach_to_background_gateway = _webui_helpers.attach_to_background_gateway
_confirm_webui_action = _webui_helpers.confirm_webui_action
_ensure_local_webui_channel = _webui_helpers.ensure_local_webui_channel
_gateway_health_bind_note = _webui_helpers.gateway_health_bind_note
_gateway_health_ready = _webui_helpers.gateway_health_ready
_gateway_health_url = _webui_helpers.gateway_health_url
_gateway_instance_command = _webui_helpers.gateway_instance_command
_host_for_local_browser = _webui_helpers.host_for_local_browser
_load_webui_setup_config = _webui_helpers.load_webui_setup_config
_open_webui_browser = _webui_helpers.open_webui_browser
_prepare_webui_bundle_for_gateway = _webui_helpers.prepare_webui_bundle_for_gateway
_print_foreground_port_conflict = _webui_helpers.print_foreground_port_conflict
_print_gateway_health_endpoint = _webui_helpers.print_gateway_health_endpoint
_print_webui_foreground_lifecycle = _webui_helpers.print_webui_foreground_lifecycle
_provider_setup_error = _webui_helpers.provider_setup_error
_resolve_webui_config_path = _webui_helpers.resolve_webui_config_path
_run_quick_start_for_webui = _webui_helpers.run_quick_start_for_webui
_tcp_endpoint_reachable = _webui_helpers.tcp_endpoint_reachable
_warn_webui_bind_scope = _webui_helpers.warn_webui_bind_scope
_webui_browser_url = _webui_helpers.webui_browser_url
_webui_build_mode_for_interactive = _webui_helpers.webui_build_mode_for_interactive
_webui_channel_enabled = _webui_helpers.webui_channel_enabled
_webui_display_url = _webui_helpers.webui_display_url
_webui_endpoint_reachable = _webui_helpers.webui_endpoint_reachable
_LOGIN_HANDLERS = _provider_commands.LOGIN_HANDLERS
_LOGOUT_HANDLERS = _provider_commands.LOGOUT_HANDLERS
_OAUTH_PROVIDER_DEFAULT_MODELS = _provider_commands.OAUTH_PROVIDER_DEFAULT_MODELS


def _signal_name(signum: int) -> str:
    with suppress(ValueError):
        return signal.Signals(signum).name
    return f"signal {signum}"


def _ensure_interactive_tty_mode() -> None:
    """Restore interactive line input after a raw-mode TTY leak."""
    try:
        fd = sys.stdin.fileno()
        if not os.isatty(fd):
            return
    except Exception:
        return

    with suppress(Exception):
        import termios

        attrs = termios.tcgetattr(fd)
        required_lflag = termios.ISIG | termios.ICANON | termios.ECHO
        blocked_input_flags = getattr(termios, "IGNCR", 0) | getattr(termios, "INLCR", 0)
        if (
            (attrs[3] & required_lflag) == required_lflag
            and attrs[0] & termios.ICRNL
            and not attrs[0] & blocked_input_flags
        ):
            return
        attrs[0] = (attrs[0] | termios.ICRNL) & ~blocked_input_flags
        attrs[3] |= required_lflag
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
        termios.tcflush(fd, termios.TCIFLUSH)
        logger.debug("Restored foreground gateway TTY mode")


def _install_gateway_shutdown_handlers(
    loop: asyncio.AbstractEventLoop,
    shutdown_event: asyncio.Event,
    tasks: list[asyncio.Task],
    print_status: Callable[[str], None],
) -> Callable[[], None]:
    """Install foreground gateway signal handlers and return a restore callback."""
    loop_signals: list[int] = []
    previous_handlers: list[tuple[int, Any]] = []
    shutdown_requested = False

    def request_shutdown(signum: int) -> None:
        nonlocal shutdown_requested
        sig_name = _signal_name(signum)
        if shutdown_requested:
            logger.warning("Forcing gateway shutdown after repeated {}", sig_name)
            for task in tasks:
                if not task.done():
                    task.cancel()
            return
        shutdown_requested = True
        logger.info("Gateway shutdown requested by {}", sig_name)
        print_status("\nShutting down... Press Ctrl+C again to force.")
        shutdown_event.set()

    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, request_shutdown, signum)
        except (NotImplementedError, RuntimeError, ValueError):
            try:
                previous = signal.getsignal(signum)
                signal.signal(signum, lambda sig, _frame: request_shutdown(sig))
            except (RuntimeError, ValueError):
                logger.debug("Could not install gateway handler for {}", _signal_name(signum))
                continue
            previous_handlers.append((signum, previous))
        else:
            loop_signals.append(signum)

    def restore() -> None:
        for signum in loop_signals:
            with suppress(NotImplementedError, RuntimeError, ValueError):
                loop.remove_signal_handler(signum)
        for signum, handler in previous_handlers:
            with suppress(RuntimeError, ValueError):
                signal.signal(signum, handler)

    return restore


def _advance_dream_cursor_if_behind(memory: Any) -> None:
    latest = memory.get_latest_cursor()
    if memory.get_last_dream_cursor() < latest:
        memory.set_last_dream_cursor(latest)


def _commit_dream_changes(memory: Any) -> str | None:
    """Commit durable Dream edits, without entering the commit path for a no-op run."""
    if not memory.git.is_initialized():
        return None
    diff_body = memory.dream_content_diff()
    if not diff_body:
        return None
    message = memory.build_dream_commit_message(
        "dream: periodic memory consolidation",
        diff_body,
    )
    return memory.git.auto_commit(message)


PromptSession = _interactive.PromptSession
FileHistory = _interactive.FileHistory
patch_stdout = _interactive.patch_stdout
print_formatted_text = _interactive.print_formatted_text
run_in_terminal = _interactive.run_in_terminal
ANSI = _interactive.ANSI
HTML = _interactive.HTML
_sanitize_surrogates = _interactive._sanitize_surrogates
SafeFileHistory = _interactive.SafeFileHistory
_ReasoningBuffer = _interactive.ReasoningBuffer

app = typer.Typer(
    name=__cli_name__,
    context_settings={"help_option_names": ["-h", "--help"]},
    help=f"{__logo__} {__app_name__} - Engineering execution kernel",
    no_args_is_help=True,
)

console = Console()
EXIT_COMMANDS = _interactive.EXIT_COMMANDS
_REASONING_SENTENCE_ENDINGS = _interactive.REASONING_SENTENCE_ENDINGS
_REASONING_FLUSH_CHARS = _interactive.REASONING_FLUSH_CHARS

_HEARTBEAT_PREAMBLE = (
    "[Your response will be delivered directly to the user's messaging app. "
    "Output ONLY the final user-facing message. Never reference internal "
    "files (HEARTBEAT.md, AWARENESS.md, etc.), your instructions, or your "
    "decision process. If nothing needs reporting, respond with just "
    "'All clear.' and nothing else.]\n\n"
)


def _heartbeat_has_active_tasks(content: str) -> bool:
    """True if HEARTBEAT.md has task lines, ignoring headers, blanks and comments."""
    in_comment = False
    in_active_section: bool = False
    for line in content.splitlines():
        stripped = line.strip()
        if in_comment:
            if "-->" in stripped:
                in_comment = False
            continue
        if not stripped or stripped.startswith("#"):
            if stripped.startswith("##") and not stripped.startswith("###"):
                heading = stripped.lstrip("#").strip().lower()
                in_active_section = heading.startswith("active tasks")
            continue
        if stripped.startswith("<!--"):
            if "-->" not in stripped[4:]:
                in_comment = True
            continue
        if in_active_section is False:
            continue
        return True
    return False


def _pick_heartbeat_target_from_sessions(
    *,
    enabled_channels: Iterable[str],
    sessions: Iterable[dict[str, Any]],
    archived_keys: Iterable[str],
    unified_session_metadata: dict[str, Any] | None = None,
) -> tuple[str, str]:
    enabled = set(enabled_channels)
    archived = set(archived_keys)
    for item in sessions:
        key = item.get("key") or ""
        if key in archived:
            continue
        if key == UNIFIED_SESSION_KEY:
            route = last_channel_from_metadata(unified_session_metadata)
            if route is not None:
                channel, chat_id = route
                if channel not in {"cli", "system"} and channel in enabled:
                    return channel, chat_id
            continue
        if ":" not in key:
            continue
        channel, chat_id = key.split(":", 1)
        if channel in {"cli", "system"}:
            continue
        if channel in enabled and chat_id:
            return channel, chat_id
    return "cli", "direct"


_PROMPT_SESSION: Any | None = None
_SAVED_TERM_ATTRS = None


def _flush_pending_tty_input() -> None:
    _interactive.flush_pending_tty_input()


def _restore_terminal() -> None:
    _interactive.restore_terminal(_SAVED_TERM_ATTRS)


def _build_cli_key_bindings():
    return _interactive.build_cli_key_bindings()


def _init_prompt_session() -> None:
    global _PROMPT_SESSION, _SAVED_TERM_ATTRS
    _PROMPT_SESSION, _SAVED_TERM_ATTRS = _interactive.init_prompt_session(
        prompt_session_cls=PromptSession,
        history_cls=SafeFileHistory,
        key_bindings_factory=_build_cli_key_bindings,
    )


def _make_console() -> Console:
    return _interactive.make_console()


def _render_interactive_ansi(render_fn) -> str:
    return _interactive.render_interactive_ansi(render_fn, base_console=console)


def _print_agent_response(
    response: str,
    render_markdown: bool,
    metadata: dict | None = None,
    show_header: bool = True,
) -> None:
    _interactive.print_agent_response(
        response,
        render_markdown,
        console_factory=_make_console,
        metadata=metadata,
        show_header=show_header,
    )


def _response_renderable(content: str, render_markdown: bool, metadata: dict | None = None):
    return _interactive.response_renderable(content, render_markdown, metadata)


async def _print_interactive_line(text: str) -> None:
    await _interactive.print_interactive_line(
        text,
        base_console=console,
        render_ansi=lambda fn, *, base_console: _render_interactive_ansi(fn),
        formatted_print=print_formatted_text,
        terminal_runner=run_in_terminal,
    )


async def _print_interactive_response(
    response: str,
    render_markdown: bool,
    metadata: dict | None = None,
) -> None:
    await _interactive.print_interactive_response(
        response,
        render_markdown,
        base_console=console,
        render_ansi=lambda fn, *, base_console: _render_interactive_ansi(fn),
        formatted_print=print_formatted_text,
        terminal_runner=run_in_terminal,
        metadata=metadata,
    )


def _print_cli_progress_line(
    text: str,
    thinking: ThinkingSpinner | None,
    renderer: StreamRenderer | None = None,
) -> None:
    _interactive.print_cli_progress_line(text, thinking, renderer, base_console=console)


def _print_cli_reasoning(
    text: str,
    thinking: ThinkingSpinner | None,
    renderer: StreamRenderer | None = None,
) -> None:
    _interactive.print_cli_reasoning(text, thinking, renderer, base_console=console)


def _flush_cli_reasoning(
    reasoning_buffer: _ReasoningBuffer,
    thinking: ThinkingSpinner | None,
    renderer: StreamRenderer | None = None,
) -> None:
    _interactive.flush_cli_reasoning(
        reasoning_buffer,
        thinking,
        renderer,
        print_reasoning=_print_cli_reasoning,
    )


async def _print_interactive_progress_line(
    text: str,
    thinking: ThinkingSpinner | None,
    renderer: StreamRenderer | None = None,
) -> None:
    await _interactive.print_interactive_progress_line(
        text,
        thinking,
        renderer,
        print_line=_print_interactive_line,
    )


async def _maybe_print_interactive_progress(
    msg: Any,
    thinking: ThinkingSpinner | None,
    channels_config: Any,
    renderer: StreamRenderer | None = None,
    reasoning_buffer: _ReasoningBuffer | None = None,
) -> bool:
    return await _interactive.maybe_print_interactive_progress(
        msg,
        thinking,
        channels_config,
        renderer,
        reasoning_buffer,
        print_progress_line=_print_interactive_progress_line,
        print_reasoning=_print_cli_reasoning,
    )


def _make_agent_progress_adapter(
    agent_loop: AgentLoop,
    thinking: ThinkingSpinner | None,
    renderer: StreamRenderer | None = None,
    *,
    reasoning_buffer_only: bool = False,
) -> Any:
    return _interactive.make_agent_progress_adapter(
        agent_loop,
        thinking,
        renderer,
        reasoning_buffer_only=reasoning_buffer_only,
        print_progress_line=_print_cli_progress_line,
        print_reasoning=_print_cli_reasoning,
    )


def _is_exit_command(command: str) -> bool:
    return _interactive.is_exit_command(command)


async def _read_interactive_input_async() -> str:
    return await _interactive.read_interactive_input_async(
        _PROMPT_SESSION,
        patch_stdout_cm=patch_stdout,
    )

def version_callback(value: bool):
    if value:
        console.print(f"{__logo__} {__app_name__} v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None, "--version", "-v", callback=version_callback, is_eager=True
    ),
):
    """Mira - Engineering execution kernel."""
    pass


# ============================================================================
# Onboard / Setup
# ============================================================================


@app.command()
def onboard(
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
    wizard: bool = typer.Option(False, "--wizard", help="Use interactive wizard"),
    non_interactive_refresh: bool = typer.Option(False, "--refresh", help="Refresh config, preserving existing settings without prompting"),
):
    """Initialize Mira configuration and workspace."""
    run_onboard_command(
        workspace=workspace,
        config=config,
        wizard=wizard,
        non_interactive_refresh=non_interactive_refresh,
        onboard_plugins=_onboard_plugins,
        sync_workspace_templates=sync_workspace_templates,
        get_workspace_path=get_workspace_path,
    )


def _onboard_plugins(config_path: Path) -> None:
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


def _print_enable_options(
    extras: dict[str, list[str] | None],
    channel_plugins: dict[str, Any],
    config: Config,
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


def _model_display(config: Config) -> tuple[str, str]:
    """Return (resolved_model_name, preset_tag) for display strings."""
    resolved = config.resolve_preset()
    name = config.agents.defaults.model_preset
    tag = f" (preset: {name})" if name else ""
    return resolved.model, tag


def _load_runtime_config(config: str | None = None, workspace: str | None = None) -> Config:
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
    _warn_deprecated_config_keys(config_path)
    if workspace:
        loaded.agents.defaults.workspace = workspace
    return loaded


def _warn_deprecated_config_keys(config_path: Path | None) -> None:
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


def _load_inspection_config(
    config: str | None = None,
    workspace: str | None = None,
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
    _warn_deprecated_config_keys(display_path)
    if workspace:
        loaded.agents.defaults.workspace = workspace
    return display_path, loaded


def _migrate_cron_store(config: "Config") -> None:
    """One-time migration: move legacy global cron store into the workspace."""
    from mira.config.paths import get_cron_dir

    legacy_path = get_cron_dir() / "jobs.json"
    new_path = config.workspace_path / "cron" / "jobs.json"
    if legacy_path.is_file() and not new_path.exists():
        new_path.parent.mkdir(parents=True, exist_ok=True)
        import shutil

        shutil.move(str(legacy_path), str(new_path))


@app.command()
def trigger(
    trigger_id: str = typer.Argument(..., help="Trigger ID returned by /trigger"),
    message: str | None = typer.Argument(None, help="Message to deliver; stdin is used when omitted"),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
):
    """Deliver a local trigger message to its bound chat session."""
    run_trigger_command(
        trigger_id=trigger_id,
        message=message,
        workspace=workspace,
        config_path_arg=config,
        console=console,
        load_runtime_config=lambda config_path, workspace_path: _load_runtime_config(
            config_path,
            workspace_path,
        ),
    )


# ============================================================================
# OpenAI-Compatible API Server
# ============================================================================


@app.command()
def serve(
    port: int | None = typer.Option(None, "--port", "-p", help="API server port"),
    host: str | None = typer.Option(None, "--host", "-H", help="Bind address"),
    timeout: float | None = typer.Option(None, "--timeout", "-t", help="Per-request timeout (seconds)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show Mira runtime logs"),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
):
    """Start the OpenAI-compatible API server (/v1/chat/completions)."""
    from mira.bus.queue import MessageBus
    from mira.providers.image_generation import image_gen_provider_configs
    from mira.session.manager import SessionManager

    run_serve_command(
        port=port,
        host=host,
        timeout=timeout,
        verbose=verbose,
        workspace=workspace,
        config_path_arg=config,
        console=console,
        deps=ServeCommandDeps(
            agent_loop_cls=lambda: AgentLoop,
            bus_cls=MessageBus,
            session_manager_cls=SessionManager,
            load_runtime_config=lambda config_path, workspace_path: _load_runtime_config(
                config_path,
                workspace_path,
            ),
            sync_workspace_templates=sync_workspace_templates,
            set_mira_logs=lambda enabled: _set_mira_logs(enabled),
            create_file_edit_activity_hook=create_file_edit_activity_hook,
            image_gen_provider_configs=image_gen_provider_configs,
            model_display=_model_display,
            is_loopback_host=is_loopback_host,
        ),
    )


# ============================================================================
# WebUI Launcher
# ============================================================================


@app.command()
def webui(
    port: int | None = typer.Option(None, "--port", "-p", help="WebUI port"),
    gateway_port: int | None = typer.Option(
        None,
        "--gateway-port",
        help="Gateway health port",
    ),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
    background: bool = typer.Option(
        False,
        "--background",
        help="Keep the gateway running after this command exits",
    ),
    no_open: bool = typer.Option(False, "--no-open", help="Do not open a browser"),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Apply safe local WebUI defaults without prompting",
    ),
    user: str | None = typer.Option(
        None,
        "--user",
        help="Temporary WebUI user account name for shared gateway use",
    ),
    group: str | None = typer.Option(
        None,
        "--group",
        help="Temporary WebUI project group; users in the same group share memory",
    ),
) -> None:
    """Prepare the local WebUI, start the gateway, and open the browser workbench."""
    run_webui_command(
        port=port,
        gateway_port=gateway_port,
        workspace=workspace,
        config=config,
        background=background,
        no_open=no_open,
        yes=yes,
        user=user,
        group=group,
        deps=WebUICommandDeps(
            ensure_interactive_tty_mode=_ensure_interactive_tty_mode,
            resolve_webui_config_path=_resolve_webui_config_path,
            sync_workspace_templates=sync_workspace_templates,
            confirm_webui_action=_confirm_webui_action,
            load_webui_setup_config=_load_webui_setup_config,
            provider_setup_error=_provider_setup_error,
            run_quick_start_for_webui=_run_quick_start_for_webui,
            ensure_local_webui_channel=_ensure_local_webui_channel,
            warn_webui_bind_scope=_warn_webui_bind_scope,
            webui_browser_url=_webui_browser_url,
            load_runtime_config=_load_runtime_config,
            webui_display_url=_webui_display_url,
            gateway_health_url=_gateway_health_url,
            gateway_health_bind_note=_gateway_health_bind_note,
            webui_build_mode_for_interactive=_webui_build_mode_for_interactive,
            prepare_webui_bundle_for_gateway=_prepare_webui_bundle_for_gateway,
            gateway_instance_command=_gateway_instance_command,
            open_webui_browser=_open_webui_browser,
            gateway_health_ready=_gateway_health_ready,
            webui_endpoint_reachable=_webui_endpoint_reachable,
            attach_to_background_gateway=_attach_to_background_gateway,
            tcp_endpoint_reachable=_tcp_endpoint_reachable,
            host_for_local_browser=_host_for_local_browser,
            print_foreground_port_conflict=_print_foreground_port_conflict,
            print_webui_foreground_lifecycle=_print_webui_foreground_lifecycle,
            run_gateway=_run_gateway,
        ),
    )


@app.command()
def desktop(
    port: int | None = typer.Option(None, "--port", "-p", help="WebUI port"),
    gateway_port: int | None = typer.Option(
        None,
        "--gateway-port",
        help="Gateway health port",
    ),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Apply safe local desktop defaults without prompting",
    ),
    debug: bool = typer.Option(False, "--debug", help="Open the native shell with WebView debug mode"),
    stop_on_close: bool = typer.Option(
        True,
        "--stop-on-close/--keep-running",
        help="Stop the gateway started by this window when the native shell closes",
    ),
) -> None:
    """Launch the Mira workbench inside a native desktop window."""
    run_desktop_command(
        port=port,
        gateway_port=gateway_port,
        workspace=workspace,
        config=config,
        yes=yes,
        debug=debug,
        stop_on_close=stop_on_close,
        deps=DesktopCommandDeps(
            resolve_webui_config_path=_resolve_webui_config_path,
            load_runtime_config=_load_runtime_config,
            webui_browser_url=_webui_browser_url,
            gateway_health_ready=_gateway_health_ready,
            webui_endpoint_reachable=_webui_endpoint_reachable,
            start_webui=webui,
        ),
    )


# ============================================================================
# Gateway / Server
# ============================================================================


def _run_gateway(
    config: Config,
    *,
    port: int | None = None,
    open_browser_url: str | None = None,
    webui_static_dist: bool = True,
    webui_bundle_mode: BuildMode = "warn",
    webui_runtime_surface: str = "browser",
    webui_runtime_capabilities: dict[str, Any] | None = None,
    health_server_enabled: bool = True,
    unconfigured_provider_error: str | None = None,
) -> None:
    """Shared gateway runtime; ``open_browser_url`` opens a tab once channels are up."""
    run_gateway_runtime(
        config,
        port=port,
        open_browser_url=open_browser_url,
        webui_static_dist=webui_static_dist,
        webui_bundle_mode=webui_bundle_mode,
        webui_runtime_surface=webui_runtime_surface,
        webui_runtime_capabilities=webui_runtime_capabilities,
        health_server_enabled=health_server_enabled,
        unconfigured_provider_error=unconfigured_provider_error,
        deps=GatewayRuntimeDeps(
            console=console,
            logger=logger,
            logo=__logo__,
            app_name=__app_name__,
            version=__version__,
            agent_loop_cls=lambda: AgentLoop,
            create_file_edit_activity_hook=create_file_edit_activity_hook,
            sync_workspace_templates=sync_workspace_templates,
            webui_browser_url=_webui_browser_url,
            host_for_local_browser=_host_for_local_browser,
            tcp_endpoint_reachable=_tcp_endpoint_reachable,
            webui_channel_enabled=_webui_channel_enabled,
            webui_endpoint_reachable=_webui_endpoint_reachable,
            print_foreground_port_conflict=_print_foreground_port_conflict,
            prepare_webui_bundle_for_gateway=_prepare_webui_bundle_for_gateway,
            migrate_cron_store=_migrate_cron_store,
            commit_dream_changes=_commit_dream_changes,
            advance_dream_cursor_if_behind=_advance_dream_cursor_if_behind,
            heartbeat_has_active_tasks=_heartbeat_has_active_tasks,
            heartbeat_preamble=_HEARTBEAT_PREAMBLE,
            read_webui_sidebar_state=read_webui_sidebar_state,
            pick_heartbeat_target_from_sessions=_pick_heartbeat_target_from_sessions,
            evaluate_response=evaluate_response,
            resolve_evaluator_prompt=resolve_evaluator_prompt,
            ensure_interactive_tty_mode=_ensure_interactive_tty_mode,
            install_gateway_shutdown_handlers=_install_gateway_shutdown_handlers,
            print_gateway_health_endpoint=_print_gateway_health_endpoint,
            gateway_health_max_connections=_GATEWAY_HEALTH_MAX_CONNECTIONS,
            gateway_health_read_timeout_seconds=_GATEWAY_HEALTH_READ_TIMEOUT_SECONDS,
        ),
    )

app.add_typer(
    create_gateway_app(
        console=console,
        log_handler_id=_log_handler_id,
        load_runtime_config=_load_runtime_config,
        run_gateway=_run_gateway,
        prepare_webui_bundle=lambda config, mode: _prepare_webui_bundle_for_gateway(
            config,
            mode=mode,
        ),
    ),
    name="gateway",
)


# ============================================================================
# Agent Commands
# ============================================================================


@app.command()
def agent(
    message: str = typer.Option(None, "--message", "-m", help="Message to send to the agent"),
    session_id: str = typer.Option("cli:direct", "--session", "-s", help="Session ID"),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
    markdown: bool = typer.Option(True, "--markdown/--no-markdown", help="Render assistant output as Markdown"),
    logs: bool = typer.Option(False, "--logs/--no-logs", help="Show Mira runtime logs during chat"),
):
    """Interact with the agent directly."""
    run_agent_command(
        message=message,
        session_id=session_id,
        workspace=workspace,
        config_path_arg=config,
        markdown=markdown,
        logs=logs,
        deps=AgentCommandDeps(
            agent_loop_cls=AgentLoop,
            load_runtime_config=_load_runtime_config,
            sync_workspace_templates=sync_workspace_templates,
            migrate_cron_store=_migrate_cron_store,
            set_mira_logs=_set_mira_logs,
            create_file_edit_activity_hook=create_file_edit_activity_hook,
            print_agent_response=_print_agent_response,
            make_model_display=_model_display,
            init_prompt_session=_init_prompt_session,
            restore_terminal=_restore_terminal,
            flush_pending_tty_input=_flush_pending_tty_input,
            read_interactive_input_async=_read_interactive_input_async,
            is_exit_command=_is_exit_command,
            maybe_print_interactive_progress=_maybe_print_interactive_progress,
            print_interactive_response=_print_interactive_response,
            make_progress=_make_agent_progress_adapter,
        ),
    )


register_channel_plugin_commands(
    app,
    console=console,
    load_inspection_config=_load_inspection_config,
    print_enable_options=_print_enable_options,
    set_mira_logs=lambda enabled: _set_mira_logs(enabled),
)


register_system_commands(app, console=console)
register_kernel_commands(app, console=console, load_inspection_config=_load_inspection_config)
register_kernel_lifecycle_commands(
    app,
    console=console,
    load_inspection_config=_load_inspection_config,
    run_gateway=lambda *args, **kwargs: _run_gateway(*args, **kwargs),
    model_display=_model_display,
)


register_provider_commands(app, console=console)


if __name__ == "__main__":
    app()
