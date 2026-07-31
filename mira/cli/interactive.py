"""Interactive CLI input and rendering helpers."""

from __future__ import annotations

import os
import select
import sys
from contextlib import nullcontext, suppress
from typing import Any

from prompt_toolkit import PromptSession, print_formatted_text
from prompt_toolkit.application import run_in_terminal
from prompt_toolkit.formatted_text import ANSI, HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console
from rich.markdown import Markdown
from rich.text import Text

from mira import __app_name__, __logo__
from mira.bus.outbound_events import (
    ProgressEvent,
    RetryWaitEvent,
    outbound_event_from_message,
)
from mira.cli.stream import StreamRenderer, ThinkingSpinner
from mira.utils.helpers import sanitize_surrogates as _sanitize_surrogates

EXIT_COMMANDS = {"exit", "quit", "/exit", "/quit", ":q"}
REASONING_SENTENCE_ENDINGS = (".", "!", "?", "。", "！", "？")
REASONING_FLUSH_CHARS = 60


class SafeFileHistory(FileHistory):
    """FileHistory subclass that sanitizes surrogate characters on write."""

    def store_string(self, string: str) -> None:
        super().store_string(_sanitize_surrogates(string))


class ReasoningBuffer:
    def __init__(self) -> None:
        self._text = ""

    def add(self, text: str) -> str | None:
        if not text:
            return None
        self._text += text
        if self._should_flush(text):
            return self.flush()
        return None

    def flush(self) -> str | None:
        text = self._text.strip()
        self._text = ""
        return text or None

    def clear(self) -> None:
        self._text = ""

    def _should_flush(self, text: str) -> bool:
        stripped = text.rstrip()
        return (
            "\n" in text
            or stripped.endswith(REASONING_SENTENCE_ENDINGS)
            or len(self._text) >= REASONING_FLUSH_CHARS
        )


def flush_pending_tty_input() -> None:
    """Drop unread keypresses typed while the model was generating output."""
    try:
        fd = sys.stdin.fileno()
        if not os.isatty(fd):
            return
    except Exception:
        return

    with suppress(Exception):
        import termios

        termios.tcflush(fd, termios.TCIFLUSH)
        return

    with suppress(Exception):
        while True:
            ready, _, _ = select.select([fd], [], [], 0)
            if not ready:
                break
            if not os.read(fd, 4096):
                break


def restore_terminal(saved_term_attrs: Any) -> None:
    """Restore terminal to its original state."""
    if saved_term_attrs is None:
        return
    with suppress(Exception):
        import termios

        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, saved_term_attrs)


def build_cli_key_bindings() -> KeyBindings:
    """Build key bindings for Enter submit and Alt/Shift+Enter newlines."""
    with suppress(Exception):
        from prompt_toolkit.input import ansi_escape_sequences as _aes

        _aes.ANSI_SEQUENCES.setdefault("\x1b[13;2u", Keys.ControlF3)

    kb = KeyBindings()

    @kb.add("enter")
    def _(event):
        event.current_buffer.validate_and_handle()

    @kb.add("escape", "enter")
    def _(event):
        event.current_buffer.insert_text("\n")

    @kb.add("escape", Keys.ControlJ)
    def _(event):
        event.current_buffer.insert_text("\n")

    @kb.add(Keys.ControlF3)
    def _(event):
        event.current_buffer.insert_text("\n")

    return kb


def init_prompt_session(
    *,
    prompt_session_cls: Any = PromptSession,
    history_cls: Any = SafeFileHistory,
    key_bindings_factory=build_cli_key_bindings,
) -> tuple[Any, Any]:
    """Create a prompt_toolkit session and return it with saved terminal state."""
    saved_term_attrs = None
    with suppress(Exception):
        import termios

        saved_term_attrs = termios.tcgetattr(sys.stdin.fileno())

    from mira.config.paths import get_cli_history_path

    history_file = get_cli_history_path()
    history_file.parent.mkdir(parents=True, exist_ok=True)

    session = prompt_session_cls(
        history=history_cls(str(history_file)),
        enable_open_in_editor=False,
        multiline=True,
        key_bindings=key_bindings_factory(),
    )
    return session, saved_term_attrs


def make_console() -> Console:
    return Console(file=sys.stdout)


def render_interactive_ansi(
    render_fn,
    *,
    base_console: Console,
) -> str:
    """Render Rich output to ANSI so prompt_toolkit can print it safely."""
    ansi_console = Console(
        force_terminal=sys.stdout.isatty(),
        color_system=base_console.color_system or "standard",
        width=base_console.width,
    )
    with ansi_console.capture() as capture:
        render_fn(ansi_console)
    return capture.get()


def response_renderable(content: str, render_markdown: bool, metadata: dict | None = None):
    """Render plain-text command output without markdown collapsing newlines."""
    if not render_markdown:
        return Text(content)
    if (metadata or {}).get("render_as") == "text":
        return Text(content)
    return Markdown(content)


def print_agent_response(
    response: str,
    render_markdown: bool,
    *,
    console_factory=make_console,
    metadata: dict | None = None,
    show_header: bool = True,
) -> None:
    """Render assistant response with consistent terminal styling."""
    output_console = console_factory()
    content = response or ""
    body = response_renderable(content, render_markdown, metadata)
    if show_header:
        output_console.print()
        output_console.print(f"[cyan]{__logo__} {__app_name__}[/cyan]")
    output_console.print(body)
    output_console.print()


async def print_interactive_line(
    text: str,
    *,
    base_console: Console,
    render_ansi=render_interactive_ansi,
    formatted_print=print_formatted_text,
    terminal_runner=run_in_terminal,
) -> None:
    """Print async interactive updates with prompt_toolkit-safe Rich styling."""
    def _write() -> None:
        ansi = render_ansi(
            lambda c: c.print(f"  [dim]↳ {text}[/dim]"),
            base_console=base_console,
        )
        formatted_print(ANSI(ansi), end="")

    await terminal_runner(_write)


async def print_interactive_response(
    response: str,
    render_markdown: bool,
    *,
    base_console: Console,
    render_ansi=render_interactive_ansi,
    formatted_print=print_formatted_text,
    terminal_runner=run_in_terminal,
    metadata: dict | None = None,
) -> None:
    """Print async interactive replies with prompt_toolkit-safe Rich styling."""
    def _write() -> None:
        content = response or ""
        ansi = render_ansi(
            lambda c: (
                c.print(),
                c.print(f"[cyan]{__logo__} {__app_name__}[/cyan]"),
                c.print(response_renderable(content, render_markdown, metadata)),
                c.print(),
            ),
            base_console=base_console,
        )
        formatted_print(ANSI(ansi), end="")

    await terminal_runner(_write)


def print_cli_progress_line(
    text: str,
    thinking: ThinkingSpinner | None,
    renderer: StreamRenderer | None = None,
    *,
    base_console: Console,
) -> None:
    """Print a CLI progress line, pausing the spinner if needed."""
    if not text.strip():
        return
    target = renderer.console if renderer else base_console
    pause = renderer.pause_spinner() if renderer else (thinking.pause() if thinking else nullcontext())
    with pause:
        if renderer:
            renderer.ensure_header()
        target.print(f"  [dim]↳ {text}[/dim]")


def print_cli_reasoning(
    text: str,
    thinking: ThinkingSpinner | None,
    renderer: StreamRenderer | None = None,
    *,
    base_console: Console,
) -> None:
    """Print reasoning/thinking content in a distinct style."""
    if not text.strip():
        return
    target = renderer.console if renderer else base_console
    pause = renderer.pause_spinner() if renderer else (thinking.pause() if thinking else nullcontext())
    with pause:
        if renderer:
            renderer.ensure_header()
        target.print(f"[dim italic] {text}[/dim italic]")


def flush_cli_reasoning(
    reasoning_buffer: ReasoningBuffer,
    thinking: ThinkingSpinner | None,
    renderer: StreamRenderer | None = None,
    *,
    print_reasoning,
) -> None:
    text = reasoning_buffer.flush()
    if text:
        print_reasoning(text, thinking, renderer)


async def print_interactive_progress_line(
    text: str,
    thinking: ThinkingSpinner | None,
    renderer: StreamRenderer | None = None,
    *,
    print_line,
) -> None:
    """Print an interactive progress line, pausing the spinner if needed."""
    if not text.strip():
        return
    if renderer:
        with renderer.pause_spinner():
            renderer.ensure_header()
            renderer.console.print(f"  [dim]↳ {text}[/dim]")
    else:
        with thinking.pause() if thinking else nullcontext():
            await print_line(text)


async def maybe_print_interactive_progress(
    msg: Any,
    thinking: ThinkingSpinner | None,
    channels_config: Any,
    renderer: StreamRenderer | None = None,
    reasoning_buffer: ReasoningBuffer | None = None,
    *,
    print_progress_line,
    print_reasoning,
) -> bool:
    event = outbound_event_from_message(msg)
    if isinstance(event, RetryWaitEvent):
        await print_progress_line(msg.content, thinking, renderer)
        return True

    if not isinstance(event, ProgressEvent):
        return False

    reasoning_buffer = reasoning_buffer or ReasoningBuffer()

    if event.reasoning_end:
        if channels_config and not channels_config.show_reasoning:
            reasoning_buffer.clear()
        else:
            flush_cli_reasoning(
                reasoning_buffer,
                thinking,
                renderer,
                print_reasoning=print_reasoning,
            )
        return True

    is_tool_hint = event.tool_hint
    is_reasoning = event.reasoning or event.reasoning_delta
    if is_reasoning:
        if channels_config and not channels_config.show_reasoning:
            reasoning_buffer.clear()
            return True
        text = reasoning_buffer.add(msg.content)
        if text:
            print_reasoning(text, thinking, renderer)
        return True
    if channels_config and is_tool_hint and not channels_config.send_tool_hints:
        return True
    if channels_config and not is_tool_hint and not channels_config.send_progress:
        return True

    await print_progress_line(msg.content, thinking, renderer)
    return True


def make_agent_progress_adapter(
    agent_loop: Any,
    thinking: ThinkingSpinner | None,
    renderer: StreamRenderer | None = None,
    *,
    reasoning_buffer_only: bool = False,
    print_progress_line,
    print_reasoning,
) -> Any:
    reasoning_buffer = ReasoningBuffer()
    if reasoning_buffer_only:
        return reasoning_buffer

    async def _cli_progress(
        content: str,
        *,
        tool_hint: bool = False,
        reasoning: bool = False,
        **_kwargs: Any,
    ) -> None:
        ch = agent_loop.channels_config

        if _kwargs.get("reasoning_end"):
            if ch and not ch.show_reasoning:
                reasoning_buffer.clear()
            else:
                flush_cli_reasoning(
                    reasoning_buffer,
                    thinking,
                    renderer,
                    print_reasoning=print_reasoning,
                )
            return

        if reasoning:
            if ch and not ch.show_reasoning:
                reasoning_buffer.clear()
                return
            text = reasoning_buffer.add(content)
            if text:
                print_reasoning(text, thinking, renderer)
            return
        if ch and tool_hint and not ch.send_tool_hints:
            return
        if ch and not tool_hint and not ch.send_progress:
            return
        print_progress_line(content, thinking, renderer)

    return _cli_progress


def is_exit_command(command: str) -> bool:
    """Return True when input should end interactive chat."""
    return command.lower() in EXIT_COMMANDS


async def read_interactive_input_async(
    prompt_session: Any,
    *,
    patch_stdout_cm=patch_stdout,
) -> str:
    """Read user input using prompt_toolkit."""
    if prompt_session is None:
        raise RuntimeError("Call _init_prompt_session() first")
    try:
        with patch_stdout_cm():
            return await prompt_session.prompt_async(
                HTML("<b fg='ansiblue'>You:</b> "),
            )
    except EOFError as exc:
        raise KeyboardInterrupt from exc
