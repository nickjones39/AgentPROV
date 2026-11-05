"""Finding AU-RA-4 (2026-11-05; 0.2.0 change batch D-1063, regen-batch row 179): ``incomplete_run`` is a loss code
(H.3.2(2)), so its issue cites the reading of ``agentdojo.incomplete_run@1`` under the D.5.4 policy, in the TraceLogger
and DRIFT mappers; a profile that verifies no code leaves the loss inferred (``unverifiable``), never proven. All content
is synthetic."""

from __future__ import annotations

from typing import Any

from agentdojo_support import map_log, new_log
from phase10d_support import SOURCES, map_doc, synthetic_path

from agentprov.adapters.agentdojo.profile import family_table
from agentprov.adapters.code_verification import rule_class
from agentprov.adapters.profiles import load_profile
from agentprov.adapters.runner.importer import proven_loss_codes
from agentprov.aer.rules import load_catalogue


def issue_rules(m: Any, code: str) -> list[str]:
    return [i["rule"] for i in m.info.issues if i["code"] == code]


def _incomplete(doc: dict[str, Any]) -> dict[str, Any]:
    """The log with its outcome keys removed, as TraceLogger leaves an interrupted run (agentdojo.incomplete_run@1)."""
    for key in ("utility", "security", "duration"):
        doc.pop(key)
    return doc


def _unverified_source() -> Any:
    src = next(s for s in SOURCES if s.variants == ("v0.k11",))
    assert family_table(load_profile(src.profile)).verified_code == ()
    return src


def test_an_incomplete_run_under_unverified_code_is_inferred_not_proven():
    """Under a profile that verifies no code the issue cites the I twin agentdojo.incomplete_run_unverified@1, so the loss
    is inferred and the execution stays ``unverifiable``."""
    src = _unverified_source()
    doc = _incomplete(new_log(pipeline_name=src.synthetic_pipeline))
    m = map_doc(src, doc, synthetic_path(src, doc))
    assert issue_rules(m, "incomplete_run") == ["agentdojo.incomplete_run_unverified@1"]
    assert rule_class("agentdojo.incomplete_run_unverified@1") == "I"
    assert "incomplete_run" not in proven_loss_codes(m.info.issues)
    assert m.validate().ok


def test_an_incomplete_run_under_verified_june_code_stays_proven():
    """The June-2024 code (c274885) that the rule cites is verified by agentdojo-upstream for its v0.k11 logs: D, proven."""
    m = map_log(_incomplete(new_log()))
    assert issue_rules(m, "incomplete_run") == ["agentdojo.incomplete_run@1"]
    assert "incomplete_run" in proven_loss_codes(m.info.issues)


def test_an_empty_log_with_no_outcome_is_no_loss_and_cites_the_rule_as_given():
    src = _unverified_source()
    doc = _incomplete(new_log(pipeline_name=src.synthetic_pipeline, messages=[]))
    m = map_doc(src, doc, synthetic_path(src, doc))
    assert issue_rules(m, "no_outcome_recorded") == ["agentdojo.incomplete_run@1"] and not issue_rules(m, "incomplete_run")


def test_the_twin_restates_its_rule():
    catalogue = load_catalogue("agentdojo")
    d, twin = catalogue.get("agentdojo.incomplete_run@1"), catalogue.get("agentdojo.incomplete_run_unverified@1")
    assert d is not None and twin is not None and d.cls == "D" and twin.cls == "I" and twin.citable
    assert twin.statement.endswith(d.statement) and "agentdojo.incomplete_run@1" in twin.statement
