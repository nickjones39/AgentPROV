"""Advisory locks of shared state outside a corpus (``agentprov.io.locks``; N.1.9 G6a; CLI robustness item 3).

A live holder refuses at once with a message that names it; a dead holder on this host is removed (bounded: a lock never
outlives its process); a foreign or unreadable one refuses. The fetch cache takes its lock only on the write path.
"""

from __future__ import annotations

import json
import platform
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from agentprov.io.locks import (
    ResourceBusyError,
    ResourceLock,
    ResourceUse,
    backend_build,
    backend_use,
    fetch_cache_lock,
    staging_use,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "raw"))
from fetch_support import make_upstream, needs_git  # noqa: E402

HOST = platform.node()


@pytest.fixture
def live_pid() -> Iterator[int]:
    """The pid of another live process (a sleeping child), killed afterwards."""
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    try:
        yield child.pid
    finally:
        child.kill()
        child.wait()


@pytest.fixture
def dead_pid() -> int:
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    return child.pid


def _record(path: Path, pid: int, host: str = HOST, command: str = "fetch") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"command": command, "host": host, "pid": pid, "started": "2026-10-14T10:00:00Z"}))


# ------------------------------------------------------------------------------------------------ the primitives
def test_a_live_holder_refuses_at_once_and_is_named(tmp_path: Path, live_pid: int) -> None:
    path = tmp_path / "x.lock"
    _record(path, live_pid, command="backends build")
    with pytest.raises(ResourceBusyError) as caught:
        ResourceLock(path, what="the thing").acquire()
    text = str(caught.value)
    assert f"the thing is in use by pid {live_pid}" in text and "'backends build'" in text and "2026-10-14" in text
    assert caught.value.exit_code == 4 and caught.value.code == "io.resource_busy"
    assert json.loads(path.read_text())["pid"] == live_pid  # never broken


def test_a_dead_holder_on_this_host_is_removed_and_the_lock_taken(tmp_path: Path, dead_pid: int) -> None:
    path = tmp_path / "x.lock"
    _record(path, dead_pid)
    with ResourceLock(path, what="the thing", command="mine"):
        assert json.loads(path.read_text())["command"] == "mine"
    assert not path.exists()


def test_a_foreign_or_unreadable_holder_refuses_and_names_the_file(tmp_path: Path, dead_pid: int) -> None:
    path = tmp_path / "x.lock"
    _record(path, dead_pid, host="another-host")
    with pytest.raises(ResourceBusyError, match="another-host.*remove"):
        ResourceLock(path, what="the thing").acquire()
    path.write_bytes(b"not json")
    with pytest.raises(ResourceBusyError, match="unreadable lock record"):
        ResourceLock(path, what="the thing").acquire()
    assert path.read_bytes() == b"not json"


def test_a_user_registration_refuses_while_the_exclusive_lock_is_held(tmp_path: Path) -> None:
    exclusive = ResourceLock(tmp_path / "build.lock", what="the build", command="backends build")
    use = ResourceUse(tmp_path / "users", what="the env", exclusive=exclusive)
    with exclusive, pytest.raises(ResourceBusyError, match="the build is held by pid"):
        use.acquire()
    assert use.live_users() == []  # the refused registration was withdrawn
    with use:
        assert [u.pid for u in use.live_users()] == [use._pid]
    assert use.live_users() == []


def test_dead_users_are_pruned_and_live_ones_kept(tmp_path: Path, live_pid: int, dead_pid: int) -> None:
    users = tmp_path / "users"
    _record(users / f"{live_pid}@{HOST}.json", live_pid, command="run")
    _record(users / f"{dead_pid}@{HOST}.json", dead_pid, command="run")
    assert [u.pid for u in ResourceUse(users, what="the env").live_users()] == [live_pid]
    assert not (users / f"{dead_pid}@{HOST}.json").exists()


def test_a_build_refuses_while_a_run_uses_the_environment_and_a_run_refuses_during_a_build(tmp_path: Path,
                                                                                           live_pid: int) -> None:
    home = tmp_path / "home"
    _record(home / "locks" / "envs" / "agentdojo-x.users" / f"{live_pid}@{HOST}.json", live_pid, command="run")
    with pytest.raises(ResourceBusyError, match="in use by pid .*rebuild would replace it"):
        with backend_build(home, "agentdojo-x"):
            pass
    assert not (home / "locks" / "envs" / "agentdojo-x.lock").exists()  # released on refusal
    (home / "locks" / "envs" / "agentdojo-x.users" / f"{live_pid}@{HOST}.json").unlink()
    with backend_build(home, "agentdojo-x"), pytest.raises(ResourceBusyError, match="being built"):
        backend_use(home, "agentdojo-x").acquire()
    with backend_use(home, "agentdojo-x"), staging_use(home, command="run") as staging:
        assert len(staging.live_users()) == 1


# ------------------------------------------------------------------------------------------------ the fetch cache
@needs_git
def test_a_concurrent_fetch_into_the_same_cache_refuses_before_running_git(tmp_path: Path, live_pid: int) -> None:
    up = make_upstream(tmp_path)
    cache = tmp_path / "cache"
    _record(cache / ".agentprov.lock", live_pid)
    fetcher = up.fetcher(cache, allow_network=True)
    with pytest.raises(ResourceBusyError, match=f"the fetch cache 'cache' is in use by pid {live_pid}"):
        fetcher.fetch(up.recipe())
    assert not (cache / "git").exists()  # nothing was written


@needs_git
def test_a_cached_read_takes_no_lock_and_the_writer_releases_its_own(tmp_path: Path, live_pid: int) -> None:
    up = make_upstream(tmp_path)
    cache = tmp_path / "cache"
    first = up.fetcher(cache, allow_network=True).fetch(up.recipe())
    assert first.network_used and not (cache / ".agentprov.lock").exists()
    _record(cache / ".agentprov.lock", live_pid)  # a writer of another pin is busy: a cache hit does not care
    again = up.fetcher(cache, allow_network=False).fetch(up.recipe())
    assert not again.network_used and again.files == first.files


@needs_git
def test_a_fetch_after_a_killed_writer_goes_ahead(tmp_path: Path, dead_pid: int) -> None:
    up = make_upstream(tmp_path)
    cache = tmp_path / "cache"
    _record(cache / ".agentprov.lock", dead_pid)
    assert up.fetcher(cache, allow_network=True).fetch(up.recipe()).network_used
    assert not (cache / ".agentprov.lock").exists()


def test_an_offline_refusal_takes_no_lock(tmp_path: Path) -> None:
    from agentprov.raw.fetch import Fetcher, NetworkRefusedError, Recipe

    cache = tmp_path / "cache"
    recipe = Recipe(kind="url", url="https://example.invalid/f.zip", sha256="ab" * 32)
    with pytest.raises(NetworkRefusedError):
        Fetcher(cache).fetch(recipe)
    assert not cache.exists()
    assert fetch_cache_lock(cache).holder() is None
