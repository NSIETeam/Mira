"""Linux-like principal policy resolution for Mira."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SAFE_TEMPORARY_USER_DENY_TOOLS = frozenset({
    "exec",
    "write_file",
    "edit_file",
    "apply_patch",
    "my_tool",
    "create_or_update_tool",
})


@dataclass(frozen=True, slots=True)
class EffectivePrincipalPolicy:
    role: str
    user_id: str
    group_id: str
    allow_tools: frozenset[str]
    deny_tools: frozenset[str]
    workspace_root: str = ""
    memory_scope: str = "group"
    exec_posture: str = "restricted"

    def allows_tool(self, name: str) -> bool:
        if name in self.deny_tools:
            return False
        return "*" in self.allow_tools or name in self.allow_tools

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "user_id": self.user_id,
            "group_id": self.group_id,
            "allow_tools": sorted(self.allow_tools),
            "deny_tools": sorted(self.deny_tools),
            "workspace_root": self.workspace_root,
            "memory_scope": self.memory_scope,
            "exec_posture": self.exec_posture,
        }


def effective_principal_policy(
    security: Any | None = None,
    *,
    user_id: str | None = None,
    group_id: str | None = None,
) -> EffectivePrincipalPolicy:
    user = (user_id or "default").strip() or "default"
    group = (group_id or "default").strip() or "default"
    role = "user" if user == "default" else "guest"
    allow_tools = {"*"}
    deny_tools: set[str] = set() if user == "default" else set(SAFE_TEMPORARY_USER_DENY_TOOLS)
    workspace_root = ""
    memory_scope = "global" if user == "default" and group == "default" else "group"
    exec_posture = "full" if user == "default" else "restricted"

    for key in (f"role:{role}", f"group:{group}", f"user:{user}"):
        policy = getattr(security, "policies", {}).get(key) if security is not None else None
        if policy is None:
            continue
        role = getattr(policy, "role", role)
        allow_tools = set(getattr(policy, "allow_tools", allow_tools))
        deny_tools.update(getattr(policy, "deny_tools", ()))
        workspace_root = getattr(policy, "workspace_root", workspace_root)
        memory_scope = getattr(policy, "memory_scope", memory_scope)
        exec_posture = getattr(policy, "exec_posture", exec_posture)

    return EffectivePrincipalPolicy(
        role=role,
        user_id=user,
        group_id=group,
        allow_tools=frozenset(allow_tools),
        deny_tools=frozenset(deny_tools),
        workspace_root=workspace_root,
        memory_scope=memory_scope,
        exec_posture=exec_posture,
    )
