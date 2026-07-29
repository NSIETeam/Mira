"""Mira kernel doctor checks and safe repairs."""

from __future__ import annotations

import socket
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from mira.config.loader import load_config, save_config
from mira.config.schema import Config
from mira.utils.helpers import sync_workspace_templates


@dataclass
class DoctorFinding:
    id: str
    severity: str
    message: str
    repairable: bool = False
    repaired: bool = False
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class KernelDoctor:
    """Diagnose common local kernel problems and apply safe repairs."""

    def __init__(
        self,
        *,
        config_path: Path,
        workspace: Path | None = None,
        webui_port: int = 8765,
        gateway_port: int = 8766,
    ) -> None:
        self.config_path = config_path.expanduser()
        self.workspace_override = workspace.expanduser() if workspace is not None else None
        self.webui_port = webui_port
        self.gateway_port = gateway_port

    def run(self, *, fix: bool = False, dry_run: bool = False) -> list[DoctorFinding]:
        findings: list[DoctorFinding] = []
        config = self._check_config(findings, fix=fix, dry_run=dry_run)
        workspace = self.workspace_override or config.workspace_path
        self._check_workspace(findings, workspace, fix=fix, dry_run=dry_run)
        self._check_web_assets(findings)
        self._check_ports(findings)
        self._check_runtime(findings)
        self._check_stale_artifacts(findings, workspace, fix=fix, dry_run=dry_run)
        return findings

    def _check_config(
        self,
        findings: list[DoctorFinding],
        *,
        fix: bool,
        dry_run: bool,
    ) -> Config:
        if self.config_path.exists():
            try:
                return load_config(self.config_path)
            except Exception as exc:
                findings.append(DoctorFinding(
                    "config.invalid",
                    "error",
                    "config exists but cannot be loaded",
                    repairable=False,
                    detail=str(exc),
                ))
                return Config()
        repaired = False
        if fix and not dry_run:
            save_config(Config(), self.config_path)
            repaired = True
        findings.append(DoctorFinding(
            "config.missing",
            "warning",
            "config file is missing",
            repairable=True,
            repaired=repaired,
            detail=str(self.config_path),
        ))
        return Config()

    def _check_workspace(
        self,
        findings: list[DoctorFinding],
        workspace: Path,
        *,
        fix: bool,
        dry_run: bool,
    ) -> None:
        if workspace.exists():
            return
        repaired = False
        if fix and not dry_run:
            workspace.mkdir(parents=True, exist_ok=True)
            sync_workspace_templates(workspace, silent=True)
            repaired = True
        findings.append(DoctorFinding(
            "workspace.missing",
            "warning",
            "workspace directory is missing",
            repairable=True,
            repaired=repaired,
            detail=str(workspace),
        ))

    def _check_web_assets(self, findings: list[DoctorFinding]) -> None:
        index = Path(__file__).resolve().parents[1] / "web" / "dist" / "index.html"
        if index.exists():
            return
        findings.append(DoctorFinding(
            "webui.assets.missing",
            "warning",
            "bundled WebUI assets are missing; rebuild the WebUI bundle",
            repairable=False,
            detail=str(index),
        ))

    def _check_ports(self, findings: list[DoctorFinding]) -> None:
        for label, port in (("webui", self.webui_port), ("gateway", self.gateway_port)):
            if not _port_open("127.0.0.1", port):
                continue
            findings.append(DoctorFinding(
                f"port.{label}.busy",
                "warning",
                f"{label} port is already in use",
                repairable=False,
                detail=f"127.0.0.1:{port}",
            ))

    def _check_runtime(self, findings: list[DoctorFinding]) -> None:
        if sys.version_info >= (3, 11):
            return
        findings.append(DoctorFinding(
            "runtime.python.unsupported",
            "error",
            "Python 3.11 or newer is required",
            repairable=False,
            detail=sys.version.split()[0],
        ))

    def _check_stale_artifacts(
        self,
        findings: list[DoctorFinding],
        workspace: Path,
        *,
        fix: bool,
        dry_run: bool,
    ) -> None:
        candidates: list[Path] = []
        for root_name in ("sessions", "memory"):
            root = workspace / root_name
            if not root.exists():
                continue
            for pattern in ("*.tmp", "*.lock"):
                candidates.extend(root.glob(pattern))
        if not candidates:
            return
        repaired = False
        if fix and not dry_run:
            for path in candidates:
                try:
                    path.unlink()
                    repaired = True
                except OSError:
                    pass
        findings.append(DoctorFinding(
            "artifacts.stale",
            "warning",
            "stale kernel temp/lock artifacts found",
            repairable=True,
            repaired=repaired,
            detail=", ".join(str(path) for path in candidates[:5]),
        ))


def _port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.15)
        return sock.connect_ex((host, port)) == 0
