"""Mira Mesh scheduling and migration primitives."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

NodeRole = Literal["user_facing", "background", "burst"]
NodeStatus = Literal["healthy", "degraded", "offline"]


@dataclass(frozen=True, slots=True)
class MeshNode:
    """One node visible to the mesh scheduler."""

    id: str
    role: NodeRole
    status: NodeStatus = "healthy"
    latency_ms: int = 10
    available_models: frozenset[str] = frozenset()
    load: float = 0.0
    updated_at: datetime = field(default_factory=datetime.now)

    @property
    def schedulable(self) -> bool:
        return self.status != "offline" and self.load < 1.0


@dataclass(frozen=True, slots=True)
class MigrationPlan:
    """Serializable plan for moving an agent process to another node."""

    agent_pid: str
    source_node: str
    target_node: str
    reason: str
    context_bytes: int


@dataclass(frozen=True, slots=True)
class MeshGossipEnvelope:
    """One directory snapshot exchanged between mesh peers."""

    source_node: str
    observed_at: datetime
    nodes: tuple[MeshNode, ...]


class MeshDirectory:
    """In-memory mesh node directory and scheduler."""

    def __init__(self) -> None:
        self._nodes: dict[str, MeshNode] = {}

    def upsert(self, node: MeshNode) -> None:
        self._nodes[node.id] = node

    def remove(self, node_id: str) -> None:
        self._nodes.pop(node_id, None)

    def list(self) -> list[MeshNode]:
        return sorted(self._nodes.values(), key=lambda node: node.id)

    def export_gossip(self, *, source_node: str) -> MeshGossipEnvelope:
        """Create a deterministic snapshot that can be sent to a peer."""
        return MeshGossipEnvelope(
            source_node=source_node,
            observed_at=datetime.now(),
            nodes=tuple(self.list()),
        )

    def apply_gossip(self, envelope: MeshGossipEnvelope) -> int:
        """Merge a peer snapshot, ignoring stale node records."""
        updated = 0
        for node in envelope.nodes:
            current = self._nodes.get(node.id)
            if current is not None and current.updated_at > node.updated_at:
                continue
            self._nodes[node.id] = node
            updated += 1
        return updated

    def choose_node(
        self,
        *,
        required_model: str | None = None,
        prefer: Literal["nearest", "least_loaded", "burst"] = "least_loaded",
    ) -> MeshNode:
        candidates = [
            node
            for node in self._nodes.values()
            if node.schedulable
            and (required_model is None or required_model in node.available_models)
        ]
        if not candidates:
            raise KeyError("no schedulable mesh node matches the request")
        if prefer == "nearest":
            return min(candidates, key=lambda node: (node.latency_ms, node.load, node.id))
        if prefer == "burst":
            burst = [node for node in candidates if node.role == "burst"]
            candidates = burst or candidates
        return min(candidates, key=lambda node: (node.load, node.latency_ms, node.id))

    def plan_migration(
        self,
        *,
        agent_pid: str,
        source_node: str,
        target_node: str,
        context_bytes: int,
        reason: str,
    ) -> MigrationPlan:
        if source_node not in self._nodes:
            raise KeyError(f"unknown source node: {source_node}")
        target = self._nodes.get(target_node)
        if target is None or not target.schedulable:
            raise KeyError(f"target node is not schedulable: {target_node}")
        return MigrationPlan(
            agent_pid=agent_pid,
            source_node=source_node,
            target_node=target_node,
            context_bytes=context_bytes,
            reason=reason,
        )
