"""Memory system: pure file I/O store and lightweight Consolidator."""

from __future__ import annotations

import json
import os
import re
import threading
from collections.abc import Iterator, Mapping, Sequence
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from mira.agent import memory_dream
from mira.runtime_context import public_history_messages
from mira.utils.gitstore import GitStore
from mira.utils.helpers import (
    ensure_dir,
    strip_think,
    truncate_text,
)
from mira.utils.prompt_templates import render_template
from mira.utils.workspace_prompts import (
    WORKSPACE_PROMPT_MAX_CHARS,
    has_workspace_prompt_override,
    load_workspace_prompt_override,
    workspace_prompt_file,
)

if TYPE_CHECKING:
    pass

_MEMORY_RECALL_STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being", "to",
    "of", "in", "for", "on", "with", "at", "by", "from", "as", "into", "about",
    "like", "through", "after", "over", "between", "out", "against", "during",
    "without", "before", "under", "around", "among", "and", "but", "or", "nor",
    "not", "so", "yet", "both", "either", "neither", "each", "every", "all",
    "any", "few", "more", "most", "other", "some", "such", "no", "only", "own",
    "same", "than", "too", "very", "just", "because", "then", "now", "also",
    "here", "there", "when", "where", "why", "how", "who", "whom", "which",
    "what", "this", "that", "these", "those", "it", "its", "i", "you", "we",
    "they", "them", "my", "your", "our", "their", "memory",
}

# ---------------------------------------------------------------------------
# MemoryStore — pure file I/O layer
# ---------------------------------------------------------------------------


class MemoryStore:
    """Pure file I/O for memory files: MEMORY.md, history.jsonl, SOUL.md, USER.md."""

    _DEFAULT_MAX_HISTORY = 1000
    # Durable files whose real working-tree delta grounds Dream commit messages.
    # Deliberately excludes memory/.dream_cursor so progress bookkeeping never
    # appears as a durable-memory edit in the audit record.
    _DREAM_CONTENT_PATHS = ("SOUL.md", "USER.md", "memory/MEMORY.md")
    # Per-file cap when embedding current contents into the Dream prompt. The
    # durable files are tiny in practice (~5 KB total), but a runaway file must
    # not unbounded the prompt.
    _DREAM_FILE_EMBED_CAP = 8000
    _INTERNAL_HISTORY_SESSION_PREFIXES = ("cron:", "dream:")
    _INTERNAL_HISTORY_SESSION_KEYS = {"heartbeat"}
    _LEGACY_ENTRY_START_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2}[^\]]*)\]\s*")
    _LEGACY_TIMESTAMP_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\]\s*")
    _LEGACY_RAW_MESSAGE_RE = re.compile(
        r"^\[\d{4}-\d{2}-\d{2}[^\]]*\]\s+[A-Z][A-Z0-9_]*(?:\s+\[tools:\s*[^\]]+\])?:"
    )
    _PROJECT_CLAUDE_FILE = "CLAUDE.md"
    _LOCAL_CLAUDE_FILE = "CLAUDE.local.md"
    _GRAPH_FILE = "graph.json"
    _TOPICS_DIR = "topics"
    _SUBAGENT_DIR = "subagents"
    _TOPIC_LINK_RE = re.compile(r"\((?:\./)?memory/topics/([A-Za-z0-9._-]+\.md)\)")
    _TOPIC_HEADING_RE = re.compile(r"^##\s+Topic:\s+([A-Za-z0-9._-]+)", re.MULTILINE)
    _PATH_ENTITY_RE = re.compile(r"`([^`\n]+(?:/[^\n`]+|\.[A-Za-z0-9_-]+))`")
    _INLINE_PATH_RE = re.compile(r"\b([A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)+)\b")
    _ISSUE_RE = re.compile(r"(?:issue|#)\s*(\d+)", re.IGNORECASE)
    _DECISION_RE = re.compile(
        r"(?:决定|改为|采用|切换到|use|using|switch to|decision:)\s+([^\n。.!?]{4,120})",
        re.IGNORECASE,
    )
    _MODULE_RE = re.compile(r"\b([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+|[A-Za-z0-9_.-]+\.(?:py|ts|tsx|js|jsx|md))\b")

    def __init__(self, workspace: Path, max_history_entries: int = _DEFAULT_MAX_HISTORY):
        self.workspace = workspace
        self.max_history_entries = max_history_entries
        self.memory_dir = ensure_dir(workspace / "memory")
        self.memory_file = self.memory_dir / "MEMORY.md"
        self.history_file = self.memory_dir / "history.jsonl"
        self.legacy_history_file = self.memory_dir / "HISTORY.md"
        self.soul_file = workspace / "SOUL.md"
        self.user_file = workspace / "USER.md"
        self.project_claude_file = workspace / self._PROJECT_CLAUDE_FILE
        self.local_claude_file = workspace / self._LOCAL_CLAUDE_FILE
        self.user_claude_file = Path.home() / ".mira" / self._PROJECT_CLAUDE_FILE
        self.graph_file = self.memory_dir / self._GRAPH_FILE
        self.topic_dir = ensure_dir(self.memory_dir / self._TOPICS_DIR)
        self.subagent_dir = ensure_dir(self.memory_dir / self._SUBAGENT_DIR)
        self._cursor_file = self.memory_dir / ".cursor"
        self._dream_cursor_file = self.memory_dir / ".dream_cursor"
        self._corruption_logged = False  # rate-limit invalid cursor warning
        self._malformed_entry_logged = False  # rate-limit bad history shape warning
        self._oversize_logged = False  # rate-limit oversized-entry warning
        self._dream_prompt_oversize_logged = False
        self._append_lock = threading.Lock()  # serialize cursor allocation + append
        self._git = GitStore(workspace, tracked_files=[
            "SOUL.md", "USER.md", "memory/MEMORY.md", "memory/.dream_cursor",
        ])
        self._maybe_migrate_legacy_history()

    @property
    def git(self) -> GitStore:
        return self._git

    # -- generic helpers -----------------------------------------------------

    @staticmethod
    def read_file(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""

    def _maybe_migrate_legacy_history(self) -> None:
        """One-time upgrade from legacy HISTORY.md to history.jsonl.

        The migration is best-effort and prioritizes preserving as much content
        as possible over perfect parsing.
        """
        if not self.legacy_history_file.exists():
            return
        if self.history_file.exists() and self.history_file.stat().st_size > 0:
            return

        try:
            legacy_text = self.legacy_history_file.read_text(
                encoding="utf-8",
                errors="replace",
            )
        except OSError:
            logger.exception("Failed to read legacy HISTORY.md for migration")
            return

        entries = self._parse_legacy_history(legacy_text)
        try:
            if entries:
                self._write_entries(entries)
                last_cursor = entries[-1]["cursor"]
                self._cursor_file.write_text(str(last_cursor), encoding="utf-8")
                # Default to "already processed" so upgrades do not replay the
                # user's entire historical archive into Dream on first start.
                self._dream_cursor_file.write_text(str(last_cursor), encoding="utf-8")

            backup_path = self._next_legacy_backup_path()
            self.legacy_history_file.replace(backup_path)
            logger.info(
                "Migrated legacy HISTORY.md to history.jsonl ({} entries)",
                len(entries),
            )
        except Exception:
            logger.exception("Failed to migrate legacy HISTORY.md")

    def _parse_legacy_history(self, text: str) -> list[dict[str, Any]]:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not normalized:
            return []

        fallback_timestamp = self._legacy_fallback_timestamp()
        entries: list[dict[str, Any]] = []
        chunks = self._split_legacy_history_chunks(normalized)

        for cursor, chunk in enumerate(chunks, start=1):
            timestamp = fallback_timestamp
            content = chunk
            match = self._LEGACY_TIMESTAMP_RE.match(chunk)
            if match:
                timestamp = match.group(1)
                remainder = chunk[match.end():].lstrip()
                if remainder:
                    content = remainder

            entries.append({
                "cursor": cursor,
                "timestamp": timestamp,
                "content": content,
            })
        return entries

    def _split_legacy_history_chunks(self, text: str) -> list[str]:
        lines = text.split("\n")
        chunks: list[str] = []
        current: list[str] = []
        saw_blank_separator = False

        for line in lines:
            if saw_blank_separator and line.strip() and current:
                chunks.append("\n".join(current).strip())
                current = [line]
                saw_blank_separator = False
                continue
            if self._should_start_new_legacy_chunk(line, current):
                chunks.append("\n".join(current).strip())
                current = [line]
                saw_blank_separator = False
                continue
            current.append(line)
            saw_blank_separator = not line.strip()

        if current:
            chunks.append("\n".join(current).strip())
        return [chunk for chunk in chunks if chunk]

    def _should_start_new_legacy_chunk(self, line: str, current: list[str]) -> bool:
        if not current:
            return False
        if not self._LEGACY_ENTRY_START_RE.match(line):
            return False
        if self._is_raw_legacy_chunk(current) and self._LEGACY_RAW_MESSAGE_RE.match(line):
            return False
        return True

    def _is_raw_legacy_chunk(self, lines: list[str]) -> bool:
        first_nonempty = next((line for line in lines if line.strip()), "")
        match = self._LEGACY_TIMESTAMP_RE.match(first_nonempty)
        if not match:
            return False
        return first_nonempty[match.end():].lstrip().startswith("[RAW]")

    def _legacy_fallback_timestamp(self) -> str:
        try:
            return datetime.fromtimestamp(
                self.legacy_history_file.stat().st_mtime,
            ).strftime("%Y-%m-%d %H:%M")
        except OSError:
            return datetime.now().strftime("%Y-%m-%d %H:%M")

    def _next_legacy_backup_path(self) -> Path:
        candidate = self.memory_dir / "HISTORY.md.bak"
        suffix = 2
        while candidate.exists():
            candidate = self.memory_dir / f"HISTORY.md.bak.{suffix}"
            suffix += 1
        return candidate

    # -- MEMORY.md (long-term facts) -----------------------------------------

    def read_memory(self) -> str:
        return self.read_file(self.memory_file)

    def write_memory(self, content: str) -> None:
        self.memory_file.write_text(content, encoding="utf-8")

    @staticmethod
    def _topic_slug(value: str) -> str:
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip().lower()).strip("-.")
        return slug or "untitled"

    def _existing_topic_slug(self, topic_name: str) -> str | None:
        wanted = self._topic_slug(topic_name)
        wanted_norm = wanted.replace("-", "").replace("_", "")
        for path in self.list_topic_files():
            candidate = path.stem
            candidate_norm = candidate.replace("-", "").replace("_", "")
            if candidate == wanted or candidate_norm == wanted_norm:
                return candidate
        return None

    def ensure_topic_index_entry(self, topic_name: str, summary: str | None = None) -> Path:
        slug = self._existing_topic_slug(topic_name) or self._topic_slug(topic_name)
        filename = f"{slug}.md"
        link = f"[{slug}](memory/topics/{filename})"
        summary_text = truncate_text((summary or topic_name).strip(), 120)
        content = self.read_memory().strip()
        section_header = "## Topic Index"
        entry_line = f"- {link}: {summary_text}"
        if not content:
            self.write_memory(f"{section_header}\n{entry_line}\n")
            return self.topic_dir / filename
        if f"(memory/topics/{filename})" in content:
            self.write_memory(self._dedupe_topic_index(content.rstrip() + "\n"))
            return self.topic_dir / filename
        lines = content.splitlines()
        insert_at = len(lines)
        section_index = next((i for i, line in enumerate(lines) if line.strip() == section_header), None)
        if section_index is None:
            if lines and lines[-1].strip():
                lines.append("")
            lines.append(section_header)
            lines.append(entry_line)
        else:
            insert_at = section_index + 1
            while insert_at < len(lines) and lines[insert_at].startswith("- "):
                insert_at += 1
            lines.insert(insert_at, entry_line)
        self.write_memory(self._dedupe_topic_index("\n".join(lines).rstrip() + "\n"))
        return self.topic_dir / filename

    def _dedupe_topic_index(self, content: str) -> str:
        lines = content.splitlines()
        section_header = "## Topic Index"
        section_index = next((i for i, line in enumerate(lines) if line.strip() == section_header), None)
        if section_index is None:
            return content
        prefix = lines[: section_index + 1]
        suffix_start = section_index + 1
        topic_lines: list[str] = []
        while suffix_start < len(lines) and lines[suffix_start].startswith("- "):
            topic_lines.append(lines[suffix_start])
            suffix_start += 1
        suffix = lines[suffix_start:]

        seen: set[str] = set()
        deduped: list[str] = []
        for line in topic_lines:
            match = self._TOPIC_LINK_RE.search(line)
            key = match.group(1) if match else line.strip()
            normalized = key.replace("-", "").replace("_", "").lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(line)
        merged = prefix + deduped + suffix
        return "\n".join(merged).rstrip() + "\n"

    def list_topic_files(self) -> list[Path]:
        return sorted(self.topic_dir.glob("*.md"))

    def read_topic_file(self, slug: str) -> str:
        safe_slug = re.sub(r"[^A-Za-z0-9._-]+", "-", slug).strip("-.")
        if not safe_slug:
            return ""
        if not safe_slug.endswith(".md"):
            safe_slug = f"{safe_slug}.md"
        return self.read_file(self.topic_dir / safe_slug)

    def write_topic_file(self, slug: str, content: str) -> Path:
        safe_slug = re.sub(r"[^A-Za-z0-9._-]+", "-", slug).strip("-.")
        if not safe_slug:
            safe_slug = "untitled"
        if not safe_slug.endswith(".md"):
            safe_slug = f"{safe_slug}.md"
        path = self.topic_dir / safe_slug
        path.write_text(content, encoding="utf-8")
        return path

    def ensure_topic_file(
        self,
        topic_name: str,
        *,
        summary: str | None = None,
        evidence: str | None = None,
        category: str = "topic",
    ) -> Path:
        path = self.ensure_topic_index_entry(topic_name, summary=summary)
        if path.exists() and path.read_text(encoding="utf-8").strip():
            return path
        title = topic_name.strip() or path.stem
        body = [
            f"# {title}",
            "",
            f"- category: {category}",
        ]
        if summary:
            body.append(f"- summary: {truncate_text(summary.strip(), 180)}")
        if evidence:
            body.extend([
                "",
                "## Evidence",
                f"- {truncate_text(evidence.strip().replace(chr(10), ' '), 240)}",
            ])
        path.write_text("\n".join(body).rstrip() + "\n", encoding="utf-8")
        return path

    def append_topic_evidence(
        self,
        topic_name: str,
        *,
        summary: str | None = None,
        evidence: str | None = None,
        category: str = "topic",
    ) -> Path:
        path = self.ensure_topic_file(
            topic_name,
            summary=summary,
            evidence=evidence,
            category=category,
        )
        if not evidence:
            return path
        content = self.read_file(path)
        evidence_line = f"- {truncate_text(evidence.strip().replace(chr(10), ' '), 240)}"
        if evidence_line in content:
            return path
        if "## Evidence" not in content:
            content = content.rstrip() + "\n\n## Evidence\n"
        content = content.rstrip() + "\n" + evidence_line + "\n"
        path.write_text(content, encoding="utf-8")
        return path

    def append_topic_graph_links(
        self,
        topic_name: str,
        *,
        entity_id: str,
        graph: dict[str, Any],
        category: str = "topic",
    ) -> Path:
        path = self.ensure_topic_file(topic_name, summary=topic_name, category=category)
        relations = graph.get("relations", []) if isinstance(graph.get("relations"), list) else []
        related_lines: list[str] = []
        for relation in relations:
            if not isinstance(relation, dict):
                continue
            source = str(relation.get("source") or "").strip()
            target = str(relation.get("target") or "").strip()
            rel_type = str(relation.get("type") or "").strip()
            if not rel_type:
                continue
            if source == entity_id and target:
                related_lines.append(f"- {rel_type}: {target}")
            elif target == entity_id and source:
                related_lines.append(f"- {rel_type}: {source}")
        if not related_lines:
            return path
        content = self.read_file(path)
        header = "## Graph Links"
        existing = set()
        for line in content.splitlines():
            if line.startswith("- ") and ":" in line:
                existing.add(line.strip())
        additions = [line for line in related_lines if line not in existing]
        if not additions:
            return path
        if header not in content:
            content = content.rstrip() + f"\n\n{header}\n"
        content = content.rstrip() + "\n" + "\n".join(additions) + "\n"
        path.write_text(content, encoding="utf-8")
        return path

    def referenced_topic_files(self) -> list[Path]:
        index = self.read_memory()
        names = {
            match.group(1)
            for match in self._TOPIC_LINK_RE.finditer(index)
        }
        names.update(f"{match.group(1)}.md" for match in self._TOPIC_HEADING_RE.finditer(index))
        files: list[Path] = []
        for name in sorted(names):
            path = self.topic_dir / name
            if path.exists():
                files.append(path)
        return files

    def topic_memory_context(self, *, max_files: int = 8, max_chars: int = 1200) -> str:
        blocks: list[str] = []
        for path in self.referenced_topic_files()[:max_files]:
            content = self.read_file(path).strip()
            if not content:
                continue
            blocks.append(
                f"### {path.name}\n{truncate_text(content, max_chars)}"
            )
        return "\n\n".join(blocks)

    # -- SOUL.md -------------------------------------------------------------

    def read_soul(self) -> str:
        return self.read_file(self.soul_file)

    def write_soul(self, content: str) -> None:
        self.soul_file.write_text(content, encoding="utf-8")

    # -- USER.md -------------------------------------------------------------

    def read_user(self) -> str:
        return self.read_file(self.user_file)

    def write_user(self, content: str) -> None:
        self.user_file.write_text(content, encoding="utf-8")

    # -- layered instruction memory -----------------------------------------

    def instruction_layers(self, workspace: Path | None = None) -> list[dict[str, Any]]:
        root = workspace or self.workspace
        project_file = root / self._PROJECT_CLAUDE_FILE
        local_file = root / self._LOCAL_CLAUDE_FILE
        project_legacy = root / "SOUL.md"
        specs: list[dict[str, Any]] = [
            {
                "id": "user",
                "label": "User CLAUDE.md",
                "primary": self.user_claude_file,
                "fallback": self.user_file,
                "fallback_label": "legacy USER.md",
            },
            {
                "id": "project",
                "label": "Project CLAUDE.md",
                "primary": project_file,
                "fallback": project_legacy,
                "fallback_label": "legacy SOUL.md",
            },
            {
                "id": "local",
                "label": "Local CLAUDE.local.md",
                "primary": local_file,
                "fallback": None,
                "fallback_label": None,
            },
        ]
        layers: list[dict[str, Any]] = []
        for spec in specs:
            primary = spec["primary"]
            fallback = spec["fallback"]
            chosen = primary if isinstance(primary, Path) and primary.exists() else fallback
            content = self.read_file(chosen) if isinstance(chosen, Path) else ""
            source = "primary" if chosen == primary else ("legacy" if chosen else "missing")
            layers.append({
                "id": spec["id"],
                "label": spec["label"],
                "path": str(chosen or primary),
                "source": source,
                "fallback_label": spec["fallback_label"],
                "loaded": bool(content.strip()),
                "content": content,
            })
        return layers

    def read_graph(self) -> dict[str, Any]:
        if not self.graph_file.exists():
            return {
                "version": 1,
                "entities": [],
                "relations": [],
                "evidence": [],
            }
        try:
            data = json.loads(self.graph_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {
                "version": 1,
                "entities": [],
                "relations": [],
                "evidence": [],
            }
        return data if isinstance(data, dict) else {
            "version": 1,
            "entities": [],
            "relations": [],
            "evidence": [],
        }

    def write_graph(self, graph: dict[str, Any]) -> None:
        self.graph_file.write_text(
            json.dumps(graph, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _graph_default() -> dict[str, Any]:
        return {
            "version": 1,
            "entities": [],
            "relations": [],
            "evidence": [],
        }

    @staticmethod
    def _graph_slug(value: str) -> str:
        return re.sub(r"[^a-z0-9._/-]+", "-", value.lower()).strip("-") or "unknown"

    @classmethod
    def _upsert_graph_entity(
        cls,
        graph: dict[str, Any],
        *,
        entity_type: str,
        name: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        entity_id = f"{entity_type}:{cls._graph_slug(name)}"
        entities = graph.setdefault("entities", [])
        for entity in entities:
            if isinstance(entity, dict) and entity.get("id") == entity_id:
                if metadata:
                    entity.setdefault("metadata", {}).update(metadata)
                return entity_id
        entry: dict[str, Any] = {
            "id": entity_id,
            "type": entity_type,
            "name": name,
        }
        if metadata:
            entry["metadata"] = metadata
        entities.append(entry)
        return entity_id

    @staticmethod
    def _upsert_graph_relation(
        graph: dict[str, Any],
        *,
        source: str,
        relation_type: str,
        target: str,
    ) -> None:
        relations = graph.setdefault("relations", [])
        for relation in relations:
            if (
                isinstance(relation, dict)
                and relation.get("source") == source
                and relation.get("type") == relation_type
                and relation.get("target") == target
            ):
                return
        relations.append({
            "source": source,
            "type": relation_type,
            "target": target,
        })

    def _extract_graph_paths(self, content: str) -> list[str]:
        seen: set[str] = set()
        paths: list[str] = []
        for regex in (self._PATH_ENTITY_RE, self._INLINE_PATH_RE):
            for match in regex.finditer(content):
                value = match.group(1).strip()
                if "/" not in value or len(value) > 180:
                    continue
                if value.startswith(("http://", "https://")):
                    continue
                normalized = value.strip("./")
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    paths.append(normalized)
        return paths[:12]

    def _extract_issue_ids(self, content: str) -> list[str]:
        seen: set[str] = set()
        issues: list[str] = []
        for match in self._ISSUE_RE.finditer(content):
            value = match.group(1)
            if value not in seen:
                seen.add(value)
                issues.append(value)
        return issues[:8]

    def _extract_decisions(self, content: str) -> list[str]:
        seen: set[str] = set()
        decisions: list[str] = []
        for match in self._DECISION_RE.finditer(content):
            text = " ".join(match.group(1).split()).strip(" -:;,.")
            if len(text) < 4:
                continue
            if text not in seen:
                seen.add(text)
                decisions.append(text)
        return decisions[:6]

    def _extract_modules(self, content: str) -> list[str]:
        seen: set[str] = set()
        modules: list[str] = []
        for match in self._MODULE_RE.finditer(content):
            value = match.group(1).strip()
            if "/" not in value and "." not in value:
                continue
            if value.startswith(("http://", "https://")):
                continue
            normalized = value.strip("./")
            if normalized and normalized not in seen:
                seen.add(normalized)
                modules.append(normalized)
        return modules[:12]

    def update_graph_from_history_entry(
        self,
        *,
        timestamp: str,
        content: str,
        session_key: str | None = None,
    ) -> None:
        text = content.strip()
        if not text:
            return
        graph = self.read_graph()
        if not isinstance(graph, dict):
            graph = self._graph_default()
        summary = truncate_text(text.replace("\n", " "), 220)
        evidence_id = f"evidence:{self._graph_slug(timestamp + '-' + summary[:64])}"
        evidence = graph.setdefault("evidence", [])
        if not any(isinstance(item, dict) and item.get("id") == evidence_id for item in evidence):
            evidence.append({
                "id": evidence_id,
                "timestamp": timestamp,
                "summary": summary,
                "session_key": session_key,
            })

        session_entity_id: str | None = None
        if session_key:
            session_entity_id = self._upsert_graph_entity(
                graph,
                entity_type="session",
                name=session_key,
            )

        for path_value in self._extract_graph_paths(text):
            file_entity_id = self._upsert_graph_entity(
                graph,
                entity_type="file",
                name=path_value,
            )
            if session_entity_id:
                self._upsert_graph_relation(
                    graph,
                    source=session_entity_id,
                    relation_type="mentions",
                    target=file_entity_id,
                )

        for module_name in self._extract_modules(text):
            module_entity_id = self._upsert_graph_entity(
                graph,
                entity_type="module",
                name=module_name,
            )
            if session_entity_id:
                self._upsert_graph_relation(
                    graph,
                    source=session_entity_id,
                    relation_type="touches_module",
                    target=module_entity_id,
                )

        for issue_id in self._extract_issue_ids(text):
            issue_entity_id = self._upsert_graph_entity(
                graph,
                entity_type="issue",
                name=f"issue-{issue_id}",
                metadata={"number": issue_id},
            )
            self.append_topic_evidence(
                f"issue-{issue_id}",
                summary=f"Tracked issue #{issue_id}",
                evidence=summary,
                category="issue",
            )
            if session_entity_id:
                self._upsert_graph_relation(
                    graph,
                    source=session_entity_id,
                    relation_type="tracks_issue",
                    target=issue_entity_id,
                )
            self.append_topic_graph_links(
                f"issue-{issue_id}",
                entity_id=issue_entity_id,
                graph=graph,
                category="issue",
            )

        for decision_text in self._extract_decisions(text):
            decision_entity_id = self._upsert_graph_entity(
                graph,
                entity_type="decision",
                name=decision_text,
            )
            self.append_topic_evidence(
                decision_text,
                summary=decision_text,
                evidence=summary,
                category="decision",
            )
            if session_entity_id:
                self._upsert_graph_relation(
                    graph,
                    source=session_entity_id,
                    relation_type="records_decision",
                    target=decision_entity_id,
                )
            self.append_topic_graph_links(
                decision_text,
                entity_id=decision_entity_id,
                graph=graph,
                category="decision",
            )

        for topic_path in self.referenced_topic_files():
            topic_name = topic_path.stem
            if topic_name not in text and topic_path.name not in text:
                continue
            topic_entity_id = self._upsert_graph_entity(
                graph,
                entity_type="topic",
                name=topic_name,
            )
            if session_entity_id:
                self._upsert_graph_relation(
                    graph,
                    source=session_entity_id,
                    relation_type="touches_topic",
                    target=topic_entity_id,
                )
            self.append_topic_evidence(
                topic_name,
                summary=topic_name,
                evidence=summary,
                category="topic",
            )
            self.append_topic_graph_links(
                topic_name,
                entity_id=topic_entity_id,
                graph=graph,
                category="topic",
            )
        self.write_graph(graph)

    def graph_memory_context(self, *, max_items: int = 12) -> str:
        graph = self.read_graph()
        entities = graph.get("entities", []) if isinstance(graph.get("entities"), list) else []
        relations = graph.get("relations", []) if isinstance(graph.get("relations"), list) else []
        lines: list[str] = []
        for entity in entities[:max_items]:
            if not isinstance(entity, dict):
                continue
            name = str(entity.get("name") or entity.get("id") or "").strip()
            kind = str(entity.get("type") or "entity").strip()
            if name:
                lines.append(f"- entity [{kind}]: {name}")
        for relation in relations[:max_items]:
            if not isinstance(relation, dict):
                continue
            source = str(relation.get("source") or relation.get("from") or "").strip()
            target = str(relation.get("target") or relation.get("to") or "").strip()
            rel_type = str(relation.get("type") or relation.get("relation") or "related_to").strip()
            if source and target:
                lines.append(f"- relation [{rel_type}]: {source} -> {target}")
        return "\n".join(lines)

    def memory_audit(self, workspace: Path | None = None) -> dict[str, Any]:
        layers = self.instruction_layers(workspace)
        graph = self.read_graph()
        topic_files = self.list_topic_files()
        referenced_topics = self.referenced_topic_files()
        memory_text = self.read_memory()
        governance_text_parts = [memory_text]
        for path in topic_files[:50]:
            try:
                governance_text_parts.append(path.read_text(encoding="utf-8"))
            except OSError:
                continue
        governance_text = "\n".join(governance_text_parts).lower()
        confidence_counts = {
            "high": governance_text.count("[confidence:high]"),
            "medium": governance_text.count("[confidence:medium]"),
            "low": governance_text.count("[confidence:low]"),
        }
        source_hint_count = governance_text.count("source:")
        conflict_count = governance_text.count("[conflict]")
        rollback_hint_count = governance_text.count("[retracted]") + governance_text.count("[rollback]")
        subagent_files = sorted(self.subagent_dir.rglob("*.json"))
        all_subagent_entries: list[dict[str, Any]] = []
        status_counts: dict[str, int] = {}
        memory_policy_counts: dict[str, int] = {}
        label_counts: dict[str, int] = {}
        error_labels: list[str] = []
        session_counts: dict[str, int] = {}
        for path in subagent_files:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {}
            status_value = str(payload.get("status") or "unknown")
            memory_policy_value = str(payload.get("memory_policy") or "default")
            label_value = str(payload.get("label") or path.stem)
            session_value = str(payload.get("session_key") or path.parent.name or "unscoped")
            status_counts[status_value] = status_counts.get(status_value, 0) + 1
            memory_policy_counts[memory_policy_value] = memory_policy_counts.get(memory_policy_value, 0) + 1
            label_counts[label_value] = label_counts.get(label_value, 0) + 1
            session_counts[session_value] = session_counts.get(session_value, 0) + 1
            if status_value == "error" and label_value not in error_labels:
                error_labels.append(label_value)
            all_subagent_entries.append({
                "path": str(path.relative_to(self.workspace)),
                "label": label_value,
                "status": status_value,
                "memory_policy": memory_policy_value,
                "session_key": session_value,
                "updated_at": str(payload.get("updated_at") or ""),
            })
        recent_subagent_entries = all_subagent_entries[-5:]
        latest_subagent_activity_at = recent_subagent_entries[-1]["updated_at"] if recent_subagent_entries else ""
        latest_activity_freshness = "idle"
        if latest_subagent_activity_at:
            try:
                latest_dt = datetime.fromisoformat(latest_subagent_activity_at)
                age_seconds = max((datetime.now() - latest_dt).total_seconds(), 0.0)
                if age_seconds <= 300:
                    latest_activity_freshness = "hot"
                elif age_seconds <= 1800:
                    latest_activity_freshness = "warm"
                else:
                    latest_activity_freshness = "cold"
            except ValueError:
                latest_activity_freshness = "unknown"
        top_labels = [
            {"label": label, "count": count}
            for label, count in sorted(label_counts.items(), key=lambda item: (-item[1], item[0]))[:3]
        ]
        top_sessions: list[dict[str, Any]] = [
            {
                "session_key": session_key,
                "count": count,
                "share": round((count / max(1, len(subagent_files))) * 100, 1),
            }
            for session_key, count in sorted(session_counts.items(), key=lambda item: (-item[1], item[0]))[:3]
        ]
        multi_session_contention = len(session_counts) >= 2
        active_session_count = len(session_counts)
        dominant_session = top_sessions[0]["session_key"] if top_sessions else None
        dominant_session_share = float(top_sessions[0]["share"]) if top_sessions else 0.0
        if not top_sessions:
            contention_severity = "idle"
        elif not multi_session_contention:
            contention_severity = "isolated"
        elif dominant_session_share >= 70.0:
            contention_severity = "saturated"
        elif dominant_session_share >= 45.0:
            contention_severity = "contested"
        else:
            contention_severity = "shared"
        if contention_severity in {"idle", "isolated"}:
            recommended_action = "no throttling needed"
        elif contention_severity == "shared":
            recommended_action = "watch queue growth"
        elif contention_severity == "contested":
            recommended_action = "consider lowering fan-out"
        else:
            recommended_action = "rate-limit dominant session"
        return {
            "layers": [
                {
                    "id": layer["id"],
                    "label": layer["label"],
                    "path": layer["path"],
                    "source": layer["source"],
                    "loaded": layer["loaded"],
                    "fallback_label": layer["fallback_label"],
                    "source_detail": (
                        "primary"
                        if layer["source"] == "primary"
                        else (layer["fallback_label"] or "missing")
                    ),
                }
                for layer in layers
            ],
            "auto_memory": {
                "index_path": str(self.memory_file),
                "history_path": str(self.history_file),
                "loaded": bool(self.read_memory().strip()),
                "topic_dir": str(self.topic_dir),
                "topic_file_count": len(topic_files),
                "referenced_topic_count": len(referenced_topics),
                "governance": {
                    "confidence_counts": confidence_counts,
                    "source_hint_count": source_hint_count,
                    "conflict_count": conflict_count,
                    "rollback_hint_count": rollback_hint_count,
                    "review_required": conflict_count > 0 or confidence_counts["low"] > 0,
                },
            },
            "graph": {
                "path": str(self.graph_file),
                "entity_count": len(graph.get("entities", [])) if isinstance(graph.get("entities"), list) else 0,
                "relation_count": len(graph.get("relations", [])) if isinstance(graph.get("relations"), list) else 0,
                "evidence_count": len(graph.get("evidence", [])) if isinstance(graph.get("evidence"), list) else 0,
            },
            "subagent_memory": {
                "dir": str(self.subagent_dir),
                "entry_count": len(subagent_files),
                "loaded": bool(subagent_files),
                "recent_entries": recent_subagent_entries,
                "status_counts": status_counts,
                "memory_policy_counts": memory_policy_counts,
                "top_labels": top_labels,
                "top_sessions": top_sessions,
                "error_labels": error_labels[:3],
                "active_session_count": active_session_count,
                "multi_session_contention": multi_session_contention,
                "dominant_session": dominant_session,
                "dominant_session_share": dominant_session_share,
                "contention_severity": contention_severity,
                "recommended_action": recommended_action,
                "latest_activity_at": latest_subagent_activity_at,
                "latest_activity_freshness": latest_activity_freshness,
            },
        }

    def write_subagent_memory(
        self,
        *,
        session_key: str | None,
        task_id: str,
        label: str,
        memory_policy: str,
        inherited_memory_layers: list[str],
        task: str,
        result: str,
        status: str,
    ) -> Path:
        session_slug = self._graph_slug(session_key or "unscoped")
        target_dir = ensure_dir(self.subagent_dir / session_slug)
        target_path = target_dir / f"{task_id}.json"
        payload = {
            "task_id": task_id,
            "session_key": session_key,
            "label": label,
            "memory_policy": memory_policy,
            "inherited_memory_layers": list(inherited_memory_layers),
            "task": truncate_text(task, 2000),
            "result": truncate_text(result, 4000),
            "status": status,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        target_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return target_path

    # -- context injection (used by context.py) ------------------------------

    def get_memory_context(self) -> str:
        long_term = self.read_memory()
        topics = self.topic_memory_context()
        graph = self.graph_memory_context()
        sections: list[str] = []
        if long_term:
            sections.append(f"## Long-term Memory Index\n{long_term}")
        if topics:
            sections.append(f"## Topic Memory\n{topics}")
        if graph:
            sections.append(f"## Knowledge Graph Memory\n{graph}")
        return "\n\n".join(sections)

    def _recall_terms(self, query: str | None) -> list[str]:
        if not query:
            return []
        cleaned = re.sub(r"[^\w\u4e00-\u9fff@/._-]+", " ", query.lower())
        seen: set[str] = set()
        terms: list[str] = []
        for token in re.split(r"[\s,，、;；:：]+", cleaned):
            term = token.strip().strip("._-")
            if len(term) < 2 or term in _MEMORY_RECALL_STOP_WORDS or term in seen:
                continue
            seen.add(term)
            terms.append(term)
            if len(terms) >= 16:
                break
        return terms

    def _recall_line_matches(self, line: str, terms: list[str]) -> list[str]:
        lowered = line.lower()
        return [term for term in terms if term and term in lowered]

    def _score_recall_line(self, line: str, terms: list[str], section_label: str) -> float:
        matches = self._recall_line_matches(line, terms)
        if not matches:
            return 0.0
        score = 0.0
        for term in matches:
            score += max(2.0, min(8.0, float(len(term))))
        if line.startswith("- "):
            score += 1.5
        elif line.startswith("#"):
            score += 1.0
        section_lower = section_label.lower()
        if "project" in section_lower and any(term in {"project", "repo", "otto", "mira"} for term in terms):
            score += 1.5
        if "session" in section_lower and any(term in {"session", "history"} for term in terms):
            score += 1.5
        if "topic" in section_lower and any(term in {"topic", "decision", "issue"} for term in terms):
            score += 1.0
        return score

    def _recall_block(
        self,
        section_label: str,
        content: str,
        terms: list[str],
        *,
        max_items: int,
    ) -> tuple[float, str]:
        scored: list[tuple[float, int, str]] = []
        for index, raw_line in enumerate(content.splitlines()):
            line = raw_line.strip()
            if not line or line == "(empty)":
                continue
            score = self._score_recall_line(line, terms, section_label)
            if score <= 0:
                continue
            scored.append((score, index, line))
        if not scored:
            return 0.0, ""
        scored.sort(key=lambda item: (-item[0], item[1], len(item[2])))
        selected_items = scored[:max_items]
        selected = [
            (
                line if line.startswith("- ") else f"- {line}"
            ) + f" (matches: {', '.join(self._recall_line_matches(line, terms)[:4])})"
            for _score, _index, line in selected_items
        ]
        if not selected:
            return 0.0, ""
        block_score = sum(score for score, _index, _line in selected_items)
        return block_score, f"## {section_label}\n" + "\n".join(selected)

    def memory_recall_context(
        self,
        *,
        query: str | None = None,
        recent_history: Sequence[Mapping[str, Any]] | None = None,
        max_sections: int = 4,
        max_items_per_section: int = 3,
        max_chars: int = 1200,
    ) -> str:
        terms = self._recall_terms(query)
        if not terms:
            return ""

        sections: list[tuple[str, str]] = [
            ("Long-term Memory", self.read_memory()),
            ("Topic Memory", self.topic_memory_context()),
            ("Knowledge Graph Memory", self.graph_memory_context()),
        ]
        if recent_history:
            recent_lines = []
            for entry in recent_history:
                content = str(entry.get("content") or "").strip()
                if not content:
                    continue
                timestamp = str(entry.get("timestamp") or "").strip()
                if timestamp:
                    recent_lines.append(f"- [{timestamp}] {content}")
                else:
                    recent_lines.append(f"- {content}")
            if recent_lines:
                sections.append(("Recent History", "\n".join(recent_lines)))

        blocks: list[tuple[float, int, str]] = []
        used_chars = 0
        for index, (label, content) in enumerate(sections):
            score, block = self._recall_block(label, content, terms, max_items=max_items_per_section)
            if not block:
                continue
            if used_chars + len(block) > max_chars:
                break
            blocks.append((score, index, block))
            used_chars += len(block)
            if len(blocks) >= max_sections:
                break

        blocks.sort(key=lambda item: (-item[0], item[1]))
        return "\n\n".join(block for _score, _index, block in blocks)

    # -- history.jsonl — append-only, JSONL format ---------------------------

    def append_history(
        self,
        entry: str,
        *,
        max_chars: int | None = None,
        session_key: str | None = None,
    ) -> int:
        """Append *entry* to history.jsonl and return its auto-incrementing cursor.

        Entries are passed through `strip_think` to drop template-level leaks
        (e.g. unclosed `<think` prefixes, `<channel|>` markers) before being
        persisted. If the cleaned content is empty but the raw entry wasn't,
        the record is persisted with an empty string rather than falling back
        to the raw leak — otherwise `strip_think`'s guarantees would be
        undone by history replay / consolidation downstream.

        A defensive cap (*max_chars*, default ``_HISTORY_ENTRY_HARD_CAP``) is
        applied as a final safety net: individual callers should cap their own
        content more tightly; this default only exists to catch unintentional
        large writes (e.g. an LLM echoing its input back as a "summary").
        """
        limit = max_chars if max_chars is not None else _HISTORY_ENTRY_HARD_CAP
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        raw = entry.rstrip()
        if len(raw) > limit:
            if not self._oversize_logged:
                self._oversize_logged = True
                logger.warning(
                    "history entry exceeds {} chars ({}); truncating. "
                    "Usually means a caller forgot its own cap; "
                    "further occurrences suppressed.",
                    limit, len(raw),
                )
            raw = truncate_text(raw, limit)
        content = strip_think(raw)
        # Cursor allocation and the append must be atomic: concurrent writers
        # could otherwise read the same current cursor and emit duplicates.
        with self._append_lock:
            cursor = self._next_cursor()
            if raw and not content:
                logger.debug(
                    "history entry {} stripped to empty (likely template leak); "
                    "persisting empty content to avoid re-polluting context",
                    cursor,
                )
            record = {"cursor": cursor, "timestamp": ts, "content": content}
            if session_key:
                record["session_key"] = session_key
            with open(self.history_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._cursor_file.write_text(str(cursor), encoding="utf-8")
            self.update_graph_from_history_entry(
                timestamp=ts,
                content=content,
                session_key=session_key,
            )
        return cursor

    @staticmethod
    def _valid_cursor(value: Any) -> int | None:
        """Non-negative int cursors only; reject bool (``isinstance(True, int)`` is True)."""
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return None
        return int(value)

    def _iter_valid_entries(self) -> Iterator[tuple[dict[str, Any], int]]:
        """Yield ``(entry, cursor)`` for well-formed entries; warn once on corruption."""
        poisoned: Any = None
        malformed_cursor: int | None = None
        for entry in self._read_entries():
            raw = entry.get("cursor")
            if raw is None:
                continue
            cursor = self._valid_cursor(raw)
            if cursor is None:
                poisoned = raw
                continue
            if not self._valid_history_payload(entry):
                malformed_cursor = cursor
                continue
            yield entry, cursor
        if poisoned is not None and not self._corruption_logged:
            self._corruption_logged = True
            logger.warning(
                "history.jsonl contains an invalid cursor ({!r}); dropping it. "
                "Usually caused by an external writer; further occurrences suppressed.",
                poisoned,
            )
        if malformed_cursor is not None and not self._malformed_entry_logged:
            self._malformed_entry_logged = True
            logger.warning(
                "history.jsonl contains a malformed entry at cursor {}; dropping it. "
                "Usually caused by an external writer; further occurrences suppressed.",
                malformed_cursor,
            )

    @staticmethod
    def _valid_history_payload(entry: dict[str, Any]) -> bool:
        if not isinstance(entry.get("timestamp"), str):
            return False
        if not isinstance(entry.get("content"), str):
            return False
        session_key = entry.get("session_key")
        return session_key is None or isinstance(session_key, str)

    def _read_cursor_counter(self) -> int | None:
        """Return the persisted cursor counter when it is usable."""
        if not self._cursor_file.exists():
            return None
        with suppress(ValueError, OSError):
            cursor = int(self._cursor_file.read_text(encoding="utf-8").strip())
            if cursor >= 0:
                return cursor
        return None

    def _next_cursor(self) -> int:
        """Read the current cursor counter and return the next value."""
        cursor_counter = self._read_cursor_counter()
        last = self._read_last_entry() or {}
        last_cursor = self._valid_cursor(last.get("cursor"))
        if cursor_counter is not None:
            if last_cursor is not None:
                return max(cursor_counter, last_cursor) + 1
            max_history_cursor = max((c for _, c in self._iter_valid_entries()), default=0)
            return max(cursor_counter, max_history_cursor) + 1

        # Fast path: trust the tail when intact.  Otherwise scan the whole
        # file and take ``max`` — that stays correct even if the monotonic
        # invariant was broken by external writes.
        if last_cursor is not None:
            return last_cursor + 1
        return max((c for _, c in self._iter_valid_entries()), default=0) + 1

    def read_unprocessed_history(self, since_cursor: int) -> list[dict[str, Any]]:
        """Return history entries with a valid cursor > *since_cursor*."""
        return [e for e, c in self._iter_valid_entries() if c > since_cursor]

    @classmethod
    def _is_internal_history_session(cls, session_key: str | None) -> bool:
        if not session_key:
            return False
        return (
            session_key in cls._INTERNAL_HISTORY_SESSION_KEYS
            or session_key.startswith(cls._INTERNAL_HISTORY_SESSION_PREFIXES)
        )

    def read_recent_history_for_prompt(
        self,
        since_cursor: int,
        *,
        session_key: str | None,
        unified_session: bool = False,
    ) -> list[dict[str, Any]]:
        """Return unprocessed history entries safe to inject into a turn prompt."""
        entries = self.read_unprocessed_history(since_cursor=since_cursor)
        if session_key is None:
            return entries
        if not unified_session:
            return [e for e in entries if e.get("session_key") == session_key]

        return [
            entry
            for entry in entries
            if (entry_session := entry.get("session_key")) == session_key
            or not self._is_internal_history_session(entry_session)
        ]

    def compact_history(self) -> None:
        """Drop oldest entries if the file exceeds *max_history_entries*."""
        if self.max_history_entries <= 0:
            return
        entries = self._read_entries()
        if len(entries) <= self.max_history_entries:
            return
        kept = entries[-self.max_history_entries:]
        self._write_entries(kept)

    # -- JSONL helpers -------------------------------------------------------

    def _read_entries(self) -> list[dict[str, Any]]:
        """Read all entries from history.jsonl."""
        entries: list[dict[str, Any]] = []
        with suppress(FileNotFoundError), open(self.history_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        parsed = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(parsed, dict):
                        entries.append(parsed)

        return entries

    def _read_last_entry(self) -> dict[str, Any] | None:
        """Read the last entry from the JSONL file efficiently."""
        try:
            with open(self.history_file, "rb") as f:
                f.seek(0, 2)
                size = f.tell()
                if size == 0:
                    return None
                read_size = min(size, 4096)
                f.seek(size - read_size)
                data = f.read().decode("utf-8")
                lines = [line for line in data.split("\n") if line.strip()]
                if not lines:
                    return None
                parsed = json.loads(lines[-1])
                return parsed if isinstance(parsed, dict) else None
        except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
            return None

    def _write_entries(self, entries: list[dict[str, Any]]) -> None:
        """Overwrite history.jsonl with the given entries (atomic write)."""
        tmp_path = self.history_file.with_suffix(self.history_file.suffix + ".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                for entry in entries:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.history_file)

            # fsync the directory so the rename is durable.
            # On Windows, opening a directory with O_RDONLY raises
            # PermissionError — skip the dir sync there (NTFS
            # journals metadata synchronously).
            with suppress(PermissionError):
                fd = os.open(str(self.history_file.parent), os.O_RDONLY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise

    # -- dream cursor --------------------------------------------------------

    def get_last_dream_cursor(self) -> int:
        if self._dream_cursor_file.exists():
            with suppress(ValueError, OSError):
                return int(self._dream_cursor_file.read_text(encoding="utf-8").strip())
        return 0

    def set_last_dream_cursor(self, cursor: int) -> None:
        self._dream_cursor_file.write_text(str(cursor), encoding="utf-8")

    def get_latest_cursor(self) -> int:
        return max(self._next_cursor() - 1, 0)

    @property
    def dream_prompt_file(self) -> Path:
        return workspace_prompt_file(self.workspace, "dream")

    def has_dream_prompt_override(self) -> bool:
        return has_workspace_prompt_override(self.dream_prompt_file)

    @staticmethod
    def default_dream_prompt() -> str:
        from mira.agent.skills import BUILTIN_SKILLS_DIR

        return render_template(
            "agent/dream.md",
            strip=True,
            skill_creator_path=str(BUILTIN_SKILLS_DIR / "skill-creator" / "SKILL.md"),
        )

    def _dream_template(self) -> str:
        text, original_chars = load_workspace_prompt_override(self.dream_prompt_file)
        if text is not None:
            if (
                original_chars > WORKSPACE_PROMPT_MAX_CHARS
                and not self._dream_prompt_oversize_logged
            ):
                self._dream_prompt_oversize_logged = True
                logger.warning(
                    "workspace Dream prompt exceeds {} chars ({}); truncating. "
                    "Further occurrences suppressed.",
                    WORKSPACE_PROMPT_MAX_CHARS, original_chars,
                )
            return text
        return self.default_dream_prompt()

    def build_dream_prompt(self, *, max_entries: int = 20) -> tuple[str, int] | None:
        """Build the Dream prompt with unprocessed history context.

        Returns ``(prompt, last_cursor)`` or ``None`` if nothing to process.

        The current contents of the durable memory files (SOUL.md, USER.md,
        memory/MEMORY.md) are embedded so the model edits the real files rather
        than a stale mental model — eliminating a class of failed/out-of-bounds
        edits that previously produced hallucinated audit records.
        """
        last_cursor = self.get_last_dream_cursor()
        entries = self.read_unprocessed_history(since_cursor=last_cursor)
        if not entries:
            return None

        batch = entries[:max_entries]
        history_text = "\n".join(
            f"[{e['timestamp']}] {truncate_text(e['content'], 500)}"
            for e in batch
        )
        template = self._dream_template()
        files_section = self._render_current_memory_files()
        prompt = (
            f"{template}\n\n{files_section}\n\n"
            f"## Conversation History\n{history_text}"
        )
        return (prompt, batch[-1]["cursor"])

    def _render_current_memory_files(self) -> str:
        """Render the durable memory files' current contents for the Dream prompt.

        Missing files render as ``(empty)``; oversized files are capped. The
        section is the ground truth the model must edit against.
        """
        files = [
            ("SOUL.md", self.soul_file),
            ("USER.md", self.user_file),
            ("memory/MEMORY.md", self.memory_file),
        ]
        blocks = []
        for label, path in files:
            try:
                content = path.read_text(encoding="utf-8") if path.exists() else ""
            except OSError:
                content = ""
            if len(content) > self._DREAM_FILE_EMBED_CAP:
                content = truncate_text(content, self._DREAM_FILE_EMBED_CAP) + "\n...[truncated]"
            blocks.append(f"### {label}\n{content}" if content.strip() else f"### {label}\n(empty)")
        return "## Current Memory Files\n" + "\n\n".join(blocks)

    def dream_content_diff(self) -> str:
        """Structured summary of uncommitted changes to the durable memory files.

        Returns "" when git is unavailable or no content file changed. This is
        the ground-truth input for diff-grounded Dream commit messages.
        """
        if not self._git.is_initialized():
            return ""
        return self._git.summarize_working_tree(list(self._DREAM_CONTENT_PATHS))

    def build_dream_tools(self) -> Any:
        """Build the restricted tool registry used by Dream runs."""
        from mira.agent.skills import BUILTIN_SKILLS_DIR
        from mira.agent.tools.apply_patch import ApplyPatchTool
        from mira.agent.tools.file_state import FileStates
        from mira.agent.tools.filesystem import EditFileTool, ReadFileTool, WriteFileTool
        from mira.agent.tools.registry import ToolRegistry

        tools = ToolRegistry()
        file_states = FileStates()
        workspace = self.workspace
        skills_dir = workspace / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)

        extra_read = [BUILTIN_SKILLS_DIR] if BUILTIN_SKILLS_DIR.exists() else None
        editable_files = [self.memory_file, self.soul_file, self.user_file]

        tools.register(ReadFileTool(  # type: ignore[abstract]
            workspace=workspace,
            allowed_dir=workspace,
            extra_read_allowed_dirs=extra_read,
            file_states=file_states,
        ))
        tools.register(EditFileTool(  # type: ignore[abstract]
            workspace=workspace,
            allowed_dir=skills_dir,
            extra_write_allowed_files=editable_files,
            file_states=file_states,
        ))
        tools.register(ApplyPatchTool(  # type: ignore[abstract]
            workspace=workspace,
            allowed_dir=skills_dir,
            extra_write_allowed_files=editable_files,
            file_states=file_states,
        ))
        tools.register(WriteFileTool(  # type: ignore[abstract]
            workspace=workspace,
            allowed_dir=skills_dir,
            file_states=file_states,
        ))
        return tools

    @staticmethod
    def dream_run_completed(
        resp: object | None,
        *,
        had_tool_errors: bool = False,
    ) -> bool:
        return memory_dream.dream_run_completed(resp, had_tool_errors=had_tool_errors)

    # -- message formatting utility ------------------------------------------

    @staticmethod
    def _format_messages(messages: list[dict[str, Any]]) -> str:
        lines = []
        for message in messages:
            if not message.get("content"):
                continue
            tools = f" [tools: {', '.join(message['tools_used'])}]" if message.get("tools_used") else ""
            lines.append(
                f"[{message.get('timestamp', '?')[:16]}] {message['role'].upper()}{tools}: {message['content']}"
            )
        return "\n".join(lines)

    def raw_archive(
        self,
        messages: list[dict[str, Any]],
        *,
        max_chars: int | None = None,
        session_key: str | None = None,
    ) -> None:
        """Fallback: dump raw messages to history.jsonl without LLM summarization."""
        limit = max_chars if max_chars is not None else _RAW_ARCHIVE_MAX_CHARS
        formatted = truncate_text(
            self._format_messages(public_history_messages(messages)),
            limit,
        )
        self.append_history(
            f"[RAW] {len(messages)} messages\n"
            f"{formatted}",
            session_key=session_key,
        )
        logger.warning(
            "Memory consolidation degraded: raw-archived {} messages", len(messages)
        )

    # ------------------------------------------------------------------
    # Dream helpers
    # ------------------------------------------------------------------

    @staticmethod
    def dream_session_key() -> str:
        return memory_dream.dream_session_key()

    @staticmethod
    def build_dream_commit_message(prefix: str, diff_body: str | None) -> str:
        return memory_dream.build_dream_commit_message(prefix, diff_body)

    @staticmethod
    def prune_dream_sessions(sessions_dir: Path, *, keep: int = 10) -> None:
        memory_dream.prune_dream_sessions(sessions_dir, keep=keep)

# Individual history.jsonl writers cap their own payloads tightly; the
# _HISTORY_ENTRY_HARD_CAP at append_history() is a belt-and-suspenders default
# that catches any new caller that forgot to set its own cap.
_RAW_ARCHIVE_MAX_CHARS = 16_000       # fallback dump (LLM failed)
_ARCHIVE_SUMMARY_MAX_CHARS = 8_000    # LLM-produced consolidation summary
_HISTORY_ENTRY_HARD_CAP = 64_000      # emergency cap in append_history
