from __future__ import annotations

import time
from types import SimpleNamespace

from mira.agent.context_governance import ContextGovernanceConfig, ContextGovernor
from mira.agent.memory import MemoryStore
from mira.agent.runner import AgentRunner
from mira.kernel.app import KernelApp, build_kernel_manifest
from mira.kernel.profile import lite_customer_profile
from mira.kernel.shell import desktop_customer_shell


def _elapsed(callable_):
    start = time.perf_counter()
    result = callable_()
    return time.perf_counter() - start, result


def _context_config(tmp_path):
    return ContextGovernanceConfig(
        provider=SimpleNamespace(generation=SimpleNamespace(max_tokens=512)),
        model="bench",
        tools=SimpleNamespace(get_definitions=lambda: []),
        workspace=tmp_path,
        session_key="bench:session",
        max_tool_result_chars=4096,
        context_window_tokens=128_000,
        context_block_limit=100_000,
        max_tokens=512,
    )


def test_context_governor_prepares_large_history_under_budget(tmp_path) -> None:
    messages = [
        {"role": "user" if idx % 2 == 0 else "assistant", "content": f"message {idx} " * 20}
        for idx in range(2_000)
    ]

    elapsed, result = _elapsed(
        lambda: ContextGovernor().prepare_for_model(_context_config(tmp_path), messages, set())
    )

    assert isinstance(result, list)
    assert elapsed < 2.0


def test_context_governor_strips_placeholder_messages_quickly() -> None:
    messages = [
        {"role": "assistant", "content": "[Previous assistant message omitted.]"}
        if idx % 5 == 0
        else {"role": "user", "content": f"payload {idx}"}
        for idx in range(10_000)
    ]

    elapsed, result = _elapsed(lambda: ContextGovernor.strip_placeholder_assistant_messages(messages))

    assert len(result) == 8_000
    assert elapsed < 0.5


def test_context_governor_backfills_missing_tool_results_quickly() -> None:
    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": f"call-{idx}", "function": {"name": "filesystem"}}],
        }
        for idx in range(1_000)
    ]

    elapsed, result = _elapsed(lambda: ContextGovernor.backfill_missing_tool_results(messages))

    assert len(result) == 2_000
    assert elapsed < 0.5


def test_memory_store_append_history_throughput(tmp_path) -> None:
    store = MemoryStore(tmp_path)

    elapsed, _ = _elapsed(lambda: [store.append_history(f"benchmark {idx}") for idx in range(200)])

    assert store.get_latest_cursor() == 200
    assert elapsed < 2.0


def test_memory_store_recent_history_read_latency(tmp_path) -> None:
    store = MemoryStore(tmp_path)
    for idx in range(500):
        store.append_history(f"benchmark {idx}")

    elapsed, result = _elapsed(lambda: store.read_unprocessed_history(since_cursor=450))

    assert len(result) == 50
    assert elapsed < 0.5


def test_kernel_manifest_build_latency() -> None:
    elapsed, result = _elapsed(
        lambda: [
            build_kernel_manifest(profile=lite_customer_profile(), shell=desktop_customer_shell())
            for _ in range(100)
        ]
    )

    assert result[-1]["identity"]["app_name"] == "Mira"
    assert elapsed < 1.0


def test_kernel_app_describe_latency() -> None:
    app = KernelApp(SimpleNamespace(_loop=None), profile=lite_customer_profile(), shell=desktop_customer_shell())

    elapsed, result = _elapsed(lambda: [app.describe() for _ in range(50)])

    assert result[-1]["runtime_control"]["active_adapter"] == "python-inprocess"
    assert elapsed < 1.5


def test_kernel_operator_command_latency() -> None:
    app = KernelApp(SimpleNamespace(_loop=None), profile=lite_customer_profile(), shell=desktop_customer_shell())
    commands = [
        "adapter status python-inprocess",
        "module show session_state",
        "runtime status",
        "scheduler status",
        "worker show",
        "kernel manifest",
        "tool queue",
    ]

    elapsed, result = _elapsed(
        lambda: [app.execute_operator_command(command) for _ in range(50) for command in commands]
    )

    assert result[-1]["ok"] is True
    assert elapsed < 1.5


def test_agent_runner_merge_content_latency() -> None:
    elapsed, result = _elapsed(
        lambda: [
            AgentRunner._merge_message_content("left", [{"type": "text", "text": "right"}])
            for _ in range(10_000)
        ]
    )

    assert result[-1][0]["text"] == "left"
    assert elapsed < 0.5


def test_agent_runner_injection_append_latency() -> None:
    messages = [{"role": "user", "content": "start"}]
    injections = [{"role": "user", "content": f"injection {idx}"} for idx in range(1_000)]

    elapsed, _ = _elapsed(lambda: AgentRunner._append_injected_messages(messages, injections))

    assert len(messages) == 1
    assert "injection 999" in messages[0]["content"]
    assert elapsed < 0.5
