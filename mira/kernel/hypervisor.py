"""LLM hypervisor primitives for /bin/think scheduling."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntFlag
from typing import Any, Literal

ThinkPriority = Literal["background", "interactive", "critical"]
ThinkPolicy = Literal["balanced", "fastest", "cheapest", "highest_quality"]


class ThinkCaps(IntFlag):
    """Capabilities requested by a /bin/think invocation."""

    NONE = 0
    REASONING = 1
    TOOLS = 2


@dataclass(frozen=True, slots=True)
class ThinkRequest:
    """Application-facing /bin/think request descriptor."""

    messages: list[dict[str, Any]]
    caps: ThinkCaps = ThinkCaps.NONE
    priority: ThinkPriority = "interactive"
    latency_budget_ms: int | None = None
    max_cost_usd: float | None = None
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0


@dataclass(frozen=True, slots=True)
class RuntimeCandidate:
    """One model runtime visible to the hypervisor scheduler."""

    id: str
    provider: str
    model: str
    context_window_tokens: int
    cost_per_1k_input_usd: float = 0.0
    cost_per_1k_output_usd: float = 0.0
    p50_latency_ms: int = 1_000
    quality_score: float = 0.5
    supports_reasoning: bool = False
    supports_tools: bool = True
    available: bool = True

    def estimate_cost_usd(self, request: ThinkRequest) -> float:
        return (
            request.estimated_input_tokens * self.cost_per_1k_input_usd
            + request.estimated_output_tokens * self.cost_per_1k_output_usd
        ) / 1000


@dataclass(frozen=True, slots=True)
class ThinkPlan:
    """Resolved execution plan for /bin/think."""

    command: str
    runtime: RuntimeCandidate
    policy: ThinkPolicy
    estimated_cost_usd: float
    score: float


class NoRuntimeCandidateError(RuntimeError):
    """Raised when no runtime satisfies a /bin/think request."""


class ContextScheduler:
    """Select an LLM runtime for a /bin/think request."""

    def __init__(self, *, policy: ThinkPolicy = "balanced") -> None:
        self.policy = policy

    def plan(self, request: ThinkRequest, candidates: list[RuntimeCandidate]) -> ThinkPlan:
        eligible = [candidate for candidate in candidates if self._eligible(request, candidate)]
        if not eligible:
            raise NoRuntimeCandidateError("no available runtime satisfies /bin/think constraints")

        scored = [
            (
                self._score(request, candidate),
                candidate,
            )
            for candidate in eligible
        ]
        score, selected = max(scored, key=lambda item: (item[0], item[1].quality_score, item[1].id))
        return ThinkPlan(
            command="/bin/think",
            runtime=selected,
            policy=self.policy,
            estimated_cost_usd=selected.estimate_cost_usd(request),
            score=score,
        )

    def _eligible(self, request: ThinkRequest, candidate: RuntimeCandidate) -> bool:
        if not candidate.available:
            return False
        total_tokens = request.estimated_input_tokens + request.estimated_output_tokens
        if total_tokens > candidate.context_window_tokens:
            return False
        if request.caps & ThinkCaps.REASONING and not candidate.supports_reasoning:
            return False
        if request.caps & ThinkCaps.TOOLS and not candidate.supports_tools:
            return False
        if (
            request.latency_budget_ms is not None
            and candidate.p50_latency_ms > request.latency_budget_ms
            and request.priority != "critical"
        ):
            return False
        if (
            request.max_cost_usd is not None
            and candidate.estimate_cost_usd(request) > request.max_cost_usd
            and request.priority != "critical"
        ):
            return False
        return True

    def _score(self, request: ThinkRequest, candidate: RuntimeCandidate) -> float:
        cost = candidate.estimate_cost_usd(request)
        latency = max(candidate.p50_latency_ms, 1)
        if self.policy == "fastest":
            return 1_000_000 / latency
        if self.policy == "cheapest":
            return 1 / max(cost, 0.000001)
        if self.policy == "highest_quality":
            return candidate.quality_score
        priority_weight = {"background": 0.4, "interactive": 1.0, "critical": 1.4}[request.priority]
        cost_penalty = min(cost * 8, 2.0)
        latency_penalty = min(latency / 10_000, 2.0)
        return candidate.quality_score * priority_weight - cost_penalty - latency_penalty
