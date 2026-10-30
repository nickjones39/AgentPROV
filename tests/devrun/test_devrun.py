"""D-705: dev runs in the core (``agentprov.devrun.plan``, ``agentprov devrun``): the settings keys, the plan, the
three steps per part (never ``--release``; D-529 sampling; the §8.3a skip), start (R2 needs ``--confirm-r2``; the run
folder, its manifest and its batch), the listing and prune (GR-25: never a folder in use; GR-26: only real run
folders, never a link). No step runs here: the batch driver is stubbed."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any, NamedTuple

import pytest

from agentprov import settings
from agentprov.cli import devrun as devrun_cmd
from agentprov.cli.main import main
from agentprov.devrun.plan import DEFAULTS, DEVRUN_FORMAT, DevSettings, plan, run_dirs

PARTS = [("agentdojo", "2024-06", "supported", "p1"), ("agentdojo", "head", "partial", "p2"),
         ("adprov-v1", "release", "supported", "p3")]


class Run(NamedTuple):
    code: int
    out: str
    err: str


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    h = tmp_path / "home"
    monkeypatch.setenv("AGENTPROV_HOME", str(h))
    return h


@pytest.fixture
def cli(capsys: pytest.CaptureFixture[str], home: Path) -> Callable[..., Run]:
    def run(*argv: str) -> Run:
        capsys.readouterr()
        code = main([*argv[:2], "--progress", "off", *argv[2:]])
        out, err = capsys.readouterr()
        return Run(code, out, err)

    return run


def test_settings_keys_round_trip_and_drive_the_plan(home: Path) -> None:
    for key, value in (("devrun.samples", "3"), ("devrun.override.agentdojo.head", "0"),
                       ("devrun.override.adprov-v1", "9"), ("devrun.exclude", "nothing/here"),
                       ("devrun.sample_mode", "spread"), ("devrun.live.cost_cap", "2.5")):
        settings.set(key, value, home=home)
    s = DevSettings.from_settings(settings.items("devrun.", home=home))
    assert s.samples == 3 and s.mode == "spread" and s.live_cost_cap == 2.5
    assert {p.key: p.samples for p in plan(s, PARTS)} == {"agentdojo/2024-06": 3, "adprov-v1/release": 9}
    assert DevSettings.from_settings(s.to_settings()) == s
    assert DEFAULTS.to_settings() == {}
    included = DevSettings(include=("agentdojo",))
    assert [p.key for p in plan(included, PARTS)] == ["agentdojo/2024-06", "agentdojo/head"]


def test_steps_never_release_and_follow_the_sampling_and_conformance_rules(tmp_path: Path) -> None:
    (part,) = plan(DevSettings(), PARTS[:1])
    steps = devrun_cmd.run_steps(part, tmp_path / "run", DevSettings(), queue=True)
    argvs = [s.request.argv for s in steps]
    assert [a[0] for a in argvs] == ["import", "validate", "recompute"]
    flat = [t for a in argvs for t in a]
    assert "--release" not in flat and "package" not in flat and "--fetch" in argvs[0] and "--seed" not in flat
    assert argvs[2][-1] == "--dry-run" and all(s.request.queue_cpu == 2 for s in steps)
    assert steps[0].request.tier == "R2" and steps[0].request.extra == {"devrun": "run", "part": "agentdojo/2024-06"}
    rnd = devrun_cmd.run_steps(part, tmp_path / "r", DevSettings(mode="random", seed=7), queue=False)[0].request
    assert rnd.argv[rnd.argv.index("--seed") + 1] == "7" and rnd.queue_cpu is None
    off = devrun_cmd.run_steps(part, tmp_path / "o", DevSettings(prov_conformance=False), queue=False)
    assert "--skip-prov-conformance" in off[0].request.argv and off[1].request.argv[-2:] == ("--tiers", "aer,sem,linkage")
    assert "--skip-prov-conformance" not in off[2].request.argv


def test_plan_writes_nothing_and_start_needs_confirm_r2(cli: Callable[..., Run], home: Path,
                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    import agentprov.devrun.plan as plan_mod

    monkeypatch.setattr(plan_mod, "importable_parts", lambda: PARTS[:2])
    doc = json.loads(cli("devrun", "plan", "--format", "json").out)
    assert doc["format"] == "agentprov-devrun-plan/0.1" and len(doc["parts"]) == 2 and len(doc["steps"]) == 6
    assert not (home / "dev-runs").exists() and not (home / "batches").exists()
    refused = cli("devrun", "start")
    assert refused.code == 4 and "--confirm-r2" in refused.err and not (home / "dev-runs").exists()
    started: list[Any] = []

    def fake_start(ctx: Any, batch: Any, confirm: bool, result: Any) -> Any:
        started.append((batch, confirm))
        return SimpleNamespace(job_id="driver-0")

    monkeypatch.setattr("agentprov.cli.batch._start", fake_start)
    run = cli("devrun", "start", "--confirm-r2", "--format", "json")
    assert run.code == 0, run.err
    out = json.loads(run.out)
    manifest = json.loads((Path(out["run_dir"]) / "devrun.json").read_text())
    assert manifest["format"] == DEVRUN_FORMAT and manifest["batch_id"] == out["batch_id"]
    ((batch, confirm),) = started
    assert confirm and batch.continue_on_failure and len(batch.steps) == 6 and out["driver_job_id"] == "driver-0"


def _run(home: Path, name: str) -> Path:
    d = home / "dev-runs" / name
    (d / "p").mkdir(parents=True)
    (d / "devrun.json").write_text(json.dumps({"format": DEVRUN_FORMAT}))
    return d


def test_prune_keeps_the_newest_and_spares_runs_in_use(cli: Callable[..., Run], home: Path, tmp_path: Path) -> None:
    from agentprov.jobs.batch import Batch, BatchStep
    from agentprov.jobs.manager import JobRequest

    names = ["20261001T000000Z", "20261002T000000Z", "20261003T000000Z", "20261004T000000Z"]
    runs = [_run(home, n) for n in names]
    (home / "dev-runs" / "not-a-run").mkdir()
    (home / "dev-runs" / "20261005T000000Z").mkdir()  # no manifest: not a run, never deleted
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "devrun.json").write_text(json.dumps({"format": DEVRUN_FORMAT}))
    os.symlink(outside, home / "dev-runs" / "20260930T000000Z")  # a link: never followed
    step = BatchStep(JobRequest(("validate", "--corpus", str(runs[1] / "p")), reads=(str(runs[1] / "p"),)))
    Batch.new(home, "unfinished", [step])  # pending: its run is in use
    assert [p.name for p in run_dirs(home)] == names
    listing = cli("devrun", "prune", "--keep", "1")
    assert listing.code == 0 and all(r.exists() for r in runs)
    assert cli("devrun", "prune", "--keep", "1", "--yes").code == 0
    assert [r.exists() for r in runs] == [False, True, False, True]
    assert (home / "dev-runs" / "not-a-run").exists() and (home / "dev-runs" / "20261005T000000Z").exists()
    assert outside.exists() and (outside / "devrun.json").exists()


def test_list_names_runs_newest_first(cli: Callable[..., Run], home: Path) -> None:
    _run(home, "20261001T000000Z")
    _run(home, "20261002T000000Z")
    doc = json.loads(cli("devrun", "list", "--format", "json").out)
    assert doc["format"] == "agentprov-devrun-list/0.1"
    assert [r["run"] for r in doc["runs"]] == ["20261002T000000Z", "20261001T000000Z"]


def test_the_summary_reads_each_parts_jobs(tmp_path: Path) -> None:
    from agentprov.devrun.plan import summarise

    jobs = []
    for cmd, counters in (("import", {"sealed": 4, "degenerate": 1}), ("validate", {}), ("recompute", {"differences": 0})):
        d = tmp_path / cmd
        d.mkdir()
        (d / "summary.json").write_text(json.dumps({"outcome": "ok", "counters": counters,
                                                    "issues_by_code": {"map.x": 3} if cmd == "import" else {}}))
        jobs.append(SimpleNamespace(record={"command": cmd, "extra": {"part": "a/p1"}}, command=cmd, outcome="ok",
                                    file=lambda name, d=d: d / name))
    (row,) = summarise(jobs)
    assert row.import_outcome == "ok" and row.counters["degenerate"] == 1 and row.issues_top == [("map.x", 3)]
    assert row.validate_outcome == "ok" and row.recompute_counters == {"differences": 0}
