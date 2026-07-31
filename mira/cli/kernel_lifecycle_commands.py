"""Kernel lifecycle/status CLI command registration."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import typer
from rich.console import Console

from mira import __app_name__, __logo__
from mira.config.schema import Config


def register_kernel_lifecycle_commands(
    app: typer.Typer,
    *,
    console: Console,
    load_inspection_config: Callable[..., tuple[Path, Config]],
    run_gateway: Callable[..., None],
    model_display: Callable[[Config], tuple[str, str]],
) -> None:
    @app.command()
    def boot(
        config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
        workspace: str | None = typer.Option(
            None,
            "--workspace",
            "-w",
            help="Workspace directory",
        ),
        profile: str = typer.Option(
            "engineering",
            "--profile",
            help="Boot runlevel: lite, engineering, desktop, or embedded",
        ),
        check_only: bool = typer.Option(
            False,
            "--check-only",
            help="Run POST checks and exit without starting a long-running process",
        ),
        json_output: bool = typer.Option(False, "--json", help="Emit machine-readable POST JSON"),
    ) -> None:
        """Run Mira boot POST checks, then start the selected runlevel."""
        from mira.kernel.boot import BootProtocol

        _config_path, loaded = load_inspection_config(config=config, workspace=workspace)
        try:
            report = BootProtocol(loaded, workspace=loaded.workspace_path).run_post(
                profile=profile
            )
        except ValueError as exc:
            console.print(f"[red]Error: {exc}[/red]")
            raise typer.Exit(1) from exc

        if json_output:
            typer.echo(json.dumps(report.to_dict(), ensure_ascii=False))
        else:
            status = "OK" if report.ok else "FAIL"
            color = "green" if report.ok else "red"
            console.print(
                f"[{color}][{status}][/{color}] Mira Kernel v{report.version} boot POST"
            )
            console.print(f"[dim]Profile: {report.profile}[/dim]")
            for check in report.checks:
                check_color = {
                    "ok": "green",
                    "warning": "yellow",
                    "error": "red",
                }[check.status]
                console.print(
                    f"[{check_color}][{check.status.upper()}][/{check_color}] "
                    f"{check.message}"
                )
                if check.detail:
                    console.print(f"[dim]  {check.detail}[/dim]")
            console.print(f"[dim]Gateway target: {report.gateway_url}[/dim]")

        if not report.ok:
            raise typer.Exit(1)
        if check_only:
            return

        if report.profile in {"lite", "embedded"}:
            console.print(
                "[yellow]Boot POST passed; this runlevel has no foreground gateway target yet.[/yellow]"
            )
            return

        run_gateway(
            loaded,
            port=loaded.gateway.port,
            webui_runtime_surface="desktop" if report.profile == "desktop" else "browser",
        )

    @app.command()
    def shutdown(
        config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
        workspace: str | None = typer.Option(
            None,
            "--workspace",
            "-w",
            help="Workspace directory",
        ),
        timeout: int = typer.Option(20, "--timeout", help="Graceful shutdown timeout in seconds"),
        json_output: bool = typer.Option(
            False,
            "--json",
            help="Emit machine-readable shutdown JSON",
        ),
    ) -> None:
        """Gracefully stop the managed Mira gateway and report lifecycle state."""
        from mira.gateway import GatewayRuntime, GatewayRuntimePaths
        from mira.kernel.boot import ShutdownProtocol

        config_path, loaded = load_inspection_config(config=config, workspace=workspace)
        runtime = GatewayRuntime(
            paths=GatewayRuntimePaths.for_instance(
                workspace=str(loaded.workspace_path),
                config_path=str(config_path),
            )
        )
        report = ShutdownProtocol(runtime, workspace=loaded.workspace_path).run(
            timeout_s=timeout
        )

        if json_output:
            typer.echo(json.dumps(report.to_dict(), ensure_ascii=False))
        else:
            status = "OK" if report.ok else "FAIL"
            color = "green" if report.ok else "red"
            console.print(
                f"[{color}][{status}][/{color}] Mira Kernel v{report.version} shutdown"
            )
            for step in report.steps:
                step_color = {
                    "ok": "green",
                    "warning": "yellow",
                    "error": "red",
                }[step.status]
                console.print(
                    f"[{step_color}][{step.status.upper()}][/{step_color}] {step.message}"
                )
                if step.detail:
                    console.print(f"[dim]  {step.detail}[/dim]")

        if not report.ok:
            raise typer.Exit(1)

    @app.command()
    def doctor(
        config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
        workspace: str | None = typer.Option(
            None,
            "--workspace",
            "-w",
            help="Workspace directory",
        ),
        profile: str = typer.Option(
            "standard",
            "--profile",
            help="Doctor profile: standard or lightweight",
        ),
        fix: bool = typer.Option(False, "--fix", help="Apply safe automatic repairs"),
        dry_run: bool = typer.Option(
            False,
            "--dry-run",
            help="Report repairs without changing files",
        ),
    ) -> None:
        """Diagnose and repair common local kernel problems."""
        from mira.kernel.doctor import KernelDoctor

        config_path = Path(config).expanduser() if config else Path.home() / ".mira" / "config.json"
        workspace_path = Path(workspace).expanduser() if workspace else None
        findings = KernelDoctor(config_path=config_path, workspace=workspace_path).run(
            profile=profile,
            fix=fix,
            dry_run=dry_run,
        )
        if not findings:
            console.print("[green]Mira doctor found no local kernel problems.[/green]")
            return
        for finding in findings:
            status = "fixed" if finding.repaired else ("fixable" if finding.repairable else "manual")
            color = "green" if finding.repaired else (
                "yellow" if finding.severity == "warning" else "red"
            )
            console.print(f"[{color}]{finding.id}[/{color}] {status}: {finding.message}")
            if finding.detail:
                console.print(f"[dim]  {finding.detail}[/dim]")
        if any(f.repairable and not f.repaired for f in findings) and not fix:
            console.print("[dim]Run with --fix to apply safe automatic repairs.[/dim]")

    @app.command()
    def status(
        config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
        workspace: str | None = typer.Option(
            None,
            "--workspace",
            "-w",
            help="Workspace directory",
        ),
    ) -> None:
        """Show Mira status."""
        config_path, loaded = load_inspection_config(config=config, workspace=workspace)
        workspace_path = loaded.workspace_path

        console.print(f"{__logo__} {__app_name__} Status\n")

        console.print(
            f"Config: {config_path} "
            f"{'[green][/green]' if config_path.exists() else '[red][/red]'}"
        )
        console.print(
            f"Workspace: {workspace_path} "
            f"{'[green][/green]' if workspace_path.exists() else '[red][/red]'}"
        )

        if config_path.exists():
            from mira.providers.registry import PROVIDERS

            model, preset_tag = model_display(loaded)
            console.print(f"Model: {model}{preset_tag}")

            for spec in PROVIDERS:
                provider = getattr(loaded.providers, spec.name, None)
                if provider is None:
                    continue
                if spec.is_oauth:
                    console.print(f"{spec.label}: [green] (OAuth)[/green]")
                elif spec.is_local:
                    if provider.api_base:
                        console.print(f"{spec.label}: [green] {provider.api_base}[/green]")
                    else:
                        console.print(f"{spec.label}: [dim]not set[/dim]")
                else:
                    has_key = bool(provider.api_key)
                    console.print(
                        f"{spec.label}: {'[green][/green]' if has_key else '[dim]not set[/dim]'}"
                    )
