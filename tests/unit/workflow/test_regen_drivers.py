"""The regeneration drivers under ``tools/regen`` (zsh) run against stubs: a fake ``HOME`` in ``tmp_path`` and a stub
``python`` that stands in for the queue, ``agentprov`` and the comparison tools. They must not write a ``.done`` marker
or exit 0 when a check fails. No real corpus, queue or repository is touched."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from wf_support import commit, git, write

REPO = Path(__file__).resolve().parents[3]

pytestmark = pytest.mark.skipif(shutil.which("zsh") is None or shutil.which("shasum") is None,
                                reason="the drivers are zsh scripts that use shasum")

#: The stub interpreter: it sources the test's hook (shell code that sees the command line in "$@"; it may exit or
#: print), runs ``-I -c`` scripts (the drivers' inline checks) in the real interpreter and otherwise exits 0.
STUB = """#!/bin/sh
[ -f "{hook}" ] && . "{hook}"
[ "$1" = -I ] && [ "$2" = -c ] && {{ shift; exec "{real}" "$@"; }}
exit 0
"""


def _stub(path: Path, hook: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(STUB.format(hook=hook, real=sys.executable), encoding="utf-8")
    path.chmod(0o755)


def _failing(*words: str) -> str:
    """Hook code: a command line that holds one of ``words`` as a whole argument exits 1."""
    return "".join(f'case " $* " in *" {w} "*) echo "stub: {w} failed" >&2; exit 1;; esac\n' for w in words)


def _run(script: Path, home: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["zsh", str(script), *args], env=dict(os.environ, HOME=str(home)), capture_output=True,
                          text=True, timeout=120)


# --- tools/regen/round/run_adprov_compat.sh -------------------------------------------------------------------------


def _compat(tmp_path: Path, *failing: str) -> tuple[subprocess.CompletedProcess[str], Path]:
    home = tmp_path / "home"
    repo = home / "Desktop/PhD/Labs/AgentPROV-framework/.claude/worktrees/agentprov-regen-plan-89e815"
    logs = home / ".agentprov/migration-work/regen-plan/logs/round"
    for d in (repo, logs, home / ".agentprov/corpora"):
        d.mkdir(parents=True)
    write(home / ".agentprov/cache", "acquisitions.jsonl", "{}\n")
    git(repo, "init", "-q")
    write(repo, ".gitignore", "/.venv/\n")
    pin = commit(repo, "base")[:8]
    hook = tmp_path / "hook.sh"
    hook.write_text(_failing(*failing), encoding="utf-8")
    _stub(repo / ".venv/bin/python", hook)
    driver = tmp_path / "tools/regen/round/run_adprov_compat.sh"
    driver.parent.mkdir(parents=True)
    text = (REPO / "tools/regen/round/run_adprov_compat.sh").read_text(encoding="utf-8")
    assert "\nPIN=5b1f6fdf\n" in text
    driver.write_text(text.replace("\nPIN=5b1f6fdf\n", f"\nPIN={pin}\n"), encoding="utf-8")
    return _run(driver, home), logs


def test_compat_driver_passes_when_every_check_passes(tmp_path: Path) -> None:
    proc, logs = _compat(tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (logs / "adprov-rg2.done").exists()


@pytest.mark.parametrize("step", ["verify", "validate"])
def test_compat_driver_fails_when_a_check_fails(tmp_path: Path, step: str) -> None:
    # AU-TRG-1: a failed ``verify --level chain`` used to be logged as PASS, with the .done marker and exit 0
    proc, logs = _compat(tmp_path, step)
    assert proc.returncode == 1
    assert not (logs / "adprov-rg2.done").exists()
    assert "FAIL adprov-rg2" in (logs / "round.log").read_text(encoding="utf-8")


# --- tools/regen/d358_building_commit.sh ----------------------------------------------------------------------------

#: One afe7038 validator batch row as ``validate --json -q`` writes it (only the members the driver's check reads).
ROPE_ROW = ('{{"exit_code": 1, "counters": {{"files": {files}, "errors": 0, "failed": {failed}, "warnings": 0}}, '
            '"issues_by_code": {{"validate.check.skipped": 6}}}}')


def _d358(tmp_path: Path, name: str, hook: str = "", build_hook: str = "") -> tuple[subprocess.CompletedProcess[str], Path]:
    home = tmp_path / "home"
    work = home / ".agentprov/migration-work/regen-plan"
    logs = work / "logs"
    logs.mkdir(parents=True)
    write(home / ".agentprov/cache", "acquisitions.jsonl", "{}\n")
    repo = tmp_path / "repo"
    driver = repo / "tools/regen/d358_building_commit.sh"
    driver.parent.mkdir(parents=True)
    shutil.copy(REPO / "tools/regen/d358_building_commit.sh", driver)
    (tmp_path / "hook.sh").write_text(hook, encoding="utf-8")
    (tmp_path / "build-hook.sh").write_text(build_hook, encoding="utf-8")
    _stub(repo / ".venv/bin/python", tmp_path / "hook.sh")
    _stub(work / "build-afe7038/.venv/bin/python", tmp_path / "build-hook.sh")
    return _run(driver, home, name), logs


def test_d358_driver_marks_a_matching_corpus_done(tmp_path: Path) -> None:
    proc, logs = _d358(tmp_path, "agentharm")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (logs / "d358-agentharm.done").exists()
    assert "ALL DONE" in (logs / "d358.log").read_text(encoding="utf-8")


def test_d358_driver_stops_when_the_trees_differ(tmp_path: Path) -> None:
    # AU-TRG-3: a failed tree comparison used to be logged only, with the .done marker and "ALL DONE"
    proc, logs = _d358(tmp_path, "agentharm", _failing("tools/regen/tree_compare.py"))
    assert proc.returncode == 1
    assert not (logs / "d358-agentharm.done").exists()
    log = (logs / "d358.log").read_text(encoding="utf-8")
    assert "STOP agentharm" in log and "ALL DONE" not in log


def _rope_import(tmp_path: Path, files: int) -> str:
    """Hook code for the queue stub: the import writes ``files`` AER files into the scratch tree."""
    out = tmp_path / "home/.agentprov/migration-work/regen-plan/out/d358-rope.partial/aer"
    return f'case " $* " in *" import "*) mkdir -p "{out}"; for i in $(seq {files}); do : > "{out}/$i.aer.jsonl"; done;; esac\n'


@pytest.mark.parametrize(("rows", "passes"), [
    ([(3, 0)], True),           # one batch, every AER counted, nothing failed (exit 1 for the skipped checks)
    ([(2, 0)], False),          # an AER the batches never counted
    ([(3, 1)], False),          # a failed AER
    ([], False),                # no batch row at all
])
def test_d358_driver_reads_the_rope_validator_batches(tmp_path: Path, rows: list[tuple[int, int]], passes: bool) -> None:
    # AU-TRG-3: the ROPE validator batches' results used to be ignored
    printed = "".join(ROPE_ROW.format(files=f, failed=x) + "\n" for f, x in rows)
    build_hook = f"case \" $* \" in *\" validate \"*) printf '%s' '{printed}'; exit 1;; esac\n"
    proc, logs = _d358(tmp_path, "rope", _rope_import(tmp_path, 3), build_hook)
    assert (proc.returncode == 0) is passes, proc.stdout + proc.stderr
    assert (logs / "d358-rope.done").exists() is passes


# --- tools/regen/round/evaluate.py and run_round.sh -----------------------------------------------------------------


def _summaries(log: Path, name: str, n: int, **change: dict) -> None:
    """The five step summaries of a corpus whose round checks all pass, with ``change`` merged into each step's."""
    steps = {
        "import": {"exit_code": 0, "counters": {"mapped": n, "sealed_clean": n - 1, "sealed_with_issues": 1,
                                                "degenerate": 0, "failed": 0}},
        "dryrun": {"exit_code": 0, "counters": {"identical": n}},
        "validate": {"exit_code": 0, "counters": {"passed": n, "failed": 0}},
        "verify": {"exit_code": 0, "counters": {"failed": 0}, "issues_by_code": {"checksums.absent": 1}},
        "compare": {"ids_only_old": 0, "ids_only_new": 0, "completeness": {}, "mismatches": [], "errors": [],
                    "compared": n, "sampled": False},
    }
    for step, body in steps.items():
        body = {**body, **change.get(step, {})}
        (log / f"{name}-{step}.json").write_text(json.dumps(body), encoding="utf-8")


def _evaluate(log: Path, name: str, n: int) -> tuple[int, dict]:
    proc = subprocess.run([sys.executable, "-I", str(REPO / "tools/regen/round/evaluate.py"), str(log), name, str(n)],
                          capture_output=True, text=True, timeout=60)
    return proc.returncode, json.loads((log / f"{name}-verdict.json").read_text(encoding="utf-8"))


def test_evaluate_passes_a_complete_round(tmp_path: Path) -> None:
    _summaries(tmp_path, "x", 5)
    rc, verdict = _evaluate(tmp_path, "x", 5)
    assert rc == 0 and verdict["pass"] and verdict["fails"] == []


@pytest.mark.parametrize(("change", "step"), [
    # AU-TRG-4: a resumed import into an existing tree maps nothing
    ({"import": {"counters": {"mapped": 0, "sealed_clean": 0, "sealed_with_issues": 0, "degenerate": 0, "failed": 0}}},
     "import"),
    ({"import": {"counters": {"mapped": 5, "sealed_clean": 3, "sealed_with_issues": 0, "degenerate": 2, "failed": 0}}},
     "import"),
    ({"verify": {"exit_code": 1}}, "verify"),
    ({"compare": {"compared": 1, "sampled": True}}, "compare"),
    ({"compare": {"compared": 5, "sampled": True}}, "compare"),
])
def test_evaluate_fails_an_incomplete_round(tmp_path: Path, change: dict, step: str) -> None:
    _summaries(tmp_path, "x", 5, **change)
    rc, verdict = _evaluate(tmp_path, "x", 5)
    assert rc == 1 and not verdict["pass"]
    assert [f.split(":")[0] for f in verdict["fails"]] == [step]


def _round(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    home = tmp_path / "home"
    repo = home / "Desktop/PhD/Labs/AgentPROV-framework/.claude/worktrees/agentprov-regen-plan-89e815"
    logs = home / ".agentprov/migration-work/regen-plan/logs/round"
    corpora = home / ".agentprov/corpora"
    for d in (repo, logs, corpora):
        d.mkdir(parents=True)
    write(home / ".agentprov/cache", "acquisitions.jsonl", "{}\n")
    git(repo, "init", "-q")
    write(repo, ".gitignore", "/.venv/\n")
    pin = commit(repo, "base")[:8]
    # the hook records every queued command line
    (tmp_path / "hook.sh").write_text(f'echo "$*" >> "{tmp_path / "calls.txt"}"\n', encoding="utf-8")
    _stub(repo / ".venv/bin/python", tmp_path / "hook.sh")
    driver = tmp_path / "tools/regen/round/run_round.sh"
    driver.parent.mkdir(parents=True)
    text = (REPO / "tools/regen/round/run_round.sh").read_text(encoding="utf-8")
    assert text.count("5b1f6fdf") == 3
    driver.write_text(text.replace("5b1f6fdf", pin), encoding="utf-8")
    return driver, home, logs, corpora


def test_run_round_refuses_an_existing_tree(tmp_path: Path) -> None:
    # AU-TRG-4: import resumes an existing DIR.partial; a re-run of a failed corpus must stop, not re-import nothing
    driver, home, logs, corpora = _round(tmp_path)
    (corpora / "mandate-agentdojo-eval-rg1.partial").mkdir()
    proc = _run(driver, home, "mandate")
    assert proc.returncode == 1
    assert "STOP mandate" in (logs / "round.log").read_text(encoding="utf-8")
    assert not (tmp_path / "calls.txt").exists()
    assert not (logs / "mandate.done").exists()


def test_run_round_never_reads_an_earlier_attempts_summary(tmp_path: Path) -> None:
    driver, home, logs, _ = _round(tmp_path)
    _summaries(logs, "mandate", 396)
    proc = _run(driver, home, "mandate")
    # the stub import writes no summary: the earlier attempt's import.json (renamed aside) must not stand in for it
    assert proc.returncode == 1
    assert "STOP mandate: no import summary" in (logs / "round.log").read_text(encoding="utf-8")
    assert not (logs / "mandate-import.json").exists()
    assert len(list(logs.glob("mandate-import.json.before-*"))) == 1
