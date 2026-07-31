"""Implementation for the `mira agent` route."""

from __future__ import annotations

import asyncio
import signal
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import typer
from rich.console import Console

from mira import __logo__
from mira.bus.outbound_events import (
    StreamDeltaEvent,
    StreamedResponseEvent,
    StreamEndEvent,
    outbound_event_from_message,
)
from mira.cli.stream import StreamRenderer, ThinkingSpinner
from mira.config.paths import is_default_workspace
from mira.config.schema import Config
from mira.utils.helpers import sanitize_surrogates
from mira.utils.restart import (
    consume_restart_notice_from_env,
    format_restart_completed_message,
    should_show_cli_restart_notice,
)

console = Console()


@dataclass(frozen=True)
class AgentCommandDeps:
    agent_loop_cls: Any
    load_runtime_config: Callable[[str | None, str | None], Config]
    sync_workspace_templates: Callable[..., None]
    migrate_cron_store: Callable[[Config], None]
    set_mira_logs: Callable[[bool], None]
    create_file_edit_activity_hook: Callable[..., Any]
    print_agent_response: Callable[..., None]
    make_model_display: Callable[[Config], tuple[str, str]]
    init_prompt_session: Callable[[], None]
    restore_terminal: Callable[[], None]
    flush_pending_tty_input: Callable[[], None]
    read_interactive_input_async: Callable[[], Any]
    is_exit_command: Callable[[str], bool]
    maybe_print_interactive_progress: Callable[..., Any]
    print_interactive_response: Callable[..., Any]
    make_progress: Callable[..., Any]


def run_agent_command(
    *,
    message: str | None,
    session_id: str,
    workspace: str | None,
    config_path_arg: str | None,
    markdown: bool,
    logs: bool,
    deps: AgentCommandDeps,
) -> None:
    """Interact with the agent directly."""
    from mira.bus.queue import MessageBus
    from mira.cron.service import CronService
    from mira.providers.image_generation import image_gen_provider_configs

    config = deps.load_runtime_config(config_path_arg, workspace)
    deps.sync_workspace_templates(config.workspace_path)

    bus = MessageBus()

    if is_default_workspace(config.workspace_path):
        deps.migrate_cron_store(config)

    cron_store_path = config.workspace_path / "cron" / "jobs.json"
    cron = CronService(cron_store_path)

    deps.set_mira_logs(logs)

    try:
        agent_loop = deps.agent_loop_cls.from_config(
            config,
            bus,
            cron_service=cron,
            image_generation_provider_configs=image_gen_provider_configs(config),
            hook_factories=[deps.create_file_edit_activity_hook],
        )
    except ValueError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(1) from exc

    restart_notice = consume_restart_notice_from_env()
    if restart_notice and should_show_cli_restart_notice(restart_notice, session_id):
        deps.print_agent_response(
            format_restart_completed_message(restart_notice.started_at_raw),
            render_markdown=False,
        )

    thinking: ThinkingSpinner | None = None

    if message:
        async def run_once() -> None:
            renderer = StreamRenderer(
                render_markdown=markdown,
                bot_name=config.agents.defaults.bot_name,
                bot_icon=config.agents.defaults.bot_icon,
            )
            response = await agent_loop.process_direct(
                message,
                session_id,
                on_progress=deps.make_progress(agent_loop, thinking, renderer),
                on_stream=renderer.on_delta,
                on_stream_end=renderer.on_end,
            )
            if not renderer.streamed:
                await renderer.close()
                print_kwargs: dict[str, Any] = {}
                if renderer.header_printed:
                    print_kwargs["show_header"] = False
                deps.print_agent_response(
                    response.content if response else "",
                    render_markdown=markdown,
                    metadata=response.metadata if response else None,
                    **print_kwargs,
                )
            await agent_loop.close_mcp()

        asyncio.run(run_once())
        return

    from mira.bus.events import InboundMessage

    deps.init_prompt_session()
    model, preset_tag = deps.make_model_display(config)
    icon = config.agents.defaults.bot_icon or __logo__
    console.print(
        f"{icon} Interactive mode [bold blue]({model})[/bold blue]{preset_tag} "
        "- type [bold]exit[/bold] or [bold]Ctrl+C[/bold] to quit\n"
    )

    if ":" in session_id:
        cli_channel, cli_chat_id = session_id.split(":", 1)
    else:
        cli_channel, cli_chat_id = "cli", session_id

    def _handle_signal(signum: int, _frame: Any) -> None:
        sig_name = signal.Signals(signum).name
        deps.restore_terminal()
        console.print(f"\nReceived {sig_name}, goodbye!")
        sys.exit(0)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, _handle_signal)
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_IGN)

    async def run_interactive() -> None:
        bus_task = asyncio.create_task(agent_loop.run())
        turn_done = asyncio.Event()
        turn_done.set()
        turn_response: list[Any] = []
        renderer: StreamRenderer | None = None
        reasoning_buffer = deps.make_progress(agent_loop, thinking, None, reasoning_buffer_only=True)

        async def _consume_outbound() -> None:
            while True:
                try:
                    msg = await asyncio.wait_for(bus.consume_outbound(), timeout=1.0)
                    event = outbound_event_from_message(msg)

                    if isinstance(event, StreamDeltaEvent):
                        if renderer:
                            await renderer.on_delta(msg.content)
                        continue
                    if isinstance(event, StreamEndEvent):
                        if renderer:
                            await renderer.on_end(resuming=event.resuming)
                        continue
                    if isinstance(event, StreamedResponseEvent):
                        if msg.content and renderer and not renderer.streamed:
                            await renderer.close()
                            print_kwargs: dict[str, Any] = {}
                            if renderer.header_printed:
                                print_kwargs["show_header"] = False
                            deps.print_agent_response(
                                msg.content,
                                render_markdown=markdown,
                                metadata=msg.metadata,
                                **print_kwargs,
                            )
                        turn_done.set()
                        continue

                    if await deps.maybe_print_interactive_progress(
                        msg,
                        renderer,
                        agent_loop.channels_config,
                        renderer,
                        reasoning_buffer,
                    ):
                        continue

                    if not turn_done.is_set():
                        if msg.content:
                            turn_response.append(msg)
                        turn_done.set()
                    elif msg.content:
                        await deps.print_interactive_response(
                            msg.content,
                            render_markdown=markdown,
                            metadata=msg.metadata,
                        )
                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    break

        outbound_task = asyncio.create_task(_consume_outbound())

        try:
            while True:
                try:
                    deps.flush_pending_tty_input()
                    if renderer:
                        renderer.stop_for_input()
                    user_input = sanitize_surrogates(await deps.read_interactive_input_async())
                    command = user_input.strip()
                    if not command:
                        continue

                    if deps.is_exit_command(command):
                        deps.restore_terminal()
                        console.print("\nGoodbye!")
                        break

                    turn_done.clear()
                    turn_response.clear()
                    reasoning_buffer.clear()
                    renderer = StreamRenderer(
                        render_markdown=markdown,
                        bot_name=config.agents.defaults.bot_name,
                        bot_icon=config.agents.defaults.bot_icon,
                    )

                    await bus.publish_inbound(
                        InboundMessage(
                            channel=cli_channel,
                            sender_id="user",
                            chat_id=cli_chat_id,
                            content=user_input,
                            metadata={"_wants_stream": True},
                        )
                    )

                    await turn_done.wait()

                    if turn_response:
                        response_msg = turn_response[0]
                        content = response_msg.content
                        meta = response_msg.metadata
                        if content and not isinstance(response_msg.event, StreamedResponseEvent):
                            if renderer:
                                await renderer.close()
                            print_kwargs: dict[str, Any] = {}
                            if renderer and renderer.header_printed:
                                print_kwargs["show_header"] = False
                            deps.print_agent_response(
                                content,
                                render_markdown=markdown,
                                metadata=meta,
                                **print_kwargs,
                            )
                    elif renderer and not renderer.streamed:
                        await renderer.close()
                except KeyboardInterrupt:
                    deps.restore_terminal()
                    console.print("\nGoodbye!")
                    break
                except EOFError:
                    deps.restore_terminal()
                    console.print("\nGoodbye!")
                    break
        finally:
            agent_loop.stop()
            outbound_task.cancel()
            await asyncio.gather(bus_task, outbound_task, return_exceptions=True)
            await agent_loop.close_mcp()

    asyncio.run(run_interactive())
