"""System configuration commands registered by the top-level CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer
from rich.console import Console


def _load_mutable_config(config_path: str | None) -> tuple[Path, Any]:
    from mira.config.loader import get_config_path, load_config, set_config_path

    resolved_config_path = Path(config_path).expanduser().resolve() if config_path else None
    if resolved_config_path is not None:
        set_config_path(resolved_config_path)
    resolved_config_path = resolved_config_path or get_config_path()
    return resolved_config_path, load_config(resolved_config_path)


def register_system_commands(app: typer.Typer, *, console: Console) -> None:
    """Register kernel module and security policy inspection commands."""
    modules_app = typer.Typer(help="Inspect and configure Mira kernel modules")
    app.add_typer(modules_app, name="modules")

    @modules_app.command("list")
    def modules_list(
        config_path: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
        json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON"),
    ) -> None:
        """List Linux-style mountable Mira modules."""
        from mira.kernel.module_registry import module_summary
        from mira.kernel.profile import get_profile

        _config_path, loaded = _load_mutable_config(config_path)
        summary = module_summary(get_profile(loaded.kernel.profile_name), loaded.modules)
        if json_output:
            typer.echo(json.dumps(summary, indent=2, ensure_ascii=False))
            return
        console.print(
            f"Mira modules: {summary['enabled']}/{summary['total']} enabled "
            f"~{summary['estimated_memory_cost_mb']} MB"
        )
        for row in summary["modules"]:
            marker = "on" if row["status"] == "enabled" else "off"
            console.print(
                f"{marker:>3} {row['name']} [{row['kind']}] "
                f"lazy={str(row['lazy']).lower()} cost={row['memory_cost_mb']}MB"
            )

    @modules_app.command("enable")
    def modules_enable(
        name: str = typer.Argument(..., help="Module name"),
        config_path: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
    ) -> None:
        """Enable a kernel module in config."""
        from mira.config.loader import save_config
        from mira.config.schema import ModuleConfig

        resolved_config_path, loaded = _load_mutable_config(config_path)
        current = loaded.modules.registry.get(name) or ModuleConfig()
        current.enabled = True
        loaded.modules.registry[name] = current
        save_config(loaded, resolved_config_path)
        console.print(f"[green]Enabled module '{name}'[/green] in {resolved_config_path}")

    @modules_app.command("disable")
    def modules_disable(
        name: str = typer.Argument(..., help="Module name"),
        config_path: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
    ) -> None:
        """Disable a kernel module in config."""
        from mira.config.loader import save_config
        from mira.config.schema import ModuleConfig

        resolved_config_path, loaded = _load_mutable_config(config_path)
        current = loaded.modules.registry.get(name) or ModuleConfig()
        current.enabled = False
        loaded.modules.registry[name] = current
        save_config(loaded, resolved_config_path)
        console.print(f"[green]Disabled module '{name}'[/green] in {resolved_config_path}")

    policy_app = typer.Typer(help="Inspect Mira Linux-style user/group policy")
    app.add_typer(policy_app, name="policy")

    @policy_app.command("show")
    def policy_show(
        user: str | None = typer.Option(None, "--user", help="User id"),
        group: str | None = typer.Option(None, "--group", help="Group id"),
        config_path: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
    ) -> None:
        """Show the effective user/group policy."""
        from mira.security.policy import effective_principal_policy

        _config_path, loaded = _load_mutable_config(config_path)
        policy = effective_principal_policy(loaded.security, user_id=user, group_id=group)
        typer.echo(json.dumps(policy.to_dict(), indent=2, ensure_ascii=False))
