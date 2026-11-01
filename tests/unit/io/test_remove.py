"""``agentprov.io.remove`` (D-1011, CI round 7): deleting read-only store files where the host refuses to, as Windows
does (``os.unlink`` is made to refuse a file without its owner's write bit)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from agentprov.io import remove


@pytest.fixture
def windows_read_only(monkeypatch: pytest.MonkeyPatch) -> None:
    real = os.unlink

    def unlink(path, *, dir_fd=None):  # type: ignore[no-untyped-def]
        if not os.stat(path, dir_fd=dir_fd, follow_symlinks=False).st_mode & 0o200:
            raise PermissionError(13, "Access is denied", os.fsdecode(path))
        return real(path, dir_fd=dir_fd)

    monkeypatch.setattr(os, "unlink", unlink)


def _tree(root: Path) -> Path:
    (root / "objects" / "ab").mkdir(parents=True)
    for name in ("ab/one.json", "ab/two.json"):
        path = root / "objects" / name
        path.write_bytes(b"x")
        os.chmod(path, 0o444)
    return root


def test_unlink_clears_the_read_only_bit(tmp_path: Path, windows_read_only: None) -> None:
    path = _tree(tmp_path / "s") / "objects" / "ab" / "one.json"
    with pytest.raises(PermissionError):
        os.unlink(path)
    remove.unlink(path)
    assert not path.exists()


@pytest.mark.parametrize("ignore_errors", [False, True])
def test_rmtree_removes_a_tree_of_read_only_files(tmp_path: Path, windows_read_only: None, ignore_errors: bool) -> None:
    root = _tree(tmp_path / "s")
    remove.rmtree(root, ignore_errors=ignore_errors)
    assert not root.exists()


def test_rmtree_raises_or_skips_what_still_fails(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        remove.rmtree(tmp_path / "absent")
    remove.rmtree(tmp_path / "absent", ignore_errors=True)


@pytest.mark.skipif(os.name != "nt", reason="the read-only attribute shared by hard links is Windows behaviour")
def test_deleting_a_hard_link_leaves_the_other_link_read_only(tmp_path: Path) -> None:
    """A scratch tree hard-links the source corpus's read-only objects: deleting the scratch link must not make the
    source's object writable (Windows keeps one read-only attribute per file, not per link)."""
    source = tmp_path / "source.json"
    source.write_bytes(b"x")
    os.chmod(source, 0o444)
    link = tmp_path / "scratch" / "link.json"
    link.parent.mkdir()
    os.link(source, link)
    remove.rmtree(link.parent)
    assert not link.parent.exists() and source.read_bytes() == b"x"
    assert not source.stat().st_mode & 0o222
