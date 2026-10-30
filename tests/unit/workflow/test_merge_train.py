"""``tools/merge_train.py``: N branches, one gate run, bisect on red, fast-forward push only (D-420).

Each test has its own bare repository as ``origin`` (a local path: no network) and a clone to work in. Gates are tiny
Python commands that look at the merged tree, so a "red" branch is one that adds a file named ``BAD``.
"""

from __future__ import annotations

import dataclasses
import json
import shlex
import subprocess
import sys
from pathlib import Path

import merge_train as mt
import pytest
from wf_support import commit, git, write

GATE_NO_BAD = shlex.join([sys.executable, "-c", "import os, sys; sys.exit(1 if os.path.exists('BAD') else 0)"])


@pytest.fixture
def clone(tmp_path: Path) -> Path:
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    work = tmp_path / "work"
    git(tmp_path, "clone", "-q", str(origin), str(work))
    write(work, "README.md", "base\n")
    commit(work, "base")
    git(work, "push", "-q", "origin", "HEAD:refs/heads/main")
    git(work, "fetch", "-q", "origin")
    return work


def _branch(work: Path, name: str, files: dict[str, str], start: str = "origin/main") -> str:
    git(work, "switch", "-q", "-c", name, start)
    for rel, text in files.items():
        write(work, rel, text)
    sha = commit(work, name)
    git(work, "switch", "-q", "--detach", "origin/main")
    return sha


def _green(sdir: Path, branch: str, sha: str, result: str = "green") -> None:
    sdir.mkdir(parents=True, exist_ok=True)
    doc = {"schema": "agentprov-session-status/1", "name": branch, "worktree": "/nowhere", "branch": branch,
           "head": sha, "dirty": False, "base": {"ref": "origin/main", "sha": None, "ahead": None, "behind": None},
           "state": "green", "waits_on": {"kind": "none"}, "last_suite": {"commit": sha, "result": result},
           "updated_at": "2026-10-14T00:00:00Z", "heartbeat_at": "2026-10-14T00:00:00Z"}
    (sdir / f"{branch}.json").write_text(json.dumps(doc), encoding="utf-8")


def _train(work: Path, sdir: Path, cmd: str, *args: str, gate: str | None = GATE_NO_BAD) -> int:
    argv = ["-C", str(work), cmd, *args, "--sessions-dir", str(sdir)]
    if gate is not None and cmd == "run":
        argv += ["--gate", gate]
    return mt.main(argv)


def _report(home: Path) -> dict:
    path = max((home / "merge-train").glob("*/report.json"), key=lambda p: p.stat().st_mtime_ns)
    return json.loads(path.read_text(encoding="utf-8"))


def _origin_main(work: Path) -> str:
    return git(work, "ls-remote", "origin", "refs/heads/main").split()[0]


@pytest.fixture
def sdir(tmp_path: Path) -> Path:
    return tmp_path / "sessions"


def test_plan_merges_in_a_scratch_worktree_and_changes_nothing(clone: Path, sdir: Path, isolated_env: Path) -> None:
    base = _origin_main(clone)
    for name in ("b1", "b2"):
        _green(sdir, name, _branch(clone, name, {f"{name}.txt": name}))
    assert _train(clone, sdir, "plan", "b1", "b2") == 0
    rep = _report(isolated_env)
    assert rep["result"] == "planned" and [e["branch"] for e in rep["merged"]] == ["b1", "b2"]
    assert "gate_runs" not in rep
    wt = Path(rep["worktree"])
    assert wt.is_relative_to(isolated_env / "merge-train") and (wt / "b1.txt").is_file() and (wt / "b2.txt").is_file()
    assert git(wt, "log", "--first-parent", "--format=%s", "-2").splitlines() == [
        f"Merge branch 'b2' (merge train {rep['run_id']}, 2/2)", f"Merge branch 'b1' (merge train {rep['run_id']}, 1/2)"]
    assert _origin_main(clone) == base


def test_admission(clone: Path, sdir: Path, isolated_env: Path) -> None:
    sha = _branch(clone, "b1", {"a": "a"})
    _branch(clone, "review/x", {"r": "r"})
    assert _train(clone, sdir, "plan", "b1") == 2  # no status file
    _green(sdir, "b1", "0" * 40)
    assert _train(clone, sdir, "plan", "b1") == 2  # green, but on another commit
    _green(sdir, "b1", sha, result="red")
    assert _train(clone, sdir, "plan", "b1") == 2
    assert "not green on its exact head" in _report(isolated_env)["refusals"][0]
    assert _train(clone, sdir, "plan", "b1", "--allow-unverified") == 0
    assert _report(isolated_env)["admitted"][0]["warnings"][0].startswith("unverified")
    _green(sdir, "b1", sha)
    assert _train(clone, sdir, "plan", "b1", "review/x", "--allow-unverified") == 2
    assert _train(clone, sdir, "plan", "b1", "review/x", "nosuch", "--skip-refused") == 0
    assert [e["branch"] for e in _report(isolated_env)["merged"]] == ["b1"]


def test_green_run_pushes_a_fast_forward_only_with_approval(clone: Path, sdir: Path, isolated_env: Path) -> None:
    base = _origin_main(clone)
    for name in ("b1", "b2", "b3"):
        _green(sdir, name, _branch(clone, name, {f"{name}.txt": name}))
    assert _train(clone, sdir, "run", "b1", "b2", "b3", "--push") == 2  # no approval
    assert _train(clone, sdir, "run", "b1", "b2", "b3", "--push", "--approval", "   ") == 2
    assert _train(clone, sdir, "run", "b1", "b2", "b3") == 0  # green, not pushed
    assert _origin_main(clone) == base
    assert _train(clone, sdir, "run", "b1", "b2", "b3", "--push", "--approval", "yes, push the train") == 0
    rep = _report(isolated_env)
    assert rep["result"] == "pushed" and rep["approval"] == "yes, push the train"
    assert len(rep["gate_runs"]) == 1  # ONE gate run for three branches
    assert _origin_main(clone) == rep["head"]
    git(clone, "fetch", "-q", "origin")
    assert git(clone, "merge-base", "--is-ancestor", base, "origin/main") == ""  # a fast-forward of the old main
    for name in ("b1", "b2", "b3"):
        assert git(clone, "rev-parse", "--verify", "--quiet", f"refs/heads/{name}")  # no branch deleted


def test_red_without_bisect_stops(clone: Path, sdir: Path, isolated_env: Path) -> None:
    base = _origin_main(clone)
    _green(sdir, "bad", _branch(clone, "bad", {"BAD": "x"}))
    assert _train(clone, sdir, "run", "bad", "--push", "--approval", "yes") == 1
    rep = _report(isolated_env)
    assert rep["result"] == "red" and rep["gate_runs"][0]["results"][0]["exit"] == 1
    assert _origin_main(clone) == base


def test_bisect_ejects_the_red_branch_and_pushes_the_rest(clone: Path, sdir: Path, isolated_env: Path) -> None:
    for name, files in (("b1", {"b1": "1"}), ("b2", {"b2": "2"}), ("bad", {"BAD": "x"}), ("b4", {"b4": "4"}),
                        ("b5", {"b5": "5"})):
        _green(sdir, name, _branch(clone, name, files))
    assert _train(clone, sdir, "run", "b1", "b2", "bad", "b4", "b5", "--bisect", "--push", "--approval", "yes") == 0
    rep = _report(isolated_env)
    assert rep["result"] == "pushed"
    assert [e["branch"] for e in rep["ejected"]] == ["bad"] and rep["ejected"][0]["ejected"] == "interaction"
    assert [e["branch"] for e in rep["merged"]] == ["b1", "b2", "b4", "b5"]
    labels = [g["label"] for g in rep["gate_runs"]]
    assert labels[:2] == ["head", "head re-run"] and labels[-1] == "head"
    assert len(labels) <= 2 + 3 + 1  # head twice, at most ceil(log2 5) probes, the new head
    tree = git(clone, "ls-tree", "--name-only", _origin_main(clone)).splitlines()
    assert "BAD" not in tree and {"b1", "b2", "b4", "b5"} <= set(tree)


def test_bisect_when_the_first_branch_is_red(clone: Path, sdir: Path, isolated_env: Path) -> None:
    _green(sdir, "bad", _branch(clone, "bad", {"BAD": "x"}), result="red")
    _green(sdir, "ok", _branch(clone, "ok", {"ok": "1"}))
    assert _train(clone, sdir, "run", "bad", "ok", "--bisect", "--allow-unverified") == 0
    rep = _report(isolated_env)
    assert rep["ejected"][0]["branch"] == "bad" and rep["ejected"][0]["ejected"] == "red"
    assert [e["branch"] for e in rep["merged"]] == ["ok"]


def test_only_red_branches_leave_nothing_to_push(clone: Path, sdir: Path, isolated_env: Path) -> None:
    base = _origin_main(clone)
    _green(sdir, "bad", _branch(clone, "bad", {"BAD": "x"}))
    assert _train(clone, sdir, "run", "bad", "--bisect", "--push", "--approval", "yes") == 1
    assert _report(isolated_env)["result"] == "red" and _origin_main(clone) == base


def test_a_flaky_red_is_not_reproducible_and_never_pushed(clone: Path, sdir: Path, isolated_env: Path,
                                                          tmp_path: Path) -> None:
    base = _origin_main(clone)
    marker = tmp_path / "failed-once"
    flaky = shlex.join([sys.executable, "-c", f"import pathlib, sys; p = pathlib.Path({str(marker)!r}); "
                                              "sys.exit(0) if p.exists() else (p.touch(), sys.exit(1))"])
    _green(sdir, "b1", _branch(clone, "b1", {"b1": "1"}))
    assert _train(clone, sdir, "run", "b1", "--bisect", "--push", "--approval", "yes", gate=flaky) == 1
    assert _report(isolated_env)["result"] == "not reproducible" and _origin_main(clone) == base


def test_conflicts_stop_the_train_unless_skipped(clone: Path, sdir: Path, isolated_env: Path) -> None:
    _green(sdir, "x1", _branch(clone, "x1", {"README.md": "one\n"}))
    _green(sdir, "x2", _branch(clone, "x2", {"README.md": "two\n"}))
    _green(sdir, "x3", _branch(clone, "x3", {"x3": "3"}))
    assert _train(clone, sdir, "plan", "x1", "x2", "x3") == 2
    rep = _report(isolated_env)
    assert rep["result"] == "conflict" and [e.get("outcome") for e in rep["attempted"]] == ["merged", "conflict", None]
    assert rep["attempted"][1]["conflicts"] == ["README.md"]
    assert _train(clone, sdir, "plan", "x1", "x2", "x3", "--skip-conflicting") == 0
    assert [e["branch"] for e in _report(isolated_env)["merged"]] == ["x1", "x3"]


GEN = """import pathlib
parts = sorted(pathlib.Path('parts').glob('*.txt'))
pathlib.Path('INDEX.md').write_text(''.join(p.read_text() for p in parts))
"""


def test_generated_file_conflicts_are_resolved_by_the_generator(clone: Path, sdir: Path, isolated_env: Path,
                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    write(clone, "gen.py", GEN)
    write(clone, "parts/a.txt", "- a\n")
    write(clone, "INDEX.md", "- a\n")
    git(clone, "switch", "-q", "-c", "tmp-main", "origin/main")
    commit(clone, "generator")
    git(clone, "push", "-q", "origin", "HEAD:refs/heads/main")
    git(clone, "fetch", "-q", "origin")
    _green(sdir, "p1", _branch(clone, "p1", {"parts/b.txt": "- b\n", "INDEX.md": "- a\n- b\n"}))
    _green(sdir, "p2", _branch(clone, "p2", {"parts/c.txt": "- c\n", "INDEX.md": "- a\n- c\n"}))
    resolver = mt.Resolver("index", "gen.py", ("INDEX.md",), (sys.executable, "gen.py"))
    monkeypatch.setattr(mt, "RESOLVERS", (resolver,))
    assert _train(clone, sdir, "run", "p1", "p2") == 0
    rep = _report(isolated_env)
    assert [e["outcome"] for e in rep["merged"]] == ["merged", "resolved"]
    assert rep["merged"][1]["resolved_by"][0]["files"] == ["INDEX.md"]
    assert (Path(rep["worktree"]) / "INDEX.md").read_text() == "- a\n- b\n- c\n"
    assert git(Path(rep["worktree"]), "status", "--porcelain") == ""

    recorder = mt.Resolver("index", "gen.py", ("INDEX.md",),
                           (sys.executable, "-c", "import json, pathlib, sys; exec(open('gen.py').read()); "
                            "pathlib.Path('args.json').write_text(json.dumps(sys.argv[1:]))", "{base}", "{branches}"))
    monkeypatch.setattr(mt, "RESOLVERS", (recorder,))
    assert _train(clone, sdir, "plan", "p1", "p2") == 0
    rep = _report(isolated_env)
    args = json.loads((Path(rep["worktree"]) / "args.json").read_text())
    assert args == [rep["base"]["sha"], rep["admitted"][0]["sha"], rep["admitted"][1]["sha"]]
    assert "<<<<<<<" not in (Path(rep["worktree"]) / "INDEX.md").read_text()

    failing = mt.Resolver("index", "gen.py", ("INDEX.md",), (sys.executable, "-c", "raise SystemExit(3)"))
    monkeypatch.setattr(mt, "RESOLVERS", (failing,))
    assert _train(clone, sdir, "plan", "p1", "p2") == 2
    assert _report(isolated_env)["attempted"][1]["resolved_by"][0]["exit"] == 3


def test_main_moved_stops_the_push(clone: Path, sdir: Path, isolated_env: Path, tmp_path: Path) -> None:
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(tmp_path / "origin.git"), str(other))
    pusher = shlex.join([sys.executable, "-c",
                         "import subprocess; c = lambda *a: subprocess.run(['git', '-C', "
                         f"{str(other)!r}, *a], check=True); "
                         "open(" + repr(str(other / "late.txt")) + ", 'w').write('late'); c('add', '-A'); "
                         "c('commit', '-q', '-m', 'late'); c('push', '-q', 'origin', 'HEAD:main')"])
    _green(sdir, "b1", _branch(clone, "b1", {"b1": "1"}))
    assert _train(clone, sdir, "run", "b1", "--fetch", "--push", "--approval", "yes", gate=pusher) == 3
    rep = _report(isolated_env)
    assert rep["result"] == "main moved" and "push" not in rep
    assert _origin_main(clone) == git(other, "rev-parse", "HEAD")


def test_one_train_at_a_time(clone: Path, sdir: Path, isolated_env: Path) -> None:
    _green(sdir, "b1", _branch(clone, "b1", {"b1": "1"}))
    with mt.single_train(isolated_env / "merge-train") as mine:
        assert mine
        assert _train(clone, sdir, "plan", "b1") == 2
    assert _train(clone, sdir, "plan", "b1") == 0


def test_status_lists_runs(clone: Path, sdir: Path, isolated_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _green(sdir, "b1", _branch(clone, "b1", {"b1": "1"}))
    assert _train(clone, sdir, "plan", "b1") == 0
    run_id = _report(isolated_env)["run_id"]
    capsys.readouterr()
    assert mt.main(["status"]) == 0
    assert run_id in capsys.readouterr().out
    assert mt.main(["status", run_id]) == 0
    assert json.loads(capsys.readouterr().out)["run_id"] == run_id
    assert mt.main(["status", "nope"]) == 2


def test_default_gate_uses_the_suite_queue_when_present(tmp_path: Path) -> None:
    assert mt.default_gates(tmp_path, "r")[0] == ["uv", "run", "pytest"]
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "suite_queue.py").write_text("", encoding="utf-8")
    (tmp_path / "tools" / "regen_pins.py").write_text("", encoding="utf-8")
    gates = mt.default_gates(tmp_path, "r")
    assert gates[0][:4] == ["uv", "run", "python", "tools/suite_queue.py"] and "--" in gates[0]
    assert gates[0][gates[0].index("-n") + 1] == "10"  # the suite gate of suite-perf phase 3
    assert ["uv", "run", "python", "tools/regen_pins.py", "--check"] in gates
    (tmp_path / "tools" / "ci_local.py").write_text("", encoding="utf-8")
    assert mt.default_gates(tmp_path, "r") == [["uv", "run", "python", "tools/ci_local.py", "--label", "merge-train r"]]


BEGIN, END = "<!-- BEGIN gen -->", "<!-- END gen -->"
README_GEN = f"""import pathlib
parts = sorted(pathlib.Path('parts').glob('*.txt'))
table = ''.join(p.read_text() for p in parts)
text = pathlib.Path('README.md').read_text()
head, rest = text.split({BEGIN!r}, 1)
tail = rest.split({END!r}, 1)[1]
pathlib.Path('README.md').write_text(head + {BEGIN!r} + '\\n' + table + {END!r} + tail)
"""


def _readme_main(clone: Path) -> None:
    write(clone, "gen.py", README_GEN)
    write(clone, "parts/a.txt", "| a |\n")
    write(clone, "README.md", f"# Title\n\nIntro.\n\n{BEGIN}\n| a |\n{END}\n\nOutro.\n")
    git(clone, "switch", "-q", "-c", "tmp-main", "origin/main")
    commit(clone, "readme with a generated block")
    git(clone, "push", "-q", "origin", "HEAD:refs/heads/main")
    git(clone, "fetch", "-q", "origin")


def test_a_generated_block_keeps_both_sides_hand_written_edits(clone: Path, sdir: Path, isolated_env: Path,
                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    _readme_main(clone)
    one = f"# Title\n\nIntro, edited by p1.\n\n{BEGIN}\n| a |\n| b |\n{END}\n\nOutro.\n"
    two = f"# Title\n\nIntro.\n\n{BEGIN}\n| a |\n| c |\n{END}\n\nOutro.\nA line from p2.\n"
    _green(sdir, "p1", _branch(clone, "p1", {"parts/b.txt": "| b |\n", "README.md": one}))
    _green(sdir, "p2", _branch(clone, "p2", {"parts/c.txt": "| c |\n", "README.md": two}))
    resolver = mt.Resolver("readme", "gen.py", ("README.md",), (sys.executable, "gen.py"), block=(BEGIN, END),
                           after_merge=True)
    monkeypatch.setattr(mt, "RESOLVERS", (resolver,))
    assert _train(clone, sdir, "plan", "p1", "p2") == 0
    rep = _report(isolated_env)
    assert [e["outcome"] for e in rep["merged"]] == ["merged", "resolved"]
    text = (Path(rep["worktree"]) / "README.md").read_text()
    assert text == f"# Title\n\nIntro, edited by p1.\n\n{BEGIN}\n| a |\n| b |\n| c |\n{END}\n\nOutro.\nA line from p2.\n"


def test_a_conflict_outside_the_block_is_a_real_conflict(clone: Path, sdir: Path, isolated_env: Path,
                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    _readme_main(clone)
    one = f"# Title one\n\nIntro.\n\n{BEGIN}\n| a |\n| b |\n{END}\n\nOutro.\n"
    two = f"# Title two\n\nIntro.\n\n{BEGIN}\n| a |\n| c |\n{END}\n\nOutro.\n"
    _green(sdir, "p1", _branch(clone, "p1", {"parts/b.txt": "| b |\n", "README.md": one}))
    _green(sdir, "p2", _branch(clone, "p2", {"parts/c.txt": "| c |\n", "README.md": two}))
    monkeypatch.setattr(mt, "RESOLVERS", (mt.Resolver("readme", "gen.py", ("README.md",), (sys.executable, "gen.py"),
                                                      block=(BEGIN, END)),))
    assert _train(clone, sdir, "plan", "p1", "p2") == 2
    assert "outside the generated block" in _report(isolated_env)["attempted"][1]["error"]


def test_stale_generated_output_is_regenerated_into_the_merge_commit(clone: Path, sdir: Path, isolated_env: Path,
                                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    _readme_main(clone)
    _green(sdir, "p1", _branch(clone, "p1", {"parts/b.txt": "| b |\n"}))  # forgot to regenerate the README
    monkeypatch.setattr(mt, "RESOLVERS", (mt.Resolver("readme", "gen.py", ("README.md",), (sys.executable, "gen.py"),
                                                      block=(BEGIN, END), after_merge=True),))
    assert _train(clone, sdir, "plan", "p1") == 0
    rep = _report(isolated_env)
    wt = Path(rep["worktree"])
    assert rep["merged"][0]["regenerated"] == ["readme"]
    assert "| b |" in (wt / "README.md").read_text()
    assert git(wt, "rev-parse", "HEAD") == rep["merged"][0]["merge_commit"]  # folded into the merge commit
    assert git(wt, "log", "-1", "--format=%s").startswith("Merge branch 'p1'")
    assert git(wt, "status", "--porcelain", "--untracked-files=no") == ""


def test_an_unmigrated_generated_doc_is_a_real_conflict(clone: Path, sdir: Path, isolated_env: Path,
                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    """BF-6: before the split, gen_docs --write does nothing, so "resolving" AGENTS.md kept ours and lost theirs."""
    write(clone, "tools/gen_docs.py", "print('not migrated')\n")
    write(clone, "AGENTS.md", "# AGENTS\n\n- **Session A.** one.\n")
    git(clone, "switch", "-q", "-c", "tmp-main", "origin/main")
    commit(clone, "agents and a gen_docs stand-in")
    git(clone, "push", "-q", "origin", "HEAD:refs/heads/main")
    git(clone, "fetch", "-q", "origin")
    _green(sdir, "a1", _branch(clone, "a1", {"AGENTS.md": "# AGENTS\n\n- **Session A.** one, updated by a1.\n"}))
    _green(sdir, "a2", _branch(clone, "a2", {"AGENTS.md": "# AGENTS\n\n- **Session A.** one, updated by a2.\n"}))
    stand_in = mt.Resolver("generated docs (agents)", "tools/gen_docs.py", ("AGENTS.md",),
                           (sys.executable, "tools/gen_docs.py"), ready="docs/agents")
    monkeypatch.setattr(mt, "RESOLVERS", (stand_in,))
    assert _train(clone, sdir, "plan", "a1", "a2") == 2
    rep = _report(isolated_env)
    assert rep["result"] == "conflict" and rep["attempted"][1]["outcome"] == "conflict"
    assert "resolved_by" not in rep["attempted"][1]


def test_the_pin_resolver_owns_only_whole_generated_files() -> None:
    """BF-7: C_data_model.md is hand-written prose with generated parts; README.md has its own block resolver;
    pins of families that can be skipped are never claimed; item-labels.json belongs to spec_labels."""
    import fnmatch

    import regen_pins as rp

    pins = next(r for r in mt.RESOLVERS if r.name == "test pins").patterns
    owned = lambda path: any(fnmatch.fnmatch(path, p) for p in pins)  # noqa: E731
    assert not owned(rp.C_SPEC) and not owned("README.md")
    assert not owned("src/agentprov/adapters/agentdojo/tables/agentdojo-history.table.toml")  # needs the cache
    assert owned("tests/golden/gate_d_digests.json") and owned("tests/adapters/agentdojo/history_aer_digests.json")
    assert owned("docs/architecture/examples/C/agentdojo_2024_pi_detector.aer.jsonl")
    assert not owned("docs/architecture/examples/C/stac_case_223.aer.jsonl")  # hand-maintained vector
    labels = [r.name for r in mt.RESOLVERS if "docs/architecture/item-labels.json" in r.patterns]
    assert labels == ["spec labels"]
    docs = {r.patterns[0]: r.ready for r in mt.RESOLVERS if r.name.startswith("generated docs")}
    assert docs == {"docs/architecture/DECISIONS.md": "docs/architecture/decisions",
                    "docs/reports/analysis/regen-batch.md": "docs/reports/analysis/regen-batch",
                    "AGENTS.md": "docs/agents"}
    (decisions,) = [r for r in mt.RESOLVERS if r.name == "generated docs (decisions)"]
    assert "docs/architecture/decision-log/*.md" in decisions.patterns  # D-1003: the parts are generated too
    assert decisions.outputs == ("docs/architecture/decision-log",)


CBEGIN, CEND = "<!-- BEGIN corpora -->", "<!-- END corpora -->"
GEN_CORPORA = f"""import pathlib
parts = sorted(pathlib.Path('cparts').glob('*.txt'))
table = ''.join(p.read_text() for p in parts)
text = pathlib.Path('README.md').read_text()
head, rest = text.split({CBEGIN!r}, 1)
tail = rest.split({CEND!r}, 1)[1]
pathlib.Path('README.md').write_text(head + {CBEGIN!r} + '\\n' + table + {CEND!r} + tail)
"""


def test_two_generated_readme_blocks_are_both_regenerated(clone: Path, sdir: Path, isolated_env: Path,
                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    """README.md holds two generated blocks (sources and corpora); a conflict in either keeps both branches'
    hand-written edits, and both blocks are filled by their own generators."""
    write(clone, "gen.py", README_GEN)
    write(clone, "gen_c.py", GEN_CORPORA)
    write(clone, "parts/a.txt", "| a |\n")
    write(clone, "cparts/x.txt", "- x\n")
    base = f"# T\n\n{BEGIN}\n| a |\n{END}\n\nMiddle.\n\n{CBEGIN}\n- x\n{CEND}\n\nEnd.\n"
    write(clone, "README.md", base)
    git(clone, "switch", "-q", "-c", "tmp-main", "origin/main")
    commit(clone, "two blocks")
    git(clone, "push", "-q", "origin", "HEAD:refs/heads/main")
    git(clone, "fetch", "-q", "origin")
    one = base.replace("| a |\n", "| a |\n| b |\n").replace("Middle.", "Middle, edited by p1.")
    two = base.replace("- x\n", "- x\n- y\n").replace("| a |\n", "| a |\n| c |\n").replace("End.", "End, by p2.")
    _green(sdir, "p1", _branch(clone, "p1", {"parts/b.txt": "| b |\n", "README.md": one}))
    _green(sdir, "p2", _branch(clone, "p2", {"parts/c.txt": "| c |\n", "cparts/y.txt": "- y\n", "README.md": two}))
    resolver = mt.Resolver("readme", "gen.py", ("README.md",), (sys.executable, "gen.py"), block=(BEGIN, END),
                           after_merge=True, more=(("gen_c.py", (CBEGIN, CEND), (sys.executable, "gen_c.py")),))
    monkeypatch.setattr(mt, "RESOLVERS", (resolver,))
    assert _train(clone, sdir, "plan", "p1", "p2") == 0
    rep = _report(isolated_env)
    assert [e["outcome"] for e in rep["merged"]] == ["merged", "resolved"]
    assert len(rep["merged"][1]["resolved_by"]) == 2  # both generators ran
    text = (Path(rep["worktree"]) / "README.md").read_text()
    assert text == (f"# T\n\n{BEGIN}\n| a |\n| b |\n| c |\n{END}\n\nMiddle, edited by p1.\n\n"
                    f"{CBEGIN}\n- x\n- y\n{CEND}\n\nEnd, by p2.\n")


# --------------------------------------------------------------------------------------------------- split docs (4a)

TOOLS = Path(mt.__file__).resolve().parent
REAL_DECISIONS = next(r for r in mt.RESOLVERS if r.name == "generated docs (decisions)")  # before any monkeypatch
SPLIT_DECISIONS = """# Brief

## Addendum D

- **D-1 (U-15).** First.
- **D-2 (2026-10-08, y).** Second.
"""


def _decisions_resolver(adopt: bool = True) -> mt.Resolver:
    """The real decisions resolver, run with this interpreter instead of ``uv run python``."""
    real = REAL_DECISIONS
    assert real.command[:3] == ("uv", "run", "python") and real.adopt and real.adopt[:3] == ("uv", "run", "python")
    return dataclasses.replace(real, command=(sys.executable, *real.command[3:]),
                               adopt=(sys.executable, *real.adopt[3:]) if adopt else None)


def _split_main(clone: Path) -> str:
    """main gets DECISIONS.md, then the split (fragments, same bytes); returns the commit before the split."""
    for name in ("gen_docs.py", "_workflow.py"):
        write(clone, f"tools/{name}", (TOOLS / name).read_text(encoding="utf-8"))
    write(clone, "docs/architecture/DECISIONS.md", SPLIT_DECISIONS)
    git(clone, "switch", "-q", "-c", "tmp-main", "origin/main")
    before = commit(clone, "decisions, before the split")
    subprocess.run([sys.executable, "tools/gen_docs.py", "--split", "decisions"], cwd=clone, check=True,
                   capture_output=True)
    commit(clone, "the split")
    git(clone, "push", "-q", "origin", "HEAD:refs/heads/main")
    git(clone, "fetch", "-q", "origin")
    return before


def _entry(n: int, who: str) -> str:
    return f"- **D-{n} (2026-10-21, {who}).** Entry {n}.\n"


def test_a_branch_from_before_the_split_keeps_its_entries(clone: Path, sdir: Path, isolated_env: Path,
                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    """Its entry is only in DECISIONS.md: --write alone regenerates from the fragments and drops it; --adopt first
    moves it into a fragment."""
    before = _split_main(clone)
    _green(sdir, "old", _branch(clone, "old", {"docs/architecture/DECISIONS.md": SPLIT_DECISIONS + _entry(6, "old")},
                                start=before))
    monkeypatch.setattr(mt, "RESOLVERS", (_decisions_resolver(adopt=False),))
    assert _train(clone, sdir, "plan", "old") == 0
    lost = (Path(_report(isolated_env)["worktree"]) / "docs/architecture/DECISIONS.md").read_text()
    assert "D-6" not in lost  # the silent loss this fix prevents

    monkeypatch.setattr(mt, "RESOLVERS", (_decisions_resolver(),))
    assert _train(clone, sdir, "plan", "old") == 0
    rep = _report(isolated_env)
    wt = Path(rep["worktree"])
    assert rep["merged"][0]["outcome"] == "merged" and rep["merged"][0]["regenerated"] == ["generated docs (decisions)"]
    assert (wt / "docs/architecture/DECISIONS.md").read_text() == SPLIT_DECISIONS + _entry(6, "old")
    assert (wt / "docs/architecture/decisions/D-6.md").read_text() == _entry(6, "old")
    check = subprocess.run([sys.executable, "tools/gen_docs.py", "--check"], cwd=wt, capture_output=True, text=True)
    assert check.returncode == 0, check.stdout + check.stderr
    assert git(wt, "status", "--porcelain") == ""


def test_a_conflicted_doc_is_regenerated_after_the_split_and_refused_before_it(
        clone: Path, sdir: Path, isolated_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    before = _split_main(clone)
    # main gains D-7 the post-split way: a fragment, then the regenerated file
    git(clone, "switch", "-q", "-c", "main-d7", "origin/main")
    write(clone, "docs/architecture/decisions/D-7.md", _entry(7, "main"))
    subprocess.run([sys.executable, "tools/gen_docs.py", "--write", "decisions"], cwd=clone, check=True,
                   capture_output=True)
    commit(clone, "D-7")
    git(clone, "push", "-q", "origin", "HEAD:refs/heads/main")
    git(clone, "fetch", "-q", "origin")
    after = git(clone, "rev-parse", "HEAD~1")  # the split, without D-7
    _green(sdir, "old", _branch(clone, "old", {"docs/architecture/DECISIONS.md": SPLIT_DECISIONS + _entry(6, "old")},
                                start=before))
    _green(sdir, "new", _branch(clone, "new", {"docs/architecture/decisions/D-8.md": _entry(8, "new"),
                                               "docs/architecture/DECISIONS.md": SPLIT_DECISIONS + _entry(8, "new")},
                                start=after))
    monkeypatch.setattr(mt, "RESOLVERS", (_decisions_resolver(),))

    assert _train(clone, sdir, "plan", "new") == 0  # fragments are the truth: both entries regenerated
    rep = _report(isolated_env)
    assert rep["merged"][0]["outcome"] == "resolved"
    assert (Path(rep["worktree"]) / "docs/architecture/DECISIONS.md").read_text() == (
        SPLIT_DECISIONS + _entry(7, "main") + _entry(8, "new"))

    assert _train(clone, sdir, "plan", "old") == 2  # ours would lose D-6, theirs D-7: back to the branch owner
    rep = _report(isolated_env)
    entry = rep["attempted"][0]
    assert entry["outcome"] == "conflict" and "resolved_by" not in entry
    assert "predates the split" in entry["error"] and "gen_docs.py --adopt" in entry["error"]
