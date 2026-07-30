import pytest

from mira.kernel.mesh import MeshDirectory, MeshNode


def test_mesh_directory_selects_least_loaded_matching_node() -> None:
    mesh = MeshDirectory()
    mesh.upsert(
        MeshNode(
            id="node-a",
            role="user_facing",
            available_models=frozenset({"fast"}),
            load=0.6,
        )
    )
    mesh.upsert(
        MeshNode(
            id="node-b",
            role="background",
            available_models=frozenset({"fast", "cheap"}),
            load=0.2,
        )
    )

    selected = mesh.choose_node(required_model="fast")

    assert selected.id == "node-b"


def test_mesh_directory_supports_burst_preference() -> None:
    mesh = MeshDirectory()
    mesh.upsert(MeshNode(id="node-a", role="background", load=0.1))
    mesh.upsert(MeshNode(id="node-c", role="burst", load=0.7))

    selected = mesh.choose_node(prefer="burst")

    assert selected.id == "node-c"


def test_mesh_directory_ignores_offline_nodes_and_plans_migration() -> None:
    mesh = MeshDirectory()
    mesh.upsert(MeshNode(id="node-a", role="user_facing"))
    mesh.upsert(MeshNode(id="node-c", role="burst", status="offline"))

    with pytest.raises(KeyError):
        mesh.plan_migration(
            agent_pid="agent-1",
            source_node="node-a",
            target_node="node-c",
            context_bytes=1024,
            reason="gpu burst",
        )

    mesh.upsert(MeshNode(id="node-c", role="burst", status="healthy"))
    plan = mesh.plan_migration(
        agent_pid="agent-1",
        source_node="node-a",
        target_node="node-c",
        context_bytes=1024,
        reason="gpu burst",
    )

    assert plan.target_node == "node-c"
    assert plan.context_bytes == 1024
