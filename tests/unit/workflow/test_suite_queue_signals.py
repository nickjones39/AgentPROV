"""``tools/suite_queue.py`` signal forwarding and the macOS ``killpg`` EPERM (B2, 2026-10-28).

On macOS ``killpg`` fails with EPERM, not ESRCH, when every member of the group is a zombie: the suite child exited and
is not reaped yet. A stop signal in that window made the old handler raise ``PermissionError`` (live-pilot finding 6).
The handler now only records the signal; the run loop forwards it while the child is known to be unreaped, so the
group id is never one that could have been reused.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[3] / "tools" / "suite_queue.py"


@pytest.fixture
def sq():
    import suite_queue  # tools/ is on sys.path (conftest.py)

    return suite_queue


def test_a_group_of_zombies_is_already_gone(sq) -> None:
    child = subprocess.Popen([sys.executable, "-c", "pass"], start_new_session=True)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:  # wait until it has exited, without reaping it
        state = subprocess.run(["ps", "-o", "stat=", "-p", str(child.pid)], capture_output=True, text=True).stdout
        if state.strip().startswith("Z") or not state.strip():
            break
        time.sleep(0.05)
    try:
        sq._signal_group(child, signal.SIGTERM)  # EPERM on macOS, ESRCH elsewhere: no exception either way
    finally:
        child.wait()


def test_a_reaped_child_is_never_signalled(sq, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(sq.os, "killpg", lambda pgid, sig: calls.append((pgid, sig)))
    child = subprocess.Popen([sys.executable, "-c", "pass"], start_new_session=True)
    child.wait()
    sq._signal_group(child, signal.SIGTERM)
    sq._signal_group(child, signal.SIGKILL)
    assert calls == []


def test_eperm_while_forwarding_does_not_break_the_wrapper(sq, monkeypatch: pytest.MonkeyPatch) -> None:
    """The child signals its parent (this process, inside ``run_child``) and keeps running; every ``killpg`` fails with
    EPERM. The signal is recorded, forwarded to the unreaped child's group only, and reported in the exit code."""
    calls: list[tuple[int, int]] = []

    def killpg(pgid: int, sig: int) -> None:
        calls.append((pgid, sig))
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(sq.os, "killpg", killpg)
    seen: list[int] = []
    child = "import os, signal, time; os.kill(os.getppid(), signal.SIGTERM); time.sleep(1.0)"
    code = sq.run_child([sys.executable, "-c", child], run_timeout=60.0, grace=1.0,
                        on_start=lambda c: seen.append(c.pid))
    assert code == 128 + signal.SIGTERM
    assert calls and {pgid for pgid, _sig in calls} == set(seen) and {sig for _p, sig in calls} == {signal.SIGTERM}


#: Runs ``run_child`` in its own process; ``on_start`` (the holder record in ``main``) signals the wrapper and then takes
#: its time, as the identity lookup and the ``holder.json`` rewrite do.
_WINDOW_DRIVER = """
import os, signal, sys, time
sys.path.insert(0, sys.argv[1])
import suite_queue as sq
pid_file, done = sys.argv[2], sys.argv[3]
def on_start(child):
    open(pid_file, 'w').write(str(child.pid))
    os.kill(os.getpid(), signal.SIGTERM)
    time.sleep(0.5)
    open(done, 'w').close()
sys.exit(sq.run_child([sys.executable, '-c', 'import time; time.sleep(60)'], run_timeout=120.0, grace=2.0,
                      on_start=on_start))
"""


def test_a_signal_while_the_child_is_being_recorded_is_forwarded_not_fatal(sq, tmp_path: Path) -> None:
    """AU-TWF-3: a SIGTERM between ``Popen`` and the end of ``on_start`` used to kill the wrapper by the default action
    (no child_pgid in holder.json, the suite running on unrecorded). The handlers are installed before the child
    starts, so the record completes, the signal reaches the child's group and the wrapper exits 128 + 15."""
    pid_file, done = tmp_path / "child.pid", tmp_path / "recorded"
    env = {k: v for k, v in os.environ.items() if not k.startswith("AGENTPROV_JOB_")}
    with (tmp_path / "stderr.txt").open("w") as err:  # a file, not a pipe: a leaked child would hold a pipe open
        driver = subprocess.run([sys.executable, "-c", _WINDOW_DRIVER, str(TOOL.parent), str(pid_file), str(done)],
                                stdout=subprocess.DEVNULL, stderr=err, timeout=120, env=env)
    pgid = int(pid_file.read_text())
    try:
        assert driver.returncode == 128 + signal.SIGTERM, (tmp_path / "stderr.txt").read_text()
        assert done.exists()  # on_start (the holder record) ran to its end
        deadline = time.monotonic() + 30
        while sq.group_alive(pgid):
            assert time.monotonic() < deadline, "the child's process group outlived the wrapper"
            time.sleep(0.05)
    finally:
        if sq.group_alive(pgid):
            os.killpg(pgid, signal.SIGKILL)


def test_a_signal_to_the_wrapper_reaches_the_suite(tmp_path: Path) -> None:
    """End to end in a separate process: SIGTERM to the wrapper stops the child's group; no traceback."""
    marker = tmp_path / "started"
    child = (f"import time; open({str(marker)!r}, 'w').close(); time.sleep(60)")
    env = {k: v for k, v in os.environ.items() if not k.startswith("AGENTPROV_JOB_")}
    wrapper = subprocess.Popen([sys.executable, str(TOOL), "--targeted", "--no-precompile", "--grace", "2", "--",
                                sys.executable, "-c", child], stderr=subprocess.PIPE, text=True, env=env)
    deadline = time.monotonic() + 30
    while not marker.exists():
        assert time.monotonic() < deadline and wrapper.poll() is None
        time.sleep(0.05)
    wrapper.send_signal(signal.SIGTERM)
    _out, err = wrapper.communicate(timeout=30)
    assert wrapper.returncode == 128 + signal.SIGTERM
    assert "Traceback" not in err
