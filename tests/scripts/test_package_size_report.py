from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_report_module():
    script = Path(__file__).resolve().parents[2] / "scripts" / "package_size_report.py"
    spec = importlib.util.spec_from_file_location("package_size_report", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_package_size_report_groups_files(tmp_path: Path):
    module = load_report_module()
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "app.js").write_bytes(b"x" * 1024)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "fixture.txt").write_bytes(b"y" * 2048)

    report = module.build_report(tmp_path, budget_mb=1, top=1)

    assert report["within_budget"] is True
    assert report["total_bytes"] == 3072
    assert report["top"][0]["name"] == "tests/fixture.txt"
    assert {row["name"] for row in report["categories"]} == {"docs-tests", "webui-assets"}
