"""Shared tool-contract family helpers for kernel and agent surfaces."""

from __future__ import annotations


def tool_contract_family(tool_name: str) -> str:
    name = str(tool_name or "").strip().lower()
    if not name:
        return "unknown"
    if name.startswith("mcp") or name.startswith("browser"):
        return "mcp"
    if name.startswith(("web", "search", "fetch")) or "search" in name or "fetch" in name:
        return "web"
    if name.startswith((
        "file",
        "fs",
        "filesystem",
        "read",
        "write",
        "edit",
        "list",
        "glob",
        "grep",
    )) or "filesystem" in name:
        return "filesystem"
    if name.startswith(("shell", "exec", "run")):
        return "shell"
    if "subagent" in name:
        return "subagent"
    if "goal" in name or "long" in name or "task" in name:
        return "long-task"
    return "core"


def tool_contract_family_counts(tools: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for tool in tools:
        family = tool_contract_family(tool)
        counts[family] = counts.get(family, 0) + 1
    return counts


def tool_contract_family_groups(tools: list[str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for tool in tools:
        family = tool_contract_family(tool)
        groups.setdefault(family, []).append(str(tool))
    return {family: sorted(items) for family, items in sorted(groups.items())}
