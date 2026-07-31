import pytest

from mira.kernel.hypervisor import (
    ContextScheduler,
    NoRuntimeCandidateError,
    RuntimeCandidate,
    ThinkCaps,
    ThinkRequest,
)


def test_bin_think_scheduler_filters_by_caps_and_budget() -> None:
    request = ThinkRequest(
        messages=[{"role": "user", "content": "review this"}],
        caps=ThinkCaps.REASONING | ThinkCaps.TOOLS,
        max_cost_usd=0.02,
        estimated_input_tokens=1000,
        estimated_output_tokens=1000,
    )
    candidates = [
        RuntimeCandidate(
            id="cheap-no-reasoning",
            provider="openai-compatible",
            model="small",
            context_window_tokens=8192,
            cost_per_1k_input_usd=0.001,
            cost_per_1k_output_usd=0.002,
            supports_reasoning=False,
        ),
        RuntimeCandidate(
            id="expensive-reasoning",
            provider="anthropic",
            model="large",
            context_window_tokens=200_000,
            cost_per_1k_input_usd=0.02,
            cost_per_1k_output_usd=0.04,
            supports_reasoning=True,
            quality_score=0.95,
        ),
        RuntimeCandidate(
            id="eligible",
            provider="openai-compatible",
            model="reasoning-mini",
            context_window_tokens=128_000,
            cost_per_1k_input_usd=0.004,
            cost_per_1k_output_usd=0.008,
            supports_reasoning=True,
            quality_score=0.8,
        ),
    ]

    plan = ContextScheduler().plan(request, candidates)

    assert plan.command == "/bin/think"
    assert plan.runtime.id == "eligible"
    assert plan.estimated_cost_usd == pytest.approx(0.012)


def test_bin_think_scheduler_supports_policy_modes() -> None:
    request = ThinkRequest(
        messages=[{"role": "user", "content": "summarize"}],
        estimated_input_tokens=100,
        estimated_output_tokens=100,
    )
    candidates = [
        RuntimeCandidate(
            id="fast",
            provider="openai-compatible",
            model="fast",
            context_window_tokens=8192,
            p50_latency_ms=200,
            quality_score=0.4,
            cost_per_1k_input_usd=0.01,
            cost_per_1k_output_usd=0.01,
        ),
        RuntimeCandidate(
            id="cheap",
            provider="openai-compatible",
            model="cheap",
            context_window_tokens=8192,
            p50_latency_ms=1200,
            quality_score=0.5,
            cost_per_1k_input_usd=0.001,
            cost_per_1k_output_usd=0.001,
        ),
        RuntimeCandidate(
            id="quality",
            provider="anthropic",
            model="quality",
            context_window_tokens=200_000,
            p50_latency_ms=900,
            quality_score=0.95,
            cost_per_1k_input_usd=0.02,
            cost_per_1k_output_usd=0.02,
        ),
    ]

    assert ContextScheduler(policy="fastest").plan(request, candidates).runtime.id == "fast"
    assert ContextScheduler(policy="cheapest").plan(request, candidates).runtime.id == "cheap"
    assert (
        ContextScheduler(policy="highest_quality").plan(request, candidates).runtime.id
        == "quality"
    )


def test_bin_think_scheduler_reports_no_candidate() -> None:
    request = ThinkRequest(
        messages=[{"role": "user", "content": "use tools"}],
        caps=ThinkCaps.TOOLS,
    )
    candidates = [
        RuntimeCandidate(
            id="no-tools",
            provider="openai-compatible",
            model="text-only",
            context_window_tokens=8192,
            supports_tools=False,
        )
    ]

    with pytest.raises(NoRuntimeCandidateError):
        ContextScheduler().plan(request, candidates)
