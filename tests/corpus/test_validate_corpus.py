"""``agentprov validate --corpus``: tiers aer, sem, prov, linkage over stored outputs, read-only (N.2.5; D-40; U4).

The sealed test corpus was validated strict at import: re-running every default tier in release mode reproduces each
stored ``validation/results.jsonl`` row byte for byte (JCS digest equal to the index's) and the D-40 summary equals the
sealed manifest's ``validation`` member, ``linkage_resolved_pct`` included (claim ``c1-linkage``).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import verify_support as vs

from agentprov.testing import fs_guard


def test_strict_validation_reproduces_the_stored_results_and_the_manifest_summary(cli, sealed, tmp_path, check_summary):
    report = tmp_path / "report.json"
    with fs_guard.unchanged(sealed):
        run = cli("validate", "--corpus", str(sealed), "--strict", "--report", str(report), "--json")
    assert run.code == 0, run.err
    summary = run.json()
    check_summary(summary)
    counters = summary["counters"]
    assert counters["executions"] == counters["passed"] == counters["results_reproduced"] == 3
    assert counters["results_differ"] == 0 and counters["linkage_resolved"] == counters["linkage_applicable"] == 3
    document = json.loads(report.read_text("utf-8"))
    assert document["format"] == "agentprov-validation-report/0.1" and document["mode"] == "release"
    assert document["validation"] == vs.manifest(sealed)["validation"]  # the D-40 shape, equal to the sealed one
    assert document["validation"]["linkage_resolved_pct"] == {"$dec": "100.00"}
    assert {t["tier"] for t in document["validation"]["tiers"]} == {2, 3, 4}
    assert document["corpus"]["root_digest"] == vs.root_digest(sealed) and len(document["results"]) == 3
    assert "linkage_resolved_pct 100.00% (claim c1-linkage)" in summary["notices"]


def test_the_report_goes_to_stdout_with_a_dash(cli, sealed):
    run = cli("validate", "--corpus", str(sealed), "--strict", "--report", "-")
    assert run.code == 0
    assert json.loads(run.out)["format"] == "agentprov-validation-report/0.1"


def test_a_report_inside_the_corpus_is_refused(cli, sealed):
    with fs_guard.unchanged(sealed):
        assert cli("validate", "--corpus", str(sealed), "--report", str(sealed / "report.json")).code == 4
        assert cli("validate", "--corpus", str(sealed), "--report", str(sealed / "validation" / "x.json")).code == 4


def test_release_asks_for_shacl_which_is_not_built_so_it_fails_as_skipped(cli, sealed):
    run = cli("validate", "--corpus", str(sealed), "--release", "--json")
    assert run.code == 1
    document = run.json()
    assert document["issues_by_code"] == {"validate.check.skipped": 1}
    assert any("tier regression: not applicable" in n for n in document["notices"])
    assert document["counters"]["results_reproduced"] == 3


def test_the_summary_names_a_skipped_tier_and_why(cli, sealed):
    """F-3 (user-guide findings): ``--release`` exited 1 for the skipped shacl tier while the printed summary said
    "0 failed" and named no skipped tier. The summary line now names it, with the reason, as skipped and not passed."""
    run = cli("validate", "--corpus", str(sealed), "--release")
    assert run.code == 1
    line = next(x for x in (run.out + run.err).splitlines() if x.startswith("validated "))
    assert "0 failed" in line
    assert "skipped, not passed: tier shacl (not implemented in this build)" in line
    assert "a skipped tier fails --strict and --release (exit 1)" in line
    nothing = cli("validate", "--corpus", str(sealed), "--tiers", "shacl")
    assert nothing.code == 0  # dev mode: a skipped tier is reported, not failed
    assert "skipped, not passed: tier shacl (not implemented in this build)" in nothing.out + nothing.err
    assert "--release" not in next(x for x in (nothing.out + nothing.err).splitlines() if "skipped, not passed" in x)


def test_a_tier_subset_and_dev_mode_are_not_compared_with_the_stored_rows(cli, sealed):
    summary = sealed.parent / "linkage-summary.json"
    run = cli("validate", "--corpus", str(sealed), "--tiers", "linkage", "--report", "-", "--summary-json", str(summary))
    report = json.loads(run.out)  # stdout holds the report alone (CC-23)
    assert run.code == 0 and report["tiers"] == ["linkage"]
    assert all(set(r["checks"]) and all(k.startswith("pv.linkage.") for k in r["checks"]) for r in report["results"])
    assert json.loads(summary.read_text())["counters"]["results_not_compared"] == 3
    run = cli("validate", "--corpus", str(sealed), "--json")
    assert run.code == 0 and run.json()["counters"]["results_not_compared"] == 3  # dev mode; the corpus ran release


def test_a_seeded_sample(cli, sealed):
    run = cli("validate", "--corpus", str(sealed), "--strict", "--sample", "2", "--seed", "s", "--json")
    assert run.code == 0 and run.json()["counters"]["executions"] == 2
    assert cli("validate", "--corpus", str(sealed), "--release", "--sample", "2", "--seed", "s").code == 2
    assert cli("validate", "--corpus", str(sealed), "--sample", "2").code == 2


def test_a_tampered_prov_file_fails_validation(cli, sealed):
    prov = vs.first_file(sealed, "prov")
    prov.write_bytes(prov.read_bytes() + b" ")
    run = cli("validate", "--corpus", str(sealed), "--strict", "--json")
    assert run.code == 1 and run.json()["issues_by_code"] == {"validate.failed": 1}


def test_a_working_corpus_is_validated_read_only(cli, tmp_path):
    import derive_support as ds

    working = ds.partial(ds.agentdojo_corpus(tmp_path))
    with fs_guard.unchanged(working):
        run = cli("validate", "--corpus", str(working), "--json")
    assert run.code == 0, run.err
    counters = run.json()["counters"]
    assert counters["executions"] == 3 and counters["results_reproduced"] == 3  # imported in dev mode


def test_usage(cli, sealed, tmp_path):
    aer = vs.first_file(sealed, "aer")
    assert cli("validate", "--corpus", str(sealed), "--aer", str(aer)).code == 2
    assert cli("validate", "--corpus", str(sealed), "--tiers", "aer,nope").code == 2
    assert cli("validate", "--corpus", str(sealed), "--prov-spec", "adprov-v2.3-compat").code == 5
    assert cli("validate", "--corpus", str(sealed), "--store", str(tmp_path)).code == 2


@pytest.mark.parametrize("strict", [True, False])
def test_the_row_helpers_equal_the_t1_job_s(sealed, strict):
    """``corpus.validation`` re-implements ``provjob.tier3_checks`` / ``tier4_row`` (L6); pinned equal here."""
    from agentprov.adapters.runner import provjob
    from agentprov.adapters.semantics_profiles import load_semantics_profile
    from agentprov.corpus import validation
    from agentprov.corpus.reader import CorpusReader
    from agentprov.sem.validate import validate_sem_document
    from agentprov.validate import validate_prov

    reader = CorpusReader.open(sealed)
    row = reader.index()[0]
    aer = reader.read_aer(row)
    sems = reader.read_sem_all(row)
    ref, doc = next(iter(sems.items()))
    report = validate_sem_document(doc, aer, mode="release" if strict else "dev",
                                   profile=load_semantics_profile(*ref.split("@")[:1], int(ref.split("@")[1])))
    assert validation.tier3_checks(report, ref) == provjob.tier3_checks(report, ref)
    tier4 = validate_prov(reader.prov_bytes(row, "agentprov-prov/0.1"), aer, sems=list(sems.values()))
    assert validation.tier4_row(tier4, strict=strict) == provjob.tier4_row(tier4, strict=strict)


def test_the_validation_api_runs_on_a_path_free_reader(sealed):
    from agentprov.corpus.reader import CorpusReader
    from agentprov.corpus.validation import validate_corpus

    result = validate_corpus(CorpusReader.open(sealed), tiers=("aer",), mode="release")
    assert result.ok and set(result.rows[0]["checks"]) == {"aer.validator"}
    with pytest.raises(ValueError):
        validate_corpus(CorpusReader.open(sealed), tiers=("shacl",))
    assert isinstance(Path(sealed), Path)


def test_report_to_stdout_with_json_is_a_usage_error_so_stdout_holds_one_document(cli, sealed):
    """CC-23 (core review C, RC-2): ``--report -`` and ``--json`` both wrote a JSON document to stdout."""
    run = cli("validate", "--corpus", str(sealed), "--report", "-", "--json")
    assert run.code == 2 and "--summary-json" in run.err
    assert run.json()["exit_code"] == 2 and run.out.count("\n") == 1  # one document: the refusal's summary


def test_an_integer_option_beyond_the_json_domain_is_a_usage_error(cli, sealed):
    """CC-15's cli/checks.py line: --jobs and --sample take the bounded integer type."""
    for flag in ("--jobs", "--sample"):
        run = cli("validate", "--corpus", str(sealed), flag, str(2**53))
        assert run.code == 2 and "at most 9007199254740991" in run.err, (flag, run.err)
