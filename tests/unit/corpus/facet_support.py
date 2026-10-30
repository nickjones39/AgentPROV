"""Synthetic AER and SEM documents for the facet tests (HL H.3.3, H.7.4; HL-T18, HL-T19).

The documents are built in memory as :class:`AerDocument` / :class:`SemDocument` values: facets read records, not
bytes, so no seal is computed. Every value is synthetic.
"""

from __future__ import annotations

import copy
from typing import Any

from agentprov.aer.reader import AerDocument
from agentprov.sem.types import SemDocument

EX = "ex_7uz2oys57hugtsueixylme4fl5"
AER_DIGEST = "ab" * 32


def header(**changes: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "k": "execution", "id": "exec", "aer": "0.1", "ex": EX, "mode": "import", "unit": "agent_execution",
        "ev": "O", "by": "config", "evf": {"/task/defense_id": "I"},
        "task": {"benchmark": "foobench", "suite": "s1", "task_id": "t1", "attack_id": "a1", "defense_id": None},
        "instrumentation": [
            {"id": "foo.display@1", "kind": "attack_parameter", "recorded": "full", "params": {"display_name": "M"}},
            {"id": "foo.retry@1", "kind": "harness_policy", "recorded": "summary"},
        ],
    }  # fmt: skip
    base.update(changes)
    return base


def records(**header_changes: Any) -> list[dict[str, Any]]:
    """A header, a benchmark actor, an agent, a judge, and one or more records of every counted kind."""
    return [
        header(**header_changes),
        {"k": "actor", "id": "bench", "kind": "benchmark", "name": "foobench", "version": "v2", "ev": "O", "by": "source",
         "evf": {"/code/dist": "D"},
         "code": {"dist": "foobench", "dist_version": "1.0", "repo": "https://example.invalid/foo", "commit": "a" * 40}},
        {"k": "actor", "id": "agent", "kind": "llm_agent", "ev": "O", "by": "config", "evf": {"/model/served": "O:provider"},
         "model": {"requested": "m-1", "served": "m-1-a"}},
        {"k": "actor", "id": "judge", "kind": "judge", "ev": "O", "by": "source", "model": {"requested": "judge-m"}},
        {"k": "scope", "id": "run", "kind": "run", "ev": "O", "by": "source"},
        {"k": "message", "id": "m0", "ev": "O", "by": "source", "role": "user"},
        {"k": "message", "id": "m1", "ev": "O", "by": "source", "role": "assistant"},
        {"k": "model_call", "id": "mc0", "ev": "D", "rule": ["tst.d@1"], "role": "agent", "served_model": "m-1-b"},
        {"k": "model_call", "id": "mc1", "ev": "O", "by": "capture", "role": "auxiliary", "served_model": "aux-m"},
        {"k": "tool_execution", "id": "te0", "ev": "D", "rule": ["tst.d@1"]},
        {"k": "decision", "id": "d0", "ev": "O", "by": "source"},
        {"k": "state_change", "id": "sc0", "ev": "O", "by": "source"},
        {"k": "activity", "id": "ac0", "ev": "O", "by": "source", "type": "foo:memory_read"},
        {"k": "activity", "id": "ac1", "ev": "I", "rule": ["tst.i@1"], "type": "foo:plan"},
        {"k": "artefact", "id": "ar0", "ev": "D", "rule": ["tst.d@1"], "type": "foo:file"},
        {"k": "judgement", "id": "j0", "ev": "O", "by": "benchmark", "evf": {"/origin": "D"}, "name": "score",
         "value": 0.25, "origin": "checker", "subject": "run"},
        {"k": "judgement", "id": "j1", "ev": "O", "by": "benchmark", "name": "refusal", "value": 1, "origin": "checker",
         "subject": "run"},
    ]  # fmt: skip


def aer(recs: list[dict[str, Any]] | None = None, *, issues: list[dict[str, Any]] | None = None,
        accounting: dict[str, Any] | None = None) -> AerDocument:
    recs = copy.deepcopy(recs if recs is not None else records())
    seal = {"k": "seal", "id": "seal", "n_records": len(recs) + 1, "records_sha256": AER_DIGEST,
            "accounting": accounting or {"status": "unverifiable", "checks": []}, "issues": issues or []}
    return AerDocument(header=recs[0], records=recs, seal=seal, execution_digest=AER_DIGEST, file_sha256="cd" * 32)


def sem(*annotations: dict[str, Any], aer_digest: str = AER_DIGEST, profile: str = "foo.sem") -> SemDocument:
    head = {"k": "sem", "id": "sem", "sem": "0.1", "ex": EX, "aer_digest": "sha256:" + aer_digest,
            "profile": {"id": profile, "version": 1}, "rules": {"tst": 1}, "ns": {}}
    body = [{"k": "ann", "id": f"a{i}", **a} for i, a in enumerate(annotations)]
    return SemDocument(header=head, records=[head, *body], seal={"k": "seal", "id": "seal"}, digest="ef" * 32,
                       file_sha256="12" * 32)


def outcome_sem() -> SemDocument:
    return sem(
        {"target": "j0", "type": "outcome", "ev": "I", "rule": ["tst.i@1"],
         "value": {"claim": "foo.score", "score": 0.25, "scale": "unit_interval"}},
        {"target": "j1", "type": "outcome", "ev": "D", "rule": ["tst.d@1"], "value": {"claim": "foo.refusal", "holds": True}},
    )  # fmt: skip
