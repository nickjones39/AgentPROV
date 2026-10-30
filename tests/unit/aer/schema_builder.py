"""Builds ``src/agentprov/schemas/aer-0.1.schema.json`` (the published JSON Schema of one AER record).

The schema is written here, independently of the in-code structural checker (``agentprov.aer._structure``), from
the field tables of C.3 and the structural subset of C.17 named in its last paragraph; only the *regular
expressions* are shared with the code (``PATTERNS``), so the differential test compares two implementations of the
same grammar, not one grammar twice. ``python tests/unit/aer/schema_builder.py`` rewrites the committed file;
``test_schema_file.py`` fails when the committed file differs from this output.

Structural subset (C.17): AER-V04 to V07, V12 (the closed ``by`` list only), V16 (closed reasons), V18 (``$``-forms,
``ext.lex`` shape) and the structural parts of V26 and V30 to V33. Everything that needs context (backward
references, unknown/value conflicts, evidence obligations, sentinels, times, accounting, the seal digest) is the
validator's job, as is the number range of V18.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from agentprov.aer import types as T
from agentprov.aer._structure import PATTERNS

SCHEMAS = Path(__file__).resolve().parents[3] / "src" / "agentprov" / "schemas"
OUT = SCHEMAS / "aer-0.1.schema.json"
#: ``aer/0.2`` (D-210..D-212): the published schema of the version this build writes. ``aer-0.1.schema.json`` stays
#: byte-identical (frozen, D-14, D-163); ``render("0.2")`` writes the second file.
OUTS = {"0.1": OUT, "0.2": SCHEMAS / "aer-0.2.schema.json"}
_VERSION = ["0.1"]  # the version being rendered (render() sets it)
_Q = "[A-Za-z0-9+/]{4}"
#: #28, aer/0.2: base64 of an even byte count (whole UTF-16BE code units): an even number of quads, or a final quad of
#: two bytes (one "=") after an even number, or of one byte ("==") after an odd number. That the units are not a valid
#: scalar sequence (a valid string is written plain) is held by the in-code validator.
_UTF16_EVEN = {"type": "string", "pattern": (
    f"^(?:(?:{_Q}{_Q})*(?:[A-Za-z0-9+/]{{3}}=|{_Q}[A-Za-z0-9+/]{{2}}==)?)$(?!\\n)")}


def _withheld_required(*names: str) -> list[str]:
    """The required list of a part: in ``aer/0.2`` its content member may be withheld (D-211), a condition on the
    record's ``unk`` that this per-part schema cannot express, so the in-code validator holds it."""
    return [n for n in names if _VERSION[0] == "0.1" or n not in ("text", "args", "value")]
KINDS = (
    "execution",
    "actor",
    "scope",
    "message",
    "model_call",
    "tool_execution",
    "decision",
    "state_change",
    "fixture",
    "judgement",
    "activity",
    "artefact",
    "seal",
)

Schema = dict[str, Any]


def pat(name: str) -> Schema:
    # "(?!\n)" after "$" stops Python's "$" from matching before a trailing newline; harmless for ECMA regexes.
    return {"type": "string", "pattern": "^(?:" + PATTERNS[name] + ")$(?!\\n)"}


def enum(values: Any) -> Schema:
    return {"enum": sorted(values, key=lambda v: (isinstance(v, str), v))}


STR: Schema = {"type": "string"}
NONEMPTY: Schema = {"type": "string", "minLength": 1}
BOOL: Schema = {"type": "boolean"}
NULL: Schema = {"type": "null"}
STR_OR_NULL: Schema = {"anyOf": [STR, NULL]}


def integer(minimum: int | None = None) -> Schema:
    out: Schema = {"type": "integer"}
    if minimum is not None:
        out["minimum"] = minimum
    return out


def ref(name: str) -> Schema:
    return {"$ref": f"#/$defs/{name}"}


def array(items: Schema, **kw: Any) -> Schema:
    return {"type": "array", "items": items, **kw}


def obj(props: dict[str, Schema], required: list[str] = (), **kw: Any) -> Schema:  # type: ignore[assignment]
    out: Schema = {"type": "object", "properties": props, "additionalProperties": False}
    if required:
        out["required"] = sorted(required)
    out.update(kw)
    return out


def unk_declares(pointer: str, value: str | None = None) -> Schema:
    entry: Schema = {"required": [pointer]}
    if value is not None:
        entry["properties"] = {pointer: {"const": value}}
    return {"required": ["unk"], "properties": {"unk": entry}}


def present_or_unk(name: str) -> Schema:
    return {"anyOf": [{"required": [name]}, unk_declares("/" + name)]}


def subtype_iff_other(name: str) -> Schema:
    return {
        "if": {"required": [name], "properties": {name: {"const": "other"}}},
        "then": {"required": ["subtype"]},
        "else": {"not": {"required": ["subtype"]}},
    }


# ---------------------------------------------------------------------------------------------------- defs
def defs() -> dict[str, Schema]:
    d: dict[str, Schema] = {}
    d["json"] = {
        "anyOf": [
            NULL,
            BOOL,
            STR,
            {"type": "number"},
            array(ref("json")),
            {"type": "object", "propertyNames": {"pattern": "^(?!\\$)"}, "additionalProperties": ref("json")},
            ref("reservedObject"),
        ]
    }
    d["jsonObject"] = {"allOf": [{"type": "object"}, ref("json")]}
    d["blobRef"] = obj(
        {"$blob": pat("digest"), "bytes": integer(0), "media": STR}, required=["$blob", "bytes"]
    )
    d["reservedObject"] = {
        "anyOf": [
            obj({"$int": pat("int_decimal")}, required=["$int"]),
            obj({"$float": enum(["NaN", "Infinity", "-Infinity", "-0"])}, required=["$float"]),
            obj({"$utf16": pat("base64") if _VERSION[0] == "0.1" else _UTF16_EVEN}, required=["$utf16"]),
            obj(
                {"$lit": {"type": "object", "additionalProperties": ref("json")} if _VERSION[0] == "0.1" else {
                    # #28, aer/0.2: $lit wraps an object with at least one member name beginning with "$"
                    "type": "object", "additionalProperties": ref("json"),
                    "not": {"propertyNames": {"not": {"pattern": "^\\$"}}}}},
                required=["$lit"],
            ),
            ref("blobRef"),
        ]
    }
    d["time"] = obj(
        {
            "start": pat("time"),
            "end": pat("time"),
            "start_naive": pat("time_naive"),
            "end_naive": pat("time_naive"),
            "dur_s": {"type": "number", "minimum": 0},
            "dur_clock": enum(T.DUR_CLOCKS),
            "mono_start_ns": integer(0),
            "mono_end_ns": integer(0),
            "raw": obj({"start": STR, "end": STR, "dur": STR}),
        },
        dependentRequired={"dur_s": ["dur_clock"], "dur_clock": ["dur_s"]},
    )
    d["usage"] = obj(
        {
            n: integer(0)
            for n in (
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "reasoning_tokens",
                "cache_read_tokens",
                "cache_write_tokens",
                "calls",
            )
        }
    )
    d["model"] = obj({n: STR for n in ("requested", "served", "provider", "endpoint")})
    d["code"] = obj(
        {"dist": STR, "dist_version": STR, "repo": STR, "commit": STR, "wheel_sha256": pat("hex64")}
    )
    forms = [
        ["a"],
        ["a", "p"],
        ["a", "bytes"],
        ["a", "bytes", "p"],
        ["a", "line"],
        ["a", "line", "p"],
        ["a", "o"],
        ["blob"],
        ["blob", "p"],
    ]
    d["locator"] = obj(
        {
            "a": pat("artefact_id"),
            "p": pat("pointer_any"),
            "bytes": array(integer(0), minItems=2, maxItems=2),
            "line": integer(0),
            "o": pat("pointer_any"),
            "blob": pat("digest"),
        },
        anyOf=[{"required": sorted(f), "propertyNames": enum(f)} for f in forms],
    )
    d["lex"] = obj(
        {
            "ord": {
                "type": "object",
                "propertyNames": {"pattern": "^(?:" + PATTERNS["pointer"] + ")$(?!\\n)"},
                "additionalProperties": array(STR, minItems=2),
                "minProperties": 1,
            },
            "flt": array(pat("pointer"), minItems=1, uniqueItems=True),
        },
        minProperties=1,
    )
    d["ext"] = {
        "type": "object",
        "propertyNames": pat("prefix"),
        "properties": {"lex": ref("lex")},
        "additionalProperties": ref("jsonObject"),
    }
    d["partText"] = obj({"t": {"const": "text"}, "text": STR_OR_NULL}, required=_withheld_required("t", "text"))
    d["partReasoning"] = obj(
        {"t": {"const": "reasoning"}, "text": STR_OR_NULL, "signature": STR, "redacted": BOOL, "provider_id": STR},
        required=_withheld_required("t", "text"),
    )
    d["partToolCall"] = obj(
        {
            "t": {"const": "tool_call"},
            "name": STR,
            "args": ref("json"),
            "args_raw": STR,
            "provider_call_id": STR_OR_NULL,
        },
        required=_withheld_required("t", "name", "args"),
    )
    d["partToolResult"] = obj(
        {
            "t": {"const": "tool_result"},
            "responds_to": pat("part_id"),
            "text": STR_OR_NULL,
            "value": ref("json"),
            "error": STR_OR_NULL,
            "name": STR,
        },
        required=["t"],
        oneOf=[
            {"required": ["text"], "not": {"required": ["value"]}},
            {"required": ["value"], "not": {"required": ["text"]}},
        ],
    )
    d["partBlob"] = obj({"t": {"const": "blob"}, "data": ref("blobRef"), "media": STR}, required=["t", "data", "media"])
    d["partFile"] = obj({"t": {"const": "file"}, "name": STR, "media": STR, "ref": STR}, required=["t", "ref"])
    d["partUri"] = obj({"t": {"const": "uri"}, "uri": STR, "media": STR}, required=["t", "uri"])
    d["partRefusal"] = obj({"t": {"const": "refusal"}, "text": STR}, required=_withheld_required("t", "text"))
    d["partOther"] = obj({"t": {"const": "other"}, "type": STR, "value": ref("json")},
                         required=_withheld_required("t", "type", "value"))
    names = {
        "text": "partText",
        "reasoning": "partReasoning",
        "tool_call": "partToolCall",
        "tool_result": "partToolResult",
        "blob": "partBlob",
        "file": "partFile",
        "uri": "partUri",
        "refusal": "partRefusal",
        "other": "partOther",
    }
    d["part"] = {
        "type": "object",
        "required": ["t"],
        "properties": {"t": enum(names)},
        "allOf": [
            {"if": {"properties": {"t": {"const": t}}, "required": ["t"]}, "then": ref(n)} for t, n in names.items()
        ],
    }
    d["artefactDescriptor"] = obj(
        {
            "id": pat("artefact_id"),
            "role": enum(T.ARTEFACT_ROLES),
            "prov_primary": enum(T.PROV_PRIMARY),
            "sha256": pat("hex64"),
            "bytes": integer(0),
            "media": STR,
            "origin": ref("origin"),
        },
        required=["id", "role", "prov_primary", "sha256", "bytes", "media", "origin"],
    )
    origins: dict[str, Schema] = {
        "git": obj(
            {
                "kind": {"const": "git"},
                "repo": STR,
                "commit": pat("hex40"),
                "path": STR,
                "blob_sha1": pat("hex40"),
                "introduced_in_commit": pat("hex40"),
            },
            required=["kind", "repo", "commit", "path", "blob_sha1"],
        ),
        "hf": obj({"kind": {"const": "hf"}, "repo": STR, "revision": STR, "path": STR}, required=["kind", "repo", "revision", "path"]),
        "zenodo": obj({"kind": {"const": "zenodo"}, "doi": STR, "file": STR}, required=["kind", "doi", "file"]),
        "url": obj({"kind": {"const": "url"}, "url": STR, "retrieved": pat("date")}, required=["kind", "url", "retrieved"]),
        "corpus": obj(
            {
                "kind": {"const": "corpus"},
                "corpus": STR,
                "version": STR,
                "producer_commit": pat("hex40"),
                "path": STR,
            },
            required=["kind", "corpus", "version", "path"],
        ),
        "capture": obj({"kind": {"const": "capture"}, "session": pat("uuid7")}, required=["kind", "session"]),
        "member": obj(
            {
                "kind": {"const": "member"},
                "container": pat("hex64"),
                "label": STR,
                "method": {"enum": [0, 8, 93]},
                "crc32": pat("crc32"),
                "size": integer(0),
            },
            required=["kind", "container", "label", "method", "crc32", "size"],
        ),
        "local": obj({"kind": {"const": "local"}, "path": STR}, required=["kind", "path"]),
    }
    d["origin"] = {
        "type": "object",
        "required": ["kind"],
        "properties": {"kind": enum(origins)},
        "allOf": [
            {"if": {"properties": {"kind": {"const": k}}, "required": ["kind"]}, "then": sub} for k, sub in origins.items()
        ],
    }
    d["issue"] = obj(
        {
            "code": {"anyOf": [enum(T.CORE_ISSUE_CODES), pat("subtype")]},
            "ids": array(pat("ref")),
            "rule": pat("rule_ref"),
            "detail": STR,
        },
        required=["code", "ids", "rule"],
    )
    d["checkEntry"] = obj(
        {
            "id": pat("rule_id"),
            "scope": pat("local_id"),
            "verdict": enum(T.ACCOUNTING_VERDICTS),
            "reason": STR,
            "observed": {
                "type": "object",
                "propertyNames": pat("namespace"),
                "additionalProperties": integer(0),
            },
        },
        required=["id", "scope", "verdict", "observed"],
    )
    return d


ENVELOPE_FIELDS = ("ev", "by", "evf", "rule", "src", "unk", "after", "ext")


def envelope(kind: str, *, after: bool = True, record_id: Schema | None = None) -> dict[str, Schema]:
    env: dict[str, Schema] = {
        "k": {"const": kind},
        "id": record_id or pat("record_id"),
        "ev": enum(["O", "D", "I"]),
        "by": enum(T.PARTIES),
        "evf": {"type": "object", "propertyNames": pat("pointer"), "additionalProperties": pat("tag")},
        "rule": array(pat("rule_ref")),
        "src": array(ref("locator")),
        "unk": {
            "type": "object",
            "propertyNames": pat("pointer"),
            "additionalProperties": enum(T.UNKNOWN_REASON_SET),
        },
        "after": array(obj({"id": pat("ref"), "b": enum(T.AFTER_BASES)}, required=["id", "b"])),
        "ext": ref("ext"),
    }
    if not after:
        del env["after"]
    return env


def kind_schema(
    kind: str,
    props: dict[str, Schema],
    required: list[str],
    *,
    all_of: list[Schema] = (),  # type: ignore[assignment]
    after: bool = True,
    record_id: Schema | None = None,
) -> Schema:
    out = obj({**envelope(kind, after=after, record_id=record_id), **props}, required=["k", "id", "ev", *required])
    if all_of:
        out["allOf"] = list(all_of)
    return out


def kinds() -> dict[str, Schema]:
    local, refid = pat("local_id"), pat("ref")
    out: dict[str, Schema] = {}
    out["execution"] = kind_schema(
        "execution",
        {
            "aer": {"const": _VERSION[0]},
            "ex": pat("ex"),
            "mode": enum(T.MODES),
            "unit": enum(T.UNITS),
            "source_key": obj(
                {
                    "sha256": pat("hex64"),
                    "loc": obj(
                        {
                            "p": pat("pointer_any"),
                            "line": integer(0),
                            "bytes": array(integer(0), minItems=2),
                        }
                    ),
                },
                required=["sha256", "loc"],
            ),
            "artifacts": array(ref("artefactDescriptor"), minItems=1),
            "adapter": obj({"id": pat("dotted"), "version": pat("semver")}, required=["id", "version"]),
            "dialect": obj({"id": pat("dotted"), "variant": NONEMPTY}, required=["id", "variant"]),
            "profile": obj(
                {"id": pat("profile_id"), "version": integer(1), "sha256": pat("hex64")},
                required=["id", "version", "sha256"],
            ),
            "rules": {"type": "object", "propertyNames": pat("namespace"), "additionalProperties": integer(1)},
            "ns": {"type": "object", "propertyNames": pat("prefix"), "additionalProperties": NONEMPTY},
            "canon": {"const": "jcs-rfc8785"},
            "hash": {"const": "sha256"},
            "capture": obj(
                {"session": pat("uuid7"), "log": pat("artefact_id"), "attempt": integer(0)},
                required=["session", "log", "attempt"],
            ),
            "related": array(
                obj({"rel": enum(T.RELATIONS), "ex": pat("ex"), "id": local}, required=["rel", "ex"])
            ),
            "task": obj(
                {
                    "benchmark": STR,
                    "suite": STR,
                    "environment": STR,
                    "task_id": STR,
                    "attack_id": STR_OR_NULL,
                    "attack_target_id": STR_OR_NULL,
                    "defense_id": STR_OR_NULL,
                },
                required=["benchmark", "task_id"] if _VERSION[0] == "0.1" else ["benchmark"],  # D-219: in-code
            ),
            "instrumentation": array(
                obj(
                    {
                        "id": pat("rule_id"),
                        "kind": enum(T.INSTRUMENTATION_KINDS),
                        "recorded": enum(T.INSTRUMENTATION_RECORDED),
                        "params": ref("json"),
                        "detail": STR,
                        "code_ref": obj(
                            {"repo": STR, "commit": pat("hex40"), "path": STR, "lines": STR},
                            required=["repo", "commit", "path"],
                        ),
                    },
                    required=["id", "kind", "recorded"],
                )
            ),
        },
        [
            "aer", "ex", "mode", "unit", "source_key", "artifacts", "adapter", "dialect", "profile", "rules",
            "ns", "canon", "hash", "task",
        ],
        all_of=[
            {
                "if": {"required": ["mode"], "properties": {"mode": {"const": "live"}}},
                "then": {"required": ["capture", "instrumentation"]},
            }
            if _VERSION[0] == "0.1" else {
                "if": {"required": ["mode"], "properties": {"mode": {"const": "live"}}},
                "then": {"required": ["capture"]},
            },
            *([] if _VERSION[0] == "0.1" else [{  # D-210: a live header cut before the instrumentation event
                "if": {
                    "required": ["mode"], "properties": {"mode": {"const": "live"}},
                    "not": {"required": ["unk"], "properties": {"unk": {
                        "required": ["/instrumentation"], "properties": {"/instrumentation": {"const": "not_captured"}}}}},
                },
                "then": {"required": ["instrumentation"]},
            }, {  # D-219 (#31 residual): a task without task_id declares it not_captured (the file's shape is in code)
                "if": {
                    "required": ["task"],
                    "not": {"required": ["unk"], "properties": {"unk": {
                        "required": ["/task/task_id"], "properties": {"/task/task_id": {"const": "not_captured"}}}}},
                },
                "then": {"properties": {"task": {"required": ["task_id"]}}},
            }]),
            {
                "if": {"required": ["mode"], "properties": {"mode": {"const": "import"}}},
                "then": {"not": {"required": ["capture"]}},
            },
        ],
        after=False,
        record_id={"const": "exec"},
    )
    out["actor"] = kind_schema(
        "actor",
        {
            "kind": enum(T.ACTOR_KINDS),
            "subtype": pat("subtype"),
            "name": STR,
            "role": STR,
            "model": ref("model"),
            "params": ref("json"),
            "version": STR,
            "code": ref("code"),
            "on_behalf_of": local,
        },
        [],
        all_of=[present_or_unk("kind"), subtype_iff_other("kind")],
        after=False,
    )
    out["scope"] = kind_schema(
        "scope",
        {
            "kind": enum(T.SCOPE_KINDS),
            "subtype": pat("subtype"),
            "parent": local,
            "actor": local,
            "index": integer(0),
            "scored": BOOL,
            "spawned_by": local,
            "t": ref("time"),
            "status": enum(T.SCOPE_STATUS),
            "usage": ref("usage"),
        },
        ["kind"],
        all_of=[
            subtype_iff_other("kind"),
            {
                "if": {"properties": {"kind": {"const": "run"}}},
                "then": {"properties": {"id": {"const": "run"}}, "not": {"required": ["parent"]}},
                "else": {"properties": {"id": {"not": {"const": "run"}}}, "required": ["parent"]},
            },
        ],
    )
    out["message"] = kind_schema(
        "message",
        {"scope": local, "role": STR, "actor": local, "parts": array(ref("part")), "generated_by": local},
        ["scope", "role", "parts"],
    )
    out["model_call"] = kind_schema(
        "model_call",
        {
            "actor": local,
            "role": enum(T.MODEL_CALL_ROLES),
            "scope": local,
            "input": array(
                {
                    "anyOf": [
                        local,
                        obj(
                            {
                                "id": local,
                                "sent": array(enum(T.SENT_TRANSFORMS), minItems=1),
                                "sent_sha256": pat("hex64"),
                            },
                            required=["id", "sent"],
                        ),
                    ]
                }
            ),
            "tools": local,
            "params": obj({"configured": ref("json"), "transmitted": ref("json")}),
            "status": enum(T.MODEL_CALL_STATUS),
            "reason": STR,
            "retry_of": local,
            "finish_reason": STR,
            "usage": ref("usage"),
            "served_model": STR,
            "response_id": STR,
            "request": ref("blobRef"),
            "response": ref("blobRef"),
            "t": ref("time"),
        },
        ["actor", "role", "scope"],
        all_of=[present_or_unk("status")],
    )
    call_unset = {"not": unk_declares("/call", "ambiguous")}
    out["tool_execution"] = kind_schema(
        "tool_execution",
        {
            "actor": local,
            "scope": local,
            "call": pat("part_id"),
            "requested_by": local,
            "authorised_by": local,
            "name": STR,
            "args": ref("json"),
            "args_effective": ref("json"),
            "status": enum(T.TOOL_EXECUTION_STATUS),
            "exception": obj({"type": STR, "message": STR}, required=["type", "message"]),
            "returned": ref("json"),
            "t": ref("time"),
        },
        ["actor", "scope", "name"],
        all_of=[
            present_or_unk("status"),
            {
                "oneOf": [
                    {"required": ["call"], "allOf": [{"not": {"required": ["requested_by"]}}, call_unset]},
                    {"required": ["requested_by"], "allOf": [{"not": {"required": ["call"]}}, call_unset]},
                    {
                        "allOf": [
                            {"not": {"required": ["call"]}},
                            {"not": {"required": ["requested_by"]}},
                            unk_declares("/call", "ambiguous"),
                        ]
                    },
                ]
            },
        ],
    )
    out["decision"] = kind_schema(
        "decision",
        {
            "actor": local,
            "scope": local,
            "subject": refid,
            "verdict": enum(T.DECISION_VERDICTS),
            "subtype": pat("subtype"),
            "reason": STR,
            "original": {"anyOf": [ref("blobRef"), pat("part_id")]},
            "t": ref("time"),
        },
        ["actor", "subject"],
        all_of=[present_or_unk("verdict"), subtype_iff_other("verdict")],
    )
    out["state_change"] = kind_schema(
        "state_change",
        {
            "scope": local,
            "cause": local,
            "target": enum(T.STATE_TARGETS),
            "subtype": pat("subtype"),
            "canon": STR,
            "before_sha256": pat("hex64"),
            "after_sha256": pat("hex64"),
            "changed": BOOL,
            "patch": array(
                {
                    "type": "object",
                    "required": ["op", "path"],
                    "properties": {
                        "op": enum(T.JSON_PATCH_OPS),
                        "path": pat("pointer_any"),
                    },
                    "additionalProperties": ref("json"),
                }
            ),
            "diff": obj(
                {"format": STR, "value": ref("json"), "truncated": BOOL}, required=["format", "value", "truncated"]
            ),
            "snapshot_before": ref("blobRef"),
            "snapshot_after": ref("blobRef"),
            "t": ref("time"),
        },
        ["scope", "target"],
        all_of=[
            subtype_iff_other("target"),
            {
                "if": {"anyOf": [{"required": ["before_sha256"]}, {"required": ["after_sha256"]}]},
                "then": {"required": ["canon"]},
            },
        ],
    )
    out["fixture"] = kind_schema(
        "fixture",
        {
            "kind": enum(T.FIXTURE_KINDS),
            "subtype": pat("subtype"),
            "vector": STR,
            "content": ref("json"),
            "media": STR,
            "actor": local,
        },
        ["kind"],
        all_of=[present_or_unk("content"), subtype_iff_other("kind")],
    )
    out["judgement"] = kind_schema(
        "judgement",
        {
            "actor": local,
            "subject": refid,
            "name": STR,
            "value": ref("json"),
            "origin": enum(T.JUDGEMENT_ORIGINS),
            "revises": local,
            "generated_by": local,
            "inputs": array(refid),
            "t": ref("time"),
        },
        ["actor", "subject", "name", "value"],
        all_of=[present_or_unk("origin")],
    )
    out["activity"] = kind_schema(
        "activity",
        {
            "type": pat("type"),
            "actor": local,
            "scope": local,
            "inputs": array(refid),
            "t": ref("time"),
            "status": enum(T.ACTIVITY_STATUS),
            "label": STR,
        },
        ["type", "scope"],
        record_id=pat("activity_id"),
    )
    out["artefact"] = kind_schema(
        "artefact",
        {
            "type": pat("type"),
            "content": ref("json"),
            "content_ref": ref("blobRef"),
            "sha256": pat("hex64"),
            "media": STR,
            "generated_by": local,
        },
        ["type"],
        all_of=[
            {
                "oneOf": [
                    {"required": ["content"], "not": {"anyOf": [{"required": ["content_ref"]}, {"required": ["unk"], "properties": {"unk": {"required": ["/content"]}}}]}},
                    {"required": ["content_ref"], "not": {"anyOf": [{"required": ["content"]}, {"required": ["unk"], "properties": {"unk": {"required": ["/content"]}}}]}},
                    {
                        "allOf": [
                            {"not": {"required": ["content"]}},
                            {"not": {"required": ["content_ref"]}},
                            {"required": ["unk"], "properties": {"unk": {"required": ["/content"]}}},
                        ]
                    },
                ]
            }
        ],
        record_id=pat("artefact_record_id"),
    )
    out["seal"] = obj(
        {
            "k": {"const": "seal"},
            "id": {"const": "seal"},
            "n_records": integer(2),
            "records_sha256": pat("hex64"),
            "accounting": obj(
                {"status": enum(T.ACCOUNTING_VERDICTS), "checks": array(ref("checkEntry"))},
                required=["status", "checks"],
            ),
            "issues": array(ref("issue")),
            "blobs": array(pat("digest"), uniqueItems=True),
        },
        required=["k", "id", "n_records", "records_sha256", "accounting", "issues"],
    )
    return out


def build() -> Schema:
    all_kinds = kinds()
    definitions = defs()
    for kind in KINDS:
        definitions[f"record_{kind}"] = all_kinds[kind]
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://w3id.org/agentprov/schemas/aer-{_VERSION[0]}.schema.json",
        "title": f"AgentPROV Execution Record (aer/{_VERSION[0]}): one record",
        "description": (
            "Structural subset of the AER validator (docs/architecture C.17: AER-V04..V07, V12 closed party list, "
            "V16 closed reasons, V18 $-forms and ext.lex shape, structural parts of V26 and V30..V33). "
            "One JSON object per line of an .aer.jsonl file. The in-code validator is authoritative; this schema "
            "is published for consumers and differentially tested against it."
            + ("" if _VERSION[0] == "0.1" else
               " aer/0.2: a part's text, args or value may be absent when the record's unk declares it withheld or "
               "not_captured (D-211), and a degenerate file's header (header, run scope and seal only) may omit "
               "task.task_id when its unk declares it not_captured (D-219). This schema holds the header's unk "
               "condition; the part conditions and the degenerate file shape are held by the in-code validator. A "
               "$utf16 payload is base64 of an even byte count, and $lit wraps an object with a member name beginning "
               "with $ (pre-round review #28); that the $utf16 units are not a valid scalar sequence is held in code.")
        ),
        "type": "object",
        "required": ["k"],
        "properties": {"k": enum(KINDS)},
        "allOf": [
            {"if": {"required": ["k"], "properties": {"k": {"const": kind}}}, "then": ref(f"record_{kind}")}
            for kind in KINDS
        ],
        "$defs": dict(sorted(definitions.items())),
    }


def render(version: str = "0.1") -> str:
    _VERSION[0] = version
    try:
        return json.dumps(build(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    finally:
        _VERSION[0] = "0.1"


if __name__ == "__main__":  # pragma: no cover
    for version, out in OUTS.items():
        out.write_text(render(version), encoding="utf-8", newline="\n")
        sys.stdout.write(f"wrote {out}\n")
