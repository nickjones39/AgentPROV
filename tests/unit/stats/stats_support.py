"""Hand-built corpora whose statistics are known (K.5.11: "a hand-built corpus whose counts are known"; not collected).

Every record, PROV document and register entry is written here, in code; no committed fixture is read and nothing touches
``~/.agentprov``. The standard agent execution (:func:`agent_records`) has one known status per field group
(:data:`EXPECTED_CELLS`), and :data:`PROV_DOC` has known statement counts (:data:`EXPECTED_STATEMENTS`).
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentprov.aer.canon import dumps_line
from agentprov.corpus.dedup import source_key
from agentprov.corpus.index import IndexRow, RawRef, StageOutput, encode_index
from agentprov.corpus.integrity import content_digest, write_checksums
from agentprov.corpus.layout import CorpusLayout
from agentprov.corpus.register import RegisterEntry, encode_register
from agentprov.io.canonical import base32_lower_nopad, jcs_bytes

SPEC = "agentprov-prov/0.1"


def q(name: str) -> dict[str, str]:
    return {"$": name, "type": "prov:QUALIFIED_NAME"}


def ex_id(n: int) -> str:
    return "ex_" + base32_lower_nopad(hashlib.sha256(f"stats-test-{n}".encode()).digest())[:26]


def header(ex: str, *, unit: str = "agent_execution", profile: str = "pa") -> dict[str, Any]:
    return {"k": "execution", "id": "exec", "aer": "0.1", "ex": ex, "mode": "import", "unit": unit,
            "source_key": {"sha256": "ab" * 32, "loc": {}}, "artifacts": [], "adapter": {"id": "tst.adapter", "version": "0.1.0"},
            "profile": {"id": profile, "version": 1}, "rules": {}, "task": {"benchmark": "tst", "task_id": "t1"}}  # fmt: skip


def agent_records(ex: str, *, profile: str = "pa", model: str = "model-a") -> list[dict[str, Any]]:
    """One agent execution with one known status per field group (:data:`EXPECTED_CELLS`)."""
    return [
        header(ex, profile=profile),
        {"k": "actor", "id": "agent", "ev": "O", "by": "config", "kind": "llm_agent", "model": {"requested": model},
         "unk": {"/model/served": "not_recorded"}},
        {"k": "actor", "id": "bench", "ev": "O", "by": "source", "kind": "benchmark", "name": "tst", "version": "1",
         "unk": {"/code": "not_recorded"}},
        {"k": "actor", "id": "env", "ev": "D", "kind": "tool_runtime", "name": "env"},
        {"k": "scope", "id": "run", "ev": "D", "kind": "run"},
        {"k": "scope", "id": "att0", "ev": "D", "kind": "attempt", "parent": "run", "index": 0},
        {"k": "fixture", "id": "fx0", "ev": "O", "by": "benchmark", "kind": "injection_payload", "content": "p"},
        {"k": "message", "id": "m0", "ev": "O", "by": "source", "scope": "att0", "role": "system",
         "parts": [{"t": "text", "text": "s"}]},
        {"k": "model_call", "id": "mc0", "ev": "D", "actor": "agent", "role": "agent", "scope": "att0", "input": ["m0"],
         "status": "kept", "finish_reason": "stop", "evf": {"/input": "I", "/finish_reason": "O:provider"},
         "unk": {"/t": "not_recorded"}},
        {"k": "message", "id": "m1", "ev": "O", "by": "source", "scope": "att0", "role": "assistant", "generated_by": "mc0",
         "parts": [{"t": "reasoning", "text": "r"}, {"t": "tool_call", "name": "f", "args": {}, "provider_call_id": "c1"}]},
        {"k": "tool_execution", "id": "te0", "ev": "D", "actor": "env", "scope": "att0", "call": "m1#1", "name": "f",
         "status": "ok", "t": {"start": "2026-01-01T00:00:00Z"}, "evf": {"/t": "O:source"}},
        {"k": "message", "id": "m2", "ev": "O", "by": "source", "scope": "att0", "role": "tool", "generated_by": "te0",
         "parts": [{"t": "tool_result", "responds_to": "m1#1", "text": "x"}], "evf": {"/parts/0/responds_to": "D"}},
        {"k": "judgement", "id": "j0", "ev": "O", "by": "benchmark", "actor": "bench", "subject": "run", "name": "utility",
         "value": True, "origin": "checker"},
    ]  # fmt: skip


#: The cell of each group for :func:`agent_records` (``env`` has no state change, so no cell).
EXPECTED_CELLS: dict[str, tuple[str, bool]] = {
    "ctx": ("I", False),  # evf /input I covers /input/0
    "tooldefs": ("unk:not_recorded", True),  # /tools absent, nothing declared
    "model_req": ("O", False),
    "model_served": ("unk:not_recorded", False),  # declared on the actor beats the undeclared call field
    "sampling": ("unk:not_recorded", True),
    "usage": ("unk:not_recorded", True),
    "finish": ("O", False),  # O:provider counts as O
    "reasoning": ("O", False),
    "sysprompt": ("O", False),
    "t_model": ("unk:not_recorded", False),
    "t_tool": ("O", False),
    "passes": ("D", False),
    "callid": ("O", False),
    "link": ("D", False),
    "payload": ("O", False),
    "outcome_logged": ("O", False),
    "checker": ("unk:not_recorded", False),  # /version O, /code declared not_recorded: the weakest wins
}

PROV_DOC: dict[str, Any] = {
    "prefix": {"x": "urn:x:"},
    "activity": {"x:t1": {"apv:evidenceClass": q("apv:Observed"), "apv:rule": "aprov.t_annotate@1"}},
    "specializationOf": {"_:s1": {"prov:specificEntity": "x:e", "prov:generalEntity": "x:g"}},
    "bundle": {
        "xd:bundle.core.aaaaaaaa": {
            "activity": {"x:b1": {"apv:evidenceClass": q("apv:Derived"), "apv:rule": "aprov.n_scope@1"},
                         "x:b2": {"apv:evidenceClass": q("apv:Derived"), "apv:rule": "aprov.n_scope@1"}},
            "used": {"x:u1": {"apv:evidenceClass": q("apv:Observed"), "apv:rule": "aprov.use_request@1"}},
            "hadMember": {"_:h1": {"prov:collection": "x:c", "prov:entity": "x:e"}},
        },
        "xd:bundle.inf.tst-assumed-v1.bbbbbbbb": {
            "used": {"x:u2": {"apv:evidenceClass": q("apv:Inferred"), "apv:rule": "aprov.use_context@1"}},
        },
        "xd:bundle.assess.tst-sem-v1.cccccccc": {
            "entity": {"x:a1": {"apv:evidenceClass": q("apv:Derived"), "apv:rule": "aprov.a_payload@1"}},
            "mentionOf": {"_:m1": {"prov:specificEntity": "x:a", "prov:generalEntity": "x:b", "prov:bundle": "x:c"}},
        },
    },
}  # fmt: skip
#: (bundle, method, stype, evidence, rule) -> n for one :data:`PROV_DOC`.
EXPECTED_STATEMENTS = {
    ("toplevel", "", "activity", "O", "aprov.t_annotate@1"): 1,
    ("core", "", "activity", "D", "aprov.n_scope@1"): 2,
    ("core", "", "used", "O", "aprov.use_request@1"): 1,
    ("inference", "tst-assumed-v1", "used", "I", "aprov.use_context@1"): 1,
    ("assessment", "tst-sem-v1", "entity", "D", "aprov.a_payload@1"): 1,
}
EXPECTED_STRUCTURAL = {("toplevel", "", "specializationOf"): 1, ("core", "", "hadMember"): 1,
                       ("assessment", "tst-sem-v1", "mentionOf"): 1}  # fmt: skip


def outcome_only_records(ex: str, *, profile: str = "pa") -> list[dict[str, Any]]:
    return [
        header(ex, unit="outcome_only", profile=profile),
        {"k": "actor", "id": "bench", "ev": "O", "by": "source", "kind": "benchmark", "name": "tst"},
        {"k": "scope", "id": "run", "ev": "D", "kind": "run"},
        {"k": "judgement", "id": "j0", "ev": "O", "by": "benchmark", "actor": "bench", "subject": "run", "name": "utility",
         "value": False, "origin": "checker"},
    ]  # fmt: skip


def seal(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    body = b"".join(dumps_line(r) for r in records)
    return {"k": "seal", "id": "seal", "n_records": len(records) + 1, "records_sha256": hashlib.sha256(body).hexdigest(),
            "accounting": {"status": "unverifiable", "checks": []}, "issues": []}  # fmt: skip


@dataclass
class Execution:
    """One execution of a hand-built corpus."""

    source_id: str = "src-a"
    profile: str = "pa@1"
    unit: str = "agent_execution"
    observed: bool = True
    status: str = "ok"
    completeness: str = "unverifiable"
    records: list[dict[str, Any]] | None = None  # default: agent_records / outcome_only_records
    prov: dict[str, Any] | None = field(default_factory=lambda: copy.deepcopy(PROV_DOC))
    register_codes: tuple[str, ...] = ()


def build_corpus(root: Path, executions: Sequence[Execution], *, sealed: bool = False, corpus_id: str = "tst-stats") -> dict[str, Any]:
    """Write the corpus at ``root``; returns ``{"root", "rows", "exs"}`` (rows in index order)."""
    layout = CorpusLayout(root)
    rows: list[IndexRow] = []
    entries: list[RegisterEntry] = []
    for n, spec in enumerate(executions):
        ex = ex_id(n)
        profile_id = spec.profile.split("@")[0]
        if spec.records is not None:
            records = copy.deepcopy(spec.records)
            records[0]["ex"] = ex
        elif spec.unit == "agent_execution":
            records = agent_records(ex, profile=profile_id)
        else:
            records = outcome_only_records(ex, profile=profile_id)
            records[0]["unit"] = spec.unit
        body = b"".join(dumps_line(r) for r in records)
        aer = body + dumps_line(seal(records))
        files = {layout.aer_relpath(ex): aer}
        prov_stage = prov_paths = None
        if spec.prov is not None:
            prov_bytes = jcs_bytes(spec.prov)
            files[layout.prov_relpath(SPEC, ex)] = prov_bytes
            prov_stage = {SPEC: StageOutput("ok", hashlib.sha256(prov_bytes).hexdigest())}
            prov_paths = {SPEC: layout.prov_relpath(SPEC, ex)}
        sha = hashlib.sha256(f"raw-{n}".encode()).hexdigest()
        rows.append(IndexRow(
            ex=ex, mode="import", unit=spec.unit, source_id=spec.source_id, snapshot_ids=("s1",),
            source_key=source_key(sha, {"p": f"/{n}"}), raw=(RawRef(sha, "primary", True),), n_origins=1,
            adapter="tst.adapter@0.1.0", profile=spec.profile, aer_digest=hashlib.sha256(body).hexdigest(),
            aer_path=layout.aer_relpath(ex), stages={"raw": "ok", "aer": "ok"}, status=spec.status,
            completeness=spec.completeness, execution_observed=spec.observed, issues=spec.register_codes, attempt=None,
            prov=prov_stage, prov_paths=prov_paths,
        ))  # fmt: skip
        for code in spec.register_codes:
            entries.append(RegisterEntry(subject={"ex": ex}, code=code, severity="info", stage="map", disposition="sealed"))
        for label, data in files.items():
            path = root.joinpath(*label.split("/"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    rows.sort(key=lambda r: r.ex)
    manifest: dict[str, Any] = {"format": "agentprov-corpus/0.1", "corpus_id": corpus_id, "sealed": sealed,
                                "state": "sealed" if sealed else "working"}  # fmt: skip
    if sealed:
        manifest["content_digest"] = content_digest(manifest)
    root.mkdir(parents=True, exist_ok=True)
    (root / "corpus.json").write_bytes(json.dumps(manifest, sort_keys=True).encode() + b"\n")
    (root / "executions.jsonl").write_bytes(encode_index(rows))
    (root / "register.jsonl").write_bytes(encode_register(entries))
    if sealed:
        write_checksums(root)
    return {"root": root, "rows": rows, "exs": [r.ex for r in rows]}


def standard_corpus(root: Path, **kw: Any) -> dict[str, Any]:
    """Two sources: ``src-a`` (3 observed agent executions, one outcome-only record) and ``src-b`` (2 agent executions,
    one not observed, and a scenario); counts listed in :data:`STANDARD_COUNTS`."""
    a, b = "src-a", "src-b"
    return build_corpus(root, [
        Execution(a, "pa@1", register_codes=("map.accounting_unverifiable",)),
        Execution(a, "pa@1", status="ok_with_issues"),
        Execution(a, "pa@1", completeness="verified_complete"),
        Execution(a, "pa@1", unit="outcome_only", observed=False, prov=None),
        Execution(b, "pb@1", register_codes=("map.accounting_unverifiable",)),
        Execution(b, "pb@1", observed=False, status="failed"),
        Execution(b, "pb@1", unit="scenario", records=[header("ex_", unit="scenario", profile="pb")], prov=None),
    ], **kw)  # fmt: skip


STANDARD_COUNTS = {
    ("src-a", "pa@1"): {"records": 4, "n_executions": 3, "unit_agent_execution": 3, "unit_outcome_only": 1,
                        "unit_scenario": 0, "execution_observed_true": 3, "execution_observed_false": 1, "status_ok": 3,
                        "status_ok_with_issues": 1, "status_failed": 0, "completeness_verified_complete": 1,
                        "completeness_known_incomplete": 0, "completeness_unverifiable": 3, "prov_output": 3,
                        "n_outcome_only": 1, "rate_excluded": 0},
    ("src-b", "pb@1"): {"records": 3, "n_executions": 1, "unit_agent_execution": 2, "unit_outcome_only": 0,
                        "unit_scenario": 1, "execution_observed_true": 2, "execution_observed_false": 1, "status_ok": 2,
                        "status_ok_with_issues": 0, "status_failed": 1, "completeness_verified_complete": 0,
                        "completeness_known_incomplete": 0, "completeness_unverifiable": 3, "prov_output": 2,
                        "n_outcome_only": 0, "rate_excluded": 0},
}  # fmt: skip
