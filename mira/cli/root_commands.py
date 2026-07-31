"""Root Typer command registration for Mira CLI."""

from __future__ import annotations

from typing import Any

import typer


def register_root_commands(app: typer.Typer, ns: Any) -> None:
    """Register root commands and expose them on ``ns`` for compatibility."""

    @app.command()
    def onboard(
        workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
        config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
        wizard: bool = typer.Option(False, "--wizard", help="Use interactive wizard"),
        non_interactive_refresh: bool = typer.Option(
            False,
            "--refresh",
            help="Refresh config, preserving existing settings without prompting",
        ),
    ):
        """Initialize Mira configuration and workspace."""
        ns.run_onboard_command(
            workspace=workspace,
            config=config,
            wizard=wizard,
            non_interactive_refresh=non_interactive_refresh,
            onboard_plugins=ns._onboard_plugins,
            sync_workspace_templates=ns.sync_workspace_templates,
            get_workspace_path=ns.get_workspace_path,
        )

    @app.command()
    def trigger(
        trigger_id: str = typer.Argument(..., help="Trigger ID returned by /trigger"),
        message: str | None = typer.Argument(
            None,
            help="Message to deliver; stdin is used when omitted",
        ),
        workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
        config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
    ):
        """Deliver a local trigger message to its bound chat session."""
        ns.run_trigger_command(
            trigger_id=trigger_id,
            message=message,
            workspace=workspace,
            config_path_arg=config,
            console=ns.console,
            load_runtime_config=lambda config_path, workspace_path: ns._load_runtime_config(
                config_path,
                workspace_path,
            ),
        )

    @app.command()
    def serve(
        port: int | None = typer.Option(None, "--port", "-p", help="API server port"),
        host: str | None = typer.Option(None, "--host", "-H", help="Bind address"),
        timeout: float | None = typer.Option(
            None,
            "--timeout",
            "-t",
            help="Per-request timeout (seconds)",
        ),
        verbose: bool = typer.Option(False, "--verbose", "-v", help="Show Mira runtime logs"),
        workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
        config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
    ):
        """Start the OpenAI-compatible API server (/v1/chat/completions)."""
        ns.run_serve_command(
            port=port,
            host=host,
            timeout=timeout,
            verbose=verbose,
            workspace=workspace,
            config_path_arg=config,
            console=ns.console,
            deps=ns._root_deps.serve(ns),
        )

    @app.command()
    def webui(
        port: int | None = typer.Option(None, "--port", "-p", help="WebUI port"),
        gateway_port: int | None = typer.Option(
            None,
            "--gateway-port",
            help="Gateway health port",
        ),
        workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
        config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
        background: bool = typer.Option(
            False,
            "--background",
            help="Keep the gateway running after this command exits",
        ),
        no_open: bool = typer.Option(False, "--no-open", help="Do not open a browser"),
        yes: bool = typer.Option(
            False,
            "--yes",
            "-y",
            help="Apply safe local WebUI defaults without prompting",
        ),
        user: str | None = typer.Option(
            None,
            "--user",
            help="Temporary WebUI user account name for shared gateway use",
        ),
        group: str | None = typer.Option(
            None,
            "--group",
            help="Temporary WebUI project group; users in the same group share memory",
        ),
    ) -> None:
        """Prepare the local WebUI, start the gateway, and open the browser workbench."""
        ns.run_webui_command(
            port=port,
            gateway_port=gateway_port,
            workspace=workspace,
            config=config,
            background=background,
            no_open=no_open,
            yes=yes,
            user=user,
            group=group,
            deps=ns._root_deps.webui(ns),
        )

    @app.command()
    def desktop(
        port: int | None = typer.Option(None, "--port", "-p", help="WebUI port"),
        gateway_port: int | None = typer.Option(
            None,
            "--gateway-port",
            help="Gateway health port",
        ),
        workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
        config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
        yes: bool = typer.Option(
            False,
            "--yes",
            "-y",
            help="Apply safe local desktop defaults without prompting",
        ),
        debug: bool = typer.Option(
            False,
            "--debug",
            help="Open the native shell with WebView debug mode",
        ),
        stop_on_close: bool = typer.Option(
            True,
            "--stop-on-close/--keep-running",
            help="Stop the gateway started by this window when the native shell closes",
        ),
    ) -> None:
        """Launch the Mira workbench inside a native desktop window."""
        ns.run_desktop_command(
            port=port,
            gateway_port=gateway_port,
            workspace=workspace,
            config=config,
            yes=yes,
            debug=debug,
            stop_on_close=stop_on_close,
            deps=ns._root_deps.desktop(ns),
        )

    @app.command()
    def agent(
        message: str = typer.Option(None, "--message", "-m", help="Message to send to the agent"),
        session_id: str = typer.Option("cli:direct", "--session", "-s", help="Session ID"),
        workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
        config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
        markdown: bool = typer.Option(
            True,
            "--markdown/--no-markdown",
            help="Render assistant output as Markdown",
        ),
        logs: bool = typer.Option(
            False,
            "--logs/--no-logs",
            help="Show Mira runtime logs during chat",
        ),
    ):
        """Interact with the agent directly."""
        ns.run_agent_command(
            message=message,
            session_id=session_id,
            workspace=workspace,
            config_path_arg=config,
            markdown=markdown,
            logs=logs,
            deps=ns._root_deps.agent(ns),
        )

    ns.onboard = onboard
    ns.trigger = trigger
    ns.serve = serve
    ns.webui = webui
    ns.desktop = desktop
    ns.agent = agent
