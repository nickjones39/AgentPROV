"""``agentprov validate --corpus``: tiers aer, sem, prov, linkage over stored outputs, read-only (N.2.5; D-40; U4).

The sealed test corpus was validated strict at import: re-running every default tier in release mode reproduces each
stored ``validation/results.jsonl`` row byte for byte (JCS digest equal to the index's) and the D-40 summary equals the
sealed manifest's ``validation`` member, ``linkage_resolved_pct`` included (claim ``c1-linkage``).
"""

from __future__ import annotations

import json
import os
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


def test_release_adds_every_applicable_tier_to_a_tiers_list(cli, sealed):
    """AU-CLIA-14: ``--release --tiers aer`` ran one tier and passed (exit 0), while ``--release`` alone fails for the
    skipped shacl tier. N.2.5(1): ``--release`` adds every applicable tier, so both runs are the same."""
    alone = cli("validate", "--corpus", str(sealed), "--release", "--json").json()
    run = cli("validate", "--corpus", str(sealed), "--release", "--tiers", "aer", "--json")
    assert run.code == 1
    document = run.json()
    assert document["counters"]["tiers_run"] == alone["counters"]["tiers_run"] == 4
    assert document["counters"]["checks_skipped"] == 1 and document["issues_by_code"] == {"validate.check.skipped": 1}
    assert any("--release runs every applicable tier: added sem, prov, linkage, shacl, regression to --tiers" in n
               for n in document["notices"])


def test_an_unreadable_settings_file_does_not_stop_validation(cli, sealed):
    """AU-CLIA-1: the tier-4 cache cap is advisory (D-894); a settings.json that is not strict JSON left every corpus
    command at exit 2 (usage). It now validates with the cache's default cap and says so in a notice."""
    home = os.environ["AGENTPROV_HOME"]
    with open(os.path.join(home, "settings.json"), "w", encoding="utf-8") as fh:
        fh.write('{"format": "agentprov-settings/0.1", "values": {}, }\n')
    run = cli("validate", "--corpus", str(sealed), "--json")
    assert run.code == 0
    assert any("tier-4 round-trip cache cap is left at its default" in n for n in run.json()["notices"])


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


def _withhold_first_artefact(sealed: Path, *, listed: bool = True) -> str:
    """Object-level withholding as sealing does it (H.4.5 item 2; D-231): the bytes of a raw object that a released
    execution cites leave ``raw/objects/`` and ``WITHHELD.json`` lists the object; the execution stays released.
    Returns the execution id. With ``listed=False`` the object is only missing (no ledger entry)."""
    from agentprov.corpus.reader import CorpusReader
    from agentprov.corpus.withheld import WithheldDocument, WithheldObject, encode_withheld, sorted_origins

    reader = CorpusReader.open(sealed)
    row = reader.index()[0]
    digest = str(reader.read_aer(row).header["artifacts"][0]["sha256"]).removeprefix("sha256:")
    origins = sorted_origins(o.origin.to_json() for o in reader.origins() if o.sha256 == digest)
    (stored,) = (sealed / "raw" / "objects" / digest[:2]).glob(digest + "*")
    stored.rename(sealed.parent / stored.name)  # where the private sidecar would keep it
    if listed:
        entry = WithheldObject(sha256=digest, origins=origins, reason="personal_data", basis="container",
                               public_note="an archive that holds a withheld member object (AD-12)")
        (sealed / "WITHHELD.json").write_bytes(encode_withheld(WithheldDocument(entries=(entry,))))
    return row.ex


def test_an_object_the_corpus_version_withholds_is_skipped_not_missing(cli, sealed):
    """Object-level withholding (H.4.5 item 2): a released execution may cite a raw object whose bytes the sealed tree
    withholds. ``verify --level chain`` counts it ``raw_withheld``; ``validate --corpus`` reported every such execution
    as failed with ``aer.blob.missing`` (all 1,055 of ast-survey-agentharm-rg2, all 1,747 of fragfuse-agentharm-w2, 6 in
    500 of dtap-bench-w2c). The checks that need the bytes cannot run: they are skipped, not passed and not failed."""
    ex = _withhold_first_artefact(sealed)
    report = sealed.parent / "report.json"
    with fs_guard.unchanged(sealed):
        run = cli("validate", "--corpus", str(sealed), "--report", str(report), "--json")
    assert run.code == 0, run.json()["failures"]
    summary = run.json()
    assert summary["counters"]["passed"] == 3 and summary["counters"]["aer_withheld"] == 1
    assert any("WITHHELD.json" in n and "skipped, not passed" in n for n in summary["notices"])
    row = next(r for r in json.loads(report.read_text("utf-8"))["results"] if r["ex"] == ex)
    assert row["aer"]["errors"] == [] and row["aer"]["verdict"] == "pass"
    assert any("WITHHELD.json" in s for s in row["aer"]["skipped"])

    strict = cli("validate", "--corpus", str(sealed), "--strict", "--json")  # D8: a skipped check fails --strict
    assert strict.code == 1
    document = strict.json()
    assert document["issues_by_code"] == {"validate.failed": 1}  # never validate.results.differ: the stored row
    assert document["failures"][0]["subject"] == {"ex": ex}  # was made before the bytes were withheld
    counters = document["counters"]
    assert counters["results_reproduced"] == 2 and counters["results_differ"] == 0
    assert counters["results_not_compared"] == 1 and counters["aer_withheld"] == 1
    assert any("WITHHELD.json" in n and "fails --strict" in n for n in document["notices"])


def test_an_absent_object_the_ledger_does_not_list_is_still_missing(cli, sealed):
    """Fail closed: only an object ``WITHHELD.json`` lists is accounted for; any other absence stays ``aer.blob.missing``."""
    _withhold_first_artefact(sealed, listed=False)
    run = cli("validate", "--corpus", str(sealed), "--report", "-")
    assert run.code == 1
    report = json.loads(run.out)
    assert report["counters"]["failed"] == 1 and "aer_withheld" not in report["counters"]
    assert [r["aer"]["errors"] for r in report["results"] if r["verdict"] == "fail"] == [["aer.blob.missing"]]


@pytest.mark.parametrize("n", [0, 1, 2, 3, 5])
def test_p8_a_streamed_sample_validates_the_executions_and_rows_the_full_run_gives(sealed, n):
    """P8: the parent keeps only the sampled rows (the n smallest sample keys, one pass over the index); they are the
    executions ``sample_executions`` chooses, and their result rows equal the full run's rows for them."""
    from agentprov.corpus.reader import CorpusReader
    from agentprov.corpus.validation import validate_corpus
    from agentprov.corpus.verify import sample_executions

    full = validate_corpus(CorpusReader.open(sealed), mode="release")
    sampled = validate_corpus(CorpusReader.open(sealed), mode="release", sample=n, seed="p8")
    every = [row["ex"] for row in full.rows]
    chosen = sample_executions(every, n, "p8")
    assert [row["ex"] for row in sampled.rows] == chosen
    assert sampled.rows == [row for row in full.rows if row["ex"] in chosen]
    assert sampled.sample == {"n": len(chosen), "of": len(every), "seed": "p8"}
    assert sampled.counters["results_reproduced"] == len(chosen) and not sampled.failures
