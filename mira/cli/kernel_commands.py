"""Kernel inspection commands registered by the top-level CLI."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from mira.config.schema import Config

InspectionConfigLoader = Callable[[str | None, str | None], tuple[Path, Config]]


def register_kernel_commands(
    app: typer.Typer,
    *,
    console: Console,
    load_inspection_config: InspectionConfigLoader,
) -> None:
    """Register kernel diagnostics without expanding the main commands module."""
    fs_app = typer.Typer(help="Inspect MiraFS virtual namespaces")
    app.add_typer(fs_app, name="fs")

    @fs_app.command("ls")
    def fs_ls(
        path: str = typer.Argument("/", help="MiraFS path such as /, /mem, /ctx, or /tool"),
        config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
        workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
        json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
    ) -> None:
        """List a MiraFS namespace."""
        from mira.kernel.fs import MiraFS, MiraFSError

        _config_path, loaded = load_inspection_config(config, workspace)
        fs = MiraFS(workspace=loaded.workspace_path)
        try:
            entries = fs.list(path)
        except MiraFSError as exc:
            console.print(f"[red]Error: {exc}[/red]")
            raise typer.Exit(1) from exc
        if json_output:
            typer.echo(json.dumps({"path": path, "entries": entries}, ensure_ascii=False))
        else:
            for entry in entries:
                console.print(entry)

    @fs_app.command("read")
    def fs_read(
        path: str = typer.Argument(..., help="MiraFS path to read"),
        config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
        workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
        json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
    ) -> None:
        """Read text from a MiraFS path."""
        from mira.kernel.fs import MiraFS, MiraFSError

        _config_path, loaded = load_inspection_config(config, workspace)
        fs = MiraFS(workspace=loaded.workspace_path)
        try:
            content = fs.read_text(path)
        except MiraFSError as exc:
            console.print(f"[red]Error: {exc}[/red]")
            raise typer.Exit(1) from exc
        if json_output:
            typer.echo(json.dumps({"path": path, "content": content}, ensure_ascii=False))
        else:
            typer.echo(content)

    @fs_app.command("write")
    def fs_write(
        path: str = typer.Argument(..., help="Writable MiraFS path under /mem"),
        content: str = typer.Argument(..., help="Text content to write"),
        config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
        workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
        json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
    ) -> None:
        """Write text into /mem."""
        from mira.kernel.fs import MiraFS, MiraFSError

        _config_path, loaded = load_inspection_config(config, workspace)
        fs = MiraFS(workspace=loaded.workspace_path)
        try:
            node = fs.write_text(path, content)
        except MiraFSError as exc:
            console.print(f"[red]Error: {exc}[/red]")
            raise typer.Exit(1) from exc
        payload = {"path": node.virtual_path, "physical_path": str(node.physical_path)}
        if json_output:
            typer.echo(json.dumps(payload, ensure_ascii=False))
        else:
            console.print(f"[green]Wrote[/green] {node.virtual_path}")

    @app.command("ps")
    def process_list(
        config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
        workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
        json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
    ) -> None:
        """List persisted agent process snapshots from sessions."""
        from mira.session.manager import SessionManager

        _config_path, loaded = load_inspection_config(config, workspace)
        sessions = SessionManager(loaded.workspace_path)
        processes: list[dict[str, Any]] = []
        for info in sessions.list_sessions():
            key = info.get("key")
            if not isinstance(key, str):
                continue
            metadata = sessions.read_session_metadata(key)
            raw = (metadata or {}).get("metadata", {}).get("agent_process")
            if isinstance(raw, dict):
                process = dict(raw)
                process["session_key"] = key
                processes.append(process)
        if json_output:
            typer.echo(json.dumps({"processes": processes}, ensure_ascii=False))
            return
        if not processes:
            console.print("[dim]No persisted agent process snapshots.[/dim]")
            return
        table = Table("PID", "Status", "User", "Model", "Session", "Goal")
        for process in processes:
            table.add_row(
                str(process.get("pid") or ""),
                str(process.get("status") or ""),
                str(process.get("user") or ""),
                str(process.get("model_hint") or ""),
                str(process.get("session_key") or ""),
                str(process.get("goal") or "")[:80],
            )
        console.print(table)

    @app.command("think-plan")
    def think_plan(
        message: str = typer.Argument(..., help="Prompt/message to plan"),
        model: str = typer.Option("local/default", "--model", help="Runtime model id"),
        provider: str = typer.Option("local", "--provider", help="Runtime provider id"),
        policy: str = typer.Option("balanced", "--policy", help="balanced, fastest, cheapest, highest_quality"),
        caps: list[str] | None = typer.Option(None, "--cap", help="Capability: reasoning or tools"),
        context_window: int = typer.Option(128_000, "--context-window", help="Runtime context window"),
        p50_latency_ms: int = typer.Option(1000, "--latency-ms", help="Runtime p50 latency"),
        quality_score: float = typer.Option(0.5, "--quality", help="Runtime quality score"),
        input_tokens: int = typer.Option(0, "--input-tokens", help="Estimated input tokens"),
        output_tokens: int = typer.Option(0, "--output-tokens", help="Estimated output tokens"),
        max_cost_usd: float | None = typer.Option(None, "--max-cost", help="Maximum request cost"),
        json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
    ) -> None:
        """Plan a /bin/think request against one candidate runtime."""
        from mira.kernel.hypervisor import (
            ContextScheduler,
            RuntimeCandidate,
            ThinkCaps,
            ThinkRequest,
        )

        requested_caps = ThinkCaps.NONE
        for cap in caps or []:
            normalized = cap.strip().lower()
            if normalized == "reasoning":
                requested_caps |= ThinkCaps.REASONING
            elif normalized == "tools":
                requested_caps |= ThinkCaps.TOOLS
            else:
                console.print(f"[red]Error: unknown cap {cap!r}[/red]")
                raise typer.Exit(1)
        candidate = RuntimeCandidate(
            id=f"{provider}:{model}",
            provider=provider,
            model=model,
            context_window_tokens=context_window,
            p50_latency_ms=p50_latency_ms,
            quality_score=quality_score,
            supports_reasoning=bool(requested_caps & ThinkCaps.REASONING),
            supports_tools=True,
        )
        request = ThinkRequest(
            messages=[{"role": "user", "content": message}],
            caps=requested_caps,
            max_cost_usd=max_cost_usd,
            estimated_input_tokens=input_tokens,
            estimated_output_tokens=output_tokens,
        )
        try:
            plan = ContextScheduler(policy=policy).plan(request, [candidate])  # type: ignore[arg-type]
        except (KeyError, ValueError, RuntimeError) as exc:
            console.print(f"[red]Error: {exc}[/red]")
            raise typer.Exit(1) from exc
        payload = {
            "command": plan.command,
            "policy": plan.policy,
            "runtime": {
                "id": plan.runtime.id,
                "provider": plan.runtime.provider,
                "model": plan.runtime.model,
            },
            "estimated_cost_usd": plan.estimated_cost_usd,
            "score": plan.score,
        }
        if json_output:
            typer.echo(json.dumps(payload, ensure_ascii=False))
        else:
            console.print(json.dumps(payload, indent=2, ensure_ascii=False))
