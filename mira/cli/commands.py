"""CLI commands for Mira."""

import os
import sys
from contextlib import suppress
from functools import partial
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

from mira import (  # noqa: E402
    __app_name__,
    __cli_name__,
    __logo__,
    __version__,
)
from mira.agent.hooks import create_file_edit_activity_hook  # noqa: E402,F401
from mira.agent.loop import AgentLoop  # noqa: E402,F401
from mira.cli import gateway_support as _gateway_support  # noqa: E402
from mira.cli import interactive as _interactive  # noqa: E402
from mira.cli import interactive_bridge as _interactive_bridge  # noqa: E402
from mira.cli import provider_commands as _provider_commands  # noqa: E402
from mira.cli import root_deps as _root_deps  # noqa: E402
from mira.cli import runtime_config as _runtime_config  # noqa: E402
from mira.cli import webui_helpers as _webui_helpers  # noqa: E402
from mira.cli.agent_command import run_agent_command  # noqa: E402,F401
from mira.cli.api_command import run_serve_command  # noqa: E402,F401
from mira.cli.channel_plugin_commands import register_channel_plugin_commands  # noqa: E402
from mira.cli.desktop_command import run_desktop_command  # noqa: E402,F401
from mira.cli.gateway import create_gateway_app  # noqa: E402
from mira.cli.gateway_runtime import run_gateway_runtime  # noqa: E402
from mira.cli.kernel_commands import register_kernel_commands  # noqa: E402
from mira.cli.kernel_lifecycle_commands import register_kernel_lifecycle_commands  # noqa: E402
from mira.cli.onboard_command import onboard_plugins as _onboard_plugins  # noqa: E402,F401
from mira.cli.onboard_command import run_onboard_command  # noqa: E402,F401
from mira.cli.provider_commands import register_provider_commands  # noqa: E402
from mira.cli.root_commands import register_root_commands  # noqa: E402
from mira.cli.stream import StreamRenderer, ThinkingSpinner  # noqa: E402,F401
from mira.cli.system_commands import register_system_commands  # noqa: E402
from mira.cli.trigger_command import run_trigger_command  # noqa: E402,F401
from mira.cli.webui_command import run_webui_command  # noqa: E402,F401
from mira.config.paths import get_workspace_path  # noqa: E402,F401
from mira.config.schema import Config  # noqa: E402
from mira.security.network import is_loopback_host  # noqa: E402,F401
from mira.utils.evaluator import evaluate_response, resolve_evaluator_prompt  # noqa: E402,F401
from mira.utils.helpers import (  # noqa: E402,F401
    sync_workspace_templates,
)
from mira.webui.build import (  # noqa: E402
    BuildMode,
)
from mira.webui.sidebar_state import read_webui_sidebar_state  # noqa: E402,F401

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

_signal_name = _gateway_support.signal_name
_ensure_interactive_tty_mode = _gateway_support.ensure_interactive_tty_mode
_install_gateway_shutdown_handlers = _gateway_support.install_gateway_shutdown_handlers
_advance_dream_cursor_if_behind = _gateway_support.advance_dream_cursor_if_behind
_commit_dream_changes = _gateway_support.commit_dream_changes


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

_HEARTBEAT_PREAMBLE = _gateway_support.HEARTBEAT_PREAMBLE
_heartbeat_has_active_tasks = _gateway_support.heartbeat_has_active_tasks
_pick_heartbeat_target_from_sessions = _gateway_support.pick_heartbeat_target_from_sessions


_PROMPT_SESSION: Any | None = None
_SAVED_TERM_ATTRS = None


_flush_pending_tty_input = _interactive.flush_pending_tty_input


_build_cli_key_bindings = _interactive.build_cli_key_bindings
_is_exit_command = _interactive.is_exit_command
_print_enable_options = partial(_runtime_config.print_enable_options, console=console)
_model_display = _runtime_config.model_display
_load_runtime_config = partial(_runtime_config.load_runtime_config, console=console)
_warn_deprecated_config_keys = partial(
    _runtime_config.warn_deprecated_config_keys,
    console=console,
)
_load_inspection_config = partial(_runtime_config.load_inspection_config, console=console)
_migrate_cron_store = _runtime_config.migrate_cron_store


_interactive_bridge.install_command_exports(sys.modules[__name__])


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


register_root_commands(app, sys.modules[__name__])


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
        deps=_root_deps.gateway(sys.modules[__name__]),
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
