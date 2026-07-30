#!/usr/bin/env python3
"""Report Mira package size and the largest contributors."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_BUDGET_MB = 119.0


@dataclass(frozen=True)
class SizeRow:
    name: str
    bytes: int
    mb: float


def _mb(value: int) -> float:
    return round(value / 1024 / 1024, 2)


def _category(path: Path) -> str:
    parts = {part.lower() for part in path.parts}
    suffix = path.suffix.lower()
    if "__pycache__" in parts or ".pytest_cache" in parts or ".ruff_cache" in parts:
        return "cache"
    if "tests" in parts or "docs" in parts or "examples" in parts:
        return "docs-tests"
    if "site-packages" in parts or "python" in parts or ".venv" in parts:
        return "python-runtime"
    if "dist" in parts and {"js", "css", "map", "woff", "woff2"} & {suffix.lstrip(".")}:
        return "webui-assets"
    if suffix in {".dylib", ".so", ".dll", ".exe", ".pyd"}:
        return "native-binaries"
    return "other"


def iter_files(root: Path):
    if root.is_file():
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            name
            for name in dirnames
            if name not in {".git", "node_modules", ".mypy_cache", ".pytest_cache", ".ruff_cache"}
        ]
        base = Path(dirpath)
        for filename in filenames:
            yield base / filename


def build_report(root: Path, budget_mb: float, top: int) -> dict:
    root = root.resolve()
    category_bytes: dict[str, int] = {}
    file_rows: list[SizeRow] = []
    seen_inodes: set[tuple[int, int]] = set()

    for path in iter_files(root):
        try:
            stat = path.stat()
        except OSError:
            continue
        inode_key = (stat.st_dev, stat.st_ino)
        if inode_key in seen_inodes:
            continue
        seen_inodes.add(inode_key)
        size = stat.st_size
        rel = path.relative_to(root) if path != root else path.name
        category_bytes[_category(rel)] = category_bytes.get(_category(rel), 0) + size
        file_rows.append(SizeRow(str(rel), size, _mb(size)))

    total = sum(row.bytes for row in file_rows)
    categories = [
        SizeRow(name, size, _mb(size))
        for name, size in sorted(category_bytes.items(), key=lambda item: item[1], reverse=True)
    ]
    largest = sorted(file_rows, key=lambda row: row.bytes, reverse=True)[:top]

    return {
        "path": str(root),
        "total_bytes": total,
        "total_mb": _mb(total),
        "budget_mb": budget_mb,
        "within_budget": _mb(total) <= budget_mb,
        "categories": [asdict(row) for row in categories],
        "top": [asdict(row) for row in largest],
    }


def print_text(report: dict) -> None:
    status = "OK" if report["within_budget"] else "OVER BUDGET"
    print(f"Mira package size: {report['total_mb']} MB / {report['budget_mb']} MB [{status}]")
    print("\nCategories:")
    for row in report["categories"]:
        print(f"  {row['mb']:>8.2f} MB  {row['name']}")
    print("\nLargest files:")
    for row in report["top"]:
        print(f"  {row['mb']:>8.2f} MB  {row['name']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="Package file or directory to audit")
    parser.add_argument("--budget-mb", type=float, default=DEFAULT_BUDGET_MB)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    parser.add_argument("--fail-on-over-budget", action="store_true")
    args = parser.parse_args()

    report = build_report(args.path, args.budget_mb, args.top)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_text(report)
    return 1 if args.fail_on_over_budget and not report["within_budget"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
