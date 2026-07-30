from pathlib import Path

from mira.config.schema import Config
from mira.kernel.boot import BootProtocol


def _workspace(root: Path) -> Path:
    workspace = root / "workspace"
    (workspace / "memory").mkdir(parents=True)
    (workspace / "sessions").mkdir(parents=True)
    return workspace


def test_boot_post_reports_core_checks(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    config = Config()
    config.agents.defaults.workspace = str(workspace)
    config.providers.openai.api_key = "sk-test"

    report = BootProtocol(config).run_post(profile="engineering")

    assert report.ok is True
    assert report.profile == "engineering"
    checks = {check.id: check for check in report.checks}
    assert checks["runtime.python"].status == "ok"
    assert checks["storage.mounts"].status == "ok"
    assert checks["providers.configured"].status == "ok"
    assert checks["skills.scan"].status == "ok"
    assert checks["scheduler.policy"].status == "ok"
    assert checks["network.ssrf_guard"].status == "ok"
    assert checks["runlevel.profile"].detail == "gateway + WebUI + channels"


def test_boot_post_accepts_profile_aliases(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    config = Config()
    config.agents.defaults.workspace = str(workspace)

    report = BootProtocol(config).run_post(profile="lightweight")

    assert report.profile == "lite"
    assert report.ok is True


def test_boot_post_rejects_unknown_profile(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    config = Config()
    config.agents.defaults.workspace = str(workspace)

    try:
        BootProtocol(config).run_post(profile="unknown")
    except ValueError as exc:
        assert "unknown boot profile" in str(exc)
    else:
        raise AssertionError("expected invalid boot profile to fail")
