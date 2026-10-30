"""Gates A and B (J.3.2, J.3.3) on the golden set (CI scope), on synthetic trees, and the order rule (J.3.0).

The golden pairs are third-party data with prompt-injection payloads by design: nothing here prints a fixture substring;
assertions are on counts, codes and digests. The full-scope run over the baseline trees is in
``tests/full_corpus/test_baseline_gates.py`` (marker ``full_corpus``).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from agentprov.migration import gates, pipeline
from agentprov.testing import golden

pytestmark = pytest.mark.skipif(not golden.golden_available(), reason="golden fixtures not found")

REPO = Path(__file__).resolve().parents[2]
J30_KEYS = [
    "report", "gate", "scope", "role", "agentprov", "baseline_lock_sha256", "specs", "environment", "inputs", "params",
    "counts", "failures", "outputs", "started_at", "ended_at", "wall_s", "verdict",
]


@pytest.fixture(scope="module")
def cfg(tmp_path_factory) -> gates.MigrationConfig:
    work = tmp_path_factory.mktemp("work")
    return gates.MigrationConfig(workers=2, work=work, reports_dir=work / "reports")


@pytest.fixture(scope="module")
def report_a(cfg) -> gates.GateReport:
    return gates.gate_a_v1_identity(cfg, scope="golden")


@pytest.fixture(scope="module")
def report_b(cfg) -> gates.GateReport:
    return gates.gate_b_compat_bytes(cfg, scope="golden")


# ------------------------------------------------------------------------------------------------ the golden set


def test_gate_a_passes_on_all_golden_pairs(report_a):
    doc = report_a.to_json()
    assert doc["verdict"] == "pass" and doc["gate"] == "A" and doc["scope"] == "golden" and doc["role"] == "release"
    assert doc["counts"] == {"expected": 19, "checked": 19, "passed": 19, "failed": 0, "skipped": 0}
    assert doc["failures"] == []
    assert doc["details"]["checks"]["release"]["A1"] == doc["details"]["checks"]["release"]["traces"]
    assert doc["details"]["checks"]["converted"]["A2"] == doc["details"]["checks"]["converted"]["traces"]
    # the producer ran twice and gave identical listings (J.3.0 determinism)
    assert {c.check: c.status for c in report_a.checks}["determinism.aer_listing"] == "pass"


def test_gate_b_passes_on_all_golden_pairs_and_prints_the_oracle_notice(report_b):
    doc = report_b.to_json()
    assert doc["verdict"] == "pass" and doc["gate"] == "B"
    assert doc["counts"]["passed"] == 19 and doc["counts"]["failed"] == 0
    for tree in doc["details"]["checks"].values():
        assert tree["B1"] == tree["B2"] == tree["traces"]
    assert any("regression oracle" in note for note in doc["notes"])
    assert [o["name"] for o in doc["outputs"]].count("compat_graph_digest_listing") == 2


def test_the_report_has_the_j30_shape(report_a):
    doc = report_a.to_json()
    assert all(key in doc for key in J30_KEYS)
    assert doc["report"] == "agentprov-migration-gate/0.1"
    assert doc["params"]["strict"] is False and doc["params"]["checks"] == ["A1", "A2"]
    assert len(doc["baseline_lock_sha256"]) == 64
    assert {i["name"] for i in doc["inputs"]} == {"release_transcripts", "converted_transcripts"}
    assert {o["name"] for o in doc["outputs"]} == {"aer_digest_listing"}
    assert doc["environment"]["python"] and doc["environment"]["packages"]["rfc8785"]


def test_the_accounting_verdicts_are_recorded_per_tree_and_reason(report_a):
    accounting = report_a.to_json()["details"]["accounting"]
    assert sum(accounting["by_tree"]["release"].values()) + sum(accounting["by_tree"]["converted"].values()) == 19
    # a converted v1 trace has no observed model-call records: its accounting is unverifiable, with the reason recorded
    assert accounting["by_tree"]["converted"] == {"unverifiable": 9}
    assert any(key.startswith("unverifiable:aer.acc.agent_calls_vs_assistant@1:") for key in accounting["by_reason"]["converted"])
    assert accounting["traces_by_status"] == {"inconsistent": 1, "unverifiable": 10}
    assert len(accounting["inconsistent_listed"]) == 1 and accounting["inconsistent_listed"][0]["observed"][0]["reported_calls"] == 6


def test_results_do_not_depend_on_the_worker_count_or_the_mode(tmp_path):
    listings = []
    for workers, in_process in ((1, False), (3, False), (1, True)):
        cfg = gates.MigrationConfig(workers=workers, in_process=in_process, work=tmp_path / f"w{workers}{in_process}")
        report = gates.gate_a_v1_identity(cfg, scope="golden")
        assert report.verdict == "pass"
        listings.append([(o["tree"], o["sha256"]) for o in report.outputs])
    assert listings[0] == listings[1] == listings[2]


def test_traces_and_failures_files_hold_digests_and_codes_only(cfg, report_a):
    folder = cfg.work / "reports" / "A-golden"
    rows = [json.loads(line) for line in (folder / "traces.jsonl").read_text().splitlines()]
    assert len(rows) == 19 and all(r["passed"] and r["a1"] and r["a2"] and r["aer_valid"] for r in rows)
    assert all(len(r["sha256"]) == 64 and len(r["aer_file_sha256"]) == 64 for r in rows)
    assert (folder / "failures.jsonl").read_text() == ""


def test_reports_carry_no_absolute_home_path(report_a, tmp_path):
    written = gates.write_report(report_a, tmp_path)
    text = written.read_text()
    assert str(Path.home()) not in text and json.loads(text)["gate"] == "A"
    assert written.name.endswith(".json") and written.parent.name == "A"


def test_a_report_can_be_written_to_an_exact_path(report_b, tmp_path):
    target = tmp_path / "out" / "B-golden.json"
    assert gates.write_report(report_b, path=target) == target
    assert json.loads(target.read_text())["verdict"] == "pass"


# ------------------------------------------------------------------------------------------------ synthetic faults


def _first_pair(tmp_path: Path) -> pipeline.PairInput:
    pairs, _trees = pipeline.golden_inputs(golden.golden_dir())
    source = pairs[0]
    transcript, graph = tmp_path / "x.transcript.json", tmp_path / "x.json"
    shutil.copy(source.transcript, transcript)
    shutil.copy(source.graph, graph)
    return pipeline.PairInput("t/x.transcript.json", "release", transcript, graph, source.origin_relpath, "x.transcript.json", "x.json")


def _run(pair: pipeline.PairInput, want: set[str], tmp_path: Path) -> pipeline.TraceRow:
    trees = {"release": pipeline.TreeSummary("release", transcripts=1, graphs=1)}
    run = pipeline.run_pipeline([pair], trees, frozenset(want), work=tmp_path / "work", workers=1, in_process=True)
    return run.rows[0]


def test_a_whitespace_difference_is_a_byte_mismatch_not_a_value_mismatch(tmp_path):
    """A trailing newline keeps the JSON value (A1 passes) and changes the bytes (A2 must fail): the two checks differ."""
    pair = _first_pair(tmp_path)
    pair.transcript.write_bytes(pair.transcript.read_bytes() + b"\n")
    row = _run(pair, {"A1", "A2"}, tmp_path)
    assert row.a1 is True and row.a2 is False
    assert row.codes == ["A2.byte_mismatch"] and not row.passed


def test_a_changed_value_fails_a_graph_comparison_with_both_b_checks(tmp_path):
    pair = _first_pair(tmp_path)
    assert pair.graph is not None
    pair.graph.write_bytes(pair.graph.read_bytes().replace(b"prov:", b"prow:", 1))
    row = _run(pair, {"B1", "B2"}, tmp_path)
    assert row.b1 is False and row.b2 is False
    assert set(row.codes) == {"B1.graph_mismatch", "B2.graph_mismatch"}


def test_a_transcript_that_is_not_v1_ends_as_a_failed_trace_not_an_exception(tmp_path):
    pair = _first_pair(tmp_path)
    pair.transcript.write_bytes(b'{"not": "a transcript"}')
    row = _run(pair, {"A1", "A2"}, tmp_path)
    assert not row.passed and row.a1 is False and row.a2 is False
    assert all("not a transcript" not in code for code in row.codes)


def test_a_missing_graph_fails_gate_b_for_that_trace(tmp_path):
    pair = _first_pair(tmp_path)
    row = _run(
        pipeline.PairInput(pair.item, pair.tree, pair.transcript, None, pair.origin_relpath, pair.tree_relpath),
        {"B1", "B2"},
        tmp_path,
    )
    assert row.codes == ["B.graph_missing"]


def test_an_unknown_check_is_a_programming_error(tmp_path):
    with pytest.raises(ValueError):
        pipeline.run_pipeline([], {}, frozenset({"A9"}), work=None, workers=1)


# ------------------------------------------------------------------------------------------------ the full-scope enumerator


@pytest.fixture
def synthetic_baseline(tmp_path):
    """A baseline-shaped directory (``corpus/corpus-prov``, ``corpus/corpus-og-agentdojo-runs-prov``) with copies of two pairs."""
    pairs, _ = pipeline.golden_inputs(golden.golden_dir())
    by_tree = {"release": next(p for p in pairs if p.tree == "release"), "converted": next(p for p in pairs if p.tree == "converted")}
    for tree, directory in (("release", "corpus-prov"), ("converted", "corpus-og-agentdojo-runs-prov")):
        folder = tmp_path / "corpus" / directory / "model" / "prov" / "attack"
        folder.mkdir(parents=True)
        shutil.copy(by_tree[tree].transcript, folder / "t.transcript.json")
        shutil.copy(by_tree[tree].graph, folder / "t.json")
    return tmp_path


def test_full_inputs_pairs_transcripts_with_graphs_in_sorted_order(synthetic_baseline):
    pairs, trees = pipeline.full_inputs(synthetic_baseline)
    assert [p.item for p in pairs] == [
        "corpus-prov/model/prov/attack/t.transcript.json",
        "corpus-og-agentdojo-runs-prov/model/prov/attack/t.transcript.json",
    ]
    assert all(p.graph is not None for p in pairs)
    assert trees["release"].unpaired_graphs == [] and trees["converted"].unpaired_transcripts == []


def test_full_inputs_reports_unpaired_files(synthetic_baseline):
    folder = synthetic_baseline / "corpus" / "corpus-prov" / "model" / "prov" / "attack"
    (folder / "t.json").unlink()
    shutil.copy(folder / "t.transcript.json", folder / "lonely.json")
    _pairs, trees = pipeline.full_inputs(synthetic_baseline)
    assert trees["release"].unpaired_transcripts == ["model/prov/attack/t.transcript.json"]
    assert trees["release"].unpaired_graphs == ["model/prov/attack/lonely.json"]


def test_the_full_scope_checks_inputs_against_the_lock_pins(synthetic_baseline, tmp_path):
    """The synthetic tree is not the frozen baseline: every trace passes, but the listing pins fail, so the gate fails."""
    cfg = gates.MigrationConfig(baseline_corpus=synthetic_baseline, workers=1, in_process=True, work=tmp_path / "w")
    report = gates.gate_a_v1_identity(cfg, scope="full")
    assert report.counts == {"expected": 2, "checked": 2, "passed": 2, "failed": 0, "skipped": 0}
    statuses = {c.check: c.status for c in report.checks}
    assert statuses["inputs.release_transcripts.lock"] == "fail" and statuses["inputs.converted_transcripts.lock"] == "fail"
    assert report.verdict == "fail"
    assert not any(c.check.startswith("determinism") for c in report.checks)  # full scope records the listing instead


def test_the_full_scope_needs_the_baseline(tmp_path):
    with pytest.raises(gates.BaselineUnavailableError):
        gates.gate_a_v1_identity(gates.MigrationConfig(), scope="full")
    with pytest.raises(gates.BaselineUnavailableError):
        gates.gate_b_compat_bytes(gates.MigrationConfig(baseline_corpus=tmp_path / "missing"), scope="full")


# ------------------------------------------------------------------------------------------------ the order rule


def _write_report(directory: Path, *, gate: str, scope: str = "full", verdict: str = "pass", commit=None, lock=None, strict=False):
    identity = gates._agentprov_identity()
    directory.mkdir(parents=True, exist_ok=True)
    document = {
        "report": gates.REPORT_FORMAT, "gate": gate, "scope": scope, "verdict": verdict,
        "agentprov": {"commit": commit or identity["commit"]},
        "baseline_lock_sha256": lock or gates.lock_sha256(gates.MigrationConfig().lock_path),
        "params": {"strict": strict},
    }
    (directory / f"{gate}.json").write_text(json.dumps(document))


def test_golden_scope_is_not_chained(tmp_path):
    gates.require_predecessors(gates.MigrationConfig(reports_dir=tmp_path), "B", "golden")


def test_full_scope_gates_refuse_to_start_without_their_predecessors(tmp_path):
    cfg = gates.MigrationConfig(reports_dir=tmp_path / "r")
    with pytest.raises(gates.GateOrderError) as excinfo:
        gates.require_predecessors(cfg, "A", "full")
    assert excinfo.value.exit_code == 4
    _write_report(tmp_path / "r" / "G0", gate="G0")
    gates.require_predecessors(cfg, "A", "full")
    with pytest.raises(gates.GateOrderError):
        gates.require_predecessors(cfg, "B", "full")
    _write_report(tmp_path / "extra", gate="A")
    gates.require_predecessors(cfg, "B", "full", extra_dirs=[tmp_path / "extra"])


def test_reports_default_to_agentprov_home_and_committed_ones_still_chain(tmp_path, monkeypatch):
    """CLI robustness item 4: nothing is written into the repository by default; the repository's migration/reports is
    still searched, so a report committed there keeps satisfying the gate order."""
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path / "home"))
    cfg = gates.MigrationConfig()
    assert cfg.reports_dir == tmp_path / "home" / "migration" / "reports"
    assert gates.default_semdiff_dir() == tmp_path / "home" / "migration" / "semdiff"
    assert gates.REPO_REPORTS_DIR not in cfg.reports_dir.parents
    monkeypatch.setattr(gates, "REPO_REPORTS_DIR", tmp_path / "repo-reports")
    with pytest.raises(gates.GateOrderError):
        gates.require_predecessors(cfg, "A", "full")
    _write_report(tmp_path / "repo-reports" / "G0", gate="G0")
    gates.require_predecessors(cfg, "A", "full")


@pytest.mark.parametrize(
    "change",
    [{"verdict": "fail"}, {"scope": "golden"}, {"commit": "0" * 40}, {"lock": "0" * 64}],
    ids=["failed", "wrong-scope", "other-commit", "other-lock"],
)
def test_a_predecessor_report_must_pass_for_this_commit_lock_and_scope(tmp_path, change):
    _write_report(tmp_path / "r", gate="G0", **change)
    with pytest.raises(gates.GateOrderError):
        gates.require_predecessors(gates.MigrationConfig(reports_dir=tmp_path / "r"), "A", "full")


def test_release_mode_needs_release_mode_predecessors(tmp_path):
    _write_report(tmp_path / "r", gate="G0", strict=False)
    with pytest.raises(gates.GateOrderError):
        gates.require_predecessors(gates.MigrationConfig(reports_dir=tmp_path / "r", strict=True), "A", "full")
    _write_report(tmp_path / "r", gate="G0", strict=True)
    gates.require_predecessors(gates.MigrationConfig(reports_dir=tmp_path / "r", strict=True), "A", "full")


def test_config_reads_the_run_workers_and_golden_dir(tmp_path):
    toml = tmp_path / "local.toml"
    toml.write_text('[env]\nAGENTPROV_BASELINE_CORPUS = "/x"\n[run]\nworkers = 3\n')
    cfg = gates.MigrationConfig.from_env({"AGENTPROV_GOLDEN_DIR": "/g"}, config_file=toml)
    assert cfg.workers == 3 and cfg.golden_dir == Path("/g")
    assert gates.MigrationConfig.from_env({}, config_file=toml, workers=5).workers == 5
