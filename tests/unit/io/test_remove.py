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


@pytest.mark.skipif(os.name != "posix" or os.geteuid() == 0, reason="a read-only directory is POSIX, and root ignores it")
def test_a_refused_unlink_leaves_a_hard_linked_object_read_only(tmp_path: Path) -> None:
    """AU-RT-2: when the unlink is refused for another reason (here: the directory is read-only) the shared inode keeps
    its mode, after both :func:`remove.unlink` and :func:`remove.rmtree`. :func:`remove.rmtree` removes the read-only
    directory's entries (a sealed corpus is read-only) by giving the directory, never the file, its write bit back."""
    source = tmp_path / "source.json"
    source.write_bytes(b"x")
    os.chmod(source, 0o444)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    os.link(source, scratch / "link.json")
    os.chmod(scratch, 0o555)
    try:
        with pytest.raises(PermissionError):
            remove.unlink(scratch / "link.json")
        assert source.stat().st_mode & 0o777 == 0o444
        remove.rmtree(scratch, ignore_errors=True)
        assert not scratch.exists() and source.stat().st_mode & 0o777 == 0o444
    finally:
        if scratch.exists():
            os.chmod(scratch, 0o700)


@pytest.mark.skipif(os.name != "posix" or os.geteuid() == 0, reason="a read-only directory is POSIX, and root ignores it")
def test_rmtree_of_a_read_only_tree_changes_nothing_above_it(tmp_path: Path) -> None:
    """A read-only tree (a sealed corpus, :mod:`agentprov.corpus.protect`) is removed whole; its hard-linked objects keep
    their mode; a read-only directory above the removed tree is not opened, so removing the tree fails there."""
    source = tmp_path / "source.json"
    source.write_bytes(b"x")
    os.chmod(source, 0o444)
    outer = tmp_path / "outer"
    tree = outer / "corpus"
    (tree / "raw" / "objects" / "ab").mkdir(parents=True)
    (tree / "corpus.json").write_bytes(b"{}")
    os.link(source, tree / "raw" / "objects" / "ab" / "link.json")
    for path in (tree / "corpus.json", tree / "raw" / "objects" / "ab", tree / "raw" / "objects", tree / "raw", tree):
        os.chmod(path, 0o444 if path.is_file() else 0o555)
    os.chmod(outer, 0o555)
    try:
        with pytest.raises(PermissionError):
            remove.rmtree(tree)  # its entries go; the tree itself is an entry of the read-only `outer`
        assert tree.is_dir() and not any(tree.iterdir())
        assert outer.stat().st_mode & 0o777 == 0o555
        os.chmod(outer, 0o755)
        remove.rmtree(tree)
        assert not tree.exists() and source.stat().st_mode & 0o777 == 0o444
    finally:
        os.chmod(outer, 0o755)


def test_a_refused_unlink_of_a_writable_file_is_not_retried(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AU-RT-2: a writable file whose unlink is refused (a sharing violation on Windows) is not chmodded."""
    path = tmp_path / "open.json"
    path.write_bytes(b"x")
    os.chmod(path, 0o640)

    def refuse(path, *, dir_fd=None):  # type: ignore[no-untyped-def]
        raise PermissionError(32, "The process cannot access the file", os.fsdecode(path))

    monkeypatch.setattr(os, "unlink", refuse)
    with pytest.raises(PermissionError):
        remove.unlink(path)
    assert path.stat().st_mode & 0o777 == 0o640


@pytest.mark.parametrize("ignore_errors", [False, True])
def test_rmtree_keeps_the_refusal_of_a_symlink_and_never_touches_its_target(tmp_path: Path, ignore_errors: bool) -> None:
    """AU-RT-1: shutil.rmtree refuses a symlink root; the retry must not chmod the target and call it removed."""
    target = tmp_path / "target"
    target.mkdir()
    (target / "f").write_bytes(b"x")
    os.chmod(target, 0o755)
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("this host cannot create a symlink")
    if ignore_errors:
        remove.rmtree(link, ignore_errors=True)
    else:
        with pytest.raises(OSError):
            remove.rmtree(link)
    assert link.is_symlink() and (target / "f").exists()
    assert target.stat().st_mode & 0o777 == 0o755


@pytest.mark.skipif(os.name != "posix" or os.geteuid() == 0, reason="a mode-000 directory is POSIX, and root reads it")
def test_rmtree_skips_a_directory_it_cannot_open(tmp_path: Path) -> None:
    """AU-RT-1: a subdirectory that cannot be opened is skipped (ignore_errors) or raised as shutil raises it, never a
    TypeError from re-calling ``os.open`` without its flags."""
    top = tmp_path / "top"
    sub = top / "sub"
    sub.mkdir(parents=True)
    (sub / "x").write_bytes(b"x")
    os.chmod(sub, 0)
    try:
        remove.rmtree(top, ignore_errors=True)
        assert sub.exists()
        with pytest.raises(PermissionError):
            remove.rmtree(top)
        assert sub.stat().st_mode & 0o777 == 0
    finally:
        os.chmod(sub, 0o700)


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
