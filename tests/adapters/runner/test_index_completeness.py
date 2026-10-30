"""Index ``completeness`` (HL H.3.2(2); D.2.9 item 8; phase-10 analysis B2).

``verified_complete`` needs a seal accounting that is ``consistent`` because at least one check was evaluated, and an
``agent_execution`` unit. ``fold_status`` of no verdicts is ``consistent`` (vacuous); an outcome-only record, an empty log
and a run error before the first assistant turn have no evaluated check and are ``unverifiable``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import import_support as support
import pytest

from agentprov.adapters.adprov.dialect import TranscriptV1Reader
from agentprov.adapters.runner.importer import LocalTree, PinCheck, import_source, index_completeness, listing_sha256
from agentprov.corpus.writer import CorpusWriter
from agentprov.io.canonical import sha256_hex

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agentdojo"))
import agentdojo_support as ads  # noqa: E402


# ------------------------------------------------------------------------------------------------ the pure rule
@pytest.mark.parametrize(("kwargs", "expected"), [
    (dict(accounting="consistent", checks_evaluated=1, unit_kind="agent_execution"), "verified_complete"),
    (dict(accounting="consistent", checks_evaluated=3, unit_kind="agent_execution"), "verified_complete"),
    # vacuous: nothing was evaluated
    (dict(accounting="consistent", checks_evaluated=0, unit_kind="agent_execution"), "unverifiable"),
    # never for an outcome-only record or a scenario, even with checks
    (dict(accounting="consistent", checks_evaluated=2, unit_kind="outcome_only"), "unverifiable"),
    (dict(accounting="consistent", checks_evaluated=2, unit_kind="scenario"), "unverifiable"),
    (dict(accounting="unverifiable", checks_evaluated=2, unit_kind="agent_execution"), "unverifiable"),
    (dict(accounting="inconsistent", checks_evaluated=2, unit_kind="agent_execution"), "known_incomplete"),
    # an adapter rule that proves loss wins, also over a vacuous accounting
    (dict(accounting="consistent", checks_evaluated=0, unit_kind="agent_execution", seal_codes={"retry_passes_inferred"}),
     "known_incomplete"),
    (dict(accounting="consistent", checks_evaluated=2, unit_kind="agent_execution", seal_codes={"incomplete_run"}),
     "known_incomplete"),
    (dict(accounting="consistent", checks_evaluated=2, unit_kind="agent_execution", seal_codes={"aborted_attempt"}),
     "known_incomplete"),
    (dict(accounting="consistent", checks_evaluated=2, unit_kind="agent_execution", seal_codes={"unexecuted_tool_call"}),
     "verified_complete"),
    (dict(accounting="inconsistent", checks_evaluated=2, unit_kind="agent_execution", degenerate=True), "unverifiable"),
])
def test_index_completeness_rule(kwargs, expected):
    args = dict(degenerate=False, seal_codes=frozenset())
    args.update(kwargs)
    assert index_completeness(**args) == expected


# ------------------------------------------------------------------------------------------------ end to end
def _import(tmp_path: Path, docs: dict[str, dict]) -> dict[str, dict]:
    """Import synthetic June-2024 logs (one per ``user_task_id`` key); returns task id -> index row."""
    root = tmp_path / "in"
    for task, doc in docs.items():
        path = root / f"runs/gpt-4o-2024-05-13/banking/{task}/important_instructions/injection_task_2.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(ads.log_bytes(dict(doc, user_task_id=task)))
    with CorpusWriter(tmp_path / "c") as corpus:
        report = import_source("agentdojo", LocalTree(root), corpus=corpus, in_process=True, part="2024-06",
                               pin_check=support.vouch(root))
    assert report.counters["mapped"] == len(docs)
    out = {}
    for line in (tmp_path / "c.partial" / "executions.jsonl").read_text().splitlines():
        row = json.loads(line)
        header = json.loads((tmp_path / "c.partial" / row["paths"]["aer"]).read_bytes().split(b"\n", 1)[0])
        out[header["task"]["task_id"]] = row
    assert sorted(out) == sorted(docs)
    return out


def test_vacuous_accounting_is_not_verified_complete(tmp_path):
    no_outcome = ads.base_log(messages=[])
    for key in ("utility", "security", "duration"):
        del no_outcome[key]
    docs = {
        "user_task_1": ads.base_log(),                                                    # a normal unit
        "user_task_2": ads.base_log(messages=[], pipeline_name="claude-3-opus-20240229"),  # outcome only, outcomes present
        "user_task_3": no_outcome,                                                        # an empty log, no outcomes
        "user_task_4": ads.base_log(                                                      # run error before any assistant turn
            messages=[{"role": "system", "content": ads.SYSTEM}, {"role": "user", "content": "Pay the bill."}],
            error="context_length_exceeded", utility=False, security=True),
    }
    rows = _import(tmp_path, docs)
    got = {task: (row["unit"], row["completeness"]) for task, row in rows.items()}
    assert got == {
        "user_task_1": ("agent_execution", "unverifiable"),  # AgentDojo logs derive their calls from the messages (C.16)
        "user_task_2": ("outcome_only", "unverifiable"),
        "user_task_3": ("outcome_only", "unverifiable"),
        "user_task_4": ("agent_execution", "unverifiable"),
    }
    assert rows["user_task_2"]["execution_observed"] is False


def test_golden_transcripts_keep_their_completeness(tmp_path):
    """The golden transcript/v1 traces (real consistent, unverifiable and inconsistent seals): the rule changes none of them
    and ``verified_complete`` is only ever given with evaluated checks."""
    labels = support.adprov_tree(tmp_path / "in")
    pairs = [(label, sha256_hex((tmp_path / "in" / label).read_bytes())) for label in labels]
    pin = {"role": "release", "tree": "corpus/corpus-prov", "commit": "579a908354b93361efe0905ffb7623256aa96a06",
           "listing_sha256": listing_sha256(pairs), "expected_files": len(pairs)}
    check = PinCheck("listing", pin, listing_origin=TranscriptV1Reader.listing_origin)
    with CorpusWriter(tmp_path / "c") as corpus:
        import_source("adprov-v1", LocalTree(tmp_path / "in"), corpus=corpus, in_process=True, part="release",
                      pin_check=check, until="aer")
    counts: dict[tuple[str, str], int] = {}
    for line in (tmp_path / "c.partial" / "executions.jsonl").read_text().splitlines():
        row = json.loads(line)
        seal = json.loads((tmp_path / "c.partial" / row["paths"]["aer"]).read_bytes().splitlines()[-1])
        accounting = seal["accounting"]
        if row["completeness"] == "verified_complete":
            assert accounting["status"] == "consistent" and accounting["checks"] and row["unit"] == "agent_execution"
        key = (row["completeness"], accounting["status"])
        counts[key] = counts.get(key, 0) + 1
    assert counts == {("verified_complete", "consistent"): 8, ("unverifiable", "unverifiable"): 1, ("known_incomplete", "inconsistent"): 1}
