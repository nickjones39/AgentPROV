"""Builds ``src/agentprov/schemas/capture-0.1.schema.json`` (the published JSON Schema of one capture/0.1 event).

The schema is written from the envelope table of C.13.2 and the event table of C.13.3. Shared shapes (JSON values,
``$``-objects, blob references, ``lex`` hints, usage, the merged instrumentation item and ``Task``, as ``cell``) are taken from the
AER schema builder so that the two published schemas cannot drift apart. ``python
tests/unit/capture/capture_schema_builder.py`` rewrites the committed file; ``test_capture_schema.py`` fails when the
committed file differs from this output.

Structural only, like the AER schema: the hash chain (``prev``), consecutive ``seq``, ``n_events``, the first/second
event order, actor tags declared in ``session.start`` and blob existence need the whole log and are the verifier's job
(``agentprov_capture``, phase 8). Every ``data`` object is closed (C.13.3: adapter extras only via ``note``).

Resolutions of under-specified C.13.3 cells (recorded in C.13.9):
- ``identity.harness`` has the shape of ``identity.benchmark`` minus the benchmark-only members: ``{dist, version,
  repo?, commit?, wheel_sha256?}``;
- ``redactions`` (C.13.5) may appear in the ``data`` of every event type, not only ``llm.request``;
- ``fixture.kind``, ``decision.verdict`` and ``outcome.judgements[].origin`` use the AER enums, including the
  ``other`` + ``subtype`` escape where AER has one;
- ``env.diff`` is a JSON value or a blob reference; ``canon`` names the canonicalisation (``jcs-rfc8785``).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_AER_DIR = Path(__file__).resolve().parents[1] / "aer"
if str(_AER_DIR) not in sys.path:
    sys.path.insert(0, str(_AER_DIR))

import schema_builder as aer  # noqa: E402  (the AER builder; shared shapes)

from agentprov.aer import types as T  # noqa: E402

OUT = Path(__file__).resolve().parents[3] / "src" / "agentprov" / "schemas" / "capture-0.1.schema.json"

Schema = dict[str, Any]
obj, ref, enum, pat, array, integer = aer.obj, aer.ref, aer.enum, aer.pat, aer.array, aer.integer
STR, BOOL, NULL, STR_OR_NULL, NONEMPTY = aer.STR, aer.BOOL, aer.NULL, aer.STR_OR_NULL, aer.NONEMPTY


def rx(pattern: str) -> Schema:
    return {"type": "string", "pattern": "^(?:" + pattern + ")$(?!\\n)"}


TS = rx(r"[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])T(?:[01][0-9]|2[0-3]):[0-5][0-9]:(?:[0-5][0-9]|60)"
        r"\.[0-9]{6}Z")
CALL = rx(r"c(?:0|[1-9][0-9]*)")
OCC = rx(r"o(?:0|[1-9][0-9]*)")
HEX64 = pat("hex64")
NAT = integer(0)

EVENT_TYPES = (
    "session.start",
    "instrumentation",
    "identity",
    "fixture",
    "pass.start",
    "llm.request",
    "llm.response",
    "tool.dispatch",
    "tool.result",
    "decision",
    "state",
    "pass.end",
    "outcome",
    "native.log",
    "note",
    "error",
    "session.end",
)


def data(props: dict[str, Schema], required: list[str] = (), **kw: Any) -> Schema:  # type: ignore[assignment]
    """A closed ``data`` object; every type may carry ``redactions`` (C.13.5)."""
    return obj({**props, "redactions": ref("redactions")}, required, **kw)


def defs() -> dict[str, Schema]:
    shared = aer.defs()
    d: dict[str, Schema] = {k: shared[k] for k in ("json", "jsonObject", "reservedObject", "blobRef", "lex", "usage")}
    exec_props = aer.build()["$defs"]["record_execution"]["properties"]
    d["instrumentationItem"] = exec_props["instrumentation"]["items"]
    task = exec_props["task"]
    # ``cell`` is Task-shaped plus ``attack_params`` (C.13.3): Task's members and requirements, one extra member.
    d["cell"] = obj({**task["properties"], "attack_params": ref("jsonObject")}, required=task["required"])
    d["exception"] = obj({"type": STR, "message": STR}, required=["type", "message"])
    d["redactions"] = array(
        {
            "type": "object",
            "properties": {"blob": aer.pat("digest"), "field": STR, "p": aer.pat("pointer_any"),
                           "rule": rx(r"cap\.secret\.[a-z][a-z0-9_]*@[1-9][0-9]*")},
            "additionalProperties": False,
            "required": ["p", "rule"],
            "oneOf": [{"required": ["blob"]}, {"required": ["field"]}],
        },
        minItems=1,
    )
    d["env"] = obj({"sha256": HEX64, "canon": NONEMPTY, "snapshot": ref("blobRef"),
                    "diff": {"anyOf": [ref("blobRef"), ref("json")]}}, required=["sha256", "canon"])
    d["envEnd"] = obj({"sha256": HEX64, "canon": NONEMPTY, "snapshot": ref("blobRef"), "changed": BOOL,
                       "diff": {"anyOf": [ref("blobRef"), ref("json")]}}, required=["sha256", "canon", "changed"])
    d["at"] = obj({"message": NAT, "call": NAT}, required=["message", "call"])
    d["actorDecl"] = obj(
        {"kind": enum(T.ACTOR_KINDS), "name": STR, "role": STR, "model": ref("model")}, required=["kind"]
    )
    d["model"] = shared["model"]
    return d


def event_data() -> dict[str, Schema]:
    v: dict[str, Schema] = {}
    v["session.start"] = data(
        {
            "capture": {"const": "0.1"},
            "session": pat("uuid7"),
            "ex": pat("ex"),
            "attempt": NAT,
            "cell": ref("cell"),
            "writer": obj({"dist": NONEMPTY, "version": NONEMPTY}, required=["dist", "version"]),
            "backend": obj({"id": NONEMPTY, "version": NONEMPTY}, required=["id", "version"]),
            "runtime": obj({"python": NONEMPTY, "platform": NONEMPTY, "lock_sha256": HEX64},
                           required=["python", "platform", "lock_sha256"]),
            "actors": {"type": "object", "minProperties": 1, "propertyNames": pat("local_id"),
                       "additionalProperties": ref("actorDecl")},
            "config_sha256": HEX64,
        },
        required=["capture", "session", "ex", "attempt", "cell", "writer", "backend", "runtime", "actors",
                  "config_sha256"],
    )
    v["instrumentation"] = data({"items": array(ref("instrumentationItem"))}, required=["items"])
    v["identity"] = data(
        {
            "benchmark": obj(
                {"name": NONEMPTY, "dist": NONEMPTY, "dist_version": NONEMPTY, "repo": STR, "commit": pat("hex40"),
                 "wheel_sha256": HEX64, "suite_set": STR, "tool_definitions_sha256": HEX64,
                 "system_prompt_sha256": HEX64},
                required=["name", "dist", "dist_version"],
            ),
            "harness": obj({"dist": NONEMPTY, "version": NONEMPTY, "repo": STR, "commit": pat("hex40"),
                            "wheel_sha256": HEX64}, required=["dist", "version"]),
            "agent": obj(
                {"model_requested": NONEMPTY, "provider": NONEMPTY, "endpoint_host": NONEMPTY,
                 "sdk": obj({"name": NONEMPTY, "version": NONEMPTY}, required=["name", "version"])},
                required=["model_requested", "provider", "endpoint_host", "sdk"],
            ),
        },
        required=["benchmark", "harness", "agent"],
    )
    v["fixture"] = data(
        {"kind": enum(T.FIXTURE_KINDS), "subtype": NONEMPTY, "vector": STR, "content": ref("json")},
        required=["kind", "content"],
        **aer.subtype_iff_other("kind"),
    )
    v["pass.start"] = data({"env": ref("env")}, required=["env"])
    v["llm.request"] = data(
        {
            "call": CALL,
            "role": enum(T.MODEL_CALL_ROLES),
            "attempt": NAT,
            "retry_of": CALL,
            "endpoint": obj({"host": NONEMPTY, "path": STR}, required=["host", "path"]),
            "params": obj({"configured": ref("jsonObject"), "transmitted": ref("jsonObject")},
                          required=["configured", "transmitted"]),
            "input_at": array(NAT, uniqueItems=True),
            "n_messages": NAT,
            "request": ref("blobRef"),
        },
        required=["call", "role", "attempt", "endpoint", "params", "request"],
    )
    v["llm.response"] = data(
        {
            "call": CALL,
            "status": enum(T.MODEL_CALL_STATUS),
            "reason": STR,
            "http_status": integer(100),
            "response": ref("blobRef"),
            "usage": ref("usage"),
            "finish_reason": STR,
            "served_model": STR,
            "response_id": STR,
            "exception": ref("exception"),
        },
        required=["call", "status"],
    )
    v["tool.dispatch"] = data(
        {"occ": OCC, "at": ref("at"), "provider_call_id": STR_OR_NULL, "name": STR, "args": ref("json"),
         "args_raw": STR},
        required=["occ", "provider_call_id", "name", "args"],
    )
    v["tool.result"] = data(
        {
            "occ": OCC,
            "status": enum(T.TOOL_EXECUTION_STATUS | {"denied"}),
            "args_effective": ref("json"),
            "returned": ref("json"),
            "rendered": STR,
            "model_visible": STR,
            "error": STR_OR_NULL,
            "exception": ref("exception"),
            "decided_by": pat("local_id"),
        },
        required=["occ", "status", "rendered", "model_visible"],
        **{"if": {"properties": {"status": {"const": "denied"}}}, "then": {"required": ["decided_by"]},
           "else": {"not": {"required": ["decided_by"]}}},
    )
    v["decision"] = data(
        {
            "actor": pat("local_id"),
            "subject": {"oneOf": [obj({"occ": OCC}, required=["occ"]), obj({"at": ref("at")}, required=["at"]),
                                  obj({"call": CALL}, required=["call"])]},
            "verdict": enum(T.DECISION_VERDICTS),
            "subtype": NONEMPTY,
            "reason": STR,
            "original": ref("blobRef"),
            "replacement": ref("blobRef"),
        },
        required=["actor", "subject", "verdict"],
        **aer.subtype_iff_other("verdict"),
    )
    v["state"] = data({"occ": OCC, "env": ref("env")}, required=["env"])
    v["pass.end"] = data({"aborted": BOOL, "messages": ref("blobRef"), "env": ref("envEnd")},
                         required=["aborted", "messages", "env"])
    v["outcome"] = data(
        {
            "judgements": array(
                obj({"name": NONEMPTY, "value": ref("json"), "origin": enum(T.JUDGEMENT_ORIGINS)},
                    required=["name", "value", "origin"]),
                minItems=1,
            ),
            "declared_semantics": ref("json"),
        },
        required=["judgements"],
    )
    v["native.log"] = data({"path": NONEMPTY, "sha256": HEX64, "bytes": NAT}, required=["path", "sha256", "bytes"])
    v["note"] = data({"ns": pat("local_id"), "kind": NONEMPTY, "payload": ref("json")},
                     required=["ns", "kind", "payload"])
    v["error"] = data({"where": NONEMPTY, "exception": ref("exception"), "traceback": ref("blobRef"), "fatal": BOOL},
                      required=["where", "exception", "fatal"])
    v["session.end"] = data(
        {"status": enum({"complete", "incomplete", "errored", "aborted"}), "n_events": integer(1),
         "appended_by": enum({"worker", "parent"})},
        required=["status", "n_events", "appended_by"],
    )
    assert tuple(v) == EVENT_TYPES
    return v


def build() -> Schema:
    d = defs()
    per_type = event_data()
    for name, schema in per_type.items():
        d["data_" + name.replace(".", "_")] = schema
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://w3id.org/agentprov/schemas/capture-0.1.schema.json",
        "title": "capture/0.1 event",
        "description": "One line of a capture/0.1 raw event log (docs/architecture C.13): the JCS-serialised event "
        "envelope of C.13.2 and the closed per-type data of C.13.3. Structural only: the hash chain, consecutive "
        "seq, n_events and the event order are checked by the verifier, not by this schema. Generated by "
        "tests/unit/capture/capture_schema_builder.py.",
        "type": "object",
        "properties": {
            "seq": NAT,
            "type": enum(EVENT_TYPES),
            "ts": TS,
            "mono_ns": NAT,
            "pass": {"anyOf": [NAT, NULL]},
            "actor": {"anyOf": [pat("local_id"), NULL]},
            "prev": {"anyOf": [HEX64, NULL]},
            "data": {"type": "object"},
            "lex": ref("lex"),
        },
        "additionalProperties": False,
        "required": sorted(["seq", "type", "ts", "mono_ns", "pass", "actor", "prev", "data"]),
        "allOf": [
            {"if": {"properties": {"seq": {"const": 0}}}, "then": {"properties": {"prev": NULL}},
             "else": {"properties": {"prev": HEX64}}},
            *[
                {"if": {"properties": {"type": {"const": name}}, "required": ["type"]},
                 "then": {"properties": {"data": ref("data_" + name.replace(".", "_"))}}}
                for name in EVENT_TYPES
            ],
        ],
        "$defs": dict(sorted(d.items())),
    }


def render() -> str:
    return json.dumps(build(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


if __name__ == "__main__":  # pragma: no cover
    OUT.write_text(render(), encoding="utf-8", newline="\n")
    sys.stdout.write(f"wrote {OUT}\n")
