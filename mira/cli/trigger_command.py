"""Local trigger CLI command implementation."""

from __future__ import annotations

import sys
from collections.abc import Callable

import typer
from rich.console import Console

from mira.config.schema import Config


def _read_trigger_cli_message(message: str | None, *, console: Console) -> str:
    """Read a trigger message from an argument or stdin."""
    if message and message.strip():
        return message
    try:
        if not sys.stdin.isatty():
            content = sys.stdin.read()
            if content.strip():
                return content
    except Exception:
        pass
    console.print("[red]Error: trigger message is required[/red]")
    raise typer.Exit(1)


def run_trigger_command(
    *,
    trigger_id: str,
    message: str | None,
    workspace: str | None,
    config_path_arg: str | None,
    console: Console,
    load_runtime_config: Callable[[str | None, str | None], Config],
) -> None:
    """Deliver a local trigger message to its bound chat session."""
    from mira.triggers.local_store import (
        LocalTriggerStore,
        TriggerDisabledError,
        TriggerNotFoundError,
        TriggerStoreError,
    )

    runtime_config = load_runtime_config(config_path_arg, workspace)
    content = _read_trigger_cli_message(message, console=console)
    store = LocalTriggerStore(runtime_config.workspace_path)
    try:
        delivery = store.enqueue(trigger_id, content)
    except (TriggerNotFoundError, TriggerDisabledError) as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(1) from exc
    except (TriggerStoreError, ValueError) as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(f"[green]Queued[/green] {delivery.trigger_id} ({delivery.id})")
