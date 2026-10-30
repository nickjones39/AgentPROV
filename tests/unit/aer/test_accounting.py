"""C.12: accounting checks, verdicts, the fold, mirrored issues; the four C.16 seals are reproduced exactly."""

from __future__ import annotations

from typing import Any

import pytest
from aer_support import VECTOR_NAMES, edit, example_records, insert_after, vector_records

from agentprov.aer.accounting import (
    CORE_CHECK_IDS,
    Accounting,
    AccountingTally,
    compute,
    fold_status,
    mirror_issues,
)


def checks(records: list[dict[str, Any]], issues: list[dict[str, Any]] = ()) -> dict[tuple[str, str], dict[str, Any]]:  # type: ignore[assignment]
    acc = compute(records[1:], issues)
    return {(c["id"], c["scope"]): c for c in acc.checks}


@pytest.mark.parametrize("name", VECTOR_NAMES)
def test_core_checks_reproduce_the_vector_seals(name: str) -> None:
    records = vector_records(name)
    seal = records[-1]
    given = [i for i in seal["issues"] if not i["code"].startswith("accounting_")]
    acc = compute(records[1:-1], given)
    assert acc.to_json() == seal["accounting"]
    assert mirror_issues(acc) == [i for i in seal["issues"] if i["code"].startswith("accounting_")]


def test_fold_status() -> None:
    assert fold_status([]) == "consistent"
    assert fold_status(["consistent", "unverifiable"]) == "unverifiable"
    assert fold_status(["unverifiable", "inconsistent", "consistent"]) == "inconsistent"


def test_example_is_unverifiable_because_calls_are_derived_from_messages() -> None:
    c = checks(example_records())
    entry = c[("aer.acc.agent_calls_vs_assistant@1", "att0")]
    assert entry["verdict"] == "unverifiable" and entry["reason"] == "model_calls_derived_from_messages"
    assert entry["observed"] == {"assistant_messages": 2, "model_calls": 2}
    assert c[("aer.acc.tool_calls_dispatched@1", "att0")]["observed"] == {"tool_calls": 1, "tool_executions": 1, "unexecuted": 0}
    assert c[("aer.acc.tool_results_linked@1", "att0")]["observed"] == {"linked": 1, "tool_results": 1}
    assert c[("aer.acc.executions_have_results@1", "att0")]["verdict"] == "consistent"
    assert compute(example_records()[1:]).status == "unverifiable"


def test_checks_are_ordered_by_catalogue_then_scope_order() -> None:
    ids = [c["id"] for c in compute(example_records()[1:]).checks]
    assert ids == [i for i in CORE_CHECK_IDS if i in ids]


def test_observed_calls_are_compared_one_to_one() -> None:
    recs = edit(example_records(), "mc0", ev="O", by="capture", src=[{"a": "a0", "p": "/messages/0"}], rule=None)
    recs = edit(recs, "mc1", ev="O", by="capture", src=[{"a": "a0", "p": "/messages/0"}], rule=None)
    assert checks(recs)[("aer.acc.agent_calls_vs_assistant@1", "att0")]["verdict"] == "consistent"
    # an extra kept call without an assistant message
    extra = dict(next(r for r in recs if r["id"] == "mc1"), id="mc2")
    recs = insert_after(recs, "mc1", extra)
    entry = checks(recs)[("aer.acc.agent_calls_vs_assistant@1", "att0")]
    assert entry["verdict"] == "inconsistent" and entry["observed"] == {"assistant_messages": 2, "model_calls": 3}


def test_a_cached_call_answers_its_assistant_message() -> None:
    """C.20(1): a cache read generates the assistant message without inference; it pairs like a kept call."""
    recs = edit(example_records(), "mc0", ev="O", by="capture", src=[{"a": "a0", "p": "/messages/0"}], rule=None)
    recs = edit(recs, "mc1", ev="O", by="capture", src=[{"a": "a0", "p": "/messages/0"}], rule=None, status="cached")
    entry = checks(recs)[("aer.acc.agent_calls_vs_assistant@1", "att0")]
    assert entry["verdict"] == "consistent" and entry["observed"] == {"assistant_messages": 2, "model_calls": 2}
    # a cache read never reaches the provider: provider-reported counts still count kept calls only
    reported = checks(edit(recs, "run", usage={"calls": 1}))[("aer.acc.reported_counts@1", "run")]
    assert reported["observed"]["reported_calls"] == 1
    # a discarded call does not answer
    discarded = edit(recs, "mc1", status="discarded")
    assert checks(discarded)[("aer.acc.agent_calls_vs_assistant@1", "att0")]["verdict"] == "inconsistent"


def test_reported_counts_consistent_inconsistent_and_finish_reasons() -> None:
    recs = edit(example_records(), "run", usage={"calls": 2})
    entry = checks(recs)[("aer.acc.reported_counts@1", "run")]
    assert entry["verdict"] == "consistent" and entry["observed"] == {"assistant_messages": 2, "lost_calls": 0, "reported_calls": 2}
    # the check replaces agent_calls_vs_assistant for the covered scopes
    assert ("aer.acc.agent_calls_vs_assistant@1", "att0") not in checks(recs)
    bad = edit(example_records(), "run", usage={"calls": 3})
    assert checks(bad)[("aer.acc.reported_counts@1", "run")]["verdict"] == "inconsistent"
    # a lost call (C.7.4) restores the balance
    lost = {
        "k": "model_call", "id": "mcl", "ev": "D", "rule": ["tst.d@1"], "actor": "agent", "role": "agent", "scope": "att0",
        "unk": {"/status": "lost", "/input": "lost"},
    }
    recs3 = insert_after(bad, "m0", lost)
    assert checks(recs3)[("aer.acc.reported_counts@1", "run")]["observed"]["lost_calls"] == 1
    assert checks(recs3)[("aer.acc.reported_counts@1", "run")]["verdict"] == "consistent"
    # finish reasons that do not match the held calls
    fr = edit(example_records(), "mc0", finish_reason="stop")
    fr = edit(fr, "run", usage={"calls": 2})
    entry = checks(fr)[("aer.acc.reported_counts@1", "run")]
    assert entry["observed"]["finish_reasons"] == 1 and entry["verdict"] == "inconsistent"


def test_unexecuted_call_needs_the_issue_and_a_denial_counts_as_handled() -> None:
    recs = [r for r in example_records() if r["id"] not in ("te0", "m2")]
    entry = checks(recs)[("aer.acc.tool_calls_dispatched@1", "att0")]
    assert entry["verdict"] == "inconsistent" and entry["observed"]["unexecuted"] == 1
    listed = checks(recs, [{"code": "unexecuted_tool_call", "ids": ["m1#1"], "rule": "aer.acc.tool_calls_dispatched@1"}])
    assert listed[("aer.acc.tool_calls_dispatched@1", "att0")]["verdict"] == "consistent"
    deny = {"k": "decision", "id": "dc0", "ev": "I", "rule": ["tst.i@1"], "actor": "agent", "subject": "m1#1", "verdict": "deny"}
    denied = insert_after(recs, "m1", deny)
    entry = checks(denied)[("aer.acc.tool_calls_dispatched@1", "att0")]
    assert entry["verdict"] == "consistent" and entry["observed"] == {
        "denied": 1, "tool_calls": 1, "tool_executions": 0, "unexecuted": 0,
    }


def test_call_handled_twice_is_inconsistent() -> None:
    deny = {"k": "decision", "id": "dc0", "ev": "I", "rule": ["tst.i@1"], "actor": "agent", "subject": "m1#1", "verdict": "deny"}
    recs = insert_after(example_records(), "m1", deny)
    assert checks(recs)[("aer.acc.tool_calls_dispatched@1", "att0")]["verdict"] == "inconsistent"


def test_orphan_result_and_several_results_per_call() -> None:
    orphan = edit(example_records(), "m2", parts=[{"t": "tool_result", "text": "x"}], unk={"/parts/0/responds_to": "ambiguous"})
    entry = checks(orphan)[("aer.acc.tool_results_linked@1", "att0")]
    assert entry["verdict"] == "inconsistent" and entry["observed"] == {"linked": 0, "tool_results": 1}
    ok = checks(orphan, [{"code": "orphan_tool_result", "ids": ["m2#0"], "rule": "aer.acc.tool_results_linked@1"}])
    assert ok[("aer.acc.tool_results_linked@1", "att0")]["verdict"] == "consistent"
    second = {
        "k": "message", "id": "m9", "ev": "O", "by": "source", "src": [{"a": "a0", "p": "/messages/4"}], "scope": "att0",
        "role": "tool", "actor": "env", "generated_by": "te0", "parts": [{"t": "tool_result", "responds_to": "m1#1", "text": "again"}],
    }
    two = insert_after(example_records(), "m2", second)
    assert checks(two)[("aer.acc.tool_results_linked@1", "att0")]["verdict"] == "inconsistent"


def test_execution_without_result_and_redact_decision_path() -> None:
    no_result = [r for r in example_records() if r["id"] != "m2"]
    assert checks(no_result)[("aer.acc.executions_have_results@1", "att0")]["verdict"] == "inconsistent"
    listed = checks(no_result, [{"code": "missing_tool_result", "ids": ["te0"], "rule": "aer.acc.executions_have_results@1"}])
    assert listed[("aer.acc.executions_have_results@1", "att0")]["verdict"] == "consistent"
    decision = {"k": "decision", "id": "dc0", "ev": "I", "rule": ["tst.i@1"], "actor": "agent", "subject": "te0", "verdict": "redact"}
    via = insert_after(example_records(), "te0", decision)
    via = edit(via, "m2", generated_by="dc0")
    assert checks(via)[("aer.acc.executions_have_results@1", "att0")]["observed"] == {"tool_executions": 1, "with_result": 1}
    assert checks(via)[("aer.acc.executions_have_results@1", "att0")]["verdict"] == "consistent"


def test_assistant_without_generated_by_needs_unk_and_issue() -> None:
    recs = edit(example_records(), "m3", generated_by=None)
    assert checks(recs)[("aer.acc.assistant_generated_by@1", "att0")]["verdict"] == "inconsistent"
    issue = [{"code": "missing_generated_by", "ids": ["m3"], "rule": "aer.acc.assistant_generated_by@1"}]
    assert checks(recs, issue)[("aer.acc.assistant_generated_by@1", "att0")]["verdict"] == "inconsistent"  # still no unk
    declared = edit(recs, "m3", unk={"/generated_by": "not_recorded"})
    entry = checks(declared, issue)[("aer.acc.assistant_generated_by@1", "att0")]
    assert entry["verdict"] == "consistent" and entry["observed"] == {"assistant_messages": 2, "with_generated_by": 1}


def test_scripted_assistant_turns_are_not_agent_output() -> None:
    recs = edit(example_records(), "m3", actor="user")  # authored by a non-llm_agent actor
    assert checks(recs)[("aer.acc.assistant_generated_by@1", "att0")]["observed"]["assistant_messages"] == 1


def test_no_item_no_check() -> None:
    assert compute([]).checks == () and compute([]).status == "consistent"
    assert compute(example_records()[1:6]).checks == ()


def test_extra_checks_are_kept_in_order_and_fold_into_the_status() -> None:
    extra = {"id": "aer.acc.passes_closed@1", "scope": "run", "verdict": "inconsistent", "observed": {"open": 1}}
    acc = compute(example_records()[1:], extra_checks=[extra])
    assert acc.checks[-1] == extra and acc.status == "inconsistent"
    assert Accounting("consistent").to_json() == {"status": "consistent", "checks": []}


def test_mirror_issues_cite_the_check() -> None:
    acc = compute(example_records()[1:])
    assert mirror_issues(acc) == [
        {"code": "accounting_unverifiable", "ids": ["att0"], "rule": "aer.acc.agent_calls_vs_assistant@1"}
    ]


def test_tally_is_incremental_and_pure() -> None:
    tally = AccountingTally()
    for rec in example_records()[1:]:
        tally.feed(rec)
    assert tally.finish().to_json() == compute(example_records()[1:]).to_json()
    assert tally.finish().to_json() == tally.finish().to_json()
