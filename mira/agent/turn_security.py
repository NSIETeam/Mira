"""Security metadata helpers for agent turns."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from mira.agent.tools.registry import ToolRegistry
from mira.security.policy import effective_principal_policy
from mira.session.manager import Session, SessionManager
from mira.webui.users import WEBUI_GROUP_METADATA_KEY, WEBUI_USER_METADATA_KEY


def tools_for_metadata(
    metadata: Mapping[str, Any] | None,
    *,
    tools: ToolRegistry,
    security_config: Any | None,
) -> ToolRegistry:
    """Return a per-principal filtered tool registry for turn metadata."""
    if not isinstance(metadata, Mapping):
        return tools
    user = metadata.get(WEBUI_USER_METADATA_KEY)
    if not isinstance(user, str) or user in ("", "default"):
        return tools
    policy = effective_principal_policy(
        security_config,
        user_id=user,
        group_id=metadata.get(WEBUI_GROUP_METADATA_KEY),
    )
    return tools.filtered_copy(exclude=set(policy.deny_tools))


def policy_for_metadata(
    metadata: Mapping[str, Any] | None,
    *,
    security_config: Any | None,
) -> Any | None:
    """Resolve the effective principal policy for turn metadata."""
    if not isinstance(metadata, Mapping):
        return None
    user = metadata.get(WEBUI_USER_METADATA_KEY)
    group = metadata.get(WEBUI_GROUP_METADATA_KEY)
    if not isinstance(user, str) or not user.strip():
        return None
    return effective_principal_policy(security_config, user_id=user, group_id=group)


def capability_policy_for_metadata(
    metadata: Mapping[str, Any] | None,
    *,
    sender_id: str | None,
) -> Any | None:
    """Build an agent capability policy from message metadata."""
    if not isinstance(metadata, Mapping):
        return None
    raw = metadata.get("capability_policy") or metadata.get("agent_capabilities")
    if not isinstance(raw, Mapping):
        return None
    from mira.kernel.acl import CapabilityPolicy, CapabilityRule

    rules: list[CapabilityRule] = []
    for capability, spec in raw.items():
        if not isinstance(capability, str) or not isinstance(spec, Mapping):
            continue
        rules.append(
            CapabilityRule(
                capability=capability,
                allow=_string_tuple(spec.get("allow")),
                deny=_string_tuple(spec.get("deny")),
                require_approval=bool(spec.get("require_approval")),
            )
        )
    if not rules:
        return None
    return CapabilityPolicy(agent=sender_id or "unknown", rules=tuple(rules))


def record_capability_audit_event(
    session: Session,
    event: Any,
    *,
    sessions: SessionManager,
) -> None:
    """Persist one capability audit event into bounded session metadata."""
    timestamp = getattr(event, "timestamp", None)
    isoformat = getattr(timestamp, "isoformat", None)
    timestamp_value = isoformat() if callable(isoformat) else str(timestamp or "")
    item = {
        "agent": str(getattr(event, "agent", "")),
        "capability": str(getattr(event, "capability", "")),
        "target": str(getattr(event, "target", "")),
        "decision": str(getattr(event, "decision", "")),
        "reason": str(getattr(event, "reason", "")),
        "timestamp": timestamp_value,
    }
    current = session.metadata.get("capability_audit_log")
    audit_log = list(current) if isinstance(current, list) else []
    audit_log.append(item)
    session.metadata["capability_audit_log"] = audit_log[-200:]
    sessions.save(session)


def _string_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list | tuple | set):
        return tuple(item for item in value if isinstance(item, str))
    return ()
