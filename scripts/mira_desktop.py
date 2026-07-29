"""PyInstaller entrypoint for the Mira desktop app."""

from mira.cli.commands import desktop


if __name__ == "__main__":
    desktop()
