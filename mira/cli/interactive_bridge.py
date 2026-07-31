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


def install_command_exports(ns: Any) -> None:
    """Install legacy ``mira.cli.commands`` interactive helper names."""

    def _restore_terminal() -> None:
        restore_terminal(ns)

    def _init_prompt_session() -> None:
        init_prompt_session(ns)

    def _make_console() -> Console:
        return make_console(ns)

    def _render_interactive_ansi(render_fn: Any) -> str:
        return render_interactive_ansi(ns, render_fn)

    def _print_agent_response(
        response: str,
        render_markdown: bool,
        metadata: dict | None = None,
        show_header: bool = True,
    ) -> None:
        print_agent_response(ns, response, render_markdown, metadata, show_header)

    def _response_renderable(
        content: str,
        render_markdown: bool,
        metadata: dict | None = None,
    ) -> Any:
        return response_renderable(ns, content, render_markdown, metadata)

    async def _print_interactive_line(text: str) -> None:
        await print_interactive_line(ns, text)

    async def _print_interactive_response(
        response: str,
        render_markdown: bool,
        metadata: dict | None = None,
    ) -> None:
        await print_interactive_response(ns, response, render_markdown, metadata)

    def _print_cli_progress_line(
        text: str,
        thinking: ThinkingSpinner | None,
        renderer: StreamRenderer | None = None,
    ) -> None:
        print_cli_progress_line(ns, text, thinking, renderer)

    def _print_cli_reasoning(
        text: str,
        thinking: ThinkingSpinner | None,
        renderer: StreamRenderer | None = None,
    ) -> None:
        print_cli_reasoning(ns, text, thinking, renderer)

    def _flush_cli_reasoning(
        reasoning_buffer: Any,
        thinking: ThinkingSpinner | None,
        renderer: StreamRenderer | None = None,
    ) -> None:
        flush_cli_reasoning(ns, reasoning_buffer, thinking, renderer)

    async def _print_interactive_progress_line(
        text: str,
        thinking: ThinkingSpinner | None,
        renderer: StreamRenderer | None = None,
    ) -> None:
        await print_interactive_progress_line(ns, text, thinking, renderer)

    async def _maybe_print_interactive_progress(
        msg: Any,
        thinking: ThinkingSpinner | None,
        channels_config: Any,
        renderer: StreamRenderer | None = None,
        reasoning_buffer: Any | None = None,
    ) -> bool:
        return await maybe_print_interactive_progress(
            ns,
            msg,
            thinking,
            channels_config,
            renderer,
            reasoning_buffer,
        )

    def _make_agent_progress_adapter(
        agent_loop: AgentLoop,
        thinking: ThinkingSpinner | None,
        renderer: StreamRenderer | None = None,
        *,
        reasoning_buffer_only: bool = False,
    ) -> Any:
        return make_agent_progress_adapter(
            ns,
            agent_loop,
            thinking,
            renderer,
            reasoning_buffer_only=reasoning_buffer_only,
        )

    async def _read_interactive_input_async() -> str:
        return await read_interactive_input_async(ns)

    ns._restore_terminal = _restore_terminal
    ns._init_prompt_session = _init_prompt_session
    ns._make_console = _make_console
    ns._render_interactive_ansi = _render_interactive_ansi
    ns._print_agent_response = _print_agent_response
    ns._response_renderable = _response_renderable
    ns._print_interactive_line = _print_interactive_line
    ns._print_interactive_response = _print_interactive_response
    ns._print_cli_progress_line = _print_cli_progress_line
    ns._print_cli_reasoning = _print_cli_reasoning
    ns._flush_cli_reasoning = _flush_cli_reasoning
    ns._print_interactive_progress_line = _print_interactive_progress_line
    ns._maybe_print_interactive_progress = _maybe_print_interactive_progress
    ns._make_agent_progress_adapter = _make_agent_progress_adapter
    ns._read_interactive_input_async = _read_interactive_input_async
