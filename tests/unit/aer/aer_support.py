"""Shared helpers for the AER tests: the four C.16 spec vectors, synthetic adapter catalogues, small builders.

The vectors are frozen specification artefacts (docs/architecture/examples/C/*.aer.jsonl), sealed as ``aer/0.1``;
``examples/C/aer-0.2/`` holds the same records sealed by this build's writer as ``aer/0.2`` (D-212: only the header's
``aer`` member and so the seal differ). Their ``profile.sha256``
values are over stand-in profile texts (erratum E22), which is why profile digests are never checked against them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentprov.aer.rules import RuleCatalogue, RuleEntry, RuleRegistry, load_catalogue

REPO = Path(__file__).resolve().parents[3]
VECTOR_DIR = REPO / "docs" / "architecture" / "examples" / "C"
VECTOR_NAMES = (
    "agentdojo_2024_pi_detector",  # C.16.1  (KAT 1)
    "adprov_v1_llama_injecagent",  # C.16.2
    "stac_case_223",  # C.16.3
    "rope_denial_qwen_autodojo",  # C.16.4
)
KAT1_EX = "ex_7uz2oys57hugtsueixylme4fl5"

#: Class-I rules among those the vectors cite (docs/architecture/examples/C/rulecheck.py ``I_RULES``).
I_RULES = frozenset(
    {
        "agentdojo.pipeline_dir_is_model_identity@1",
        "agentdojo.defence_suffix@1",
        "agentdojo.context_is_prefix@1",
        "agentdojo.pi_detector_sentinel@1",
        "agentdojo.naive_local_timestamp_unverified@1",
        "agentdojo.payload_attributed_to_attacker@1",
        "agentdojo.auto_execution_unverified@1",
        "agentdojo.checker_inputs_unverified@1",
        "adprov.v1_capture_code_semantics@1",
        "adprov.context_is_prefix@1",
        "rope.guard_active_in_main_tree@1",
        "rope.model_dir_identity@1",
        "rope.harness_is_vendored_autodojo@1",
        "rope.denial_error_pattern@1",
        "stac.assistant_turns_scripted@1",
        "stac.prefix_user_turns_by_prompt_writer@1",
        "stac.prompt_written_after_execution@1",
        "stac.planning_after_prefix@1",
        "stac.tool_status_from_content@1",
    }
)


def vector_path(name: str, version: str = "0.1") -> Path:
    """The ``aer/0.1`` spec vector, or its ``aer/0.2`` reseal (``version="0.2"``)."""
    return VECTOR_DIR / f"{name}.aer.jsonl" if version == "0.1" else VECTOR_DIR / f"aer-{version}" / f"{name}.aer.jsonl"


def vector_bytes(name: str) -> bytes:
    return vector_path(name).read_bytes()


def vector_lines(name: str) -> list[bytes]:
    return vector_bytes(name).splitlines(keepends=True)


def vector_records(name: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in vector_lines(name)]


def cited_rule_ids(records: list[dict[str, Any]]) -> set[str]:
    out: set[str] = set()
    for rec in records:
        out.update(r.split("#", 1)[0] for r in rec.get("rule", []))
        for issue in rec.get("issues", []):
            out.add(issue["rule"].split("#", 1)[0])
        for check in rec.get("accounting", {}).get("checks", []):
            out.add(check["id"])
    return out


def synthetic_catalogue(namespace: str, rule_ids: set[str], *, issue_codes: tuple[str, ...] = (), version: int = 1,
                        types: frozenset[str] = frozenset()) -> RuleCatalogue:
    """An in-memory catalogue declaring ``rule_ids`` (class I for the vectors' I rules, else D) and the ``activity``/
    ``artefact`` ``types`` of its namespace."""
    rules = {}
    for rid in sorted(r for r in rule_ids if r.split(".", 1)[0] == namespace):
        name, _, ver = rid.partition("@")
        twin = name.endswith("_unverified")  # every _unverified twin is class I (D.5.4; regeneration-batch item 3)
        rules[rid] = RuleEntry(name, int(ver), "I" if rid in I_RULES or twin else "D", "active", "synthetic test rule")
    own = frozenset(t for t in types if t.split(":", 1)[0] == namespace)
    return RuleCatalogue(namespace, version, "agentprov-rule-catalogue/0.1", frozenset(issue_codes), frozenset(), own, rules)


def vector_registry() -> RuleRegistry:
    """The package ``aer`` catalogue plus synthetic ``agentdojo``/``adprov``/``rope``/``stac`` catalogues."""
    cited: set[str] = set()
    types: set[str] = set()  # e.g. agentdojo:load_environment in C.16.1 (regeneration-batch item 5)
    for name in VECTOR_NAMES:
        cited |= cited_rule_ids(vector_records(name))
        types |= {str(r["type"]) for r in vector_records(name) if r.get("k") in ("activity", "artefact")}
    registry = RuleRegistry([load_catalogue("aer", 1)], autoload=False)
    # every version the vectors declare (D-31: C.16.1/C.16.2 are on agentdojo and adprov 2, the ROPE vector on 1)
    declared = {(ns, v) for name in VECTOR_NAMES for ns, v in vector_records(name)[0]["rules"].items() if ns != "aer"}
    for ns, version in sorted(declared):
        codes = ("target_response_not_released",) if ns == "stac" else ()
        registry.add(synthetic_catalogue(ns, cited, issue_codes=codes, version=version, types=frozenset(types)))
    return registry


class MemoryStore:
    """Minimal in-memory RawStore for tests."""

    def __init__(self, objects: dict[str, bytes] | None = None) -> None:
        self.objects = dict(objects or {})

    def put(self, data: bytes) -> str:
        from agentprov.io.canonical import sha256_hex

        digest = sha256_hex(data)
        self.objects[digest] = data
        return digest

    def has(self, sha256: str) -> bool:
        return sha256 in self.objects

    def size(self, sha256: str) -> int:
        return len(self.objects[sha256])

    def read_bytes(self, sha256: str) -> bytes:
        return self.objects[sha256]


# --------------------------------------------------------------------------------------------- a small valid AER
import copy  # noqa: E402
import hashlib  # noqa: E402

from agentprov.aer.ids import import_execution_id, mapping_id  # noqa: E402
from agentprov.aer.validate import ValidationReport, validate_records  # noqa: E402

ARTEFACT_DOC = {"messages": [{"i": n} for n in range(12)], "meta": {"k": 1}}
ARTEFACT_BYTES = json.dumps(ARTEFACT_DOC, separators=(",", ":")).encode()
ARTEFACT_SHA = hashlib.sha256(ARTEFACT_BYTES).hexdigest()
ADAPTER_ID, PROFILE_ID = "tst.adapter", "tst-profile"


def make_registry() -> RuleRegistry:
    """The package ``aer`` catalogue plus a synthetic ``tst`` catalogue (``tst.d@1`` class D, ``tst.i@1`` class I)."""
    registry = RuleRegistry([load_catalogue("aer", 1)], autoload=False)
    rules = {
        "tst.d@1": RuleEntry("tst.d", 1, "D", "active", "test D rule"),
        "tst.d2@1": RuleEntry("tst.d2", 1, "D", "active", "second test D rule"),
        "tst.i@1": RuleEntry("tst.i", 1, "I", "active", "test I rule"),
    }
    registry.add(
        RuleCatalogue(
            "tst",
            1,
            "agentprov-rule-catalogue/0.1",
            frozenset({"odd_thing"}),
            frozenset({"tst.sub"}),
            frozenset({"tst:plan", "tst:message", "tst:memory_read", "tst:note"}),
            rules,
        )
    )
    return registry


def loc(n: int) -> dict[str, Any]:
    return {"a": "a0", "p": f"/messages/{n}"}


def observed(rec: dict[str, Any], n: int) -> dict[str, Any]:
    """Make ``rec`` an observed record (``ev: O``, ``by: source``) that cites message ``n`` of the artefact."""
    rec.update({"ev": "O", "by": "source", "src": [loc(n)]})
    return rec


def derived(rec: dict[str, Any], rule: str = "tst.d@1") -> dict[str, Any]:
    rec.update({"ev": "D", "rule": [rule]})
    return rec


def example_records() -> list[dict[str, Any]]:
    """A small valid import: user message, one tool round trip, final answer; accounting ``unverifiable``."""
    key = {"p": ""}
    header: dict[str, Any] = {
        "k": "execution",
        "id": "exec",
        "ev": "O",
        "by": "config",
        "aer": "0.1",
        "ex": import_execution_id(mapping_id(ADAPTER_ID, PROFILE_ID), ARTEFACT_SHA, key),
        "mode": "import",
        "unit": "agent_execution",
        "source_key": {"sha256": ARTEFACT_SHA, "loc": key},
        "artifacts": [
            {
                "id": "a0",
                "role": "primary",
                "prov_primary": "native",
                "sha256": ARTEFACT_SHA,
                "bytes": len(ARTEFACT_BYTES),
                "media": "application/json",
                "origin": {"kind": "url", "url": "https://example.invalid/a.json", "retrieved": "2026-10-08"},
            }
        ],
        "adapter": {"id": ADAPTER_ID, "version": "0.1.0"},
        "dialect": {"id": "tst.dialect", "variant": "v1"},
        "profile": {"id": PROFILE_ID, "version": 1, "sha256": "0" * 64},
        "rules": {"aer": 1, "tst": 1},
        "ns": {"tst": "https://example.invalid/ns/tst#"},
        "canon": "jcs-rfc8785",
        "hash": "sha256",
        "task": {"benchmark": "tst", "task_id": "t1"},
        "src": [{"a": "a0", "p": "/meta"}],
        "unk": {"/instrumentation": "not_recorded"},
    }
    return [
        header,
        derived({"k": "actor", "id": "agent", "kind": "llm_agent", "name": "agent-under-test"}),
        derived({"k": "actor", "id": "env", "kind": "tool_runtime", "on_behalf_of": "agent"}),
        derived({"k": "actor", "id": "user", "kind": "simulated_user"}),
        derived({"k": "scope", "id": "run", "kind": "run", "actor": "agent"}),
        derived({"k": "scope", "id": "att0", "kind": "attempt", "parent": "run", "scored": True}),
        observed(
            {"k": "message", "id": "m0", "scope": "att0", "role": "user", "actor": "user",
             "parts": [{"t": "text", "text": "hello"}]},
            0,
        ),
        derived({"k": "model_call", "id": "mc0", "actor": "agent", "role": "agent", "scope": "att0",
                 "input": ["m0"], "status": "kept"}),
        observed(
            {"k": "message", "id": "m1", "scope": "att0", "role": "assistant", "actor": "agent", "generated_by": "mc0",
             "parts": [{"t": "text", "text": None}, {"t": "tool_call", "name": "lookup", "args": {"q": "x"}}]},
            1,
        ),
        derived({"k": "tool_execution", "id": "te0", "actor": "env", "scope": "att0", "call": "m1#1", "name": "lookup",
                 "status": "ok"}),
        observed(
            {"k": "message", "id": "m2", "scope": "att0", "role": "tool", "actor": "env", "generated_by": "te0",
             "parts": [{"t": "tool_result", "responds_to": "m1#1", "text": "result"}]},
            2,
        ),
        derived({"k": "model_call", "id": "mc1", "actor": "agent", "role": "agent", "scope": "att0",
                 "input": ["m0", "m1", "m2"], "status": "kept"}),
        observed(
            {"k": "message", "id": "m3", "scope": "att0", "role": "assistant", "actor": "agent", "generated_by": "mc1",
             "parts": [{"t": "text", "text": "done"}]},
            3,
        ),
    ]


def example_store() -> MemoryStore:
    return MemoryStore({ARTEFACT_SHA: ARTEFACT_BYTES})


def seal_record(
    records: list[dict[str, Any]],
    issues: list[dict[str, Any]] | None = None,
    registry: RuleRegistry | None = None,
) -> dict[str, Any]:
    """A correct seal for ``records`` (header first): digest, count, recomputed accounting and mirrored issues."""
    from agentprov.aer.accounting import compute, mirror_issues
    from agentprov.aer.canon import dumps_line

    given = [dict(i) for i in (issues or [])]
    accounting = compute(records[1:], given)
    keys = {(i["code"], i["rule"], tuple(i["ids"])) for i in given}
    for mirror in mirror_issues(accounting):
        if (mirror["code"], mirror["rule"], tuple(mirror["ids"])) not in keys:
            given.append(dict(mirror))
    body = b"".join(dumps_line(r) for r in records)
    seal: dict[str, Any] = {
        "k": "seal",
        "id": "seal",
        "n_records": len(records) + 1,
        "records_sha256": hashlib.sha256(body).hexdigest(),
        "accounting": accounting.to_json(),
        "issues": given,
    }
    blobs = sorted(
        {m["$blob"] for r in records for m in _walk_blobs(r)}
    )
    if blobs:
        seal["blobs"] = blobs
    return seal


def _walk_blobs(value: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if isinstance(value, dict) and set(value) == {"$lit"} and isinstance(value["$lit"], dict):
        for v in value["$lit"].values():  # C.11.3: the body's member names are literal, never a $blob ref
            out.extend(_walk_blobs(v))
    elif isinstance(value, dict):
        if "$blob" in value:
            out.append(value)
        else:
            for v in value.values():
                out.extend(_walk_blobs(v))
    elif isinstance(value, list):
        for v in value:
            out.extend(_walk_blobs(v))
    return out


def validate_example(
    records: list[dict[str, Any]],
    *,
    mode: str = "release",
    with_store: bool = True,
    issues: list[dict[str, Any]] | None = None,
    seal: bool = True,
) -> ValidationReport:
    """Validate ``records`` (header first) with a freshly computed seal appended unless ``seal=False``."""
    registry = make_registry()
    full = [*records, seal_record(records, issues)] if seal else list(records)
    return validate_records(
        full, store=example_store() if with_store else None, catalogues=registry, mode=mode  # type: ignore[arg-type]
    )


def codes_of(report: ValidationReport, *, errors_only: bool = True) -> list[str]:
    return [f.code for f in (report.errors if errors_only else report.findings)]


def edit(records: list[dict[str, Any]], record_id: str, **changes: Any) -> list[dict[str, Any]]:
    """A deep copy of ``records`` with ``changes`` applied to the record ``record_id`` (``None`` deletes a member)."""
    out = copy.deepcopy(records)
    for rec in out:
        if rec["id"] == record_id:
            for key, value in changes.items():
                if value is None:
                    rec.pop(key, None)
                else:
                    rec[key] = value
            return out
    raise KeyError(record_id)


def insert_after(records: list[dict[str, Any]], record_id: str, new: dict[str, Any]) -> list[dict[str, Any]]:
    out = copy.deepcopy(records)
    index = next(i for i, r in enumerate(out) if r["id"] == record_id)
    out.insert(index + 1, copy.deepcopy(new))
    return out


def structural_templates() -> list[dict[str, Any]]:
    """Structurally valid records covering all 13 kinds (vectors, the example and hand-made optional-field cases)."""
    out: list[dict[str, Any]] = []
    for name in VECTOR_NAMES:
        out.extend(vector_records(name))
    out.extend(example_records())
    header = copy.deepcopy(example_records()[0])
    header.update(
        {
            "mode": "live",
            "capture": {"session": "0190a6e0-1d5c-7a3b-8c4d-123456789abc", "log": "a0", "attempt": 0},
            "instrumentation": [
                {"id": "tst.native@1", "kind": "behaviour_preserving", "recorded": "full", "params": {"n": [1, {"$lit": {"$x": 1}}]},
                 "code_ref": {"repo": "r", "commit": "a" * 40, "path": "p", "lines": "1-3"}}
            ],
            "related": [{"rel": "replays", "ex": "ex_aaaaaaaaaaaaaaaaaaaaaaaaaa", "id": "m0"}],
            "ext": {"lex": {"ord": {"/task": ["task_id", "benchmark"]}, "flt": ["/task/x"]}, "tst": {"a": 1}},
        }
    )
    header["artifacts"][0]["origin"] = {"kind": "member", "container": "0" * 64, "label": "m.json", "method": 93, "crc32": "0a0b0c0d", "size": 1}
    out.append(header)
    out.extend(
        [
            {"k": "state_change", "id": "st0", "ev": "D", "rule": ["tst.d@1"], "scope": "att0", "cause": "te0", "target": "agent_store",
             "canon": "jcs-rfc8785", "before_sha256": "a" * 64, "after_sha256": "b" * 64, "changed": True,
             "patch": [{"op": "add", "path": "/a", "value": {"$int": str(2**60)}}, {"op": "move", "path": "/b", "from": "/a"}],
             "diff": {"format": "f", "value": [1], "truncated": False}, "snapshot_before": {"$blob": "sha256:" + "a" * 64, "bytes": 1},
             "t": {"start": "2026-10-08T12:00:00Z", "dur_s": 1.5, "dur_clock": "wall", "raw": {"dur": "1.5"}}},
            {"k": "fixture", "id": "fx0", "ev": "D", "rule": ["tst.d@1"], "kind": "other", "subtype": "tst.sub", "vector": "v",
             "content": {"$utf16": "AGE="}, "media": "text/plain", "actor": "agent"},
            {"k": "decision", "id": "dc0", "ev": "I", "rule": ["tst.i@1"], "actor": "agent", "scope": "att0", "subject": "m1#1",
             "verdict": "modify", "reason": "r", "original": {"$blob": "sha256:" + "c" * 64, "bytes": 2}},
            {"k": "decision", "id": "dc1", "ev": "I", "rule": ["tst.i@1"], "actor": "agent", "subject": "te0", "verdict": "redact",
             "original": "m1#0", "unk": {"/reason": "not_recorded"}},
            {"k": "judgement", "id": "j0", "ev": "D", "rule": ["tst.d@1"], "actor": "env", "subject": "run", "name": "u", "value": {"x": [1.5, None]},
             "origin": "recomputed", "revises": "j1", "generated_by": "mc1", "inputs": ["m1", "m2#0"], "t": {"end_naive": "2026-10-08T12:00:00"}},
            {"k": "activity", "id": "ac0", "ev": "D", "rule": ["tst.d@1"], "type": "tst:plan", "actor": "agent", "scope": "att0",
             "inputs": ["m0", "af0"], "t": {"start": "2026-10-08T12:00:00Z"}, "status": "aborted", "label": "l"},
            {"k": "artefact", "id": "af0", "ev": "D", "rule": ["tst.d@1"], "type": "tst:note", "content_ref": {"$blob": "sha256:" + "a" * 64, "bytes": 3},
             "sha256": "a" * 64, "media": "image/png", "generated_by": "ac0"},
            {"k": "artefact", "id": "af1", "ev": "D", "rule": ["tst.d@1"], "type": "tst:note", "unk": {"/content": "withheld"}},
            {"k": "tool_execution", "id": "te9", "ev": "D", "rule": ["tst.d@1"], "actor": "env", "scope": "att0", "requested_by": "agent",
             "authorised_by": "dc0", "name": "f", "args": {"a": 1}, "args_effective": {"a": 1.5}, "status": "error",
             "exception": {"type": "E", "message": "m"}, "returned": [1, 2], "t": {"mono_start_ns": 1, "mono_end_ns": 2}},
            {"k": "model_call", "id": "mc9", "ev": "O", "by": "capture", "src": [{"blob": "sha256:" + "a" * 64, "p": "/x"}], "actor": "agent",
             "role": "auxiliary", "scope": "att0", "input": ["m0", {"id": "m1", "sent": ["formatting", "truncation"], "sent_sha256": "a" * 64}],
             "tools": "fx0", "params": {"configured": {"t": 0.5}, "transmitted": {}}, "status": "cached", "reason": "r", "retry_of": "mc0",
             "finish_reason": "stop", "usage": {"input_tokens": 3, "calls": 1}, "served_model": "m", "response_id": "r",
             "request": {"$blob": "sha256:" + "a" * 64, "bytes": 1, "media": "x"}, "response": {"$blob": "sha256:" + "b" * 64, "bytes": 1},
             "t": {"start": "2026-10-08T12:00:00.5Z", "end": "2026-10-08T12:00:01Z"}},
            {"k": "scope", "id": "sc1", "ev": "D", "rule": ["tst.d@1"], "kind": "subagent", "parent": "run", "actor": "agent", "index": 3,
             "scored": False, "spawned_by": "te0", "status": "limit", "usage": {"input_tokens": 1}},
            {"k": "actor", "id": "act2", "ev": "D", "rule": ["tst.d@1"], "kind": "judge", "name": "n", "role": "r", "model": {"requested": "m", "endpoint": "h"},
             "params": {"t": 1}, "version": "v", "code": {"dist": "d", "wheel_sha256": "a" * 64}, "on_behalf_of": "agent"},
            {"k": "message", "id": "m9", "ev": "O", "by": "source", "src": [{"a": "a0", "bytes": [0, 5], "p": "/x"}, {"a": "a0", "line": 2}, {"a": "a0", "o": "/url"}, {"a": "a0"}],
             "scope": "att0", "role": "x", "parts": [
                 {"t": "reasoning", "text": None, "signature": "s", "redacted": True, "provider_id": "p"},
                 {"t": "tool_result", "responds_to": "m1#1", "value": None},
                 {"t": "tool_result", "text": None, "error": None, "name": "n"},
                 {"t": "other", "type": "t", "value": None},
             ], "after": [{"id": "m0", "b": "pos"}]},
        ]
    )
    return out
