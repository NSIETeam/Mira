"""Gateway runtime implementation for the CLI gateway command."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer

from mira.config.paths import is_default_workspace
from mira.config.schema import Config
from mira.webui.build import BuildMode


@dataclass(frozen=True)
class GatewayRuntimeDeps:
    console: Any
    logger: Any
    logo: str
    app_name: str
    version: str
    agent_loop_cls: Callable[[], Any]
    create_file_edit_activity_hook: Callable[..., Any]
    sync_workspace_templates: Callable[[Path], Any]
    webui_browser_url: Callable[[Config], str]
    host_for_local_browser: Callable[[str], str]
    tcp_endpoint_reachable: Callable[..., bool]
    webui_channel_enabled: Callable[[Config], bool]
    webui_endpoint_reachable: Callable[[str], bool]
    print_foreground_port_conflict: Callable[..., Any]
    prepare_webui_bundle_for_gateway: Callable[..., Any]
    migrate_cron_store: Callable[[Config], Any]
    commit_dream_changes: Callable[[Any], str | None]
    advance_dream_cursor_if_behind: Callable[[Any], Any]
    heartbeat_has_active_tasks: Callable[[str], bool]
    heartbeat_preamble: str
    read_webui_sidebar_state: Callable[[], dict[str, Any]]
    pick_heartbeat_target_from_sessions: Callable[..., tuple[str, str]]
    evaluate_response: Callable[..., Any]
    resolve_evaluator_prompt: Callable[[Path], str]
    ensure_interactive_tty_mode: Callable[[], Any]
    install_gateway_shutdown_handlers: Callable[..., Callable[[], None]]
    print_gateway_health_endpoint: Callable[[str, int], Any]
    gateway_health_max_connections: int
    gateway_health_read_timeout_seconds: float


def run_gateway_runtime(
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
    deps: GatewayRuntimeDeps,
) -> None:
    """Shared gateway runtime; ``open_browser_url`` opens a tab once channels are up."""
    from mira.agent.model_presets import load_model_preset_catalog
    from mira.agent.tools.message import MessageTool
    from mira.agent.turn_delivery import TurnDeliveryFactory
    from mira.bus.queue import MessageBus
    from mira.bus.runtime_events import RuntimeEventBus
    from mira.channels.manager import ChannelManager
    from mira.config.watcher import watch_config_file
    from mira.cron.bound_runner import run_bound_cron_job
    from mira.cron.service import CronJobSkippedError, CronService
    from mira.cron.session_turns import is_bound_cron_job
    from mira.cron.types import CronJob
    from mira.providers.factory import (
        build_provider_snapshot,
        build_unconfigured_provider_snapshot,
        load_provider_snapshot,
    )
    from mira.providers.fallback_provider import FallbackProvider
    from mira.providers.image_generation import image_gen_provider_configs
    from mira.session.keys import UNIFIED_SESSION_KEY, session_key_for_channel
    from mira.session.manager import SessionManager
    from mira.session.webui_turns import (
        WebuiTurnCoordinator,
        WebuiTurnRoutePolicy,
        build_webui_fallback_model_observer,
    )
    from mira.triggers.local_runner import run_local_trigger_queue
    from mira.triggers.local_store import LocalTriggerStore
    from mira.webui.token_usage import TokenUsageHook

    port = port if port is not None else config.gateway.port
    webui_url = deps.webui_browser_url(config)
    gateway_host_for_browser = deps.host_for_local_browser(config.gateway.host)
    if health_server_enabled and deps.tcp_endpoint_reachable(gateway_host_for_browser, port):
        deps.print_foreground_port_conflict(
            webui_url=webui_url,
            gateway_host=config.gateway.host,
            gateway_port=port,
        )
        raise typer.Exit(1)
    if deps.webui_channel_enabled(config) and deps.webui_endpoint_reachable(webui_url):
        deps.print_foreground_port_conflict(
            webui_url=webui_url,
            gateway_host=config.gateway.host,
            gateway_port=port,
        )
        raise typer.Exit(1)

    deps.console.print(
        f"{deps.logo} Starting {deps.app_name} gateway version {deps.version} on port {port}...",
    )
    deps.prepare_webui_bundle_for_gateway(
        config,
        mode=webui_bundle_mode,
        webui_static_dist=webui_static_dist,
    )
    deps.sync_workspace_templates(config.workspace_path)
    bus = MessageBus()
    runtime_events = RuntimeEventBus()
    fallback_model_observer = build_webui_fallback_model_observer(bus)

    def _observe_fallback_models(snapshot):
        if isinstance(snapshot.provider, FallbackProvider):
            snapshot.provider.set_fallback_model_observer(fallback_model_observer)
        return snapshot

    def _load_gateway_provider_snapshot(*args: Any, **kwargs: Any):
        try:
            return _observe_fallback_models(load_provider_snapshot(*args, **kwargs))
        except ValueError as exc:
            if unconfigured_provider_error is None:
                raise
            return build_unconfigured_provider_snapshot(config, str(exc))

    if unconfigured_provider_error is not None:
        provider_snapshot = build_unconfigured_provider_snapshot(
            config,
            unconfigured_provider_error,
        )
    else:
        try:
            provider_snapshot = _observe_fallback_models(build_provider_snapshot(config))
        except ValueError as exc:
            message = str(exc)
            if "No API key configured for provider" in message:
                provider_snapshot = build_unconfigured_provider_snapshot(config, message)
            else:
                deps.console.print(f"[red]Error: {exc}[/red]")
                raise typer.Exit(1) from exc
    session_manager = SessionManager(config.workspace_path)

    from mira.config.loader import get_config_path
    from mira.gateway.runtime import GatewayRuntime, GatewayRuntimePaths

    config_path = str(get_config_path().resolve(strict=False))
    GatewayRuntime.refresh_state_pid(
        paths=GatewayRuntimePaths.for_instance(
            workspace=str(config.workspace_path)
            if not is_default_workspace(config.workspace_path)
            else None,
            config_path=config_path,
        )
    )

    if is_default_workspace(config.workspace_path):
        deps.migrate_cron_store(config)

    cron_store_path = config.workspace_path / "cron" / "jobs.json"
    cron = CronService(cron_store_path)
    trigger_store = LocalTriggerStore(config.workspace_path)

    turn_delivery_factory = TurnDeliveryFactory(
        bus,
        runtime_events,
        route_policy=WebuiTurnRoutePolicy(session_manager),
    )

    agent = deps.agent_loop_cls().from_config(
        config,
        bus,
        provider=provider_snapshot.provider,
        model=provider_snapshot.model,
        context_window_tokens=provider_snapshot.context_window_tokens,
        cron_service=cron,
        session_manager=session_manager,
        image_generation_provider_configs=image_gen_provider_configs(config),
        provider_snapshot_loader=_load_gateway_provider_snapshot,
        preset_catalog_loader=load_model_preset_catalog,
        runtime_events=runtime_events,
        turn_delivery_factory=turn_delivery_factory,
        provider_signature=provider_snapshot.signature,
        hooks=[TokenUsageHook(timezone_name=config.agents.defaults.timezone)],
        local_trigger_store=trigger_store,
        hook_factories=[deps.create_file_edit_activity_hook],
    )
    webui_turn_coordinator = WebuiTurnCoordinator(
        bus=bus,
        sessions=session_manager,
        schedule_background=lambda coro: agent._schedule_background(coro),
    )
    webui_turn_coordinator.subscribe(runtime_events)
    from mira.bus.events import OutboundMessage

    def _channel_session_key(channel: str, chat_id: str) -> str:
        return session_key_for_channel(
            channel,
            chat_id,
            unified_session=config.agents.defaults.unified_session,
        )

    async def _deliver_to_channel(
        msg: OutboundMessage, *, record: bool = False, session_key: str | None = None,
    ) -> None:
        """Publish a user-visible message and mirror it into that channel's session."""
        metadata = dict(msg.metadata or {})
        record = record or bool(metadata.pop("_record_channel_delivery", False))
        if metadata != (msg.metadata or {}):
            msg = OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=msg.content,
                reply_to=msg.reply_to,
                media=msg.media,
                metadata=metadata,
                buttons=msg.buttons,
            )
        if (
            record
            and msg.channel != "cli"
            and msg.content.strip()
            and hasattr(session_manager, "get_or_create")
            and hasattr(session_manager, "save")
        ):
            key = session_key or _channel_session_key(msg.channel, msg.chat_id)
            session = session_manager.get_or_create(key)
            extra: dict[str, Any] = {"_channel_delivery": True}
            if msg.media:
                extra["media"] = list(msg.media)
            session.add_message("assistant", msg.content, **extra)
            session_manager.save(session)
        await bus.publish_outbound(msg)

    message_tool = getattr(agent, "tools", {}).get("message")
    if isinstance(message_tool, MessageTool):
        message_tool.set_send_callback(_deliver_to_channel)

    hb_cfg = config.gateway.heartbeat

    async def on_cron_job(job: CronJob) -> str | None:
        """Execute a cron job through the agent."""
        async def _silent(*_args, **_kwargs):
            pass

        if job.name == "dream":
            from mira.agent.memory import DreamRunProgress, MemoryStore

            dream_session_key = MemoryStore.dream_session_key
            prune_dream_sessions = MemoryStore.prune_dream_sessions

            store = agent.context.memory
            progress = DreamRunProgress()
            resp = None
            try:
                result = store.build_dream_prompt()
                if result is None:
                    deps.logger.info("Dream: nothing to process")
                    return None
                prompt, last_cursor = result
                key = dream_session_key()
                resp = await agent.process_direct(
                    prompt,
                    session_key=key,
                    ephemeral=True,
                    tools=store.build_dream_tools(),
                    on_progress=progress,
                )
                diff_body = store.dream_content_diff()
                completed = MemoryStore.dream_run_completed(
                    resp,
                    had_tool_errors=progress.had_tool_errors,
                )
                if completed:
                    store.set_last_dream_cursor(last_cursor)
                    if diff_body:
                        deps.logger.info(
                            "Dream cron job completed, cursor advanced to {}",
                            last_cursor,
                        )
                    else:
                        deps.logger.info(
                            "Dream cron job completed with no memory changes; "
                            "cursor advanced to {}",
                            last_cursor,
                        )
                else:
                    deps.logger.warning(
                        "Dream cron job did not complete; cursor remains at {}",
                        store.get_last_dream_cursor(),
                    )
            except Exception:
                deps.logger.exception("Dream cron job failed")
            finally:
                from mira.webui.token_usage import record_response_token_usage

                record_response_token_usage(
                    resp,
                    source="dream",
                    timezone_name=config.agents.defaults.timezone,
                )
                sha = deps.commit_dream_changes(store)
                if sha:
                    deps.logger.info("Dream commit: {}", sha)
                store.compact_history()
                prune_dream_sessions(agent.sessions.sessions_dir)
            return None

        if job.name == "heartbeat":
            heartbeat_file = config.workspace_path / "HEARTBEAT.md"
            try:
                content = heartbeat_file.read_text(encoding="utf-8")
            except OSError:
                deps.logger.debug("Heartbeat: HEARTBEAT.md missing")
                return None
            if not deps.heartbeat_has_active_tasks(content):
                deps.logger.debug("Heartbeat: HEARTBEAT.md has no active tasks")
                return None

            channel, chat_id = _pick_heartbeat_target()
            if channel == "cli":
                return None

            prompt = (
                deps.heartbeat_preamble
                + "You are executing periodic heartbeat tasks. Read the active tasks below, "
                + f"perform each one, and report what you did:\n\n{content}"
            )

            suppress_token = None
            if isinstance(message_tool, MessageTool):
                suppress_token = message_tool.set_suppress_delivery(True)
            try:
                resp = await agent.process_direct(
                    prompt,
                    session_key="heartbeat",
                    channel=channel,
                    chat_id=chat_id,
                    on_progress=_silent,
                )
            finally:
                if isinstance(message_tool, MessageTool) and suppress_token is not None:
                    message_tool.reset_suppress_delivery(suppress_token)

            session = agent.sessions.get_or_create("heartbeat")
            session.retain_recent_legal_suffix(hb_cfg.keep_recent_messages)
            agent.sessions.save(session)

            if not resp or not resp.content:
                return None

            response = resp.content
            evaluator_prompt = deps.resolve_evaluator_prompt(config.workspace_path)

            should_notify = await deps.evaluate_response(
                response=response,
                task_context=prompt,
                provider=agent.provider,
                model=agent.model,
                evaluator_prompt=evaluator_prompt,
                default_notify=False,
            )

            if should_notify:
                deps.logger.info("Heartbeat: completed, delivering response")
                await _deliver_to_channel(
                    OutboundMessage(channel=channel, chat_id=chat_id, content=response),
                    record=True,
                )
            else:
                deps.logger.info("Heartbeat: silenced by post-run evaluation")
            return response

        if is_bound_cron_job(job):
            return await run_bound_cron_job(job, agent=agent, cron=cron)

        reason = "unbound agent cron job must be recreated from a chat session"
        deps.logger.warning(
            "Cron: skipped unbound agent job '{}' ({}): {}",
            job.name,
            job.id,
            reason,
        )
        raise CronJobSkippedError(reason)

    cron.on_job = on_cron_job

    def _webui_runtime_model_name() -> str | None:
        model = getattr(agent, "model", None)
        if isinstance(model, str):
            stripped = model.strip()
            return stripped or None
        return None

    channels = ChannelManager(
        config,
        bus,
        session_manager=session_manager,
        cron_service=cron,
        local_trigger_store=trigger_store,
        webui_runtime_model_name=_webui_runtime_model_name,
        webui_cron_pending_job_ids=getattr(agent, "pending_cron_job_ids_for_session", None),
        webui_local_trigger_pending_ids=getattr(
            agent,
            "pending_local_trigger_ids_for_session",
            None,
        ),
        webui_static_dist=webui_static_dist,
        webui_runtime_surface=webui_runtime_surface,
        webui_runtime_capabilities=webui_runtime_capabilities,
    )

    def _pick_heartbeat_target() -> tuple[str, str]:
        """Pick a routable channel/chat target for heartbeat-triggered messages."""
        sidebar_state = deps.read_webui_sidebar_state()
        unified_metadata = None
        if config.agents.defaults.unified_session:
            record = session_manager.read_session_metadata(UNIFIED_SESSION_KEY)
            if isinstance(record, dict) and isinstance(record.get("metadata"), dict):
                unified_metadata = record["metadata"]
        return deps.pick_heartbeat_target_from_sessions(
            enabled_channels=channels.enabled_channels,
            sessions=session_manager.list_sessions(),
            archived_keys=sidebar_state.get("archived_keys", []),
            unified_session_metadata=unified_metadata,
        )

    if channels.enabled_channels:
        deps.console.print(f"[green][/green] Channels enabled: {', '.join(channels.enabled_channels)}")
    else:
        deps.console.print("[yellow]Warning: No channels enabled[/yellow]")

    cron_status = cron.status()
    if cron_status["jobs"] > 0:
        deps.console.print(f"[green][/green] Cron: {cron_status['jobs']} scheduled jobs")

    if hb_cfg.enabled:
        deps.console.print(f"[green][/green] Heartbeat: every {hb_cfg.interval_s}s")
    else:
        deps.console.print("[yellow][/yellow] Heartbeat: disabled")

    async def _health_server(host: str, health_port: int):
        """Lightweight HTTP health endpoint on the gateway port."""
        import json as _json

        connection_slots = asyncio.Semaphore(deps.gateway_health_max_connections)

        async def handle(reader, writer):
            if connection_slots.locked():
                writer.close()
                return

            async with connection_slots:
                try:
                    data = await asyncio.wait_for(
                        reader.read(4096),
                        timeout=deps.gateway_health_read_timeout_seconds,
                    )
                    request_line = data.split(b"\r\n", 1)[0].decode(
                        "utf-8",
                        errors="replace",
                    )
                    method, path = "", ""
                    parts = request_line.split(" ")
                    if len(parts) >= 2:
                        method, path = parts[0], parts[1]

                    if method == "GET" and path == "/health":
                        body = _json.dumps({"status": "ok"})
                        status = "200 OK"
                        content_type = "application/json"
                    else:
                        body = "Not Found"
                        status = "404 Not Found"
                        content_type = "text/plain"

                    resp = (
                        f"HTTP/1.0 {status}\r\n"
                        f"Content-Type: {content_type}\r\n"
                        f"Content-Length: {len(body)}\r\n"
                        "Connection: close\r\n"
                        f"\r\n{body}"
                    )
                    writer.write(resp.encode())
                    await writer.drain()
                except (asyncio.TimeoutError, ConnectionError):
                    pass
                finally:
                    writer.close()

        server = await asyncio.start_server(handle, host, health_port)
        deps.print_gateway_health_endpoint(host, health_port)
        async with server:
            await server.serve_forever()

    from mira.cron.types import CronPayload, CronSchedule

    dream_cfg = config.agents.defaults.dream
    if dream_cfg.enabled:
        cron.register_system_job(CronJob(
            id="dream",
            name="dream",
            schedule=dream_cfg.build_schedule(config.agents.defaults.timezone),
            payload=CronPayload(kind="system_event"),
        ))
        deps.console.print(f"[green][/green] Dream: {dream_cfg.describe_schedule()}")
    else:
        deps.console.print("[yellow]○[/yellow] Dream: disabled")
        deps.advance_dream_cursor_if_behind(agent.context.memory)

    if hb_cfg.enabled:
        cron.register_system_job(CronJob(
            id="heartbeat",
            name="heartbeat",
            schedule=CronSchedule(
                kind="every",
                every_ms=hb_cfg.interval_s * 1000,
                tz=config.agents.defaults.timezone,
            ),
            payload=CronPayload(kind="system_event"),
        ))

    async def _open_browser_when_ready() -> None:
        """Wait for the gateway to bind, then point the user's browser at the webui."""
        if not open_browser_url:
            return
        import webbrowser
        from urllib.parse import urlparse

        parsed = urlparse(open_browser_url)
        target_host = parsed.hostname or config.gateway.host or "127.0.0.1"
        target_port = parsed.port or port
        for _ in range(40):
            try:
                reader, writer = await asyncio.open_connection(
                    target_host,
                    target_port,
                )
                writer.close()
                with suppress(Exception):
                    await writer.wait_closed()
                break
            except OSError:
                await asyncio.sleep(0.1)
        try:
            webbrowser.open(open_browser_url)
            deps.console.print(f"[green][/green] Opened browser at {open_browser_url}")
        except Exception as exc:
            deps.console.print(
                f"[yellow]Could not open browser ({exc}); visit {open_browser_url}[/yellow]",
            )

    async def run():
        tasks: list[asyncio.Task] = []
        shutdown_task: asyncio.Task | None = None
        runtime_tasks: asyncio.Future | None = None
        runtime_tasks_drained = False
        shutdown_event = asyncio.Event()
        deps.ensure_interactive_tty_mode()
        restore_shutdown_handlers = deps.install_gateway_shutdown_handlers(
            asyncio.get_running_loop(),
            shutdown_event,
            tasks,
            deps.console.print,
        )
        try:
            await cron.start()
            agent.runtime_resolver.invalidate()
            tasks = [
                asyncio.create_task(
                    watch_config_file(
                        Path(config_path),
                        lambda: agent.invalidate_runtime_config(),
                    ),
                    name="mira-config-watcher",
                ),
                asyncio.create_task(agent.run(), name="mira-agent-loop"),
                asyncio.create_task(channels.start_all(), name="mira-channels"),
                asyncio.create_task(
                    run_local_trigger_queue(
                        store=trigger_store,
                        submit_turn=getattr(agent, "submit_local_trigger_turn", None),
                        is_channel_enabled=lambda name: channels.get_channel(name) is not None,
                    ),
                    name="mira-local-triggers",
                ),
            ]
            if health_server_enabled:
                tasks.append(asyncio.create_task(
                    _health_server(config.gateway.host, port),
                    name="mira-health-server",
                ))
            if open_browser_url:
                tasks.append(asyncio.create_task(
                    _open_browser_when_ready(),
                    name="mira-open-browser",
                ))
            runtime_tasks = asyncio.gather(*tasks)
            shutdown_task = asyncio.create_task(
                shutdown_event.wait(),
                name="mira-gateway-shutdown",
            )
            done, _pending = await asyncio.wait(
                {runtime_tasks, shutdown_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if runtime_tasks in done:
                runtime_tasks_drained = True
                await runtime_tasks
            elif runtime_tasks is not None:
                runtime_tasks.cancel()
        except KeyboardInterrupt:
            deps.console.print("\nShutting down...")
        except Exception:
            import traceback

            deps.console.print("\n[red]Error: Gateway crashed unexpectedly[/red]")
            deps.console.print(traceback.format_exc())
        finally:
            try:
                if shutdown_task and not shutdown_task.done():
                    shutdown_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await shutdown_task
                cron.stop()
                agent.stop()
                await channels.stop_all()
                for task in tasks:
                    if not task.done():
                        task.cancel()
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                if runtime_tasks is not None and not runtime_tasks_drained:
                    with suppress(asyncio.CancelledError, Exception):
                        await runtime_tasks
                flushed = agent.sessions.flush_all()
                if flushed:
                    deps.logger.info("Shutdown: flushed {} session(s) to disk", flushed)
            finally:
                restore_shutdown_handlers()

    asyncio.run(run())
