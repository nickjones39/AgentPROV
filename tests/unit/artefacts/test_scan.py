"""Classification, unclassified anomalies, determinism and the summary table (D.15.3, D.15.4, D.15.7)."""

from __future__ import annotations

import copy
import json
import random

import pytest
from art_support import PROFILE, catalogue, clean, entry, header, replaced, seal, with_records

from agentprov.artefacts import UNCLASSIFIED_PREFIX, Finding, ScanError, scan, scan_many, table


def judgement(origin: str = "harness_default", **changes):
    rec = {"k": "judgement", "id": "j0", "actor": "env", "subject": "run", "name": "security", "value": True, "origin": origin,
           "rule": ["tst.constant@1#/origin"]}  # fmt: skip
    rec.update(changes)
    return rec


def imposed() -> list[dict]:
    return with_records(clean(), judgement())


# ---------------------------------------------------------------------------------------------------- claiming


def test_a_generic_detector_entry_claims_every_hit_of_that_detector():
    c = catalogue(entry("imposed", detector="artefact.generic.harness_imposed_outcome", handling="CR", handling_rule="aer.time_order@1"))
    (f,) = scan(imposed(), [c])
    assert (f.entries, f.handling, f.classified) == (("tst.art.imposed",), ("CR",), True)
    assert f.artefact_ids == ("tst.art.imposed",)


def test_a_mapper_rule_entry_claims_only_hits_that_cite_its_rule():
    cites = catalogue(entry("constant", detector="tst.constant@1", cls="D"))
    other = catalogue(entry("other", detector="tst.elsewhere@1", cls="D"))
    assert scan(imposed(), [cites])[0].entries == ("tst.art.constant",)
    assert scan(imposed(), [other])[0].entries == ()
    assert scan(imposed(), [other])[0].artefact_ids == (UNCLASSIFIED_PREFIX + "harness_imposed_outcome",)


def test_a_claim_names_a_detector_and_optionally_a_variant():
    base = with_records(clean(), judgement("harness_rule"))
    wide = catalogue(entry("w", detector="tst.n@1", cls="D", extra='claims = ["artefact.generic.harness_imposed_outcome"]\n'))
    right = catalogue(entry("r", detector="tst.n@1", cls="D", extra='claims = ["artefact.generic.harness_imposed_outcome#harness_rule"]\n'))
    wrong = catalogue(entry("x", detector="tst.n@1", cls="D", extra='claims = ["artefact.generic.harness_imposed_outcome#harness_default"]\n'))
    assert scan(base, [wide])[0].entries == ("tst.art.w",)
    assert scan(base, [right])[0].entries == ("tst.art.r",)
    assert scan(base, [wrong])[0].entries == ()


def test_a_seal_issue_code_in_recorded_as_claims_the_hits_it_produced():
    records = with_records(clean(), seal_record=seal(issues=[{"code": "tst.odd", "ids": ["m2"], "rule": "tst.r@1"}]))
    claimed = catalogue(entry("odd", detector="tst.other@1", cls="D", extra='recorded_as = { issues = ["tst.odd"] }\n'))
    assert scan(records, [claimed])[0].entries == ("tst.art.odd",)
    assert scan(records, [catalogue(entry("odd", detector="tst.other@1", cls="D"))])[0].entries == ()


def test_the_check_id_of_an_accounting_hit_is_a_citable_rule():
    check = {"id": "aer.acc.reported_counts@1", "scope": "att0", "verdict": "inconsistent", "observed": {}}
    records = with_records(clean(), seal_record=seal(checks=[check]))
    c = catalogue(entry("exceed", detector="aer.acc.reported_counts@1", cls="D"))
    (f,) = scan(records, [c])
    assert f.detector.endswith("accounting_inconsistent") and f.entries == ("tst.art.exceed",)


def test_several_entries_may_claim_one_finding():
    c = catalogue(
        entry("a", detector="artefact.generic.harness_imposed_outcome"),
        entry("b", detector="tst.constant@1", cls="D", handling="NR"),
    )
    (f,) = scan(imposed(), [c])
    assert f.entries == ("tst.art.a", "tst.art.b") and f.handling == ("FO", "NR")


def test_scope_profiles_restrict_the_entry():
    scoped = catalogue(entry("p", detector="artefact.generic.harness_imposed_outcome", extra='scope = { profiles = ["other-profile"] }\n'))
    assert scan(imposed(), [scoped])[0].entries == ()
    here = catalogue(entry("p", detector="artefact.generic.harness_imposed_outcome", extra=f'scope = {{ profiles = ["{PROFILE}"] }}\n'))
    assert scan(imposed(), [here])[0].entries == ("tst.art.p",)


def test_an_entry_without_profiles_applies_to_every_profile():
    c = catalogue(entry("p", detector="artefact.generic.harness_imposed_outcome"))
    records = imposed()
    records[0]["profile"] = {"id": "anything"}
    assert scan(records, [c])[0].entries == ("tst.art.p",)
    del records[0]["profile"]
    assert scan(records, [c])[0].entries == ("tst.art.p",)


# ---------------------------------------------------------------------------------------------------- unclassified


def test_an_unknown_anomaly_yields_artefact_unclassified():
    records = replaced(clean(), "mc1", finish_reason="something_new")
    (f,) = scan(records, [catalogue(entry("unrelated"))])
    assert not f.classified
    assert f.artefact_ids == ("artefact.unclassified.abnormal_finish",)
    assert f.ids == ("mc1",)


def test_a_mapper_issue_code_absent_from_the_catalogue_is_unclassified():
    issue = {"code": "tst.never_seen", "ids": ["te0"], "rule": "tst.r@1"}
    (f,) = scan(with_records(clean(), seal_record=seal(issues=[issue])), [catalogue(entry("unrelated"))])
    assert f.artefact_ids == ("artefact.unclassified.seal_issue",)
    assert f.variant == "tst.never_seen" and f.ids == ("te0",)


def test_an_empty_catalogue_list_classifies_nothing_and_drops_nothing():
    records = with_records(replaced(clean(), "mc1", finish_reason="length"), judgement())
    found = scan(records, [])
    assert [f.artefact_ids[0] for f in found] == [
        "artefact.unclassified.abnormal_finish",
        "artefact.unclassified.harness_imposed_outcome",
    ]


def test_unclassified_findings_are_never_filtered_even_beside_claimed_ones():
    c = catalogue(entry("imposed", detector="artefact.generic.harness_imposed_outcome"))
    records = with_records(replaced(clean(), "mc1", finish_reason="length"), judgement())
    classified = {f.detector.rsplit(".", 1)[1]: f.classified for f in scan(records, [c])}
    assert classified == {"abnormal_finish": False, "harness_imposed_outcome": True}


# ---------------------------------------------------------------------------------------------------- determinism


def messy() -> list[dict]:
    records = with_records(
        replaced(clean(), "mc1", finish_reason="length"),
        judgement(),
        {"k": "scope", "id": "att1", "kind": "attempt", "parent": "run", "unk": {"/index": "lost"}, "ev": "D"},
        seal_record=seal(issues=[{"code": "tst.odd", "ids": ["m2"], "rule": "tst.r@1"}]),
    )
    return replaced(records, "te0", unk={"/t": "not_recorded"})


def test_scan_is_deterministic_and_sorted():
    cats = [catalogue(entry("imposed", detector="artefact.generic.harness_imposed_outcome"))]
    first, second = scan(messy(), cats), scan(copy.deepcopy(messy()), cats)
    assert first == second
    assert [f.sort_key for f in first] == sorted(f.sort_key for f in first)
    assert json.dumps([f.to_json() for f in first], sort_keys=True) == json.dumps([f.to_json() for f in second], sort_keys=True)


def test_catalogue_order_does_not_change_the_result():
    a = catalogue(entry("a", detector="artefact.generic.harness_imposed_outcome"), family="fa", namespaces='["tst"]')
    b = catalogue(entry("b", detector="artefact.generic.harness_imposed_outcome"), family="fb", namespaces='["tst"]')
    assert scan(imposed(), [a, b]) == scan(imposed(), [b, a])


def test_scan_many_does_not_depend_on_input_order():
    other = copy.deepcopy(imposed())
    other[0]["ex"] = "ex_bbbbbbbbbbbbbbbbbbbbbbbbbb"
    runs = [imposed(), other, clean(), messy()]
    expected = scan_many(runs, [])
    shuffled = list(runs)
    random.Random(7).shuffle(shuffled)
    assert scan_many(shuffled, []) == expected
    assert [f.ex for f in expected] == sorted(f.ex for f in expected)


def test_the_catalogue_on_and_off_leave_the_aer_unchanged():
    """The D.15.7 differential: scanning with and without a catalogue never changes a record byte."""
    records = messy()
    before = json.dumps(records, sort_keys=True)
    with_cat = scan(records, [catalogue(entry("a", detector="artefact.generic.harness_imposed_outcome"))])
    without = scan(records, [])
    assert json.dumps(records, sort_keys=True) == before
    assert [f.sort_key for f in with_cat] == [f.sort_key for f in without]  # same hits; only the classification differs
    assert [f.ids for f in with_cat] == [f.ids for f in without]


def test_scan_accepts_any_iterable_of_records():
    assert scan(iter(imposed()), []) == scan(imposed(), [])


def test_findings_have_a_json_form_without_source_content():
    (f,) = scan(imposed(), [])
    doc = f.to_json()
    assert set(doc) == {"classified", "detector", "entries", "ex", "handling", "ids", "issue_codes", "n", "rules", "variant"}
    assert json.loads(json.dumps(doc)) == doc


# ---------------------------------------------------------------------------------------------------- input checks


@pytest.mark.parametrize("records", [[], [{"k": "message", "id": "m"}], [clean()[1], clean()[0]]])
def test_scan_needs_the_header_first(records):
    with pytest.raises(ScanError):
        scan(records, [])


def test_a_header_without_ex_still_scans():
    records = [{"k": "execution", "id": "exec", "unit": "outcome_only"}, seal()]
    (f,) = scan(records, [])
    assert f.ex == "unknown"


# ---------------------------------------------------------------------------------------------------- the table


def finding(ex: str, entries: tuple[str, ...], handling: tuple[str, ...], n: int = 1, detector: str = "artefact.generic.pass_loss") -> Finding:
    return Finding(ex, detector, "", entries, handling, ("x",) * min(n, 25), n)


def test_table_counts_executions_and_hits_per_artefact():
    findings = [
        finding("ex_3", ("a.art.x",), ("CR",), n=2),
        finding("ex_1", ("a.art.x",), ("CR",), n=1),
        finding("ex_1", ("a.art.x",), ("CR",), n=4, detector="artefact.generic.sentinel_time"),
        finding("ex_2", (), (), detector="artefact.generic.abnormal_finish"),
    ]
    rows = table(findings, n_executions=4)
    assert [r.artefact_id for r in rows] == ["a.art.x", "artefact.unclassified.abnormal_finish"]
    x, u = rows
    assert (x.handling, x.executions, x.hits, x.proportion, x.first) == ("CR", 2, 7, 0.5, ("ex_1", "ex_3"))
    assert (u.handling, u.executions, u.hits, u.proportion, u.first) == (None, 1, 1, 0.25, ("ex_2",))


def test_table_without_a_denominator_has_no_proportion():
    (row,) = table([finding("ex_1", ("a.art.x",), ("FO",))])
    assert row.proportion is None
    assert table([finding("ex_1", ("a.art.x",), ("FO",))], n_executions=0)[0].proportion is None


def test_table_lists_the_first_five_executions_only():
    rows = table([finding(f"ex_{i}", ("a.art.x",), ("FO",)) for i in (9, 8, 7, 6, 5, 4, 3)])
    assert rows[0].first == ("ex_3", "ex_4", "ex_5", "ex_6", "ex_7") and rows[0].executions == 7


def test_a_finding_claimed_by_two_entries_counts_in_both_rows():
    rows = table([finding("ex_1", ("a.art.x", "a.art.y"), ("CR", "NR"))])
    assert [(r.artefact_id, r.handling) for r in rows] == [("a.art.x", "CR"), ("a.art.y", "NR")]


def test_table_is_independent_of_finding_order():
    findings = [finding(f"ex_{i}", ("a.art.x",), ("CR",), n=i) for i in range(1, 8)] + [finding("ex_1", (), ())]
    expected = table(findings, n_executions=10)
    shuffled = list(findings)
    random.Random(3).shuffle(shuffled)
    assert table(shuffled, n_executions=10) == expected
    assert json.dumps([r.to_json() for r in expected], sort_keys=True) == json.dumps([r.to_json() for r in table(shuffled, n_executions=10)], sort_keys=True)


def test_negative_denominator_is_refused():
    with pytest.raises(ValueError):
        table([], n_executions=-1)


def test_table_of_a_real_scan():
    c = catalogue(entry("imposed", detector="artefact.generic.harness_imposed_outcome", handling="CR", handling_rule="aer.time_order@1"))
    runs = [imposed(), clean(), messy()]
    for n, run in enumerate(runs):
        run[0]["ex"] = f"ex_{n:026d}"
    rows = table(scan_many(runs, [c]), n_executions=3)
    by_id = {r.artefact_id: r for r in rows}
    assert by_id["tst.art.imposed"].executions == 2 and by_id["tst.art.imposed"].handling == "CR"
    assert by_id["artefact.unclassified.abnormal_finish"].executions == 1
    assert by_id["artefact.unclassified.pass_loss"].proportion == pytest.approx(1 / 3)


def test_header_helper_is_a_valid_scan_input():
    assert scan([header(), seal()], [])[0].artefact_ids == ("artefact.unclassified.empty_execution",)
