"""Dependency assembly for root CLI routes.

This module keeps ``mira.cli.commands`` focused on Typer route wiring while
still resolving dependencies from that module at call time. Tests and plugins
that monkeypatch legacy ``mira.cli.commands._*`` names keep working.
"""

from __future__ import annotations

from typing import Any

from mira.cli.agent_command import AgentCommandDeps
from mira.cli.api_command import ServeCommandDeps
from mira.cli.desktop_command import DesktopCommandDeps
from mira.cli.gateway_runtime import GatewayRuntimeDeps
from mira.cli.webui_command import WebUICommandDeps


def serve(ns: Any) -> ServeCommandDeps:
    from mira.bus.queue import MessageBus
    from mira.providers.image_generation import image_gen_provider_configs
    from mira.session.manager import SessionManager

    return ServeCommandDeps(
        agent_loop_cls=lambda: ns.AgentLoop,
        bus_cls=MessageBus,
        session_manager_cls=SessionManager,
        load_runtime_config=lambda config_path, workspace_path: ns._load_runtime_config(
            config_path,
            workspace_path,
        ),
        sync_workspace_templates=ns.sync_workspace_templates,
        set_mira_logs=lambda enabled: ns._set_mira_logs(enabled),
        create_file_edit_activity_hook=ns.create_file_edit_activity_hook,
        image_gen_provider_configs=image_gen_provider_configs,
        model_display=ns._model_display,
        is_loopback_host=ns.is_loopback_host,
    )


def webui(ns: Any) -> WebUICommandDeps:
    return WebUICommandDeps(
        ensure_interactive_tty_mode=ns._ensure_interactive_tty_mode,
        resolve_webui_config_path=ns._resolve_webui_config_path,
        sync_workspace_templates=ns.sync_workspace_templates,
        confirm_webui_action=ns._confirm_webui_action,
        load_webui_setup_config=ns._load_webui_setup_config,
        provider_setup_error=ns._provider_setup_error,
        run_quick_start_for_webui=ns._run_quick_start_for_webui,
        ensure_local_webui_channel=ns._ensure_local_webui_channel,
        warn_webui_bind_scope=ns._warn_webui_bind_scope,
        webui_browser_url=ns._webui_browser_url,
        load_runtime_config=ns._load_runtime_config,
        webui_display_url=ns._webui_display_url,
        gateway_health_url=ns._gateway_health_url,
        gateway_health_bind_note=ns._gateway_health_bind_note,
        webui_build_mode_for_interactive=ns._webui_build_mode_for_interactive,
        prepare_webui_bundle_for_gateway=ns._prepare_webui_bundle_for_gateway,
        gateway_instance_command=ns._gateway_instance_command,
        open_webui_browser=ns._open_webui_browser,
        gateway_health_ready=ns._gateway_health_ready,
        webui_endpoint_reachable=ns._webui_endpoint_reachable,
        attach_to_background_gateway=ns._attach_to_background_gateway,
        tcp_endpoint_reachable=ns._tcp_endpoint_reachable,
        host_for_local_browser=ns._host_for_local_browser,
        print_foreground_port_conflict=ns._print_foreground_port_conflict,
        print_webui_foreground_lifecycle=ns._print_webui_foreground_lifecycle,
        run_gateway=ns._run_gateway,
    )


def desktop(ns: Any) -> DesktopCommandDeps:
    return DesktopCommandDeps(
        resolve_webui_config_path=ns._resolve_webui_config_path,
        load_runtime_config=ns._load_runtime_config,
        webui_browser_url=ns._webui_browser_url,
        gateway_health_ready=ns._gateway_health_ready,
        webui_endpoint_reachable=ns._webui_endpoint_reachable,
        start_webui=ns.webui,
    )


def gateway(ns: Any) -> GatewayRuntimeDeps:
    return GatewayRuntimeDeps(
        console=ns.console,
        logger=ns.logger,
        logo=ns.__logo__,
        app_name=ns.__app_name__,
        version=ns.__version__,
        agent_loop_cls=lambda: ns.AgentLoop,
        create_file_edit_activity_hook=ns.create_file_edit_activity_hook,
        sync_workspace_templates=ns.sync_workspace_templates,
        webui_browser_url=ns._webui_browser_url,
        host_for_local_browser=ns._host_for_local_browser,
        tcp_endpoint_reachable=ns._tcp_endpoint_reachable,
        webui_channel_enabled=ns._webui_channel_enabled,
        webui_endpoint_reachable=ns._webui_endpoint_reachable,
        print_foreground_port_conflict=ns._print_foreground_port_conflict,
        prepare_webui_bundle_for_gateway=ns._prepare_webui_bundle_for_gateway,
        migrate_cron_store=ns._migrate_cron_store,
        commit_dream_changes=ns._commit_dream_changes,
        advance_dream_cursor_if_behind=ns._advance_dream_cursor_if_behind,
        heartbeat_has_active_tasks=ns._heartbeat_has_active_tasks,
        heartbeat_preamble=ns._HEARTBEAT_PREAMBLE,
        read_webui_sidebar_state=ns.read_webui_sidebar_state,
        pick_heartbeat_target_from_sessions=ns._pick_heartbeat_target_from_sessions,
        evaluate_response=ns.evaluate_response,
        resolve_evaluator_prompt=ns.resolve_evaluator_prompt,
        ensure_interactive_tty_mode=ns._ensure_interactive_tty_mode,
        install_gateway_shutdown_handlers=ns._install_gateway_shutdown_handlers,
        print_gateway_health_endpoint=ns._print_gateway_health_endpoint,
        gateway_health_max_connections=ns._GATEWAY_HEALTH_MAX_CONNECTIONS,
        gateway_health_read_timeout_seconds=ns._GATEWAY_HEALTH_READ_TIMEOUT_SECONDS,
    )


def agent(ns: Any) -> AgentCommandDeps:
    return AgentCommandDeps(
        agent_loop_cls=ns.AgentLoop,
        load_runtime_config=ns._load_runtime_config,
        sync_workspace_templates=ns.sync_workspace_templates,
        migrate_cron_store=ns._migrate_cron_store,
        set_mira_logs=ns._set_mira_logs,
        create_file_edit_activity_hook=ns.create_file_edit_activity_hook,
        print_agent_response=ns._print_agent_response,
        make_model_display=ns._model_display,
        init_prompt_session=ns._init_prompt_session,
        restore_terminal=ns._restore_terminal,
        flush_pending_tty_input=ns._flush_pending_tty_input,
        read_interactive_input_async=ns._read_interactive_input_async,
        is_exit_command=ns._is_exit_command,
        maybe_print_interactive_progress=ns._maybe_print_interactive_progress,
        print_interactive_response=ns._print_interactive_response,
        make_progress=ns._make_agent_progress_adapter,
    )
