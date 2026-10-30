"""Gate G0 (J.3.1) on a synthetic baseline repository, the report shape (J.3.0) and the real baseline (``full_corpus``)."""

from __future__ import annotations

import dataclasses
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agentprov.migration import gates
from agentprov.migration.lock import LockError
from git_support import TAG, git, make_lock, make_repo, sha, snapshot, write_lock

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")

REPO = Path(__file__).resolve().parents[2]
J30_KEYS = [
    "report", "gate", "scope", "role", "agentprov", "baseline_lock_sha256", "specs", "environment", "inputs", "params",
    "counts", "failures", "outputs", "started_at", "ended_at", "wall_s", "verdict",
]


@pytest.fixture(scope="module")
def world_template(tmp_path_factory):
    """The synthetic baseline repository, built once per module (7 git calls)."""
    return make_repo(tmp_path_factory.mktemp("g0-template"))


@pytest.fixture
def world(tmp_path, world_template):
    """A copy of the template per test (tests commit, tag and edit files in their own repository), locked from the copy
    itself, so the lock never describes another repository."""
    repo = tmp_path / world_template.name
    shutil.copytree(world_template, repo, symlinks=True)
    lock_path = write_lock(tmp_path / "baseline.lock.json", make_lock(repo))
    cfg = gates.MigrationConfig(baseline_corpus=repo, lock_path=lock_path, reports_dir=tmp_path / "reports", workers=2)
    return repo, lock_path, cfg


def _status(report):
    return {c.check: c.status for c in report.checks}


def _with(cfg, **over):
    return gates.MigrationConfig(**{f: getattr(cfg, f) for f in cfg.__dataclass_fields__} | over)


def test_g0_passes_on_a_matching_baseline_and_marks_the_unrecorded_hashes_skipped(world):
    _, _, cfg = world
    report = gates.verify_baseline(cfg)
    status = _status(report)
    assert report.verdict == "pass"
    assert {k: v for k, v in status.items() if v != "pass"} == {
        "environment.requirements_lock": "skipped", "environment.baseline_wheel": "skipped",
    }
    assert report.counts == {"expected": 12, "checked": 10, "passed": 10, "failed": 0, "skipped": 2}
    assert report.notes and all("not record" in n for n in report.notes)  # skipped is never silent
    assert {i["name"] for i in report.inputs} == set(json.loads(cfg.lock_path.read_text())["trees"])


def test_g0_strict_release_mode_fails_on_unrecorded_hashes(world):
    _, _, cfg = world
    report = gates.verify_baseline(_with(cfg, strict=True))
    assert report.verdict == "fail" and report.params["strict"] is True
    assert {c.check for c in report.checks if c.status == "fail"} == {"environment.requirements_lock", "environment.baseline_wheel"}


def test_g0_checks_the_recorded_requirements_and_wheel_hashes(tmp_path, world):
    repo, lock_path, cfg = world
    req, wheel = tmp_path / "req.txt", tmp_path / "w.whl"
    req.write_bytes(b"pins\n")
    wheel.write_bytes(b"wheel bytes")
    write_lock(lock_path, make_lock(repo, requirements_lock_sha256=sha(b"pins\n"), baseline_wheel_sha256=sha(b"wheel bytes")))
    good = _with(cfg, requirements_path=req, baseline_wheel=wheel, strict=True)
    assert gates.verify_baseline(good).verdict == "pass"
    wheel.write_bytes(b"other")
    bad = gates.verify_baseline(good)
    assert bad.verdict == "fail" and _status(bad)["environment.baseline_wheel"] == "fail" and _status(bad)["environment.requirements_lock"] == "pass"
    wheel.unlink()
    assert _status(gates.verify_baseline(good))["environment.baseline_wheel"] == "fail"  # recorded but missing


def test_g0_fails_when_a_corpus_file_changes_is_added_or_removed(world):
    repo, _, cfg = world
    target = repo / "corpus" / "corpus-prov" / "m1" / "prov" / "atk" / "a.json"
    original = target.read_bytes()
    target.write_bytes(original + b" ")
    report = gates.verify_baseline(cfg)
    assert report.verdict == "fail" and _status(report)["tree.release_graphs"] == "fail"
    assert _status(report)["tree.release_transcripts"] == "pass"
    target.write_bytes(original)
    (repo / "runs" / "pipe" / "extra.json").write_bytes(b"{}")
    report = gates.verify_baseline(cfg)
    assert _status(report)["tree.native_runs"] == "fail" and "2 files" in next(c.detail for c in report.checks if c.check == "tree.native_runs")
    (repo / "runs" / "pipe" / "extra.json").unlink()
    shutil.rmtree(repo / "runs")
    assert _status(gates.verify_baseline(cfg))["tree.native_runs"] == "fail"


def test_g0_fails_on_a_dirty_working_tree_and_on_a_changed_tracked_file(world):
    repo, _, cfg = world
    (repo / "untracked.txt").write_text("x")
    report = gates.verify_baseline(cfg)
    assert report.verdict == "fail" and _status(report)["git.status_clean"] == "fail"
    (repo / "untracked.txt").unlink()
    (repo / "README.md").write_text("edited\n")
    report = gates.verify_baseline(cfg)
    assert _status(report)["git.status_clean"] == "fail"
    assert _status(report)["git.tracked_files"] == "pass"  # blobs are read from the lock commit, not the work tree


def test_g0_accepts_a_later_head_when_the_tag_resolves_to_the_lock_commit(world):
    repo, _, cfg = world
    (repo / "later.txt").write_text("later\n")
    git(repo, "add", "later.txt")
    git(repo, "commit", "-q", "-m", "later")
    report = gates.verify_baseline(cfg)
    head = next(c for c in report.checks if c.check == "git.head")
    assert head.status == "pass" and "tag resolves" in head.detail and report.verdict == "pass"
    git(repo, "tag", "-f", "-a", TAG, "-m", "moved")  # the tag now points to the later commit
    moved = gates.verify_baseline(cfg)
    assert _status(moved)["git.tag_object"] == "fail" and _status(moved)["git.head"] == "fail" and moved.verdict == "fail"


def test_g0_fails_for_a_lightweight_or_missing_tag_and_for_moved_published_tags(world):
    repo, _, cfg = world
    git(repo, "tag", "-d", "baseline-tag")
    assert _status(gates.verify_baseline(cfg))["git.tag_object"] == "fail"
    git(repo, "tag", "baseline-tag")  # lightweight: cat-file -t says commit
    report = gates.verify_baseline(cfg)
    assert _status(report)["git.tag_object"] == "fail" and "not an annotated tag" in next(c.detail for c in report.checks if c.check == "git.tag_object")
    (repo / "x.txt").write_text("x")
    git(repo, "add", "x.txt")
    git(repo, "commit", "-q", "-m", "second")
    git(repo, "tag", "-f", "-a", "pub-1", "-m", "moved")
    assert _status(gates.verify_baseline(cfg))["git.existing_tags"] == "fail"


def test_g0_never_writes_to_the_baseline_repository(world):
    repo, _, cfg = world
    (repo / "dirty.txt").write_text("make git status want to look")
    before = snapshot(repo)
    gates.verify_baseline(cfg)
    assert snapshot(repo) == before


@pytest.mark.parametrize("config", ["unset", "not_a_directory", "not_git"])
def test_g0_raises_an_environment_error_without_a_usable_baseline(world, tmp_path, config):
    _, _, cfg = world
    target = {"unset": None, "not_a_directory": tmp_path / "nope", "not_git": tmp_path}[config]
    with pytest.raises(gates.BaselineUnavailableError) as info:
        gates.verify_baseline(_with(cfg, baseline_corpus=target))
    assert info.value.exit_code == 3


def test_g0_raises_on_an_invalid_lock(world, tmp_path):
    _, _, cfg = world
    bad = tmp_path / "bad.lock.json"
    bad.write_text("{}")
    with pytest.raises(LockError):
        gates.verify_baseline(_with(cfg, lock_path=bad))


# --------------------------------------------------------------------------------------------- the report (J.3.0)


def test_the_report_has_the_j30_shape_and_no_absolute_paths(world, tmp_path):
    _, lock_path, cfg = world
    fixed = datetime(2026, 10, 8, 1, 2, 3, tzinfo=UTC)
    report = gates.verify_baseline(cfg, clock=lambda: fixed)
    doc = report.to_json()
    assert [k for k in doc if k in J30_KEYS] == J30_KEYS
    assert doc["report"] == "agentprov-migration-gate/0.1" and doc["gate"] == "G0" and doc["scope"] == "full" and doc["role"] == "release"
    assert doc["baseline_lock_sha256"] == sha(lock_path.read_bytes())
    assert set(doc["specs"]) == {"aer", "sem", "agentprov-prov", "adprov-v2.3-compat"} and doc["specs"]["aer"] == "aer/0.2"
    assert doc["environment"]["baseline_python"] is None and doc["environment"]["python"].startswith(f"{sys.version_info.major}.")
    assert set(doc["agentprov"]) == {"version", "commit", "dirty"}
    assert set(doc["counts"]) == {"expected", "checked", "passed", "failed", "skipped"}
    assert doc["params"]["strict"] is False and doc["started_at"] == "2026-10-08T01:02:03Z" and doc["verdict"] == "pass"
    assert report.report_id.startswith("2026-10-08-")
    text = json.dumps(doc)
    for path in (tmp_path, REPO, Path.home()):
        assert str(path) not in text, "reports carry no absolute user paths"


def test_write_report_uses_the_gate_directory_and_the_report_id(world, tmp_path):
    _, _, cfg = world
    report = gates.verify_baseline(cfg, clock=lambda: datetime(2026, 10, 8, tzinfo=UTC))
    path = gates.write_report(report, cfg.reports_dir)
    assert path == cfg.reports_dir / "G0" / f"{report.report_id}.json"
    assert json.loads(path.read_text())["verdict"] == "pass" and path.read_text().endswith("}\n")


def _synthetic_report(scope: str, *, strict: bool = False, gate: str = "A") -> gates.GateReport:
    return gates.GateReport(
        gate=gate, scope=scope, role="release", agentprov={"commit": "7f8f8cb3" + "0" * 32}, baseline_lock_sha256="a" * 64,
        specs={}, environment={}, inputs=(), params={"strict": strict}, checks=(gates.Check("x", gates.PASS),), outputs=(),
        started_at="2026-10-14T09:00:00Z", ended_at="2026-10-14T12:00:00Z", wall_s=1.0,
    )


@pytest.mark.parametrize(("scope", "strict"), [("golden", False), ("sample", False), ("full", True)], ids=["golden", "sample", "strict"])
def test_the_default_path_never_replaces_a_report_of_another_scope_or_mode(tmp_path, scope, strict):
    """CB-27: ``<date>-<commit>`` names no scope, so a later golden, sample or release-mode run on the same day and commit
    reached the full-scope report's file and replaced the evidence that AD-07 and J.3.0 look up."""
    first = gates.write_report(_synthetic_report("full"), tmp_path)
    before = first.read_bytes()
    with pytest.raises(gates.ReportExistsError) as excinfo:
        gates.write_report(_synthetic_report(scope, strict=strict), tmp_path)
    assert excinfo.value.exit_code == 4 and excinfo.value.code == "migration.report.exists" and "--report" in str(excinfo.value)
    assert first.read_bytes() == before
    assert gates._passing_report_exists([tmp_path], gate="A", scope="full", commit="7f8f8cb3" + "0" * 32, lock_digest="a" * 64, strict=False)


def test_a_rerun_of_the_same_scope_and_mode_replaces_the_default_report_and_an_exact_path_is_kept(tmp_path):
    first = gates.write_report(_synthetic_report("full"), tmp_path)
    assert gates.write_report(dataclasses.replace(_synthetic_report("full"), wall_s=2.0), tmp_path) == first
    assert json.loads(first.read_text())["wall_s"] == 2.0
    assert gates.write_report(_synthetic_report("golden"), path=first) == first  # --report: the user chose the file
    assert json.loads(first.read_text())["scope"] == "golden"


def test_failures_are_listed_without_payload_text_and_capped_at_100():
    checks = tuple(gates.Check(f"c{i}", "fail", "d") for i in range(150))
    report = gates.GateReport(
        gate="G0", scope="full", role="release", agentprov={"commit": None}, baseline_lock_sha256="0" * 64, specs={},
        environment={}, inputs=(), params={}, checks=checks, outputs=(), started_at="2026-10-08T00:00:00Z",
        ended_at="2026-10-08T00:00:00Z", wall_s=0.0,
    )
    assert len(report.failures) == 100 and report.counts["failed"] == 150 and report.report_id.endswith("-nocommit")


# --------------------------------------------------------------------------------------------- configuration


def test_config_reads_the_j26_variables_with_the_environment_winning_over_local_toml(tmp_path):
    toml = tmp_path / "local.toml"
    toml.write_text('[env]\nAGENTPROV_BASELINE_CORPUS = "/from/file"\nAGENTPROV_BASELINE_PYTHON = "/py/file"\nOTHER = "ignored"\n')
    cfg = gates.MigrationConfig.from_env({"AGENTPROV_BASELINE_CORPUS": "/from/env"}, config_file=toml)
    assert cfg.baseline_corpus == Path("/from/env") and cfg.baseline_python == Path("/py/file")
    assert cfg.upstream_cache is None and cfg.work is None
    assert gates.MigrationConfig.from_env({}).baseline_corpus is None
    assert gates.MigrationConfig.from_env({}, strict=True).strict is True
    toml.write_text("not = [toml")
    with pytest.raises(gates.BaselineUnavailableError):
        gates.MigrationConfig.from_env({}, config_file=toml)


# --------------------------------------------------------------------------------------------- the real baseline


@pytest.mark.full_corpus
def test_g0_passes_on_the_real_baseline():
    """Needs the local baseline: ``AGENTPROV_BASELINE_CORPUS`` (or ``migration/local.toml``). The release gate of K.20."""
    cfg = gates.MigrationConfig.from_env(config_file=REPO / "migration" / "local.toml")
    if cfg.baseline_corpus is None or not cfg.baseline_corpus.is_dir():
        pytest.skip("AGENTPROV_BASELINE_CORPUS is not set to the AgentDojo-PROV baseline checkout (full_corpus gate)")
    report = gates.verify_baseline(cfg)
    assert report.verdict == "pass", [(c.check, c.detail) for c in report.checks if c.status == "fail"]
    # every check is a pass except the two J.1.6 hashes the lock does not record yet; a skip is never a pass (D8)
    assert {c.check for c in report.checks if c.status != "pass"} <= {"environment.requirements_lock", "environment.baseline_wheel"}
    assert report.counts["passed"] >= 10 and report.counts["failed"] == 0
