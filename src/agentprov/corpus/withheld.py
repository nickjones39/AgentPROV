"""``WITHHELD.json``: the withheld-evidence ledger ``agentprov-withheld/0.1`` (and ``/0.2``) of a sealed corpus (HL H.4.5;
G.9.5; D-230, D-311).

A sealed corpus is what is released (H.1.5): a raw object or an execution that must not be released is **withheld** when
the corpus version is built. Its bytes and its derived files leave the sealed tree (sealing renames them into the private
sidecar ``DIR.withheld/``, :mod:`agentprov.corpus.withhold`), and the corpus root carries ``WITHHELD.json``, covered by
``checksums.sha256`` and declared in the manifest's ``files.withheld``. Nothing in the document holds a withheld value or
any fragment of it: digests, pinned origins, closed-vocabulary reasons, rule ids and generated or profile-declared notes
only::

    {"entries": [{"affected_executions": ["ex_…"], "basis": "purge", "bytes": 1234, "decided_on": "2026-10-12",
                  "finding": null, "media_type": "application/json",
                  "origins": [{"blob_sha1": "…", "commit": "…", "kind": "git", "path": "…", "repo": "…"}],
                  "public_note": "…", "reason": "secret", "sha256": "sha256:…"}],
     "executions": [{"digests": {"aer": "sha256:…", "prov": {"agentprov-prov/0.1": {"json": "sha256:…"}},
                                 "sem": {"agentdojo.suites@1": "sha256:…"}, "validation": "sha256:…"},
                     "ex": "ex_…", "snapshot_ids": ["2024-06"]}],
     "format": "agentprov-withheld/0.1",
     "policies": []}

* ``entries`` (object level, the G.9.5 shape): one per withheld raw object, sorted by ``sha256``. ``reason`` is ``secret``,
  ``personal_data``, ``licence`` or ``takedown``; ``basis`` says what withheld it: ``purge`` (a tombstone, G.9.6),
  ``raw_policy`` (a snapshot whose raw policy is ``withhold``, H.4.1), ``profile_rule`` (a ``[withhold]`` rule of the
  source profile hit the object or a derived record of an execution that cites it) or ``container`` (an archive whose
  bytes hold a withheld member, AD-12). ``origins`` are the object's ``raw/origins.jsonl`` origins (at least one; the
  pinned origin it can be fetched from again). ``bytes`` and ``media_type`` are ``null`` when the build cannot know them
  (a purged object whose size no record kept): never a placeholder. ``finding`` names the rule that matched (``detector``,
  ``rule``, ``fingerprint`` = ``<corpus path>:<rule id>``), never the match. ``affected_executions`` are the executions
  withheld *because of this object*; an execution that cites the object but is not listed stays released (object-level
  withholding: its derived records do not hold the value, e.g. a configuration field the mapper never reads).
* ``executions``: one per withheld execution, sorted by ``ex``, each named by at least one entry. Its index row left the
  index, its AER, SEM, PROV and view files left the tree, and its validation row left ``validation/``; ``snapshot_ids``
  and the stage ``digests`` (the index row's, same shape) remain, so the execution can be recomputed locally from the
  pinned origin and checked against them. The source key is not kept (its locator can hold source-derived names).
* ``policies``: the source-profile ``[withhold]`` policy the build applied (profile id, version and digest; rule ids,
  kinds and scopes; the release-scan rule ids its backstop enforces, :mod:`agentprov.release.builder`). The markers and
  patterns themselves stay in the profile copy under ``rules/``.

**Three versions (D-311, D-454).** ``agentprov-withheld/0.2`` differs from ``/0.1`` in one place: a policy rule's
``kind`` may also be ``issue`` (a rule that selects executions by an AER seal issue code, :mod:`agentprov.corpus.withhold`).
``/0.3`` differs from ``/0.2`` in one place: an entry's ``basis`` may also be ``unscanned`` (an archive the decoded scan
could not read, withheld instead of refusing the seal). The format is a function of the content: ``/0.3`` exactly when an
entry's basis is ``unscanned``, else ``/0.2`` exactly when a policy has an ``issue`` rule, else ``/0.1``. So every earlier
document keeps its bytes, and the ``/0.1`` and ``/0.2`` schemas are frozen as published (D-163).

The document is written as a corpus-layer single JSON document (H.1.4(2)). :data:`DOCUMENT` declares its shape once; the
published schema ``src/agentprov/schemas/withheld-0.1.schema.json`` is generated from it (:func:`schema_bytes`; the
committed file is pinned equal by a test, and frozen with its version, D-163). :func:`decode_withheld` is the
authoritative reader: the structural check plus the semantic rules the schema cannot express (sorted, unique arrays; every
affected execution listed under ``executions`` and every execution named by an entry; origins that parse as object
origins; one-line notes).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from importlib import resources
from typing import Any, Final

from agentprov.corpus.shapes import Arr, Const, Enum, Issue, MapOf, Nullable, Obj, Ref, Shape, Str
from agentprov.errors import AgentProvError, IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads
from agentprov.io.canonical import is_sha256_hex, jcs_bytes

__all__ = [
    "BASES",
    "BASES_03",
    "DOCUMENT",
    "FORMAT",
    "FORMAT_02",
    "FORMAT_03",
    "FORMAT_04",
    "FORMAT_05",
    "REASONS",
    "SCHEMA_ID",
    "SCHEMA_RESOURCE",
    "SCHEMA_RESOURCE_02",
    "SCHEMA_RESOURCE_03",
    "SCHEMA_RESOURCE_04",
    "SCHEMA_RESOURCE_05",
    "WithheldDocument",
    "WithheldError",
    "WithheldExecution",
    "WithheldFinding",
    "WithheldObject",
    "WithheldPolicy",
    "decode_withheld",
    "encode_withheld",
    "load_published_schema",
    "schema_bytes",
    "validate_withheld",
    "withheld_schema",
    "withheld_summary",
]

FORMAT: Final = "agentprov-withheld/0.1"
SCHEMA_ID: Final = "https://w3id.org/agentprov/schemas/withheld-0.1.schema.json"
SCHEMA_RESOURCE: Final = "withheld-0.1.schema.json"
#: The version that admits ``issue`` rules (D-311); written only for a document whose policies hold one.
FORMAT_02: Final = "agentprov-withheld/0.2"
SCHEMA_RESOURCE_02: Final = "withheld-0.2.schema.json"
#: The version that admits the basis ``unscanned`` (D-454); written only for a document with such an entry.
FORMAT_03: Final = "agentprov-withheld/0.3"
SCHEMA_RESOURCE_03: Final = "withheld-0.3.schema.json"
#: The version that admits ``address`` rules (D-810): a rule that matches the digests of the e-mail addresses a corpus's spec
#: lists (persona-file class ``withhold``), never a literal. Written only for a document whose policies hold one; it also
#: admits every basis of 0.3.
FORMAT_04: Final = "agentprov-withheld/0.4"
SCHEMA_RESOURCE_04: Final = "withheld-0.4.schema.json"
#: The version that admits ``object`` rules (D-964): the stored raw objects and executions a corpus spec's ``[withhold]``
#: table lists by digest and id (release-scan findings a review decided to withhold), never a value. Written only for a
#: document whose policies hold one; it also admits every basis and rule kind of 0.4.
FORMAT_05: Final = "agentprov-withheld/0.5"
SCHEMA_RESOURCE_05: Final = "withheld-0.5.schema.json"
#: G.9.5 ``reason``, in the priority used when one object is withheld for several reasons (the first wins).
REASONS: Final = ("secret", "personal_data", "takedown", "licence")
#: What withheld an object, in the priority used when several causes apply (the first wins).
BASES: Final = ("purge", "profile_rule", "raw_policy", "container")
#: The bases of ``agentprov-withheld/0.3`` (D-454): also ``unscanned``, an archive the decoded scan could not read. It
#: comes last, so any other cause of the same object names the entry's basis.
BASES_03: Final = (*BASES, "unscanned")
SCOPES: Final = ("executions", "object")
RULE_KINDS: Final = ("marker", "pattern")
#: The rule kinds of ``agentprov-withheld/0.2`` (D-311).
RULE_KINDS_02: Final = ("marker", "pattern", "issue")
#: The rule kinds of ``agentprov-withheld/0.4`` (D-810).
RULE_KINDS_04: Final = (*RULE_KINDS_02, "address")
#: The rule kinds of ``agentprov-withheld/0.5`` (D-964).
RULE_KINDS_05: Final = (*RULE_KINDS_04, "object")
NOTE_MAX: Final = 200

_SHA = r"sha256:[0-9a-f]{64}"
_EX = r"ex_([a-z2-7]{26}|[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})"
_ID = r"[a-z0-9][a-z0-9_.-]*"
_RULE_ID = r"[a-z0-9][a-z0-9_.-]{0,63}"
_DATE = r"[0-9]{4}-[0-9]{2}-[0-9]{2}"
_SEM_REF = r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*@[1-9][0-9]*"
#: One printable line: no C0/C1 control, no line or paragraph separator (G.8.2).
_LINE = r"[^\x00-\x1f\x7f-\x9f\u2028\u2029]+"

FINDING: Final = Obj({"detector": Str(r"[a-z][a-z0-9-]*/[0-9]+", max_len=64),
                      "rule": Str(r"[a-z][a-z0-9_.-]*@[1-9][0-9]*:" + _RULE_ID, max_len=160),
                      "fingerprint": Str(r"[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*:" + _RULE_ID, max_len=300)})
def _entry_shape(bases: Sequence[str]) -> Obj:
    return Obj({
    "sha256": Str(_SHA),
    "bytes": Nullable(Ref("count")),
    "media_type": Nullable(Str(r"[a-z]+/[A-Za-z0-9.+-]+", max_len=100)),
    "origins": Arr(MapOf(Ref("json")), min_items=1),
    "reason": Enum(REASONS),
    "basis": Enum(tuple(bases)),
    "finding": Nullable(FINDING),
    "affected_executions": Arr(Str(_EX)),
    "decided_on": Nullable(Str(_DATE)),
    "public_note": Str(_LINE, min_len=1, max_len=NOTE_MAX),
    })  # fmt: skip


ENTRY: Final = _entry_shape(BASES)
DIGESTS: Final = Obj({"aer": Str(_SHA)}, {"sem": MapOf(Nullable(Str(_SHA)), key_pattern=_SEM_REF),
                                          "prov": MapOf(Obj({"json": Nullable(Str(_SHA))})),
                                          "validation": Nullable(Str(_SHA))})  # fmt: skip
EXECUTION: Final = Obj({"ex": Str(_EX), "snapshot_ids": Arr(Str(_ID), min_items=1), "digests": DIGESTS})


def _policy_shape(kinds: Sequence[str]) -> Obj:
    return Obj({
        "profile": Obj({"id": Str(r"[a-z][a-z0-9_.-]*"), "version": Ref("positive"), "sha256": Str(_SHA)}),
        "rules": Arr(Obj({"id": Str(_RULE_ID), "kind": Enum(tuple(kinds)), "scope": Enum(SCOPES)}), min_items=1),
        "scan_rules": Arr(Str(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}")),
    })  # fmt: skip


def _document_shape(format_id: str, kinds: Sequence[str], bases: Sequence[str] = BASES) -> Obj:
    entry = ENTRY if tuple(bases) == BASES else _entry_shape(bases)
    return Obj({"format": Const(format_id), "entries": Arr(entry, min_items=1), "executions": Arr(EXECUTION),
                "policies": Arr(_policy_shape(kinds))})  # fmt: skip


POLICY: Final = _policy_shape(RULE_KINDS)
DOCUMENT: Final = _document_shape(FORMAT, RULE_KINDS)
DOCUMENT_02: Final = _document_shape(FORMAT_02, RULE_KINDS_02)
DOCUMENT_03: Final = _document_shape(FORMAT_03, RULE_KINDS_02, BASES_03)
DOCUMENT_04: Final = _document_shape(FORMAT_04, RULE_KINDS_04, BASES_03)
DOCUMENT_05: Final = _document_shape(FORMAT_05, RULE_KINDS_05, BASES_03)
#: format -> (document shape, schema resource) for every version this build reads and writes.
VERSIONS: Final[Mapping[str, tuple[Obj, str]]] = {FORMAT: (DOCUMENT, SCHEMA_RESOURCE),
                                                  FORMAT_02: (DOCUMENT_02, SCHEMA_RESOURCE_02),
                                                  FORMAT_03: (DOCUMENT_03, SCHEMA_RESOURCE_03),
                                                  FORMAT_04: (DOCUMENT_04, SCHEMA_RESOURCE_04),
                                                  FORMAT_05: (DOCUMENT_05, SCHEMA_RESOURCE_05)}


class _Count(Shape):
    """A non-negative integer within +-(2^53 - 1) (H.1.4(3))."""

    def check(self, value: Any, pointer: str, issues: list[Issue], defs: Mapping[str, Shape]) -> None:
        if isinstance(value, bool) or not isinstance(value, int):
            self._type_error(value, pointer, issues, "an integer")
        elif not 0 <= value <= 2**53 - 1:
            issues.append(Issue(pointer, "range", "integer out of range"))

    def schema(self) -> dict[str, Any]:
        return {"type": "integer", "minimum": 0, "maximum": 2**53 - 1}


class _Positive(_Count):
    def check(self, value: Any, pointer: str, issues: list[Issue], defs: Mapping[str, Shape]) -> None:
        super().check(value, pointer, issues, defs)
        if isinstance(value, int) and not isinstance(value, bool) and value == 0:
            issues.append(Issue(pointer, "range", "integer out of range"))

    def schema(self) -> dict[str, Any]:
        return {"type": "integer", "minimum": 1, "maximum": 2**53 - 1}


class _Json(Shape):
    """Any JSON value without floating-point numbers (an origin member)."""

    def check(self, value: Any, pointer: str, issues: list[Issue], defs: Mapping[str, Shape]) -> None:
        if value is None or isinstance(value, bool | int | str):
            return
        if isinstance(value, list):
            for i, item in enumerate(value):
                self.check(item, f"{pointer}/{i}", issues, defs)
            return
        if isinstance(value, Mapping):
            for key, item in value.items():
                self.check(item, f"{pointer}/{key}", issues, defs)
            return
        self._type_error(value, pointer, issues, "a JSON value without floating-point numbers")

    def schema(self) -> dict[str, Any]:
        return {"type": ["null", "boolean", "integer", "string", "array", "object"],
                "items": {"$ref": "#/$defs/json"}, "additionalProperties": {"$ref": "#/$defs/json"}}


DEFS: Final[Mapping[str, Shape]] = {"json": _Json(), "count": _Count(), "positive": _Positive()}


class WithheldError(AgentProvError):
    """A ``WITHHELD.json`` that is not a valid ``agentprov-withheld/0.1`` document (exit 1)."""

    code = "corpus.withheld.invalid"
    exit_code = 1


# ================================================================================================ schema
def withheld_schema(format_id: str = FORMAT) -> dict[str, Any]:
    """The published JSON Schema (draft 2020-12) of ``agentprov-withheld/0.1`` (or of ``format_id``)."""
    shape, resource = VERSIONS[format_id]
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://w3id.org/agentprov/schemas/{resource}",
        "title": f"AgentPROV withheld-evidence ledger {format_id} (WITHHELD.json)",
        "description": "Generated from agentprov.corpus.withheld (HL H.4.5; G.9.5). The in-code reader "
        "agentprov.corpus.withheld.decode_withheld is authoritative and adds semantic checks this schema cannot "
        "express (sorted unique arrays, cross-references between entries and executions, object origins).",
        **shape.schema(),
        "$defs": {name: shape.schema() for name, shape in DEFS.items()},
    }


def schema_bytes(format_id: str = FORMAT) -> bytes:
    """The bytes of the published schema file: sorted keys, two-space indentation, final LF (H.1.4(2))."""
    return (json.dumps(withheld_schema(format_id), sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def load_published_schema(resource: str = SCHEMA_RESOURCE) -> bytes:
    """A committed ``src/agentprov/schemas/withheld-0.<n>.schema.json`` (copied into a sealed corpus that withholds)."""
    return resources.files("agentprov").joinpath("schemas", resource).read_bytes()


# ================================================================================================ values
@dataclass(frozen=True, slots=True)
class WithheldFinding:
    """The rule that matched (never the match): detector ``agentprov-withhold/<n>``, ``<profile>@<v>:<rule id>``, and the
    fingerprint ``<corpus path>:<rule id>``."""

    detector: str
    rule: str
    fingerprint: str

    def to_json(self) -> dict[str, str]:
        return {"detector": self.detector, "fingerprint": self.fingerprint, "rule": self.rule}


@dataclass(frozen=True, slots=True)
class WithheldObject:
    """One ``entries`` item; ``sha256`` is bare hex, ``origins`` are origin objects (``{"kind": …, …}``)."""

    sha256: str
    origins: tuple[Mapping[str, Any], ...]
    reason: str
    basis: str
    public_note: str
    affected_executions: tuple[str, ...] = ()
    bytes: int | None = None
    media_type: str | None = None
    finding: WithheldFinding | None = None
    decided_on: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "affected_executions": list(self.affected_executions), "basis": self.basis, "bytes": self.bytes,
            "decided_on": self.decided_on, "finding": None if self.finding is None else self.finding.to_json(),
            "media_type": self.media_type, "origins": [dict(o) for o in self.origins], "public_note": self.public_note,
            "reason": self.reason, "sha256": "sha256:" + self.sha256,
        }  # fmt: skip


@dataclass(frozen=True, slots=True)
class WithheldExecution:
    """One ``executions`` item: the id, snapshots and stage digests of an execution that left the corpus."""

    ex: str
    snapshot_ids: tuple[str, ...]
    digests: Mapping[str, Any]

    def to_json(self) -> dict[str, Any]:
        return {"digests": json.loads(json.dumps(self.digests)), "ex": self.ex, "snapshot_ids": list(self.snapshot_ids)}

    def sem_profiles(self) -> list[str]:
        """The semantics profiles with an output file (a non-null digest)."""
        return sorted(p for p, d in dict(self.digests.get("sem") or {}).items() if d is not None)

    def prov_specs(self) -> list[str]:
        """The PROV specs with an output file (a non-null digest)."""
        return sorted(s for s, d in dict(self.digests.get("prov") or {}).items() if (d or {}).get("json") is not None)


@dataclass(frozen=True, slots=True)
class WithheldPolicy:
    """One ``policies`` item: the source-profile ``[withhold]`` policy the build applied."""

    profile_id: str
    profile_version: int
    profile_sha256: str  # "sha256:<hex>"
    rules: tuple[tuple[str, str, str], ...]  # (id, kind, scope), sorted by id
    scan_rules: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {"profile": {"id": self.profile_id, "sha256": self.profile_sha256, "version": self.profile_version},
                "rules": [{"id": i, "kind": k, "scope": s} for i, k, s in self.rules],
                "scan_rules": list(self.scan_rules)}  # fmt: skip


@dataclass(frozen=True)
class WithheldDocument:
    """A parsed or built ``WITHHELD.json``."""

    entries: tuple[WithheldObject, ...]
    executions: tuple[WithheldExecution, ...] = ()
    policies: tuple[WithheldPolicy, ...] = ()
    _objects: dict[str, WithheldObject] = field(init=False, repr=False, compare=False)
    _executions: dict[str, WithheldExecution] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_objects", {e.sha256: e for e in self.entries})
        object.__setattr__(self, "_executions", {e.ex: e for e in self.executions})

    @property
    def objects(self) -> Mapping[str, WithheldObject]:
        """Bare hex digest -> entry."""
        return self._objects

    @property
    def execution_map(self) -> Mapping[str, WithheldExecution]:
        """Execution id -> execution."""
        return self._executions

    @property
    def format(self) -> str:
        """``agentprov-withheld/0.5`` when a policy has an ``object`` rule (D-964), else ``/0.4`` when it has an ``address``
        rule (D-810), else ``/0.3`` when an entry's basis is ``unscanned`` (D-454), else ``/0.2`` when a policy has an
        ``issue`` rule (D-311), else ``/0.1``."""
        if any(kind == "object" for p in self.policies for _, kind, _ in p.rules):
            return FORMAT_05
        if any(kind == "address" for p in self.policies for _, kind, _ in p.rules):
            return FORMAT_04
        if any(e.basis == "unscanned" for e in self.entries):
            return FORMAT_03
        return FORMAT_02 if any(kind == "issue" for p in self.policies for _, kind, _ in p.rules) else FORMAT

    @property
    def schema_resource(self) -> str:
        """The published schema of :attr:`format` (its copy under ``schemas/`` of a sealed corpus)."""
        return VERSIONS[self.format][1]

    def to_json(self) -> dict[str, Any]:
        return {"entries": [e.to_json() for e in self.entries], "executions": [e.to_json() for e in self.executions],
                "format": self.format, "policies": [p.to_json() for p in self.policies]}  # fmt: skip

    def counts(self) -> dict[str, int]:
        return {"executions": len(self.executions), "objects": len(self.entries)}


# ================================================================================================ validation
def _semantic(issues: list[Issue], pointer: str, detail: str) -> None:
    issues.append(Issue(pointer, "semantic", detail, "semantic"))


def _sorted_unique(values: Sequence[Any], key: Any = None) -> bool:
    keys = [key(v) if key else v for v in values]
    return keys == sorted(set(keys)) and len(set(keys)) == len(keys)


def validate_withheld(obj: Any) -> list[Issue]:
    """Validate a parsed ``WITHHELD.json`` object; an empty list means valid (see the module docstring)."""
    issues: list[Issue] = []
    version = obj.get("format") if isinstance(obj, Mapping) else None
    shape = VERSIONS[version][0] if isinstance(version, str) and version in VERSIONS else DOCUMENT
    shape.check(obj, "", issues, DEFS)
    if issues or not isinstance(obj, Mapping):
        return issues
    from agentprov.raw.origins import Origin, OriginError

    entries, executions = obj["entries"], obj["executions"]
    if not _sorted_unique([e["sha256"] for e in entries]):
        _semantic(issues, "/entries", "entries are sorted by sha256 and unique")
    if not _sorted_unique([e["ex"] for e in executions], key=lambda x: x.encode("ascii")):
        _semantic(issues, "/executions", "executions are sorted by ex and unique")
    listed = {e["ex"] for e in executions}
    named: set[str] = set()
    for i, entry in enumerate(entries):
        affected = entry["affected_executions"]
        if not _sorted_unique(affected, key=lambda x: x.encode("ascii")):
            _semantic(issues, f"/entries/{i}/affected_executions", "sorted and unique")
        missing = set(affected) - listed
        if missing:
            _semantic(issues, f"/entries/{i}/affected_executions", f"{len(missing)} execution(s) not under executions")
        named.update(affected)
        canon: list[bytes] = []
        for j, origin in enumerate(entry["origins"]):
            try:
                canon.append(jcs_bytes(Origin.from_json(origin).to_json()))
            except (OriginError, AgentProvError, ValueError, TypeError):
                _semantic(issues, f"/entries/{i}/origins/{j}", "not an object origin (C.3.12)")
        if len(canon) == len(entry["origins"]) and not _sorted_unique(canon):
            _semantic(issues, f"/entries/{i}/origins", "sorted by their JCS bytes and unique")
        if entry["decided_on"] is not None:
            try:
                if date.fromisoformat(entry["decided_on"]).isoformat() != entry["decided_on"]:
                    raise ValueError
            except ValueError:
                _semantic(issues, f"/entries/{i}/decided_on", "a calendar date YYYY-MM-DD")
        if (entry["basis"] == "profile_rule") != (entry["finding"] is not None):
            _semantic(issues, f"/entries/{i}/finding", "a finding exactly for basis profile_rule")
        if entry["public_note"] != entry["public_note"].strip():
            _semantic(issues, f"/entries/{i}/public_note", "no leading or trailing white space")
    unnamed = listed - named
    if unnamed:
        _semantic(issues, "/executions", f"{len(unnamed)} execution(s) are named by no entry")
    for i, execution in enumerate(executions):
        if list(execution["snapshot_ids"]) != sorted(set(execution["snapshot_ids"])):
            _semantic(issues, f"/executions/{i}/snapshot_ids", "sorted and unique")
    policies = obj["policies"]
    ids = [f"{p['profile']['id']}@{p['profile']['version']}" for p in policies]
    if not _sorted_unique(ids):
        _semantic(issues, "/policies", "one policy per profile, sorted")
    for i, policy in enumerate(policies):
        if not _sorted_unique([r["id"] for r in policy["rules"]]):
            _semantic(issues, f"/policies/{i}/rules", "sorted by id and unique")
        if not _sorted_unique(policy["scan_rules"]):
            _semantic(issues, f"/policies/{i}/scan_rules", "sorted and unique")
    unscanned = any(e["basis"] == "unscanned" for e in entries)
    has_object_rule = any(r["kind"] == "object" for p in policies for r in p["rules"])
    addressed = any(r["kind"] == "address" for p in policies for r in p["rules"])
    if (obj["format"] == FORMAT_05) != has_object_rule:
        _semantic(issues, "/format", f"{FORMAT_05} exactly when a policy has an object rule (D-964)")
    elif has_object_rule:
        pass  # 0.5 admits every basis and rule kind of the earlier versions
    elif (obj["format"] == FORMAT_04) != addressed:
        _semantic(issues, "/format", f"{FORMAT_04} exactly when a policy has an address rule (D-810)")
    elif addressed:
        pass  # 0.4 admits every basis and rule kind of the earlier versions
    elif (obj["format"] == FORMAT_03) != unscanned:
        _semantic(issues, "/format", f"{FORMAT_03} exactly when an entry's basis is unscanned (D-454)")
    elif not unscanned and (obj["format"] == FORMAT_02) != any(r["kind"] == "issue" for p in policies for r in p["rules"]):
        _semantic(issues, "/format", f"{FORMAT_02} exactly when a policy has an issue rule (D-311)")
    return issues


# ================================================================================================ read and write
def _object_from_json(entry: Mapping[str, Any]) -> WithheldObject:
    finding = entry["finding"]
    return WithheldObject(
        sha256=entry["sha256"][7:], origins=tuple(dict(o) for o in entry["origins"]), reason=entry["reason"],
        basis=entry["basis"], public_note=entry["public_note"], affected_executions=tuple(entry["affected_executions"]),
        bytes=entry["bytes"], media_type=entry["media_type"], decided_on=entry["decided_on"],
        finding=None if finding is None else WithheldFinding(finding["detector"], finding["rule"], finding["fingerprint"]),
    )  # fmt: skip


def _policy_from_json(policy: Mapping[str, Any]) -> WithheldPolicy:
    profile = policy["profile"]
    return WithheldPolicy(profile["id"], profile["version"], profile["sha256"],
                          tuple((r["id"], r["kind"], r["scope"]) for r in policy["rules"]), tuple(policy["scan_rules"]))


def from_json(obj: Any) -> WithheldDocument:
    """A :class:`WithheldDocument` from a parsed object; :class:`WithheldError` when :func:`validate_withheld` objects."""
    issues = validate_withheld(obj)
    if issues:
        shown = "; ".join(f"{i.pointer or '/'} {i.code}" for i in issues[:5])
        raise WithheldError(f"WITHHELD.json is not a valid agentprov-withheld document ({len(issues)} issue(s)): {shown}")
    return WithheldDocument(
        entries=tuple(_object_from_json(e) for e in obj["entries"]),
        executions=tuple(WithheldExecution(e["ex"], tuple(e["snapshot_ids"]), e["digests"]) for e in obj["executions"]),
        policies=tuple(_policy_from_json(p) for p in obj["policies"]),
    )


def decode_withheld(data: bytes, limits: IngestLimits | None = None) -> WithheldDocument:
    """Parse ``WITHHELD.json`` bytes strictly (bounded strict JSON, then :func:`validate_withheld`)."""
    try:
        value = strict_json_loads(data, limits)
    except IngestError as exc:
        raise WithheldError(f"WITHHELD.json is not strict JSON ({exc.code})") from None
    return from_json(value)


def encode_withheld(document: WithheldDocument) -> bytes:
    """The bytes of ``WITHHELD.json`` (H.1.4(2)); the document is validated first (a builder bug fails closed)."""
    value = document.to_json()
    from_json(value)
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def withheld_summary(document: WithheldDocument) -> list[dict[str, Any]]:
    """What was withheld and why, for the datasheet (H.9; counts and notes only, never a value): one row per
    ``(reason, basis)`` in priority order with its object and execution counts and its distinct public notes."""
    groups: dict[tuple[str, str], list[WithheldObject]] = {}
    for entry in document.entries:
        groups.setdefault((entry.reason, entry.basis), []).append(entry)
    rows = []
    for (reason, basis), entries in sorted(groups.items(), key=lambda kv: (REASONS.index(kv[0][0]), BASES_03.index(kv[0][1]))):
        executions = {ex for e in entries for ex in e.affected_executions}
        rows.append({"basis": basis, "executions": len(executions), "notes": sorted({e.public_note for e in entries}),
                     "objects": len(entries), "reason": reason})
    return rows


def one_line_note(text: str) -> str:
    """``text`` as a ``public_note``: one line, controls removed, white space collapsed, at most 200 characters."""
    clean = re.sub(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]+", " ", str(text))
    clean = " ".join(clean.split())
    return clean[:NOTE_MAX].rstrip() or "withheld (H.4.5)"


def sorted_origins(origins: Iterable[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    """Origin objects sorted by their JCS bytes, duplicates removed (the order :func:`validate_withheld` requires)."""
    unique = {jcs_bytes(dict(o)): dict(o) for o in origins}
    return tuple(unique[k] for k in sorted(unique))


def is_digest(value: object) -> bool:
    return isinstance(value, str) and value.startswith("sha256:") and is_sha256_hex(value[7:])
