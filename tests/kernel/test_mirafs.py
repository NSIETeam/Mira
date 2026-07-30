import pytest

from mira.kernel.fs import MiraFS, MiraFSError


def test_mirafs_exposes_root_namespaces(tmp_path) -> None:
    fs = MiraFS(workspace=tmp_path, tool_names=lambda: ["read_file", "exec"])

    assert fs.list("/") == ["mem", "ctx", "tool"]
    assert fs.list("/tool") == ["exec", "read_file"]
    assert '"exec"' in fs.read_text("/tool")


def test_mirafs_writes_and_reads_mem_namespace(tmp_path) -> None:
    fs = MiraFS(workspace=tmp_path)

    node = fs.write_text("/mem/knowledge/note.md", "hello")

    assert node.physical_path == tmp_path / "memory" / "knowledge" / "note.md"
    assert fs.read_text("/mem/knowledge/note.md") == "hello"
    assert fs.list("/mem/knowledge") == ["note.md"]


def test_mirafs_maps_ctx_read_only(tmp_path) -> None:
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    (sessions / "abc.jsonl").write_text('{"_type":"metadata"}\n', encoding="utf-8")
    fs = MiraFS(workspace=tmp_path)

    assert fs.list("/ctx") == ["abc.jsonl"]
    assert "metadata" in fs.read_text("/ctx/abc.jsonl")
    with pytest.raises(MiraFSError, match="limited to /mem"):
        fs.write_text("/ctx/abc.jsonl", "nope")


def test_mirafs_rejects_escape_paths(tmp_path) -> None:
    fs = MiraFS(workspace=tmp_path)

    with pytest.raises(MiraFSError):
        fs.resolve("/mem/../secret")
