"""MiraFS virtual namespace primitives."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

MiraFSKind = Literal["root", "mem", "ctx", "tool"]


class MiraFSError(ValueError):
    """Raised when a virtual MiraFS operation is invalid."""


@dataclass(frozen=True, slots=True)
class MiraFSNode:
    """Resolved MiraFS node."""

    virtual_path: str
    kind: MiraFSKind
    physical_path: Path | None = None


class MiraFS:
    """Small virtual filesystem for AI-native kernel namespaces."""

    def __init__(
        self,
        *,
        workspace: Path,
        tool_names: Callable[[], list[str]] | None = None,
    ) -> None:
        self.workspace = workspace
        self._tool_names = tool_names or (lambda: [])

    def resolve(self, virtual_path: str) -> MiraFSNode:
        path = _normalize_virtual_path(virtual_path)
        if path == "/":
            return MiraFSNode("/", "root")
        head, tail = _split_head(path)
        if head == "mem":
            return MiraFSNode(path, "mem", _safe_join(self.workspace / "memory", tail))
        if head == "ctx":
            return MiraFSNode(path, "ctx", _safe_join(self.workspace / "sessions", tail))
        if head == "tool":
            return MiraFSNode(path, "tool")
        raise MiraFSError(f"unknown MiraFS namespace: /{head}")

    def list(self, virtual_path: str = "/") -> list[str]:
        node = self.resolve(virtual_path)
        if node.kind == "root":
            return ["mem", "ctx", "tool"]
        if node.kind == "tool":
            return sorted(self._tool_names())
        assert node.physical_path is not None
        if not node.physical_path.exists():
            return []
        if node.physical_path.is_file():
            return [node.physical_path.name]
        return sorted(path.name for path in node.physical_path.iterdir())

    def read_text(self, virtual_path: str) -> str:
        node = self.resolve(virtual_path)
        if node.kind == "root":
            return "\n".join(self.list("/"))
        if node.kind == "tool":
            return json.dumps({"tools": self.list("/tool")}, ensure_ascii=False)
        assert node.physical_path is not None
        if not node.physical_path.is_file():
            raise MiraFSError(f"MiraFS path is not a file: {virtual_path}")
        return node.physical_path.read_text(encoding="utf-8")

    def write_text(self, virtual_path: str, content: str) -> MiraFSNode:
        node = self.resolve(virtual_path)
        if node.kind != "mem":
            raise MiraFSError("MiraFS writes are currently limited to /mem")
        assert node.physical_path is not None
        node.physical_path.parent.mkdir(parents=True, exist_ok=True)
        node.physical_path.write_text(content, encoding="utf-8")
        return node


def _normalize_virtual_path(path: str) -> str:
    normalized = "/" + path.strip().lstrip("/")
    parts = [part for part in normalized.split("/") if part]
    if any(part in {".", ".."} for part in parts):
        raise MiraFSError("MiraFS paths may not contain . or .. segments")
    return "/" + "/".join(parts) if parts else "/"


def _split_head(path: str) -> tuple[str, str]:
    parts = [part for part in path.split("/") if part]
    if not parts:
        return "", ""
    return parts[0], "/".join(parts[1:])


def _safe_join(root: Path, tail: str) -> Path:
    root = root.resolve(strict=False)
    candidate = (root / tail).resolve(strict=False)
    if candidate != root and root not in candidate.parents:
        raise MiraFSError("MiraFS path escapes namespace root")
    return candidate
