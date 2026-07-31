from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_unix_installer_dry_run_uses_nsiteam_distribution() -> None:
    result = subprocess.run(
        ["sh", str(ROOT / "scripts" / "install.sh"), "--dry-run"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    output = result.stdout
    assert "mira-ai" in output
    assert "uv tool install" in output or "pipx install" in output or "pip install" in output
    assert "HKUDS/mira" not in output


def test_unix_dev_installer_dry_run_uses_nsiteam_repository() -> None:
    result = subprocess.run(
        ["sh", str(ROOT / "scripts" / "install.sh"), "--dev", "--dry-run"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    assert "https://github.com/NSIETeam/Mira/archive/refs/heads/main.zip" in result.stdout
    assert "HKUDS/mira" not in result.stdout


def test_install_docs_do_not_point_stable_paths_at_unrelated_mira_package() -> None:
    checked = [ROOT / "README.md", ROOT / "docs" / "quick-start.md", ROOT / "docs" / "troubleshooting.md"]
    text = "\n".join(path.read_text(encoding="utf-8") for path in checked)
    forbidden = ["uv tool install mira\n", "pip install mira\n", "python -m pip install mira\n"]
    for command in forbidden:
        assert command not in text
    assert "mira-ai" in text
    assert "HKUDS/mira" not in text
