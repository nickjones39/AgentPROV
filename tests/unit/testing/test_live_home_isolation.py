"""The live-backend tests' session home stays theirs (bug pass BF-34, handed over by suite-perf).

``tests/integration/test_run_live_{agentdojo,autodojo}.py`` build their backend environment once per session into a
temporary ``$AGENTPROV_HOME``. The variable used to be set in the session fixture and restored only at session end, so
``tests/conftest.py`` kept that home for every later test on the same xdist worker instead of giving it a fresh one.

A child pytest runs one live test (the build replaced by a stub, so nothing is built and nothing touches the network),
then an ordinary test, in that order and in one process; a plugin records each test's ``$AGENTPROV_HOME``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]

PLUGIN = '''
import os

SEEN = {}


def pytest_collection_finish(session):
    for item in session.items:
        if item.module.__name__.rsplit(".", 1)[-1].startswith("test_run_live_"):
            item.module._main = lambda *argv: (0, "", "")  # the backend build, stubbed


def pytest_runtest_call(item):
    SEEN[item.nodeid] = os.environ.get("AGENTPROV_HOME", "")


def pytest_terminal_summary(terminalreporter):
    for nodeid, home in SEEN.items():
        terminalreporter.write_line(f"HOME-PROBE {nodeid} {home}")
'''

LIVE = {
    "agentdojo": "tests/integration/test_run_live_agentdojo.py::test_the_build_records_its_marker_and_passes_the_offline_check",
    "autodojo": "tests/integration/test_run_live_autodojo.py::test_a_filter_defence_is_refused_with_its_nltk_state",
}
LATER = "tests/unit/testing/test_write_guard.py"


@pytest.mark.skipif(os.name == "nt", reason="the live-backend modules are POSIX-only")
@pytest.mark.parametrize("backend", sorted(LIVE))
def test_a_later_test_on_the_same_worker_gets_its_own_home(tmp_path: Path, backend: str) -> None:
    (tmp_path / "bf34_probe.py").write_text(PLUGIN, encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(tmp_path), os.environ.get("PYTHONPATH")]))}
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "bf34_probe", "-p", "no:randomly", "-p", "no:cacheprovider",
         "-p", "no:xdist", "-q", LIVE[backend], LATER],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=600,
    )  # fmt: skip
    seen = dict(line.split(" ", 2)[1:] for line in done.stdout.splitlines() if line.startswith("HOME-PROBE "))
    live = seen.get(LIVE[backend])
    later = {nodeid: home for nodeid, home in seen.items() if nodeid.startswith(LATER)}
    assert live and later, done.stdout[-2000:] + done.stderr[-2000:]
    assert all(home != live for home in later.values()), (live, later)
