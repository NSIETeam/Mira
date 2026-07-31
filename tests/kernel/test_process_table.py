from mira.kernel.process import AgentContextSpace, ProcessTable


def test_process_table_spawn_list_and_snapshot() -> None:
    table = ProcessTable()
    process = table.spawn(
        user="king",
        goal="Code review",
        context=AgentContextSpace(
            system_prompt="reviewer",
            history_window=[{"role": "user", "content": "review PR"}],
            memory_map=("/mem/project",),
            tool_caps=frozenset({"fs/read"}),
        ),
    )

    assert process.pid.startswith("agent-")
    assert process.status == "running"
    assert table.list() == [process]
    snapshot = process.snapshot()
    assert snapshot["context"]["tool_caps"] == ["fs/read"]
    assert snapshot["context"]["memory_map"] == ["/mem/project"]


def test_process_table_stop_resume_and_kill_preserve_context() -> None:
    table = ProcessTable()
    process = table.spawn(user="king", goal="Generate report")

    stopped = table.stop_for_swap(process.pid, reason="preempted")

    assert stopped["status"] == "stopped"
    assert stopped["stopped_reason"] == "preempted"
    assert table.resume(process.pid).status == "running"
    killed = table.kill(process.pid, reason="user requested")
    assert killed["status"] == "terminated"
    assert killed["stopped_reason"] == "user requested"


def test_process_table_fork_copies_context_without_sharing_history() -> None:
    table = ProcessTable()
    parent = table.spawn(
        user="king",
        goal="Investigate bug",
        context=AgentContextSpace(history_window=[{"role": "user", "content": "bug"}]),
    )

    child = table.fork(parent.pid, role="reviewer")

    assert child.pid != parent.pid
    assert child.goal == "Investigate bug (reviewer)"
    child.context.history_window.append({"role": "assistant", "content": "child"})
    assert len(parent.context.history_window) == 1
