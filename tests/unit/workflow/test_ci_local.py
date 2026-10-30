"""``tools/ci_local.py``: the ci.yml jobs on this machine (D-462). The job table must stay in step with ci.yml."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import ci_local as cl
import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]
DISPATCH_ONLY = "github.event_name == 'workflow_dispatch'"


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load((REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))


def test_every_ci_job_has_a_local_job_with_the_same_dispatch_rule(workflow: dict) -> None:
    jobs = workflow["jobs"]
    mirrored = {j.ci_job: j for j in cl.JOBS if j.ci_job}
    assert set(mirrored) == set(jobs)
    for name, spec in jobs.items():
        assert mirrored[name].dispatch_only == (spec.get("if") == DISPATCH_ONLY), name
        assert mirrored[name].id == name
    assert {j.id for j in cl.JOBS if j.ci_job is None} == {"generated", "pins", "readme-sources", "ids"}


def test_the_lockfile_lists_match_ci(workflow: dict) -> None:
    core = " ".join(str(step.get("run", "")) for step in workflow["jobs"]["core"]["steps"])
    projects = re.search(r"for p in ([^;]+); do", core)
    assert projects and tuple(projects.group(1).split()) == cl.LOCK_PROJECTS
    osv = " ".join(str(s.get("with", {}).get("scan-args", "")) for s in workflow["jobs"]["dependencies"]["steps"])
    assert tuple(re.findall(r"--lockfile=(\S+)", osv)) == cl.OSV_LOCKFILES
    ci_markers = [str(s.get("run", "")) for s in workflow["jobs"]["core"]["steps"] if "pytest -m" in str(s.get("run"))]
    assert ci_markers and cl.CORE_MARKERS in ci_markers[0]


def test_the_generated_job_checks_docs_registry_and_spec_citations(tmp_path: Path) -> None:
    ctx = cl.Context(root=tmp_path, rundir=tmp_path, label="x", allow_network=False)
    tools = {(s.argv[s.argv.index("python") + 1], s.argv[-1]) for s in cl._generated(ctx)}
    assert tools == {("tools/gen_docs.py", "--check"), ("tools/gen_registry.py", "--check"),
                     ("tools/spec_labels.py", "--check")}


def test_core_runs_the_merge_gate_through_the_queue(tmp_path: Path) -> None:
    ctx = cl.Context(root=tmp_path, rundir=tmp_path, label="x", allow_network=False)
    (suite,) = [s for s in cl._core(ctx) if "tools/suite_queue.py" in s.argv]
    assert suite.argv[suite.argv.index("--") + 1:] == cl.suite_argv()
    options = ("--dist", "loadgroup", "-p", "no:randomly", "-p", "no:cacheprovider")
    assert cl.suite_argv({}, cpus=12) == ("pytest", "-n", "10", *options)  # the user's -n 10 on the M2 Max
    assert cl.suite_argv({}, cpus=36) == ("pytest", "-n", "24", *options)  # the Mac Studio
    assert cl.suite_argv({"AGENTPROV_SUITE_WORKERS": "6"}, cpus=36) == ("pytest", "-n", "6", *options)
    for bad in ("0", "-2", "ten"):
        with pytest.raises(SystemExit):
            cl.suite_workers({"AGENTPROV_SUITE_WORKERS": bad})
    assert "suite_queue.py" in (REPO / "README.md").read_text(encoding="utf-8")
    if (REPO / "AGENTS.md").is_file():  # the development repository only (the public export leaves it out, D-1004)
        assert "suite_queue.py" in (REPO / "AGENTS.md").read_text(encoding="utf-8")


def test_selection() -> None:
    default = [j.id for j in cl.select(None, [], False)]
    assert "old-vs-new" not in default and "fuzz-thorough" not in default and "core" in default
    assert "backend-autodojo" in [j.id for j in cl.select(None, [], True)]
    assert [j.id for j in cl.select(["secrets", "fuzz-thorough"], [], False)] == ["secrets", "fuzz-thorough"]
    assert "core" not in [j.id for j in cl.select(None, ["core"], False)]
    with pytest.raises(ValueError, match="unknown job"):
        cl.select(["nope"], [], False)


def _py(code: str) -> tuple[str, ...]:
    return (sys.executable, "-c", code)


FAKE_JOBS = (
    cl.Job("ok", None, lambda ctx: [cl.Step("passes", _py("print('fine')"))]),
    cl.Job("bad", None, lambda ctx: [cl.Step("fails", _py("raise SystemExit(3)")),
                                     cl.Step("never", _py("raise SystemExit(9)"))]),
    cl.Job("net", None, lambda ctx: [cl.Step("x", _py("pass"))], network=True),
    cl.Job("tool", None, lambda ctx: [cl.Step("x", _py("pass"))], requires=("no-such-tool-xyz",)),
    cl.Job("sync", None, lambda ctx: [cl.Step("sync", _py("import sys; print('error: Network connectivity is "
                                                            "disabled'); sys.exit(2)"), sync=True)]),
)


def test_statuses_report_and_exit_codes(repo: Path, isolated_env: Path, monkeypatch: pytest.MonkeyPatch,
                                        capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(cl, "JOBS", FAKE_JOBS)
    assert cl.main(["-C", str(repo), "--only", "ok,net,tool"]) == 0  # skips do not fail without --strict
    out = capsys.readouterr().out
    assert "net" in out and "needs the network" in out and "not installed: no-such-tool-xyz" in out
    assert cl.main(["-C", str(repo), "--only", "ok,net", "--strict"]) == 1
    assert cl.main(["-C", str(repo), "--only", "ok,bad"]) == 1
    report = _last_report(isolated_env)
    statuses = {j["job"]: (j["status"], [s["name"] for s in j["steps"]]) for j in report["jobs"]}
    assert statuses == {"ok": ("pass", ["passes"]), "bad": ("fail", ["fails"])}  # stops at the failing step
    assert cl.main(["-C", str(repo), "--only", "sync"]) == 0
    assert _last_report(isolated_env)["jobs"][0]["status"] == "unavailable"
    log = next((isolated_env / "ci-local").glob("*/sync.log")).read_text()
    assert "--offline" in log  # syncs run offline unless --allow-network


def _last_report(home: Path) -> dict:
    path = max((home / "ci-local").glob("*/report.json"), key=lambda p: p.stat().st_mtime_ns)
    return json.loads(path.read_text(encoding="utf-8"))


def test_list_names_every_job(capsys: pytest.CaptureFixture[str]) -> None:
    assert cl.main(["--list"]) == 0
    out = capsys.readouterr().out
    for job in cl.JOBS:
        assert job.id in out
    assert "network, dispatch-only" in out
