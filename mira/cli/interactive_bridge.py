"""Compatibility bridge for interactive helpers exported by ``commands``."""

from __future__ import annotations

from typing import Any

from rich.console import Console

from mira.agent.loop import AgentLoop
from mira.cli.stream import StreamRenderer, ThinkingSpinner


def restore_terminal(ns: Any) -> None:
    ns._interactive.restore_terminal(ns._SAVED_TERM_ATTRS)


def init_prompt_session(ns: Any) -> None:
    ns._PROMPT_SESSION, ns._SAVED_TERM_ATTRS = ns._interactive.init_prompt_session(
        prompt_session_cls=ns.PromptSession,
        history_cls=ns.SafeFileHistory,
        key_bindings_factory=ns._build_cli_key_bindings,
    )


def make_console(ns: Any) -> Console:
    return ns._interactive.make_console()


def render_interactive_ansi(ns: Any, render_fn: Any) -> str:
    return ns._interactive.render_interactive_ansi(render_fn, base_console=ns.console)


def print_agent_response(
    ns: Any,
    response: str,
    render_markdown: bool,
    metadata: dict | None = None,
    show_header: bool = True,
) -> None:
    ns._interactive.print_agent_response(
        response,
        render_markdown,
        console_factory=ns._make_console,
        metadata=metadata,
        show_header=show_header,
    )


def response_renderable(
    ns: Any,
    content: str,
    render_markdown: bool,
    metadata: dict | None = None,
) -> Any:
    return ns._interactive.response_renderable(content, render_markdown, metadata)


async def print_interactive_line(ns: Any, text: str) -> None:
    await ns._interactive.print_interactive_line(
        text,
        base_console=ns.console,
        render_ansi=lambda fn, *, base_console: ns._render_interactive_ansi(fn),
        formatted_print=ns.print_formatted_text,
        terminal_runner=ns.run_in_terminal,
    )


async def print_interactive_response(
    ns: Any,
    response: str,
    render_markdown: bool,
    metadata: dict | None = None,
) -> None:
    await ns._interactive.print_interactive_response(
        response,
        render_markdown,
        base_console=ns.console,
        render_ansi=lambda fn, *, base_console: ns._render_interactive_ansi(fn),
        formatted_print=ns.print_formatted_text,
        terminal_runner=ns.run_in_terminal,
        metadata=metadata,
    )


def print_cli_progress_line(
    ns: Any,
    text: str,
    thinking: ThinkingSpinner | None,
    renderer: StreamRenderer | None = None,
) -> None:
    ns._interactive.print_cli_progress_line(text, thinking, renderer, base_console=ns.console)


def print_cli_reasoning(
    ns: Any,
    text: str,
    thinking: ThinkingSpinner | None,
    renderer: StreamRenderer | None = None,
) -> None:
    ns._interactive.print_cli_reasoning(text, thinking, renderer, base_console=ns.console)


def flush_cli_reasoning(
    ns: Any,
    reasoning_buffer: Any,
    thinking: ThinkingSpinner | None,
    renderer: StreamRenderer | None = None,
) -> None:
    ns._interactive.flush_cli_reasoning(
        reasoning_buffer,
        thinking,
        renderer,
        print_reasoning=ns._print_cli_reasoning,
    )


async def print_interactive_progress_line(
    ns: Any,
    text: str,
    thinking: ThinkingSpinner | None,
    renderer: StreamRenderer | None = None,
) -> None:
    await ns._interactive.print_interactive_progress_line(
        text,
        thinking,
        renderer,
        print_line=ns._print_interactive_line,
    )


async def maybe_print_interactive_progress(
    ns: Any,
    msg: Any,
    thinking: ThinkingSpinner | None,
    channels_config: Any,
    renderer: StreamRenderer | None = None,
    reasoning_buffer: Any | None = None,
) -> bool:
    return await ns._interactive.maybe_print_interactive_progress(
        msg,
        thinking,
        channels_config,
        renderer,
        reasoning_buffer,
        print_progress_line=ns._print_interactive_progress_line,
        print_reasoning=ns._print_cli_reasoning,
    )


def make_agent_progress_adapter(
    ns: Any,
    agent_loop: AgentLoop,
    thinking: ThinkingSpinner | None,
    renderer: StreamRenderer | None = None,
    *,
    reasoning_buffer_only: bool = False,
) -> Any:
    return ns._interactive.make_agent_progress_adapter(
        agent_loop,
        thinking,
        renderer,
        reasoning_buffer_only=reasoning_buffer_only,
        print_progress_line=ns._print_cli_progress_line,
        print_reasoning=ns._print_cli_reasoning,
    )


async def read_interactive_input_async(ns: Any) -> str:
    return await ns._interactive.read_interactive_input_async(
        ns._PROMPT_SESSION,
        patch_stdout_cm=ns.patch_stdout,
    )
