"""The tier-4 check registry: outcome statuses, ``ok`` versus ``passed`` (a skipped check fails release mode, D8)."""

from __future__ import annotations

from agentprov.validate.tiers import MAX_FINDINGS, CheckOutcome, Finding, Tier4Report, outcome


def test_outcome_passes_without_findings_and_fails_with_them() -> None:
    assert outcome("c", []).status == "pass"
    failed = outcome("c", [Finding("pv.x.b", "w"), Finding("pv.x.a", "w"), Finding("pv.x.a", "w")])
    assert failed.status == "fail"
    assert [f.code for f in failed.findings] == ["pv.x.a", "pv.x.b"]  # sorted and de-duplicated


def test_findings_are_bounded() -> None:
    o = outcome("c", (Finding("pv.x.a", str(i)) for i in range(MAX_FINDINGS + 5)))
    assert len(o.findings) == MAX_FINDINGS and o.truncated == 5


def test_skipped_check_is_ok_but_not_passed() -> None:
    report = Tier4Report([outcome("a", []), CheckOutcome("b", "skipped", reason="why")])
    assert report.ok and not report.passed
    report.outcomes.append(CheckOutcome("c", "not_applicable", reason="why"))
    assert report.summary() == {"pass": 1, "fail": 0, "skipped": 1, "not_applicable": 1}


def test_failed_check_fails_both() -> None:
    report = Tier4Report([outcome("a", [Finding("pv.x.a")])])
    assert not report.ok and not report.passed
    assert report.codes() == {"pv.x.a"}
    assert report.as_json()["outcomes"][0]["status"] == "fail"


def test_diagnostics_never_decide_the_verdict() -> None:
    report = Tier4Report([outcome("a", [])], diagnostics=[Finding("pv.constraints.time.start_after_end", "x:a")])
    assert report.passed
