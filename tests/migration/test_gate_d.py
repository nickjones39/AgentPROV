"""Gate D (J.3.5; D-49): ``agentprov migrate gate-d`` on the golden AERs and on stored AERs of a corpus, read-only.

The corpora here are built from the golden mappings (``gate_d_support``); the real corpora are exercised by the
``full_corpus`` test ``test_validation_all``.
"""

from __future__ import annotations

import copy
import dataclasses
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agentprov.cli.main import main
from agentprov.migration import gate_d, gates
from agentprov.migration.gate_d_worker import WorkItem, run_item
from agentprov.testing import fs_guard, golden

from gate_d_support import build_corpus

pytestmark = pytest.mark.skipif(not golden.golden_available(), reason="golden fixtures not found")


@pytest.fixture(autouse=True)
def _no_local_environment(monkeypatch):
    for name in ("AGENTPROV_BASELINE_CORPUS", "AGENTPROV_MIGRATION_WORK", "AGENTPROV_BASELINE_PYTHON", "AGENTPROV_BASELINE_WHEEL"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def cli(capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("AGENTPROV_PROGRESS", raising=False)

    def run(*argv: str):
        capsys.readouterr()
        code = main(list(argv))
        out, err = capsys.readouterr()
        return code, out, err

    return run


@pytest.fixture(scope="module")
def golden_work() -> dict[str, WorkItem]:
    return {i.label: i for i in gate_d.golden_items(None)}


@pytest.fixture
def release_corpus(tmp_path, golden_work) -> Path:
    items = [golden_work[k] for k in ("R01", "R02", "R03")]
    build_corpus(tmp_path / "rel.partial", items, "release")
    return tmp_path / "rel"


@pytest.fixture
def native_corpus(tmp_path, golden_work) -> Path:
    items = [golden_work[k] for k in ("N-C01", "N-C02")]
    build_corpus(tmp_path / "nat.partial", items, "native")
    return tmp_path / "nat"


@pytest.fixture
def empty_config(tmp_path) -> str:
    path = tmp_path / "local.toml"
    path.write_text("[env]\n")
    return str(path)


# ------------------------------------------------------------------------------------------------ golden scope


def test_golden_scope_reproduces_the_gate_d_test_through_the_cli(cli, tmp_path, empty_config):
    target = tmp_path / "out" / "D-golden.json"
    code, out, err = cli("migrate", "gate-d", "--in-process", "--config", empty_config, "--report", str(target), "-q")
    assert code == 0, err
    report = json.loads(target.read_text())
    assert report["gate"] == "D" and report["scope"] == "golden" and report["role"] == "release" and report["verdict"] == "pass"
    assert report["counts"] == {"expected": 28, "checked": 28, "passed": 28, "failed": 0, "skipped": 0}
    statuses = {c["check"]: c["status"] for c in report["checks"]}
    assert statuses["pins.golden_digests"] == statuses["determinism.twice"] == statuses["performance.r08_completes"] == "pass"
    assert set(report["details"]["trees"]) == {"release", "converted", "native"}
    assert report["details"]["trees"]["release"]["executions"] == 10
    assert {o["name"] for o in report["outputs"]} >= {"aer_digest_listing", "sem_digest_listing", "prov_digest_listing", "executions_jsonl"}
    assert (tmp_path / "out" / "D-golden.md").read_text().startswith("# Gate D (golden")
    rows = [json.loads(line) for line in (tmp_path / "out" / "D-golden.executions.jsonl").read_text().splitlines()]
    assert len(rows) == 28 and all(r["ok"] and r["statements"] > 0 and r["wall_s"] > 0 for r in rows)
    pinned = json.loads((Path(__file__).resolve().parents[1] / "golden" / "gate_d_digests.json").read_text())
    assert {r["item"]: "sha256:" + r["prov"] for r in rows} == {k: v["prov"] for k, v in pinned.items()}


def test_golden_scope_takes_no_corpus_arguments(cli, empty_config, release_corpus):
    code, _out, err = cli("migrate", "gate-d", "--config", empty_config, "--corpus", str(release_corpus))
    assert code == 2 and "golden scope" in err


# ------------------------------------------------------------------------------------------------ stored AERs, read-only


def test_a_corpus_slice_passes_and_the_corpus_is_not_written(cli, tmp_path, release_corpus, native_corpus, empty_config):
    target = tmp_path / "reports" / "D-sample.json"
    with fs_guard.unchanged(tmp_path / "rel.partial"), fs_guard.unchanged(tmp_path / "nat.partial"):
        code, _out, err = cli(
            "migrate", "gate-d", "--scope", "full", "--limit", "2", "--in-process", "--config", empty_config,
            "--corpus", str(release_corpus), "--corpus", str(native_corpus), "--report", str(target), "-q",
        )  # fmt: skip
    assert code == 0, err
    report = json.loads(target.read_text())
    assert report["scope"] == "sample" and report["role"] == "diagnostic" and report["verdict"] == "pass"
    assert report["counts"]["expected"] == 4 and report["counts"]["failed"] == 0
    release = report["details"]["trees"]["release"]
    assert release["executions"] == 2 and release["rederived_vs_stored_digests"] == {"prov_equal": 2, "sem_equal": 2}
    assert release["check_statuses"]["d8.aer"] == {"pass": 2}
    assert not any(s == "skipped" for counts in release["check_statuses"].values() for s in counts)
    assert [i["name"] for i in report["inputs"]] == ["rel", "nat"]
    assert not list((tmp_path / "rel.partial").rglob("*.json.tmp"))


def test_the_report_is_never_written_into_a_corpus(cli, release_corpus, empty_config):
    code, _out, err = cli(
        "migrate", "gate-d", "--scope", "full", "--limit", "1", "--in-process", "--config", empty_config,
        "--corpus", str(release_corpus), "--report", str(release_corpus.parent / "rel.partial" / "D.json"),
    )  # fmt: skip
    assert code == 4 and "inside a corpus" in err and "migration.gate_d.inside_corpus" in err
    assert not (release_corpus.parent / "rel.partial" / "D.json").exists()


@pytest.mark.parametrize("inside", ["rel.partial", "rel.partial/reports"])
def test_a_default_report_target_inside_a_corpus_is_refused_before_any_work(cli, release_corpus, empty_config, monkeypatch, inside):
    """CB-26: the default target ``<reports-dir>/D/<id>.json`` is checked like ``--report``, before any execution runs."""
    ran: list[object] = []
    real_execute = gate_d.execute
    monkeypatch.setattr(gate_d, "execute", lambda items, **kw: ran.append(items) or real_execute(items, **kw))
    corpus_dir = release_corpus.parent / "rel.partial"
    with fs_guard.unchanged(corpus_dir):
        code, _out, err = cli(
            "migrate", "gate-d", "--scope", "full", "--limit", "1", "--in-process", "--config", empty_config,
            "--corpus", str(release_corpus), "--reports-dir", str(release_corpus.parent / inside),
        )  # fmt: skip
    assert code == 4 and "migration.gate_d.inside_corpus" in err
    assert ran == []


def test_a_sample_run_never_replaces_the_full_scope_report_at_the_default_path(cli, tmp_path, release_corpus, empty_config, monkeypatch):
    """CB-27: a ``--limit`` run on the day and commit of a full-scope run reaches the same default stem; it is refused
    before any work runs, and the full-scope report, its ``.md`` and its executions file stay."""
    ran: list[object] = []
    real_execute = gate_d.execute
    monkeypatch.setattr(gate_d, "execute", lambda items, **kw: ran.append(items) or real_execute(items, **kw))
    commit = gates._agentprov_identity()["commit"]
    stem = f"{datetime.now(UTC):%Y-%m-%d}-{commit[:7] if isinstance(commit, str) else 'nocommit'}"
    full = tmp_path / "reports" / "D" / f"{stem}.json"
    full.parent.mkdir(parents=True)
    full.write_text(json.dumps({"report": gates.REPORT_FORMAT, "gate": "D", "scope": "full", "verdict": "pass", "params": {"strict": False}}))
    code, _out, err = cli(
        "migrate", "gate-d", "--scope", "full", "--limit", "1", "--in-process", "--config", empty_config,
        "--corpus", str(release_corpus), "--reports-dir", str(tmp_path / "reports"),
    )  # fmt: skip
    assert code == 4 and "migration.report.exists" in err and "--report" in err
    assert ran == [] and json.loads(full.read_text())["scope"] == "full"
    assert sorted(p.name for p in full.parent.iterdir()) == [full.name]


def test_a_full_scope_gate_d_refuses_without_its_predecessors(cli, tmp_path, release_corpus, empty_config):
    code, _out, err = cli(
        "migrate", "gate-d", "--scope", "full", "--config", empty_config, "--corpus", str(release_corpus),
        "--reports-dir", str(tmp_path / "none"),
    )  # fmt: skip
    assert code == 4 and "gate G0" in err


def test_full_scope_needs_a_corpus_and_a_missing_corpus_is_a_usage_error(cli, tmp_path, empty_config):
    assert cli("migrate", "gate-d", "--scope", "full", "--config", empty_config)[0] == 2
    code, _out, _err = cli("migrate", "gate-d", "--scope", "full", "--limit", "1", "--config", empty_config, "--corpus", str(tmp_path / "absent"))
    assert code == 2


def test_other_gates_refuse_the_gate_d_arguments(cli, empty_config):
    code, _out, err = cli("migrate", "gate-a", "--config", empty_config, "--limit", "3")
    assert code == 2 or "unrecognized" in err


def test_two_corpora_of_one_tree_are_refused(cli, tmp_path, golden_work, release_corpus, empty_config):
    build_corpus(tmp_path / "rel2.partial", [golden_work["R04"]], "release")
    code, _out, err = cli(
        "migrate", "gate-d", "--scope", "full", "--limit", "1", "--in-process", "--config", empty_config,
        "--corpus", str(release_corpus), "--corpus", str(tmp_path / "rel2"),
    )  # fmt: skip
    assert code == 2 and "two corpora classify as the release tree" in err


def test_a_tampered_stored_aer_fails_the_gate_without_content(cli, tmp_path, release_corpus, empty_config):
    aer = sorted((tmp_path / "rel.partial" / "aer").rglob("*.aer.jsonl"))[0]
    data = aer.read_bytes()
    aer.write_bytes(data.replace(b'"k":"message"', b'"k":"messagE"', 1))
    target = tmp_path / "D.json"
    code, out, _err = cli(
        "migrate", "gate-d", "--scope", "full", "--limit", "3", "--in-process", "--config", empty_config,
        "--corpus", str(release_corpus), "--report", str(target), "--json", "-q",
    )  # fmt: skip
    assert code == 1
    report = json.loads(target.read_text())
    assert report["verdict"] == "fail" and report["counts"]["failed"] == 1
    assert report["failures"][0]["check"] == "gate_d.error"
    assert "messagE" not in target.read_text()


def test_full_scope_reports_incomplete_and_absent_trees_and_accepts_gaps_explicitly(tmp_path, release_corpus, empty_config):
    cfg = gates.MigrationConfig.from_env(config_file=Path(empty_config), in_process=True)
    run = gate_d.gate_d_validate(cfg, scope="full", corpora=[release_corpus])
    status = {c.check: c.status for c in run.report.checks}
    assert run.report.scope == "full" and run.report.verdict == "fail"
    assert status["inputs.release.complete"] == "fail"
    assert status["inputs.converted.present"] == status["inputs.native.present"] == "fail"
    assert "crosscount.release.tool_execution_activities" not in status  # 3 of 17,664: the table is not evaluated
    run = gate_d.gate_d_validate(cfg, scope="full", corpora=[release_corpus], accept_gaps=["converted", "native"])
    status = {c.check: c.status for c in run.report.checks}
    assert status["inputs.converted.present"] == status["inputs.native.present"] == "pass"
    assert run.report.details["gaps"] == ["converted", "native"] and any("accepted gap" in n for n in run.report.notes)
    assert run.report.verdict == "fail"  # the release tree is still incomplete (3 of 17,664)


def test_full_scope_fails_when_every_j35_tree_is_an_accepted_gap(tmp_path, golden_work, empty_config):
    build_corpus(tmp_path / "oth.partial", [golden_work[k] for k in ("N-C01", "N-C02")], "other")
    cfg = gates.MigrationConfig.from_env(config_file=Path(empty_config), in_process=True)
    run = gate_d.gate_d_validate(cfg, scope="full", corpora=[tmp_path / "oth"], accept_gaps=list(gate_d.TREES))
    status = {c.check: c.status for c in run.report.checks}
    assert set(run.report.details["trees"]) == {"other"} and run.report.details["gaps"] == ["release", "converted", "native"]
    assert status["inputs.release.present"] == status["inputs.converted.present"] == status["inputs.native.present"] == "pass"
    assert status["inputs.migration_trees.present"] == "fail"  # no J.3.5 tree was validated: the report cannot unlock gate E
    assert run.report.scope == "full" and run.report.verdict == "fail"


def test_the_result_is_identical_in_process_and_across_worker_counts(tmp_path, release_corpus, native_corpus, empty_config):
    def listing(workers: int, in_process: bool):
        cfg = gates.MigrationConfig.from_env(config_file=Path(empty_config), workers=workers, in_process=in_process)
        run = gate_d.gate_d_validate(cfg, scope="full", limit=3, corpora=[release_corpus, native_corpus])
        rows = [{k: v for k, v in r.items() if k != "wall_s"} for r in run.rows]
        return rows, [o for o in run.report.outputs if o["name"].endswith("_listing")]

    assert listing(1, True) == listing(2, False)


def test_workers_0_is_the_host_default(tmp_path, release_corpus, empty_config, monkeypatch):
    """``--workers 0`` takes the host default (:func:`resolve_worker_count`), as its help says; it was min(8, CPUs)."""
    seen: list[int] = []

    class Stop(Exception):
        pass

    def execute(items, *, workers, in_process, progress):
        seen.append(workers)
        raise Stop

    monkeypatch.setattr(gate_d, "resolve_worker_count", lambda requested: 37 if requested == 0 else requested)
    monkeypatch.setattr(gate_d, "execute", execute)
    for requested, expected in ((0, 37), (3, 3)):
        cfg = gates.MigrationConfig.from_env(config_file=Path(empty_config), workers=requested)
        with pytest.raises(Stop):
            gate_d.gate_d_validate(cfg, scope="full", limit=1, corpora=[release_corpus])
        assert seen.pop() == expected


# ------------------------------------------------------------------------------------------------ the J.3.5 table and checks


def test_the_cross_count_table_is_the_j35_table():
    table = {i.name: (i.release, i.converted) for i in gate_d.CROSS_COUNTS}
    assert table["tool_execution_activities"] == (64_781, 68_620)
    assert table["tool_call_request_entities"] == (64_829, 68_773)
    assert table["requests_without_execution"] == (48, 153)
    assert table["model_invocations_generating_assistant_message"] == (64_897, 73_551)
    assert table["user_message_entities"] == (17_664, 21_658) and table["system_message_entities"] == (17_664, 18_027)
    assert table["executions_without_tool_execution"] == (1_417, 762)
    assert gate_d.EXPECTED_EXECUTIONS == {"release": 17_664, "converted": 18_027, "native": 18_241}


def test_tree_checks_compare_the_aggregates_with_the_table():
    def details(delta: int):
        return {"metrics": {i.metric: i.release + (delta if i.metric == "te_prov" else 0) for i in gate_d.CROSS_COUNTS}, "check_statuses": {}}

    good = {c.check: c.status for c in gate_d._tree_checks("release", [], details(0), complete=True)}
    assert all(s == "pass" for s in good.values())
    bad = {c.check: c.status for c in gate_d._tree_checks("release", [], details(1), complete=True)}
    assert [k for k, s in bad.items() if s == "fail"] == ["crosscount.release.tool_execution_activities"]
    partial = gate_d._tree_checks("release", [], details(0), complete=False)
    assert not any(c.check.startswith("crosscount") for c in partial)


def _derived(item: WorkItem):
    from agentprov.aer.reader import load_aer_bytes
    from agentprov.adapters.runner.provjob import PROFILES
    from agentprov.prov.engine import derive
    from agentprov.sem.engine import annotate

    doc = load_aer_bytes(item.aer)
    profile = PROFILES["agentdojo.suites@1"]
    result = derive(doc, [annotate(doc, profile)], sem_profiles={(profile.id, profile.version): profile}, check_aer=False)
    return doc, result


def _codes(doc, result, **kw):
    from agentprov.migration import gate_d_worker

    codes: list[str] = []
    gate_d_worker._dedicated(result, doc, codes, v1=kw.get("v1", True), migration=True)
    return set(codes)


def test_the_dedicated_checks_pass_on_a_derivation_and_catch_each_defect(golden_work):
    doc, result = _derived(golden_work["R01"])
    assert _codes(doc, result) == set()
    core = next(i for i in result.document["bundle"] if ".core." in i)

    def seeded():
        """The derivation with one ``used`` and one ``wasInformedBy`` copied into the core bundle. Since the D-24
        ``_unverified`` twins (regeneration-batch item 3) the golden core holds neither: the v1 relations are inferred."""
        document = copy.deepcopy(result.document)
        bundles = document["bundle"]
        for section in ("used", "wasInformedBy"):
            if bundles[core].get(section):
                continue
            donor = next(b for name, b in bundles.items() if name != core and b.get(section))
            key = next(iter(donor[section]))
            bundles[core].setdefault(section, {})[key] = copy.deepcopy(donor[section][key])
        return document

    control = _codes(doc, dataclasses.replace(result, document=seeded()))

    def mutated(edit):
        document = seeded()
        edit(document["bundle"], core)
        return _codes(doc, dataclasses.replace(result, document=document))

    def drop_rule(bundles, core):
        key = next(iter(bundles[core]["used"]))
        del bundles[core]["used"][key]["apv:rule"]

    def relation_time(bundles, core):
        bundles[core]["wasGeneratedBy"][next(iter(bundles[core]["wasGeneratedBy"]))]["prov:time"] = "2024-01-01T00:00:00Z"

    def sentinel(bundles, core):
        act = next(iter(bundles[core]["activity"]))
        bundles[core]["activity"][act]["prov:startTime"] = "0"

    def generic(bundles, core):
        bundles[core]["used"][next(iter(bundles[core]["used"]))]["apv:rule"] = "aprov.g_use@1"

    def context_in_core(bundles, core):
        bundles[core]["used"][next(iter(bundles[core]["used"]))]["apv:rule"] = "aprov.use_context@1"

    def uses_activity(bundles, core):
        used = bundles[core]["used"][next(iter(bundles[core]["used"]))]
        used["prov:entity"] = next(iter(bundles[core]["activity"]))

    def informed_without_premise(bundles, core):
        inf = bundles[core]["wasInformedBy"]
        del inf[next(iter(inf))]["apv:premise"]

    cases = {
        "ne.relation_without_rule": drop_rule, "ne.time_on_relation": relation_time, "ne.time_sentinel": sentinel,
        "ne.generic_statement": generic, "ne.context_membership_in_core": context_in_core,
        "ne.activity_used": uses_activity, "ne.informed_by": informed_without_premise,
    }
    for code, edit in cases.items():
        assert code not in control, code  # the seed alone does not raise it
        assert code in mutated(edit), code


def test_a_cross_count_defect_is_a_per_execution_failure(golden_work):
    doc, result = _derived(golden_work["R02"])
    metrics = {"te_prov": 0}
    from agentprov.migration import gate_d_worker

    codes: list[str] = []
    gate_d_worker._cross_counts(doc, {**gate_d_worker._dedicated(result, doc, [], v1=True, migration=True), **metrics}, codes)
    assert "xc.tool_executions" in codes


def test_an_item_that_raises_becomes_a_code_not_an_exception(tmp_path):
    bad = WorkItem("x", "release", aer=b"not an aer", raw=b"", adapter="adprov.transcript_v1@0.1.0")
    result = run_item(bad)
    assert result["codes"] and result["codes"][0].startswith("gate_d.error:")


def test_environment_loads_are_expected_from_the_execution_itself():
    """Regeneration-batch item 5 (D-370): the TraceLogger mapper adds one ``agentdojo:load_environment`` activity to an
    execution with injection payload fixtures. Gate D derives that expectation from each AER, never from a set total."""
    from types import SimpleNamespace

    from agentprov.migration import gate_d_worker

    def doc(adapter: str, kinds: list[str]):
        records = [{"k": "fixture", "kind": k} for k in kinds]
        return SimpleNamespace(header={"adapter": {"id": adapter}},
                               of_kind=lambda kind: [r for r in records if r["k"] == kind])

    assert gate_d_worker._environment_loads_expected(doc("agentdojo.tracelogger", ["injection_payload"])) == 1
    assert gate_d_worker._environment_loads_expected(doc("agentdojo.tracelogger", ["injection_payload"] * 3)) == 1
    assert gate_d_worker._environment_loads_expected(doc("agentdojo.tracelogger", [])) == 0
    assert gate_d_worker._environment_loads_expected(doc("adprov.transcript_v1", ["injection_payload"])) == 0


def test_tree_checks_compare_environment_loads_with_their_derived_count():
    def details(observed: int, derived: int):
        metrics = {i.metric: i.converted for i in gate_d.CROSS_COUNTS}
        metrics.update(env_load_activities=observed, env_load_expected=derived)
        return {"metrics": metrics, "check_statuses": {}}

    good = {c.check: c.status for c in gate_d._tree_checks("native", [], details(16_003, 16_003), complete=True)}
    assert good["crosscount.native.environment_load_activities"] == "pass"
    assert good["crosscount.native.activity_records"] == "pass"  # J.3.5's 0 holds: the exempt load is counted apart
    bad = {c.check: c.status for c in gate_d._tree_checks("native", [], details(16_003, 16_004), complete=True)}
    assert [k for k, s in bad.items() if s == "fail"] == ["crosscount.native.environment_load_activities"]


def test_an_unexpected_environment_load_is_a_per_execution_failure(golden_work):
    from agentprov.migration import gate_d_worker

    doc, result = _derived(golden_work["R02"])
    base = gate_d_worker._dedicated(result, doc, [], v1=True, migration=True)
    codes: list[str] = []
    gate_d_worker._cross_counts(doc, dict(base), codes)
    assert "xc.environment_load" not in codes  # a v1 transcript: no load expected, none present
    extra = dataclasses.replace(doc, records=[*doc.records, {"k": "activity", "id": "load0", "type": "agentdojo:load_environment"}])
    codes = []
    metrics = dict(base)
    gate_d_worker._cross_counts(extra, metrics, codes)
    assert "xc.environment_load" in codes and metrics["activity_records"] == 0 and metrics["env_load_activities"] == 1
