"""Argument hygiene for the workflow tools: no abbreviated long options (GR-45) and finite queue budgets (GR-30).

An abbreviation such as ``ci_local.py --allow-net`` used to select ``--allow-network`` and so enable the network;
every tool's parser (and subparser) now refuses abbreviations. ``suite_queue.py`` refuses a budget that would switch
admission off (``inf``, ``nan``, 0 or below) and a NaN or negative ``--cpu`` / ``--mem-gib``.
"""

from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import ci_local as cl
import pytest
import suite_queue as sq

TOOLS = Path(cl.__file__).resolve().parent

#: (tool, argv with an abbreviated long option): ``--hel`` would otherwise be ``--help`` and exit 0.
ABBREVIATED = [
    ("ci_local.py", ["--allow-net", "--list"]),
    ("ci_local.py", ["--hel"]),
    ("suite_queue.py", ["--hel"]),
    ("merge_train.py", ["--hel"]),
    ("merge_train.py", ["plan", "--hel"]),
    ("reserve_id.py", ["--hel"]),
    ("reserve_id.py", ["scan", "--stri"]),
    ("session_status.py", ["--hel"]),
    ("session_status.py", ["set", "--stat", "green"]),
    ("queue_status.py", ["--hel"]),
    ("regen_pins.py", ["--hel"]),
    ("gen_docs.py", ["--hel"]),
    ("gen_registry.py", ["--hel"]),
    ("spec_labels.py", ["--hel"]),
]


@pytest.mark.parametrize(("tool", "argv"), ABBREVIATED, ids=[f"{t}:{' '.join(a)}" for t, a in ABBREVIATED])
def test_abbreviated_long_options_are_refused(tool: str, argv: list[str], tmp_path: Path) -> None:
    done = subprocess.run([sys.executable, str(TOOLS / tool), *argv], cwd=tmp_path, capture_output=True, text=True,
                          timeout=60)
    assert done.returncode == 2, (done.stdout, done.stderr)
    assert "unrecognized arguments" in done.stderr or "invalid choice" in done.stderr or "required" in done.stderr


def test_ci_local_allow_net_does_not_enable_the_network(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cl.main(["--allow-net", "--list"])
    assert exc.value.code == 2 and "unrecognized arguments: --allow-net" in capsys.readouterr().err
    assert cl.main(["--allow-network", "--list"]) == 0  # the full spelling still works


@pytest.mark.parametrize("raw", ["inf", "-inf", "nan", "0", "-2", "1e400", "abc", "\u00b2"])  # "²" passes isdigit()
@pytest.mark.parametrize("name", ["AGENTPROV_JOB_CPU_BUDGET", "AGENTPROV_JOB_MEM_GIB_BUDGET"])
def test_a_budget_that_would_switch_admission_off_is_refused(name: str, raw: str) -> None:
    with pytest.raises(sq.BudgetError, match=f"\\${name} must be a finite number above 0"):
        sq.budget({name: raw})


def test_valid_budgets_and_the_unknown_memory_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    assert sq.budget({"AGENTPROV_JOB_CPU_BUDGET": "4", "AGENTPROV_JOB_MEM_GIB_BUDGET": "16.5"}) == (4.0, 16.5)
    assert sq.budget({"AGENTPROV_JOB_CPU_BUDGET": ""})[0] == max(1, sq.ncpu() - 2)  # empty means unset
    monkeypatch.setattr(sq, "physical_gib", lambda: None)
    cpu, mem = sq.budget({"AGENTPROV_JOB_CPU_BUDGET": "6"})
    assert (cpu, mem) == (6.0, 24.0) and math.isfinite(mem)  # was inf: memory never limited admission


def test_the_queue_refuses_to_run_with_a_bad_budget(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                    capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("AGENTPROV_JOB_CPU_BUDGET", "inf")
    with pytest.raises(SystemExit) as exc:
        sq.main(["--queue-dir", str(tmp_path / "q"), "--status"])
    assert exc.value.code == 2 and "$AGENTPROV_JOB_CPU_BUDGET must be a finite number" in capsys.readouterr().err
    assert not (tmp_path / "q").exists()  # refused before touching the queue


@pytest.mark.parametrize(("flag", "value"), [("--cpu", "nan"), ("--cpu", "-1"), ("--mem-gib", "inf")])
def test_reservation_options_must_be_finite(flag: str, value: str, tmp_path: Path,
                                            capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        sq.main(["--queue-dir", str(tmp_path / "q"), flag, value, "--", "true"])
    assert exc.value.code == 2 and "must be a finite number, 0 or above" in capsys.readouterr().err
