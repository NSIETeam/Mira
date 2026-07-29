"""PyInstaller entrypoint for the Mira desktop app."""

from mira.cli.commands import desktop


if __name__ == "__main__":
    desktop(
        port=None,
        gateway_port=None,
        workspace=None,
        config=None,
        yes=False,
        debug=False,
        stop_on_close=True,
    )
