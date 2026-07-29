"""Lightweight maturity primitives inspired by mature agent frameworks.

The module is intentionally small: it provides stable contracts that can be
mounted by the kernel without pulling heavy orchestration dependencies into the
default startup path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from mira.agent.tools.base import ToolResult
from mira.providers.base import ToolCallRequest
from mira.utils.helpers import estimate_message_tokens


@dataclass(frozen=True, slots=True)
class AgentRoleProfile:
    name: str
    purpose: str
    system_hint: str
    default_memory_policy: str = "default"
    default_weight: int = 1


_ROLE_PROFILES: dict[str, AgentRoleProfile] = {
    "implementer": AgentRoleProfile(
        name="implementer",
        purpose="Ship concrete changes with minimal architecture churn.",
        system_hint="Act as an implementation subagent. Prefer small patches and concrete outputs.",
        default_memory_policy="default",
        default_weight=2,
    ),
    "reviewer": AgentRoleProfile(
        name="reviewer",
        purpose="Find correctness, safety, regression, and test gaps.",
        system_hint="Act as a review subagent. Findings first; avoid rewriting unless asked.",
        default_memory_policy="task_only",
        default_weight=1,
    ),
    "researcher": AgentRoleProfile(
        name="researcher",
        purpose="Gather focused facts and compare options.",
        system_hint="Act as a research subagent. Cite constraints and return decision-ready notes.",
        default_memory_policy="default",
        default_weight=1,
    ),
    "doctor": AgentRoleProfile(
        name="doctor",
        purpose="Diagnose runtime, packaging, and environment failures.",
        system_hint="Act as a diagnostic subagent. Reproduce the symptom, isolate cause, then propose the smallest fix.",
        default_memory_policy="full",
        default_weight=2,
    ),
}


def list_agent_role_profiles() -> list[dict[str, Any]]:
    return [
        {
            "name": profile.name,
            "purpose": profile.purpose,
            "default_memory_policy": profile.default_memory_policy,
            "default_weight": profile.default_weight,
        }
        for profile in sorted(_ROLE_PROFILES.values(), key=lambda item: item.name)
    ]


def resolve_agent_role_profile(role: str | None) -> AgentRoleProfile | None:
    normalized = str(role or "").strip().lower()
    if not normalized or normalized in {"auto", "default"}:
        return None
    return _ROLE_PROFILES.get(normalized)


def apply_agent_role_to_task(task: str, role: str | None) -> str:
    profile = resolve_agent_role_profile(role)
    if profile is None:
        return task
    return f"{profile.system_hint}\n\nTask:\n{task}"


@dataclass(frozen=True, slots=True)
class VirtualContextPage:
    kept_messages: list[dict[str, Any]]
    paged_count: int
    budget_tokens: int
    summary_message: dict[str, Any] | None = None


class VirtualContextManager:
    """Small virtual-context pager for old turns.

    It does not summarize with an LLM. It pages older messages into a compact
    breadcrumb so the main loop can stay cheap and deterministic.
    """

    def __init__(self, *, max_summary_chars: int = 1200) -> None:
        self.max_summary_chars = max(200, max_summary_chars)

    def page(self, messages: list[dict[str, Any]], *, budget_tokens: int) -> VirtualContextPage:
        if budget_tokens <= 0:
            return VirtualContextPage(list(messages), 0, budget_tokens)

        kept: list[dict[str, Any]] = []
        used = 0
        for message in reversed(messages):
            tokens = estimate_message_tokens(message)
            if kept and used + tokens > budget_tokens:
                break
            kept.append(dict(message))
            used += tokens
        kept.reverse()
        paged_count = max(0, len(messages) - len(kept))
        if paged_count <= 0:
            return VirtualContextPage(kept, 0, budget_tokens)

        summary_text = self._breadcrumb(messages[:paged_count])
        summary = {
            "role": "system",
            "content": (
                "[Mira virtual context]\n"
                f"{paged_count} older message(s) were paged out of the live window.\n"
                f"Breadcrumb:\n{summary_text}"
            ),
            "metadata": {"virtual_context": True, "paged_count": paged_count},
        }
        return VirtualContextPage([summary, *kept], paged_count, budget_tokens, summary)

    def _breadcrumb(self, messages: list[dict[str, Any]]) -> str:
        chunks: list[str] = []
        for message in messages[-12:]:
            role = str(message.get("role") or "unknown")
            content = message.get("content")
            if isinstance(content, list):
                text = " ".join(
                    str(block.get("text") or "")
                    for block in content
                    if isinstance(block, dict) and block.get("type") == "text"
                )
            else:
                text = str(content or "")
            text = " ".join(text.split())
            if text:
                chunks.append(f"- {role}: {text[:180]}")
        breadcrumb = "\n".join(chunks) or "- no textual breadcrumb available"
        return breadcrumb[: self.max_summary_chars]


@dataclass(frozen=True, slots=True)
class MediaPart:
    kind: str
    source: str
    mime_type: str = ""
    name: str = ""

    def to_dict(self) -> dict[str, str]:
        data = {"kind": self.kind, "source": self.source}
        if self.mime_type:
            data["mime_type"] = self.mime_type
        if self.name:
            data["name"] = self.name
        return data


def normalize_media_contract(content: str, media: list[Any] | None = None) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = []
    if content.strip():
        parts.append({"type": "text", "text": content})
    for item in media or ():
        if isinstance(item, dict):
            source = str(item.get("source") or item.get("url") or item.get("path") or "").strip()
            kind = str(item.get("kind") or item.get("type") or "file").strip().lower()
            mime_type = str(item.get("mime_type") or item.get("mimeType") or "").strip()
            name = str(item.get("name") or "").strip()
        else:
            source = str(item or "").strip()
            lower = source.lower()
            kind = "image" if lower.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")) else "file"
            mime_type = ""
            name = source.rsplit("/", 1)[-1]
        if not source:
            continue
        parts.append({"type": "media", **MediaPart(kind, source, mime_type, name).to_dict()})
    return parts


@dataclass(frozen=True, slots=True)
class WorkflowStep:
    step_id: str
    task: str
    role: str = "implementer"
    depends_on: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.step_id,
            "task": self.task,
            "role": self.role,
            "depends_on": list(self.depends_on),
        }


def parse_workflow_dsl(payload: str | dict[str, Any]) -> list[WorkflowStep]:
    data = json.loads(payload) if isinstance(payload, str) else payload
    if not isinstance(data, dict):
        raise ValueError("workflow must be a JSON object")
    raw_steps = data.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ValueError("workflow.steps must be a non-empty list")
    steps: list[WorkflowStep] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_steps, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"workflow step {index} must be an object")
        step_id = str(raw.get("id") or f"step-{index}").strip()
        task = str(raw.get("task") or "").strip()
        if not step_id or not task:
            raise ValueError(f"workflow step {index} requires id and task")
        if step_id in seen:
            raise ValueError(f"duplicate workflow step id: {step_id}")
        depends = raw.get("depends_on") or raw.get("dependsOn") or []
        if isinstance(depends, str):
            depends = [depends]
        if not isinstance(depends, list):
            raise ValueError(f"workflow step {step_id} depends_on must be a list")
        steps.append(WorkflowStep(
            step_id=step_id,
            task=task,
            role=str(raw.get("role") or "implementer").strip() or "implementer",
            depends_on=tuple(str(item) for item in depends if str(item).strip()),
        ))
        seen.add(step_id)
    missing = sorted({dep for step in steps for dep in step.depends_on if dep not in seen})
    if missing:
        raise ValueError(f"workflow depends on unknown step(s): {', '.join(missing)}")
    return steps


class ToolMiddleware(Protocol):
    async def before_execute(
        self,
        tool_call: ToolCallRequest,
        tool: Any,
        params: Any,
    ) -> ToolResult | None:
        ...

    async def after_execute(
        self,
        tool_call: ToolCallRequest,
        tool: Any,
        params: Any,
        result: Any,
    ) -> None:
        ...

    async def on_error(
        self,
        tool_call: ToolCallRequest,
        tool: Any,
        params: Any,
        error: Any,
    ) -> None:
        ...


@dataclass(slots=True)
class ToolMiddlewareStack:
    middlewares: list[ToolMiddleware] = field(default_factory=list)

    async def before_execute(
        self,
        tool_call: ToolCallRequest,
        tool: Any,
        params: Any,
    ) -> ToolResult | None:
        for middleware in self.middlewares:
            result = await middleware.before_execute(tool_call, tool, params)
            if result is not None:
                return result
        return None

    async def after_execute(
        self,
        tool_call: ToolCallRequest,
        tool: Any,
        params: Any,
        result: Any,
    ) -> None:
        for middleware in self.middlewares:
            await middleware.after_execute(tool_call, tool, params, result)

    async def on_error(
        self,
        tool_call: ToolCallRequest,
        tool: Any,
        params: Any,
        error: Any,
    ) -> None:
        for middleware in self.middlewares:
            await middleware.on_error(tool_call, tool, params, error)
