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
