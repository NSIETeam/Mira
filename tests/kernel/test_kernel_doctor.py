from __future__ import annotations

from mira.kernel.doctor import KernelDoctor


def test_doctor_dry_run_reports_missing_config_and_workspace(tmp_path):
    config_path = tmp_path / "config.json"
    workspace = tmp_path / "workspace"

    findings = KernelDoctor(config_path=config_path, workspace=workspace).run(dry_run=True)

    ids = {finding.id for finding in findings}
    assert "config.missing" in ids
    assert "workspace.missing" in ids
    assert not config_path.exists()
    assert not workspace.exists()


def test_doctor_fix_creates_config_workspace_and_removes_stale_artifacts(tmp_path):
    config_path = tmp_path / "config.json"
    workspace = tmp_path / "workspace"
    stale_dir = workspace / "sessions"
    stale_dir.mkdir(parents=True)
    stale = stale_dir / "old.tmp"
    stale.write_text("x", encoding="utf-8")

    findings = KernelDoctor(config_path=config_path, workspace=workspace).run(fix=True)

    ids = {finding.id for finding in findings}
    assert "config.missing" in ids
    assert "artifacts.stale" in ids
    assert config_path.exists()
    assert workspace.exists()
    assert not stale.exists()


def test_doctor_lightweight_profile_reports_python_launcher(tmp_path):
    config_path = tmp_path / "config.json"
    workspace = tmp_path / "workspace"

    findings = KernelDoctor(config_path=config_path, workspace=workspace).run(
        profile="lightweight",
        dry_run=True,
    )

    ids = {finding.id for finding in findings}
    assert "lightweight.launcher.python" in ids
    assert "release.signing.missing" in ids
