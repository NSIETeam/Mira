"""Mira boot protocol and POST checks."""

from __future__ import annotations

import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

from mira import __version__
from mira.agent.skills import SkillsLoader
from mira.config.schema import Config, ProviderConfig
from mira.security.network import configure_ssrf_whitelist, validate_url_target

BootProfile = Literal["lite", "engineering", "desktop", "embedded"]
BootStatus = Literal["ok", "warning", "error"]


@dataclass(slots=True)
class BootCheck:
    """One POST check result."""

    id: str
    status: BootStatus
    message: str
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BootReport:
    """Boot POST report for CLI, Docker smoke tests, and future native launchers."""

    version: str
    profile: BootProfile
    gateway_url: str
    checks: list[BootCheck] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(check.status != "error" for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["ok"] = self.ok
        return payload


class BootProtocol:
    """POST sequence for Mira runlevels without owning the long-running process."""

    _VALID_PROFILES: set[str] = {"lite", "engineering", "desktop", "embedded"}

    def __init__(self, config: Config, *, workspace: Path | None = None) -> None:
        self.config = config
        self.workspace = workspace or config.workspace_path

    def run_post(self, *, profile: str = "engineering") -> BootReport:
        boot_profile = self._normalize_profile(profile)
        checks: list[BootCheck] = [
            self._check_runtime(),
            self._check_storage(),
            self._check_providers(),
            self._check_skills(),
            self._check_scheduler(),
            self._check_network_guard(),
            self._check_runlevel(boot_profile),
        ]
        return BootReport(
            version=__version__,
            profile=boot_profile,
            gateway_url=f"http://{self.config.gateway.host}:{self.config.gateway.port}",
            checks=checks,
        )

    def _normalize_profile(self, profile: str) -> BootProfile:
        normalized = profile.strip().lower().replace("_", "-")
        aliases = {
            "standard": "engineering",
            "server": "engineering",
            "lightweight": "lite",
        }
        normalized = aliases.get(normalized, normalized)
        if normalized not in self._VALID_PROFILES:
            raise ValueError(
                f"unknown boot profile {profile!r}; expected lite, engineering, desktop, or embedded"
            )
        return cast(BootProfile, normalized)

    def _check_runtime(self) -> BootCheck:
        if sys.version_info >= (3, 11):
            return BootCheck("runtime.python", "ok", f"Python {sys.version.split()[0]} ready")
        return BootCheck(
            "runtime.python",
            "error",
            "Python 3.11 or newer is required",
            detail=sys.version.split()[0],
        )

    def _check_storage(self) -> BootCheck:
        memory_dir = self.workspace / "memory"
        sessions_dir = self.workspace / "sessions"
        missing = [str(path) for path in (memory_dir, sessions_dir) if not path.exists()]
        if missing:
            return BootCheck(
                "storage.mounts",
                "warning",
                "memory/context directories are not initialized yet",
                detail=", ".join(missing),
            )
        if not _is_writable(memory_dir) or not _is_writable(sessions_dir):
            return BootCheck(
                "storage.mounts",
                "error",
                "memory/context directories are not writable",
                detail=str(self.workspace),
            )
        return BootCheck("storage.mounts", "ok", "/mem and /ctx storage are writable")

    def _check_providers(self) -> BootCheck:
        configured = _configured_provider_names(self.config.providers)
        if configured:
            return BootCheck(
                "providers.configured",
                "ok",
                f"{len(configured)} provider(s) configured",
                detail=", ".join(configured[:8]),
            )
        return BootCheck(
            "providers.configured",
            "warning",
            "no API-backed model provider is configured",
            detail="set providers.*.api_key or use a local/direct provider before production boot",
        )

    def _check_skills(self) -> BootCheck:
        loader = SkillsLoader(
            self.workspace,
            disabled_skills=set(self.config.agents.defaults.disabled_skills),
        )
        skills = loader.list_skills(filter_unavailable=True)
        if not skills:
            return BootCheck("skills.scan", "warning", "no available skills found")
        return BootCheck("skills.scan", "ok", f"{len(skills)} skills available")

    def _check_scheduler(self) -> BootCheck:
        max_subagents = self.config.agents.defaults.max_concurrent_subagents
        heartbeat = self.config.gateway.heartbeat
        detail = f"subagents={max_subagents}, heartbeat={'on' if heartbeat.enabled else 'off'}"
        return BootCheck("scheduler.policy", "ok", "scheduler defaults loaded", detail=detail)

    def _check_network_guard(self) -> BootCheck:
        configure_ssrf_whitelist(self.config.tools.ssrf_whitelist)
        ok, reason = validate_url_target("http://169.254.169.254/latest/meta-data")
        if ok:
            return BootCheck(
                "network.ssrf_guard",
                "error",
                "SSRF guard allowed cloud metadata target",
            )
        detail = f"blocked metadata target: {reason}"
        if self.config.tools.ssrf_whitelist:
            detail += f"; whitelist={len(self.config.tools.ssrf_whitelist)} CIDR(s)"
        return BootCheck("network.ssrf_guard", "ok", "SSRF guard active", detail=detail)

    def _check_runlevel(self, profile: BootProfile) -> BootCheck:
        if profile == "lite":
            target = "agent loop only"
        elif profile == "engineering":
            target = "gateway + WebUI + channels"
        elif profile == "desktop":
            target = "native desktop shell + gateway"
        else:
            target = "embedded host contract"
        return BootCheck("runlevel.profile", "ok", f"{profile} runlevel selected", detail=target)


def _is_writable(path: Path) -> bool:
    probe = path / ".mira-boot-write-test"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError:
        return False
    return True


def _configured_provider_names(providers: Any) -> list[str]:
    names: list[str] = []
    for name, value in providers:
        if isinstance(value, ProviderConfig) and (
            value.api_key or value.api_base or _provider_is_direct(name)
        ):
            names.append(str(name))
    for name, value in (providers.model_extra or {}).items():
        if isinstance(value, ProviderConfig) and (value.api_key or value.api_base):
            names.append(str(name))
    return sorted(set(names))


def _provider_is_direct(name: str) -> bool:
    return name in {"github_copilot", "openai_codex"}
