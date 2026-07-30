import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from typer.testing import CliRunner

from mira.cli.commands import app
from mira.config.loader import save_config
from mira.config.schema import Config
from mira.session.manager import Session, SessionManager

runner = CliRunner()


def _config_file(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    (workspace / "memory").mkdir(parents=True)
    (workspace / "sessions").mkdir(parents=True)
    config = Config()
    config.agents.defaults.workspace = str(workspace)
    config.providers.openai.api_key = "sk-test"
    path = tmp_path / "config.json"
    save_config(config, path)
    return path


def test_boot_check_only_outputs_json(tmp_path: Path) -> None:
    config_path = _config_file(tmp_path)

    result = runner.invoke(app, ["boot", "--config", str(config_path), "--check-only", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["ok"] is True
    assert payload["profile"] == "engineering"
    assert {check["id"] for check in payload["checks"]} >= {
        "runtime.python",
        "storage.mounts",
        "providers.configured",
        "skills.scan",
        "scheduler.policy",
        "network.ssrf_guard",
        "runlevel.profile",
    }


def test_boot_starts_gateway_after_successful_post(tmp_path: Path) -> None:
    config_path = _config_file(tmp_path)
    calls = []

    def _fake_run_gateway(config: Config, **kwargs: object) -> None:
        calls.append((config, kwargs))

    with patch("mira.cli.commands._run_gateway", side_effect=_fake_run_gateway):
        result = runner.invoke(app, ["boot", "--config", str(config_path), "--profile", "desktop"])

    assert result.exit_code == 0
    assert calls
    assert calls[0][1]["webui_runtime_surface"] == "desktop"


def test_shutdown_outputs_json_and_stops_gateway(tmp_path: Path) -> None:
    config_path = _config_file(tmp_path)
    stops = []

    class _Runtime:
        def __init__(self, **_kwargs: object) -> None:
            self.state_path = tmp_path / "gateway.json"
            self.log_path = tmp_path / "gateway.log"

        def status(self) -> SimpleNamespace:
            return SimpleNamespace(
                running=True,
                pid=12345,
                state_path=self.state_path,
                log_path=self.log_path,
            )

        def stop(self, *, timeout_s: int) -> SimpleNamespace:
            stops.append(timeout_s)
            return SimpleNamespace(ok=True, message="gateway_stopped")

    with patch("mira.gateway.GatewayRuntime", _Runtime):
        result = runner.invoke(
            app,
            ["shutdown", "--config", str(config_path), "--timeout", "7", "--json"],
        )

    assert result.exit_code == 0
    assert stops == [7]
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["ok"] is True
    assert {step["id"] for step in payload["steps"]} == {
        "gateway.inspect",
        "gateway.drain",
        "storage.snapshot",
    }


def test_shutdown_treats_not_running_as_clean(tmp_path: Path) -> None:
    config_path = _config_file(tmp_path)

    class _Runtime:
        def __init__(self, **_kwargs: object) -> None:
            self.state_path = tmp_path / "gateway.json"
            self.log_path = tmp_path / "gateway.log"

        def status(self) -> SimpleNamespace:
            return SimpleNamespace(
                running=False,
                pid=None,
                state_path=self.state_path,
                log_path=self.log_path,
            )

    with patch("mira.gateway.GatewayRuntime", _Runtime):
        result = runner.invoke(app, ["shutdown", "--config", str(config_path), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["ok"] is True
    assert [step["id"] for step in payload["steps"]] == [
        "gateway.inspect",
        "storage.snapshot",
    ]


def test_fs_cli_writes_reads_and_lists_mem(tmp_path: Path) -> None:
    config_path = _config_file(tmp_path)

    write = runner.invoke(
        app,
        ["fs", "write", "/mem/notes/a.md", "hello", "--config", str(config_path), "--json"],
    )
    assert write.exit_code == 0
    written = json.loads(write.stdout.strip().splitlines()[-1])
    assert written["path"] == "/mem/notes/a.md"

    read = runner.invoke(app, ["fs", "read", "/mem/notes/a.md", "--config", str(config_path), "--json"])
    assert read.exit_code == 0
    payload = json.loads(read.stdout.strip().splitlines()[-1])
    assert payload["content"] == "hello"

    listed = runner.invoke(app, ["fs", "ls", "/mem/notes", "--config", str(config_path), "--json"])
    assert listed.exit_code == 0
    assert json.loads(listed.stdout.strip().splitlines()[-1])["entries"] == ["a.md"]


def test_ps_cli_lists_persisted_agent_process_snapshots(tmp_path: Path) -> None:
    config_path = _config_file(tmp_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    workspace = Path(config["agents"]["defaults"]["workspace"])
    manager = SessionManager(workspace)
    session = Session(
        key="cli:process",
        metadata={
            "agent_process": {
                "pid": "agent-0001",
                "status": "terminated",
                "user": "king",
                "model_hint": "test-model",
                "goal": "run task",
            }
        },
    )
    manager.save(session, fsync=True)

    result = runner.invoke(app, ["ps", "--config", str(config_path), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["processes"][0]["pid"] == "agent-0001"
    assert payload["processes"][0]["session_key"] == "cli:process"


def test_think_plan_cli_outputs_bin_think_plan() -> None:
    result = runner.invoke(
        app,
        [
            "think-plan",
            "hello",
            "--provider",
            "openai",
            "--model",
            "gpt-test",
            "--cap",
            "reasoning",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["command"] == "/bin/think"
    assert payload["runtime"]["id"] == "openai:gpt-test"
