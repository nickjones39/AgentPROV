"""``agentprov.testing.fs_guard`` (K.3.2): any change below a guarded tree fails; reading does not."""

from __future__ import annotations

import os

import pytest

from agentprov.testing import fs_guard


def tree(tmp_path):
    root = tmp_path / "t"
    (root / "a" / "b").mkdir(parents=True)
    (root / "a" / "b" / "f.txt").write_bytes(b"one")
    (root / "g.bin").write_bytes(b"\0\1")
    os.symlink("a/b/f.txt", root / "link")
    return root


def test_reading_changes_nothing(tmp_path):
    root = tree(tmp_path)
    with fs_guard.unchanged(root) as before:
        (root / "a" / "b" / "f.txt").read_bytes()
        list(os.scandir(root))
    assert set(before.entries) == {"", "a", "a/b", "a/b/f.txt", "g.bin", "link"}
    assert before.entries["link"].kind == "link" and before.entries["link"].target == "a/b/f.txt"


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (lambda r: (r / "g.bin").write_bytes(b"\0\2"), "changed g.bin"),  # same size, other bytes
        (lambda r: (r / "new").write_bytes(b""), "added new"),
        (lambda r: (r / "g.bin").unlink(), "removed g.bin"),
        (lambda r: os.chmod(r / "g.bin", 0o444), "changed g.bin (mode)"),
        (lambda r: os.utime(r / "g.bin", ns=(0, 0)), "changed g.bin (mtime_ns)"),
        (lambda r: ((r / "tmp").write_bytes(b""), (r / "tmp").unlink()), "changed . (mtime_ns)"),  # created and removed
        (lambda r: ((r / "link").unlink(), os.symlink("g.bin", r / "link")), "link"),
    ],
)
def test_any_change_fails(tmp_path, change, expected):
    root = tree(tmp_path)
    os.utime(root, ns=(1, 1))  # so that a directory mtime change is visible even on a coarse clock
    before = fs_guard.snapshot(root)
    change(root)
    with pytest.raises(fs_guard.FsGuardError) as exc:
        fs_guard.assert_unchanged(before, fs_guard.snapshot(root))
    assert expected in str(exc.value)


def test_labels_are_escaped_in_the_report(tmp_path):
    root = tree(tmp_path)
    with pytest.raises(fs_guard.FsGuardError) as exc, fs_guard.unchanged(root):
        (root / "x\u202ey").write_bytes(b"")
    assert "\u202e" not in str(exc.value) and "<U+202E>" in str(exc.value)
