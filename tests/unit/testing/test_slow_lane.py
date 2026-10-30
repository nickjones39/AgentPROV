"""The ``slow`` lane (D-409) is a developer convenience only: the merge gate deselects nothing.

* The gate command documented in AGENTS.md and the README, and pytest's ``addopts``, select no subset (no ``-m``, ``-k``,
  ``--deselect`` or ``--ignore``).
* A test listed in ``tests/slow_tests.txt`` is collected by a plain run and deselected only under ``-m "not slow"``.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SELECTING = re.compile(r"(?:^|\s)(-m|-k|--deselect|--ignore(?:-glob)?)(?:[\s=]|$)")


#: Where the gate command is documented; the public export has no AGENTS.md (D-1004), so the README always counts.
GATE_DOCS = ("AGENTS.md", "README.md")


def _gate_commands() -> list[str]:
    commands = []
    for name in GATE_DOCS:
        if name == "AGENTS.md" and not (REPO / name).is_file():
            continue
        text = (REPO / name).read_text(encoding="utf-8")
        commands += [m.group(1) for m in re.finditer(r"`(uv run python tools/suite_queue\.py --label [^`]*)`", text)]
        commands += re.findall(r"^(uv run python tools/suite_queue\.py --label .*)$", text, flags=re.M)
    return commands


def test_the_documented_gate_command_and_addopts_select_no_subset() -> None:
    commands = _gate_commands()
    assert commands, "neither AGENTS.md nor the README documents the gate command"
    for command in commands:
        assert not SELECTING.search(command.split(" -- ", 1)[-1]), command
    addopts = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["pytest"]["ini_options"]
    assert not SELECTING.search(str(addopts.get("addopts", ""))), addopts["addopts"]


def _collect(*args: str) -> str:
    env = {k: v for k, v in os.environ.items() if k != "PYTEST_ADDOPTS"}
    done = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", *args],
                          cwd=REPO, env=env, capture_output=True, text=True, timeout=600)
    assert done.returncode in (0, 5), done.stdout[-2000:] + done.stderr[-2000:]  # 5: everything was deselected
    return done.stdout


def test_a_listed_slow_test_is_collected_by_a_plain_run_and_deselected_only_by_not_slow() -> None:
    path = REPO / "tests" / "slow_tests.txt"
    assert path.is_file(), "tests/slow_tests.txt is missing: regenerate it with tools/slow_tests.py --write"
    listed = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
              if line.strip() and not line.startswith("#")]
    # a listed test whose own file marks nothing slow, so only the list can deselect it
    unmarked = [n for n in listed if "mark.slow" not in (REPO / n.split("::")[0]).read_text(encoding="utf-8")]
    assert unmarked, "tests/slow_tests.txt lists no test outside the files that mark their own slow tests"
    nid = unmarked[0]
    plain = _collect(nid)
    assert nid in plain and "deselected" not in plain
    lane = _collect(nid, "-m", "not slow")
    assert nid not in lane.splitlines() and "1 deselected" in lane
