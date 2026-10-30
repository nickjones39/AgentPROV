"""io.atomic: atomic writes, directory swap, the single-writer lock, the stale-temporary sweep (N.1.9 G6/G9)."""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path

import pytest

from agentprov.host import detect_host
from agentprov.io import atomic
from agentprov.io.atomic import (
    DestinationExistsError,
    LockFile,
    LockHeldError,
    atomic_swap_dir,
    atomic_write_bytes,
    atomic_write_text,
    pid_alive,
    suffixed,
    sweep_stale_tmp,
    tmp_path_for,
)

DEAD_PID = 2**22 + 12345  # beyond the default pid space on every platform we run on

needs_posix_permissions = pytest.mark.skipif(
    not detect_host(probe=False).caps.posix_permissions,
    reason="chmod bits do not read back on this host (a probed capability; access is governed by ACLs)",
)


@pytest.fixture(autouse=True)
def _dead_pid_is_dead() -> None:
    assert not pid_alive(DEAD_PID)


def test_write_bytes_replaces_and_leaves_no_temporary(tmp_path: Path) -> None:
    target = tmp_path / "a.bin"
    atomic_write_bytes(target, b"one")
    atomic_write_bytes(target, b"two\n")
    assert target.read_bytes() == b"two\n"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.bin"]


def test_write_text_does_not_translate_newlines(tmp_path: Path) -> None:
    target = tmp_path / "t.txt"
    atomic_write_text(target, "a\nb\r\nc")
    assert target.read_bytes() == b"a\nb\r\nc"


@needs_posix_permissions
def test_write_mode_is_applied(tmp_path: Path) -> None:
    target = tmp_path / "m.bin"
    atomic_write_bytes(target, b"x", mode=0o600)
    assert target.stat().st_mode & 0o777 == 0o600


def test_failed_write_keeps_old_content_and_removes_temporary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "keep.bin"
    atomic_write_bytes(target, b"old")

    def boom(src: object, dst: object) -> None:
        raise OSError("simulated rename failure")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError, match="simulated"):
        atomic_write_bytes(target, b"new")
    monkeypatch.undo()
    assert target.read_bytes() == b"old"
    assert not tmp_path_for(target).exists()


def test_suffixed_appends_to_the_name() -> None:
    assert suffixed(Path("d/a.b"), ".json") == Path("d/a.b.json")


def test_swap_dir_moves_partial_to_final(tmp_path: Path) -> None:
    src = tmp_path / "c.partial"
    src.mkdir()
    (src / "f").write_text("x")
    atomic_swap_dir(src, tmp_path / "c")
    assert (tmp_path / "c" / "f").read_text() == "x"
    assert not src.exists()


def test_swap_dir_refuses_existing_destination_with_exit_4(tmp_path: Path) -> None:
    src, dst = tmp_path / "c.partial", tmp_path / "c"
    src.mkdir()
    dst.mkdir()
    with pytest.raises(DestinationExistsError) as info:
        atomic_swap_dir(src, dst)
    assert info.value.exit_code == 4
    assert src.exists()


def test_swap_dir_requires_a_directory(tmp_path: Path) -> None:
    f = tmp_path / "f"
    f.write_text("x")
    with pytest.raises(NotADirectoryError):
        atomic_swap_dir(f, tmp_path / "g")


def test_lock_is_exclusive_and_released(tmp_path: Path) -> None:
    path = tmp_path / ".agentprov.lock"
    with LockFile(path, command="import") as lock:
        assert lock.held
        doc = json.loads(path.read_text())
        assert (
            doc["pid"] == os.getpid() and doc["host"] == socket.gethostname() and doc["command"] == "import"
        )
        with pytest.raises(LockHeldError) as info:
            LockFile(path).acquire()
        assert info.value.exit_code == 4
    assert not path.exists()


def test_stale_lock_needs_break_flag(tmp_path: Path) -> None:
    path = tmp_path / ".agentprov.lock"
    stale = {"command": "x", "host": socket.gethostname(), "pid": DEAD_PID, "started": "2026-01-01T00:00:00Z"}
    path.write_text(json.dumps(stale))
    with pytest.raises(LockHeldError, match="stale"):
        LockFile(path).acquire()
    with LockFile(path, break_stale=True) as lock:
        assert lock.held
        assert json.loads(path.read_text())["pid"] == os.getpid()


def test_foreign_host_and_garbage_locks_are_never_broken(tmp_path: Path) -> None:
    path = tmp_path / ".agentprov.lock"
    path.write_text(json.dumps({"command": "x", "host": "other-host", "pid": DEAD_PID, "started": "t"}))
    with pytest.raises(LockHeldError):
        LockFile(path, break_stale=True).acquire()
    path.write_text("not json")
    with pytest.raises(LockHeldError):
        LockFile(path, break_stale=True).acquire()
    assert path.read_text() == "not json"


def test_release_does_not_remove_a_lock_taken_over_by_someone_else(tmp_path: Path) -> None:
    path = tmp_path / ".agentprov.lock"
    lock = LockFile(path)
    lock.acquire()
    path.write_text(json.dumps({"command": "x", "host": "h", "pid": 1, "started": "t"}))
    lock.release()
    assert path.exists()


def test_sweep_removes_only_dead_pid_temporaries(tmp_path: Path) -> None:
    dead = tmp_path / f"a.json.tmp-{DEAD_PID}"
    alive = tmp_path / f"b.json.tmp-{os.getpid()}"
    other = tmp_path / "c.json"
    nested = tmp_path / "sub" / f"d.tmp-{DEAD_PID}"
    nested.parent.mkdir()
    for f in (dead, alive, other, nested):
        f.write_text("x")
    link = tmp_path / f"link.tmp-{DEAD_PID}"
    link.symlink_to(other)

    assert sweep_stale_tmp(tmp_path, dry_run=True) == [dead]
    assert dead.exists()
    assert sweep_stale_tmp(tmp_path) == [dead]
    assert not dead.exists() and alive.exists() and other.exists() and nested.exists() and link.is_symlink()
    assert sweep_stale_tmp(tmp_path, recursive=True) == [nested]
    assert sweep_stale_tmp(tmp_path / "missing") == []


def test_sweep_keeps_names_that_are_not_agentprov_temporaries(tmp_path: Path) -> None:
    """Escaping audit F-12: non-ASCII digits, a 4,301-digit "pid", a pid beyond the OS range and a trailing newline."""
    names = ["b.tmp-\u0661\u0662", "c.tmp-" + "9" * 200, f"d.tmp-{atomic._MAX_PID + 1}", f"e.tmp-{2**40}"]
    if os.name != "nt":  # Windows refuses a newline in a file name
        names.append(f"a.tmp-{DEAD_PID}\n")
    assert atomic._TMP_RE.search("x.tmp-" + "9" * 5000) is None  # no int() of 4,301+ digits (longer than any name)
    for name in names:
        (tmp_path / name).write_text("x")
    assert sweep_stale_tmp(tmp_path) == []
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(names)


def test_a_lock_naming_a_pid_beyond_the_os_range_is_held_not_a_crash(tmp_path: Path) -> None:
    path = tmp_path / ".agentprov.lock"
    path.write_text(json.dumps({"command": "x", "host": socket.gethostname(), "pid": 2**40, "started": "t"}))
    with pytest.raises(LockHeldError):
        LockFile(path, break_stale=True).acquire()
    assert pid_alive(2**40) and pid_alive(10**30) and not pid_alive(0)


def test_module_exports_are_stable() -> None:
    assert set(atomic.__all__) >= {"atomic_write_bytes", "atomic_write_text", "atomic_swap_dir", "LockFile"}


def _stale_lock(path: Path) -> None:
    host = socket.gethostname()
    path.write_text(json.dumps({"pid": DEAD_PID, "host": host, "command": "crashed", "started": "2026-01-01T00:00:00Z"}))


def test_two_breakers_of_one_stale_lock_never_both_hold_it(tmp_path: Path) -> None:
    """Pre-round review D #6: B read the stale record, A broke it and took the lock, then B unlinked A's live lock and
    took it too. B's unlink now happens only under the break token and only while the dead record is still there."""
    path = tmp_path / ".agentprov.lock"
    _stale_lock(path)
    host = socket.gethostname()
    a = LockFile(path, break_stale=True, pid=os.getpid(), host=host, command="A")
    b = LockFile(path, break_stale=True, pid=os.getpid(), host=host, command="B")
    real_read = b.read
    calls = {"n": 0}

    def interleaved():  # type: ignore[no-untyped-def]
        info = real_read()
        calls["n"] += 1
        if calls["n"] == 1:  # between B's first read of the stale record and its break, A breaks it and takes it
            a.acquire()
        return info

    b.read = interleaved  # type: ignore[method-assign]
    with pytest.raises(LockHeldError):
        b.acquire()
    assert a.held and not b.held
    assert json.loads(path.read_text())["command"] == "A"
    assert not b.break_token.exists()
    a.release()


def test_a_left_break_token_refuses_instead_of_breaking(tmp_path: Path) -> None:
    path = tmp_path / ".agentprov.lock"
    _stale_lock(path)
    lock = LockFile(path, break_stale=True, host=socket.gethostname())
    lock.break_token.write_text("12345 elsewhere\n")
    with pytest.raises(LockHeldError, match=r"\.agentprov\.lock\.break"):
        lock.acquire()
    assert json.loads(path.read_text())["command"] == "crashed"


def test_a_single_breaker_still_takes_a_stale_lock(tmp_path: Path) -> None:
    path = tmp_path / ".agentprov.lock"
    _stale_lock(path)
    with LockFile(path, break_stale=True, host=socket.gethostname(), command="me") as lock:
        assert lock.held and json.loads(path.read_text())["command"] == "me"
        assert not lock.break_token.exists()
