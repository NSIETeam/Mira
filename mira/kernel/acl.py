"""Capability ACL primitives for agent processes."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

CapabilityDecision = Literal["allow", "deny", "approval_required"]


@dataclass(frozen=True, slots=True)
class CapabilityRule:
    """One path-aware capability rule."""

    capability: str
    allow: tuple[str, ...] = ()
    deny: tuple[str, ...] = ()
    require_approval: bool = False


@dataclass(frozen=True, slots=True)
class CapabilityRequest:
    """Requested operation against a capability namespace."""

    agent: str
    capability: str
    target: str


@dataclass(frozen=True, slots=True)
class CapabilityAuditEvent:
    """Audit entry for denied or approval-gated operations."""

    agent: str
    capability: str
    target: str
    decision: CapabilityDecision
    reason: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True, slots=True)
class CapabilityResult:
    """Capability policy evaluation result."""

    decision: CapabilityDecision
    reason: str = ""

    @property
    def allowed(self) -> bool:
        return self.decision == "allow"


class CapabilityPolicy:
    """Path-aware capability policy for one agent."""

    def __init__(self, *, agent: str, rules: tuple[CapabilityRule, ...]) -> None:
        self.agent = agent
        self.rules = {rule.capability: rule for rule in rules}
        self.audit_log: list[CapabilityAuditEvent] = []

    def evaluate(self, request: CapabilityRequest) -> CapabilityResult:
        rule = self.rules.get(request.capability)
        if request.agent != self.agent:
            result = CapabilityResult("deny", "request agent does not match policy owner")
        elif rule is None:
            result = CapabilityResult("deny", "capability is not granted")
        elif _matches_any(request.target, rule.deny):
            result = CapabilityResult("deny", "target matches deny rule")
        elif rule.allow and not _matches_any(request.target, rule.allow):
            result = CapabilityResult("deny", "target is outside allow list")
        elif rule.require_approval:
            result = CapabilityResult("approval_required", "human approval is required")
        else:
            result = CapabilityResult("allow")

        if result.decision != "allow":
            self.audit_log.append(
                CapabilityAuditEvent(
                    agent=request.agent,
                    capability=request.capability,
                    target=request.target,
                    decision=result.decision,
                    reason=result.reason,
                )
            )
        return result

    def derive_child(
        self,
        *,
        agent: str,
        requested_caps: frozenset[str] | None = None,
    ) -> "CapabilityPolicy":
        """Create a child policy that can only lose capabilities."""
        allowed = requested_caps if requested_caps is not None else frozenset(self.rules)
        rules = tuple(rule for name, rule in self.rules.items() if name in allowed)
        return CapabilityPolicy(agent=agent, rules=rules)


def _matches_any(target: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(target, pattern) for pattern in patterns)
