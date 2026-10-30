"""The sealed corpus manifest ``corpus.json`` (``agentprov-corpus/0.1``; HL H.2): declaration, validator, schema, builders.

**Declaration.** :data:`MANIFEST` and the ``$defs`` of :data:`DEFS` declare every H.2 object as a :mod:`shapes
<agentprov.corpus.shapes>` tree. The published schema ``src/agentprov/schemas/corpus-0.1.schema.json`` is generated from
them (:func:`corpus_schema`; the committed file is pinned equal by a test) and carries, as ``$defs`` (H.2.1(1)), the
index row (``agentprov-index/0.1``), the register entry (``agentprov-register/0.1``), the derivation document
(``agentprov-derivation/0.1``) and the ``raw/members.jsonl`` row. Every object is closed except the profile's
``[lineage]`` duplicates entries, which follow the profile schema, and the index row's adapter facets ``x.*``.

**Validator.** :func:`validate_manifest` is the authoritative validator (H.2.1(2)): the structural check of
:data:`MANIFEST` (``level = "schema"``, the same verdict as the published schema; HL-T1) plus semantic checks the schema
cannot express (``level = "semantic"``): no floating-point number and integers within +-(2^53 - 1) (H.1.4(3)); every
snapshot's ``candidates == executions + not_imported`` (H.2.3, H.6.1 R5); the corpus counts add up; ``content_digest``
recomputes (H.5.4); a sealed manifest has ``release.status == "sealed"``; the licence class equals ``(derived.spdx,
sorted restrictions)`` (AD-20(b)); the assessment says "not legal advice"; no snapshot origin is ``local``; oracle specs
are exactly the regression-oracle specs among ``prov_specs`` (R-55); sorted, unique arrays where H.2 says sorted.

**Builders** (pure functions; :mod:`agentprov.corpus.package` does the IO). U4 (``verify --level chain``) and U5 (the
deposit builder) reuse them:

* :func:`snapshot_counts` / :func:`corpus_counts`: H.2.3 and H.2.9 counts **recomputed** from the index, the register and
  ``raw/members.jsonl``, never copied from the importer's counters (D-33). ``candidates`` are the selected
  execution-bearing files or members: an execution row (one per source key, whatever its number of origins) or a
  ``not_imported`` entry that is not a selection exclusion; a register entry whose path an exclude glob of the snapshot
  matches is a selection exclusion, counted in ``selection_excluded`` and never a candidate (H.6.1 R1).
* :func:`snapshot_origin_from_pin`: the sealed snapshot origin, built from the pin the working manifest recorded and the
  object-level origins it vouched for; never ``local`` (D-33).
* :class:`AerStats`: one pass over the AER (and SEM, PROV) of every execution: records by kind, generic types, model
  summaries (H.2.8), complete framework identities (H.2.4, with ``tool_definitions_sha256``, ``system_prompt_sha256``
  and ``executions``), and the rule ids each catalogue contributed (``rules_used``, H.2.5).
* :func:`digests_of` (H.2.11), :func:`validation_summary` (H.2.12; D-40), :func:`duplicate_summary` (H.7; D-41),
  :func:`file_ref`.
"""

from __future__ import annotations

import datetime
import fnmatch
import hashlib
import json
import posixpath
import re
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from importlib import resources
from typing import Any, Final

from agentprov.aer.reader import AerDocument
from agentprov.aer.rules import RULE_ID_RE, RULE_REF_RE
from agentprov.corpus.buildstep import ABSENT_REASONS, BUILD_COMMANDS, BUILD_STAGES, step_problems
from agentprov.corpus.facets import framework_identity
from agentprov.corpus.index import (
    COMPLETENESS,
    CORE_FACET_TYPES,
    ORACLE_SPECS,
    ORACLE_STATUS,
    STAGE_STATES,
    STATUSES,
    UNITS,
    IndexRow,
    check_corpus_json,
)
from agentprov.corpus.integrity import content_digest, set_digest
from agentprov.corpus.register import RegisterEntry
from agentprov.corpus.shapes import (
    AnyOf,
    Arr,
    Bool,
    Const,
    Enum,
    Int,
    Issue,
    MapOf,
    Null,
    Nullable,
    Obj,
    Ref,
    Shape,
    Str,
    Tagged,
)
from agentprov.errors import AgentProvError
from agentprov.io.canonical import jcs_bytes, sha256_hex
from agentprov.raw.members import MemberRow
from agentprov.sem.types import SemDocument

__all__ = [
    "CORPUS_FORMATS",
    "DEFS",
    "CONTEXT_ROLE",
    "DEFS_BY_FORMAT",
    "FORMAT",
    "MANIFEST",
    "MANIFESTS",
    "aer_schema_resource",
    "format_for_aer",
    "schema_resource",
    "RECORD_KINDS",
    "SCHEMA_ID",
    "SCHEMA_RESOURCE",
    "AerStats",
    "ManifestError",
    "corpus_counts",
    "corpus_schema",
    "digests_of",
    "duplicate_summary",
    "file_ref",
    "is_exclusion",
    "load_published_schema",
    "raw_dispositions",
    "snapshot_counts",
    "origin_matches_pin",
    "ONTOLOGY_VERSIONS",
    "PINNED_OBJECT",
    "SNAPSHOT_INPUT",
    "sealed_origin_pin",
    "snapshot_origin_from_pin",
    "validate_def",
    "validate_manifest",
    "validate_row",
    "validation_summary",
]

#: The corpus formats this build reads, each with the one AER format its records use (D-212: one AER version per corpus
#: version). ``agentprov-corpus/0.1`` (``aer/0.1``) stays readable and verifiable; this build seals ``0.2``.
CORPUS_FORMATS: Final[Mapping[str, str]] = {"agentprov-corpus/0.1": "aer/0.1", "agentprov-corpus/0.2": "aer/0.2"}
FORMAT: Final = "agentprov-corpus/0.2"


def schema_resource(fmt: str = FORMAT) -> str:
    """The package resource name of a corpus format's published schema (``corpus-0.1.schema.json``, ...)."""
    return f"corpus-{fmt.rsplit('/', 1)[-1]}.schema.json"


def aer_schema_resource(fmt: str = FORMAT) -> str:
    """The published AER schema a corpus of format ``fmt`` carries (``aer-0.2.schema.json`` for ``0.2``)."""
    return f"aer-{CORPUS_FORMATS[fmt].rsplit('/', 1)[-1]}.schema.json"


def format_for_aer(aer_format: str | None) -> str:
    """The corpus format whose records are ``aer_format`` (the current one when it is not a known AER format)."""
    return next((c for c, a in CORPUS_FORMATS.items() if a == aer_format), FORMAT)


SCHEMA_ID: Final = f"https://w3id.org/agentprov/schemas/{schema_resource()}"
SCHEMA_RESOURCE: Final = schema_resource()
APV_IRI: Final = "https://w3id.org/agentprov/ns#"
#: The 13 record kinds of ``aer/0.1`` (Addendum B B-1), in H.2.9 order.
RECORD_KINDS: Final = (
    "execution", "actor", "scope", "message", "model_call", "tool_execution", "decision", "state_change", "fixture",
    "judgement", "activity", "artefact", "seal")  # fmt: skip
PROV_SPECS: Final = ("agentprov-prov/0.1", "adprov-v2.3-compat")
FILE_ROLES: Final = ("index", "register", "origins", "members", "derivation", "validation_results", "validation_summary",
                     "spec", "card", "changes")  # fmt: skip
OPTIONAL_FILE_ROLES: Final = ("references", "withheld")
EVIDENCE: Final = ("O", "D", "I")


class ManifestError(AgentProvError):
    """A manifest cannot be built from the corpus (a corpus-level check failed; exit 1)."""

    code = "corpus.manifest.invalid"
    exit_code = 1


# ================================================================================================ declaration
SHA = r"sha256:[0-9a-f]{64}"
HEX40 = r"[0-9a-f]{40}"
SEMVER = (
    r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(-[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?(\+[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?"
)
CORPUS_ID = r"[a-z0-9]+(-[a-z0-9]+)*"
REGISTRY_ID = r"[a-z0-9][a-z0-9_.-]*"
PROFILE_ID = r"[a-z][a-z0-9_.-]*"
SEM_PROFILE_ID = r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*"
SEM_PROFILE_REF = SEM_PROFILE_ID + r"@[1-9][0-9]*"
NS = r"[a-z][a-z0-9_]*"
RULE_ID = r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+@[1-9][0-9]*"
REGISTER_CODE = r"[a-z][a-z0-9_]*(\.[a-z0-9_]+)+"
EX = r"ex_([a-z2-7]{26}|[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})"
RELPATH = r"[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*"
SUBTREE = r"([A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*)?"
RFC3339_UTC = r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?Z"
DOI = r"10\.[0-9]{4,9}/[A-Za-z0-9._;()/:-]+"

_S = Str()
_NE = Str(min_len=1)
_SHA = Str(SHA)
_INT = Int()
_POS = Int(minimum=1)
_EVID = Enum(EVIDENCE)
_STRS = Arr(_NE)


def _states() -> MapOf:
    return MapOf(_INT, keys=STAGE_STATES)


#: The ``apv`` vocabulary version each corpus format records in ``ontology.version`` (D-500/D-501): apv 0.2.0 rides with
#: ``agentprov-corpus/0.2`` (user decision 2026-10-14); ``agentprov-corpus/0.1`` is frozen at 0.1.0 (D-163).
ONTOLOGY_VERSIONS: Final[Mapping[str, str]] = {"agentprov-corpus/0.1": "0.1.0", "agentprov-corpus/0.2": "0.2.0"}

#: One byte part of an archive stored as parts (D-249), as a sealed ``agentprov-corpus/0.2`` origin names it (D-217).
ORIGIN_PART: Final = Obj({"file": _NE, "bytes": _INT, "sha256": _SHA}, {"md5": Str(r"[0-9a-f]{32}")})


def _snapshot_origin(fmt: str) -> Tagged:
    """The sealed snapshot origin (H.2.3) of corpus format ``fmt``: ``agentprov-corpus/0.2`` adds the optional ``parts``
    of a ``zenodo`` or ``hf`` archive stored as byte parts (D-217); ``agentprov-corpus/0.1`` is frozen (D-163)."""
    parts = {} if fmt == "agentprov-corpus/0.1" else {"parts": Arr(ORIGIN_PART, min_items=2)}
    return Tagged("kind", {
        "git": Obj({"repo": Str(r"https://[A-Za-z0-9.-]+/[A-Za-z0-9_.~/-]+"), "commit": Str(HEX40)},
                   {"subtree": Str(SUBTREE), "subtrees": Arr(Str(RELPATH), min_items=2), "subtree_sha1": Str(HEX40)}),
        "zenodo": Obj({"doi": Str(DOI), "file": _NE}, {"md5": Str(r"[0-9a-f]{32}"), "member_prefix": _NE, **parts}),
        "hf": Obj({"dataset": _NE, "revision": Str(HEX40), "gated": Bool()}, {"path": _NE, **parts}),
        "url": Obj({"url": Str(r"https://\S+"), "retrieved_at": Str(RFC3339_UTC)}),
        "corpus": Obj({"corpus": _NE, "version": _NE, "producer_commit": Str(HEX40)}),
        "capture": Obj({"session_ids": Arr(_NE, min_items=1)}),
    })  # fmt: skip


SNAPSHOT_ORIGIN: Final = _snapshot_origin("agentprov-corpus/0.1")

LINEAGE: Final = Obj({}, {
    "built_on": _STRS,
    "vendored": _STRS,
    "cited_by": _STRS,
    "owns": _STRS,
    "excludes": _STRS,
    "content_dedup": Const("never"),
    "duplicates": Arr(Obj({"of": _NE, "path": _NE, "relation": Enum(("byte_identical", "replicate", "mirror",
                                                                     "derived_conversion")),
                           "owner": _NE}, {"part": _NE})),
})  # fmt: skip

PROFILE_REF: Final = Obj({"id": Str(PROFILE_ID), "version": _POS, "sha256": _SHA,
                          "path": Str(r"rules/[a-z0-9][a-z0-9_.-]*\.profile\.toml")})
SEM_PROFILE_REF_SHAPE: Final = Obj({"id": Str(SEM_PROFILE_ID), "version": _POS, "sha256": _SHA,
                                    "paths": Arr(Str(r"rules/[a-z0-9][a-z0-9_.-]*\.profile\.toml"), min_items=1)})

#: A context role (D.16.14 R2): the pin role a profile names in ``[import] context_artefacts`` entries ``"<role>:<glob>"``.
CONTEXT_ROLE: Final = r"[A-Za-z0-9][A-Za-z0-9_.-]*"

#: The object-level origin of a pinned object (D.16.14 R3), as ``raw/origins.jsonl`` holds it (C.3.12).
PINNED_OBJECT_ORIGIN: Final = Tagged("kind", {
    "git": Obj({"repo": _NE, "commit": Str(HEX40), "path": _NE, "blob_sha1": Str(HEX40)},
               {"introduced_in_commit": Str(HEX40)}),
    "hf": Obj({"repo": _NE, "revision": Str(HEX40), "path": _NE}),
    "zenodo": Obj({"doi": Str(DOI), "file": _NE}),
    "url": Obj({"url": Str(r"https://\S+"), "retrieved": _NE}),
})  # fmt: skip


#: The stored archive input of a snapshot (D-200) or a context tree (D-530), as the working snapshot records it; a split
#: archive (D-249) lists its byte parts in order. Sealed ``agentprov-corpus/0.2`` keeps it, so a re-map of the sealed
#: corpus re-expands the archive (D-223).
SNAPSHOT_INPUT: Final = Obj({"kind": Const("archive"), "label": _NE, "sha256": _SHA, "bytes": _INT},
                            {"parts": Arr(Obj({"file": _NE, "sha256": _SHA, "bytes": _INT}), min_items=2)})


def _context_entry(fmt: str) -> Obj:
    """One context tree of a sealed ``agentprov-corpus/0.2`` snapshot (D-221): the role, its sealed origin (from the
    role's recorded pin, as the snapshot's own, D-33), the stored archive when the role is an archive pin, the pin
    verification (every file vouched for) and the number of context files stored."""
    return Obj({
        "role": Str(CONTEXT_ROLE),
        "origin": _snapshot_origin(fmt),
        # re-check RC-15: a context tree is vouched for by its download pin's archive or blob by blob (D-221 addendum)
        "verification": Obj({"kind": Enum(("download", "blob")), "verified": _INT, "unverified": Int(minimum=0, maximum=0)}),
        "stored": _INT,
    }, {"input": SNAPSHOT_INPUT})


PINNED_OBJECT: Final = Obj({"label": _NE, "origin": PINNED_OBJECT_ORIGIN, "sha256": _SHA, "bytes": _INT})


def _snapshot(fmt: str) -> Obj:
    """A snapshot entry (H.2.3) of corpus format ``fmt`` (its origins per :func:`_snapshot_origin`). Under
    ``agentprov-corpus/0.2`` it may carry the stored archive input (``input``, D-223) and the per-unit inputs of D.16.14
    (D-221): ``context`` (one entry per context tree, by role), ``pinned_objects`` (by label) and ``context_skipped`` (the
    roles imported with ``--no-context``), so a re-map of the sealed corpus re-expands the archive and keeps the
    ``<role>:`` joins. ``agentprov-corpus/0.1`` is frozen (D-163)."""
    origin = _snapshot_origin(fmt)
    per_unit = {} if fmt == "agentprov-corpus/0.1" else {
        "input": SNAPSHOT_INPUT,
        "context": Arr(_context_entry(fmt), min_items=1),
        "pinned_objects": Arr(PINNED_OBJECT, min_items=1),
        "context_skipped": Arr(Str(CONTEXT_ROLE), min_items=1),
    }
    return Obj({
    "snapshot_id": Str(REGISTRY_ID),
    "origin": origin,
    "alt_origins": Arr(origin),
    "selection": Obj({"include": Arr(_NE), "exclude": Arr(Obj({"glob": _NE, "code": Str(r"select\.[a-z_]+"),
                                                                "owner": Nullable(_NE)}))}),
    "raw_policy": Enum(("include", "reference", "withhold")),
    "counts": Obj({"candidates": _INT, "executions": _INT, "not_imported": _INT,
                   "selection_excluded": MapOf(_INT, key_pattern=r"select\.[a-z_]+")}),
}, per_unit)  # fmt: skip


def _source_entry(fmt: str) -> Obj:
    """A source entry (H.2.3) of corpus format ``fmt``."""
    return Obj({
    "source_id": Str(REGISTRY_ID),
    "profile": PROFILE_REF,
    "parts": Arr(Str(REGISTRY_ID), min_items=1),
    "snapshots": Arr(_snapshot(fmt), min_items=1),
    "lineage": LINEAGE,
    "mirrors": Arr(_snapshot_origin(fmt)),
})


#: The ``agentprov-corpus/0.1`` declarations (frozen, D-163); ``_manifest_shape`` builds each format's own.
SNAPSHOT: Final = _snapshot("agentprov-corpus/0.1")
SOURCE_ENTRY: Final = _source_entry("agentprov-corpus/0.1")

FRAMEWORK_IDENTITY: Final = Obj({
    "fw": Str(r"fw_[a-z2-7]{16}"),
    "distribution": Nullable(_NE),
    "reported_version": Nullable(_S),
    "source": Nullable(Obj({}, {"commit": _NE, "repo": _NE, "wheel_sha256": _NE})),
    "source_tree_sha256": Nullable(_SHA),
    "suite_set": Nullable(_S),
    "tool_definitions_sha256": Nullable(_SHA),
    "system_prompt_sha256": Nullable(_SHA),
    "ev": MapOf(_EVID, keys=("distribution", "reported_version", "source", "source_tree_sha256", "suite_set",
                             "tool_definitions_sha256", "system_prompt_sha256")),
    "executions": _POS,
})  # fmt: skip

#: D-780: one process that built part of the corpus (``agentprov-corpus/0.2``; ``corpus.buildstep`` holds the rules).
BUILD_STEP: Final = Obj({
    "agentprov_version": _NE,
    "command": Enum(BUILD_COMMANDS),
    "stages": Arr(Enum(BUILD_STAGES)),
}, {
    "git_commit": Str(HEX40),
    "git_tree_clean": Bool(),
    "git_commit_absent_reason": Enum(ABSENT_REASONS),
    "distributions_sha256": _SHA,
})  # fmt: skip


def _producer(fmt: str) -> Obj:
    """``Producer`` (H.2.7) of corpus format ``fmt``: ``agentprov-corpus/0.1`` is frozen (D-163) and has no
    ``build_steps``; ``agentprov-corpus/0.2`` gains that one optional key (D-780)."""
    return Obj({
    "agentprov_version": _NE,
    "git_commit": Str(HEX40),
    "git_tree_clean": Bool(),
    "python": Obj({"implementation": _NE, "version": _NE}),
    "interpreter_advisory": Nullable(Obj({"floor": _NE, "python_version": _NE, "missing": _STRS})),
    "platform": Obj({"system": _S, "release": _S, "machine": _S}),
    "lockfile_sha256": Nullable(_SHA),
    "distributions_sha256": _SHA,
    "key_distributions": MapOf(_NE),
    "zlib_version": _NE,
    "isolation": Enum(("t1", "in-process")),
    "sandbox": Nullable(Obj({"kind": Enum(("sandbox_exec", "dedicated_user", "vm")),
                             "declared_by": Enum(("probe", "operator"))}, {"profile_sha256": _SHA})),
}, {"lockfile_absent_reason": _NE, **({} if fmt == "agentprov-corpus/0.1" else {"build_steps": Arr(BUILD_STEP)})})  # fmt: skip


MODEL_SUMMARY: Final = Obj({
    "requested": Nullable(_NE),
    "served": Arr(_NE),
    "provider": Nullable(_NE),
    "ev": Obj({"requested": Nullable(_EVID), "served": Nullable(Const("O"))}),
    "executions": _POS,
})

COUNTS: Final = Obj({
    "candidates": _INT,
    "executions": _INT,
    "not_imported": _INT,
    "by_unit": Obj({k: _INT for k in UNITS}),
    "by_status": Obj({k: _INT for k in STATUSES}),
    "by_completeness": Obj({k: _INT for k in COMPLETENESS}),
    "execution_observed": Obj({"true": _INT, "false": _INT}),
    "by_stage": Obj({"expand": Obj({"ok": _INT, "failed": _INT}), "aer": _states(), "sem": MapOf(_states()),
                     "prov": MapOf(_states()), "validation": _states()}),
    "issues_by_code": MapOf(_INT, key_pattern=REGISTER_CODE),
    "not_imported_by_code": MapOf(_INT, key_pattern=REGISTER_CODE),
    "selection_excluded_by_code": MapOf(_INT, key_pattern=r"select\.[a-z_]+"),
    "records_by_kind": Obj({k: _INT for k in RECORD_KINDS}),
    "generic_types": Obj({"activity": MapOf(_INT), "artefact": MapOf(_INT)}),
    "members": Nullable(Obj({"containers": _INT, "selected": _INT, "not_selected": _INT, "rejected": _INT})),
    "attempts": Nullable(Obj({"cells": _INT, "executions": _INT, "max_attempt": _INT})),
})  # fmt: skip

DUPLICATES: Final = Obj({
    "content_dedup": Const("never"),
    "collapsed": _INT,
    "multi_origin_executions": _INT,
    "multi_snapshot_executions": _INT,
    "owned_elsewhere": _INT,
})

LICENCES: Final = Obj({
    "raw": Arr(Obj({"source_id": Str(REGISTRY_ID), "spdx": Nullable(_NE), "licence_files": Arr(Str(r"LICENSES/" + RELPATH)),
                    "copyright": _STRS, "basis": _NE, "data_licence_explicit": Bool()}), min_items=1),
    "policy": Obj({"licence_policy": Enum(("include", "reference", "nc_partition", "forbidden")),
                   "raw_policy": Enum(("include", "reference", "withhold"))}),
    "derived": Obj({"spdx": _NE, "basis": Enum(("inherit", "user-decision")), "decided_by": _NE,
                    "text_path": Const("LICENSES/DERIVED.txt")}),
    "redistribution": Enum(("permitted", "permitted-non-commercial", "not-permitted")),
    "attribution": _STRS,
    "embedded": Arr(Obj({"what": _NE, "status": _NE})),
    "restrictions": _STRS,
    "class": Obj({"spdx": _NE, "restrictions": _STRS}),
    "assessment": Str(r"[\s\S]*not legal advice[\s\S]*"),
})  # fmt: skip

FACET_DECL: Final = Obj({
    "name": _NE,
    "type": Enum(("string", "integer", "boolean", "string[]", "object", "object[]")),
    "from": _NE,
    "may_be_inferred": Bool(),
    "core": Bool(),
})

FILE_REF: Final = Obj({"path": Str(RELPATH), "sha256": _SHA, "bytes": _INT, "lines": Nullable(_INT)})

DIGESTS: Final = Obj({
    "raw_set": _SHA,
    "aer_set": _SHA,
    "sem_set": MapOf(_SHA, key_pattern=SEM_PROFILE_REF),
    "prov_set": MapOf(Obj({"json": _SHA})),
    "validation_set": _SHA,
    "index": _SHA,
    "register": _SHA,
    "members": _SHA,
})

_TALLY = {"pass": _INT, "fail": _INT, "skipped": _INT, "not_applicable": _INT}
VALIDATION: Final = Obj({
    "mode": Enum(("strict", "dev")),
    "checks": Arr(Obj({"id": _NE, "version": _NE, "tier": Int(minimum=1, maximum=7), **_TALLY})),
    "tiers": Arr(Obj({"tier": Int(minimum=1, maximum=7), "checks": _INT, **_TALLY, "executions": _INT,
                      "executions_passed": _INT})),
    "linkage": Obj({"spec": _NE, "applicable": _INT, "resolved": _INT}),
    "linkage_resolved_pct": Nullable(Obj({"$dec": Str(r"(100\.00|[0-9]{1,2}\.[0-9]{2})")})),
    "libraries": MapOf(_NE),
})  # fmt: skip

RELEASE: Final = Obj({
    "status": Enum(("dev", "release-candidate", "sealed")),
    "created": Nullable(Str(RFC3339_UTC)),
    "source_date_epoch": Nullable(_INT),
    "version_doi": Nullable(Str(DOI)),
    "concept_doi": Nullable(Str(DOI)),
    "previous": Nullable(Obj({"corpus_version": Str(SEMVER), "content_digest": _SHA})),
})

LIVE_BLOCK: Final = Obj({
    "backend": _NE,
    "session_ids": _STRS,
    "llm_element": Enum(("native", "gateway_compat")),
    "instrumentation": Arr(Obj({"id": _NE, "kind": _NE, "sessions": _INT})),
    "resampled": _INT,
    "retried": _INT,
    "test_only": Bool(),
    "lockfiles_sha256": MapOf(_SHA),
})

def _manifest_shape(fmt: str) -> Obj:
    """The ``corpus.json`` declaration of corpus format ``fmt`` (the two versions differ in ``format``, ``formats.corpus``
    and ``formats.aer`` only)."""
    return Obj({
    "format": Const(fmt),
    "corpus_id": Str(CORPUS_ID, max_len=64),
    "corpus_version": Str(SEMVER),
    "title": Str(min_len=1, max_len=200),
    "mode": Enum(("import", "live")),
    "layout": Obj({"shard_depth": Int(minimum=1, maximum=2)}),
    "sources": Arr(_source_entry(fmt), min_items=1),
    "framework_identities": Arr(FRAMEWORK_IDENTITY),
    "adapters": Arr(Obj({"id": Str(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+"), "version": Str(SEMVER), "code_sha256": _SHA,
                         "dialects": Arr(_NE, min_items=1)}), min_items=1),
    "profiles": Obj({"source": Arr(PROFILE_REF, min_items=1), "semantics": Arr(SEM_PROFILE_REF_SHAPE)}),
    "rule_catalogues": Arr(Obj({"id": Str(NS), "version": _POS, "sha256": _SHA,
                                "path": Str(r"rules/([a-z][a-z0-9_]*\.rules\.toml|prov/[a-z0-9][a-z0-9.-]*\.toml)"),
                                "n_rules": _INT, "rules_used": Arr(Str(RULE_ID))})),
    "formats": Obj({"corpus": Const(fmt), "index": Const("agentprov-index/0.1"),
                    "register": Const("agentprov-register/0.1"), "aer": Const(CORPUS_FORMATS[fmt]),
                    "sem": Nullable(Const("sem/0.1")), "capture": Nullable(Const("capture/0.1"))}),
    "prov_specs": Arr(Enum(PROV_SPECS), min_items=1),
    "oracle_specs": Arr(Obj({"spec": Enum(tuple(sorted(ORACLE_SPECS))), "status": Const(ORACLE_STATUS),
                             "gate_report": Nullable(_SHA)})),
    "ontology": Obj({"prefix": Const("apv"), "iri": Const(APV_IRI), "version": Const(ONTOLOGY_VERSIONS[fmt])}),
    "producer": _producer(fmt),
    "live": Nullable(LIVE_BLOCK),
    "models": Arr(MODEL_SUMMARY),
    "counts": COUNTS,
    "duplicates": DUPLICATES,
    "licences": LICENCES,
    "facet_schema": Arr(FACET_DECL),
    "files": Obj({role: FILE_REF for role in FILE_ROLES}, {role: FILE_REF for role in OPTIONAL_FILE_ROLES}),
    "digests": DIGESTS,
    "validation": VALIDATION,
    "datasheet": Obj({"card_sha256": _SHA, "statements_sha256": _SHA, "statements": Arr(_NE),
                      "claims": Arr(Obj({"id": _NE, "holds": Bool()}))}),
    "content_digest": _SHA,
    "release": RELEASE,
    "sealed": Bool(),
    })  # fmt: skip


MANIFESTS: Final[Mapping[str, Obj]] = {fmt: _manifest_shape(fmt) for fmt in CORPUS_FORMATS}
MANIFEST: Final = MANIFESTS[FORMAT]

# ------------------------------------------------------------------------------------------------ $defs: rows
_STAGE = Enum(STAGE_STATES)
_RAW_REF = Obj({"sha256": _SHA, "role": Enum(("primary", "capture_log", "native_log", "supporting")), "included": Bool()})
_UNKNOWN = Obj({"$unk": Enum(("not_recorded", "lost", "overwritten", "withheld", "ambiguous", "not_captured",
                              "not_applicable"))})  # fmt: skip
_OUTCOME = Obj({"name": Nullable(_S), "value": AnyOf((Null(), Bool(), Int(minimum=None, maximum=None), _S, Arr(Ref("json")),
                                                      MapOf(Ref("json")))),
                "origin": Nullable(_S), "claim": AnyOf((Null(), Ref("json"))), "holds": Nullable(Bool()),
                "score": AnyOf((Null(), Ref("json"))), "scale": AnyOf((Null(), Ref("json"))),
                "ev": MapOf(_EVID, keys=("name", "value", "origin", "claim", "holds", "score", "scale"))})  # fmt: skip
_CORE_FACETS = {
    "task": Nullable(MapOf(Ref("json"))),
    "framework": Nullable(Str(r"fw_[a-z2-7]{16}")),
    "model.requested": _STRS,
    "model.served": _STRS,
    **{name: _INT for name, kind in CORE_FACET_TYPES.items() if kind == "integer"},
    "generic_types": Arr(Str(r"[a-z][a-z0-9_]*:[A-Za-z_][A-Za-z0-9_.-]*")),
    "outcome": Arr(_OUTCOME),
}
_INDEX_WORKING: dict[str, Shape] = {
    "ex": Str(EX),
    "mode": Enum(("import", "live")),
    "unit": Enum(UNITS),
    "source_id": Str(REGISTRY_ID),
    "snapshot_ids": Arr(Str(REGISTRY_ID), min_items=1),
    "source_key": Str(r"sha256:[0-9a-f]{64}#[\s\S]*"),
    "raw": Arr(_RAW_REF, min_items=1),
    "n_origins": _POS,
    "adapter": Str(r"[a-z][a-z0-9_.]*@[0-9]+\.[0-9]+\.[0-9]+"),
    "profile": Str(r"[a-z][a-z0-9_.-]*@[1-9][0-9]*"),
    "digests": Obj({"aer": _SHA}, {"sem": MapOf(Nullable(_SHA), key_pattern=SEM_PROFILE_REF),
                                    "prov": MapOf(Obj({"json": Nullable(_SHA)})), "validation": Nullable(_SHA)}),
    "paths": Obj({"aer": Str(RELPATH)}, {"sem": MapOf(Str(RELPATH), key_pattern=SEM_PROFILE_REF),
                                        "prov": MapOf(Obj({"json": Str(RELPATH)}))}),
    "stages": Obj({"raw": _STAGE, "aer": _STAGE}, {"sem": MapOf(_STAGE, key_pattern=SEM_PROFILE_REF),
                                                   "prov": MapOf(_STAGE), "validation": _STAGE}),
    "status": Enum(STATUSES),
    "completeness": Enum(COMPLETENESS),
    "execution_observed": Bool(),
    "issues": Arr(Str(REGISTER_CODE)),
    "attempt": Nullable(_INT),
}  # fmt: skip
_INDEX_FULL: dict[str, Shape] = {
    "logical_key": Nullable(Str(r"lk_[a-z2-7]{26}")),
    "cell": MapOf(Ref("json"), key_pattern=r"[a-z][a-z0-9_]*"),
    # core facets are required; adapter facets x.<ns>.<name> are the only open part of the schema (H.2.1(2))
    "facets": Obj(_CORE_FACETS, {}),
    "ev": MapOf(_EVID),
    "oracles": MapOf(Obj({"status": Const(ORACLE_STATUS), "gate_report": Nullable(_SHA)}), keys=tuple(sorted(ORACLE_SPECS))),
}
INDEX_ROW: Final = AnyOf((Obj(_INDEX_WORKING), Obj({**_INDEX_WORKING, **_INDEX_FULL})))

REGISTER_ROW: Final = Obj({
    "rid": Str(r"r_[a-z2-7]{20}"),
    "subject": AnyOf((Obj({"ex": Str(EX)}), Obj({"source_key": _NE}), Obj({"snapshot_id": _NE, "path": _NE}))),
    "subject_key": _NE,
    "code": Str(REGISTER_CODE),
    "severity": Enum(("info", "warning", "error")),
    "stage": Enum(("select", "ingest", "expand", "map", "sem", "prov", "validate", "capture", "package")),
    "disposition": Enum(("sealed", "not_imported", "failed", "withheld")),
    "rule": Nullable(_NE),
    "detail": Str(max_len=200),
    "owner": Nullable(Obj({"corpus_id": _NE, "source_id": _NE})),
    "ids": _STRS,
    "previous": Nullable(Obj({"corpus_version": _NE, "rid": Str(r"r_[a-z2-7]{20}")})),
})  # fmt: skip

MEMBERS_ROW: Final = Obj({
    "container": _SHA,
    "crc32": Str(r"[0-9a-f]{8}"),
    "disposition": Enum(("selected", "not_selected", "rejected")),
    "fn_digest": _SHA,
    "label": Nullable(_NE),
    "method": Int(minimum=0, maximum=0xFFFF),
    "sha256": Nullable(_SHA),
    "size": Nullable(_INT),
}, {"code": Str(r"ingest\.[a-z_]+\.[a-z_]+")})  # fmt: skip

_STAGE_DEF_COMMON = {"stage": _NE, "fn": _NE, "fn_digest": _SHA}


def _derivation_shape(aer_format: str) -> Obj:
    """``derivation.json`` of a corpus whose records are ``aer_format`` (its ``aer`` stage names that format)."""
    return Obj({
    "format": Const("agentprov-derivation/0.1"),
    "stages": Arr(Tagged("stage", {
        "expand": Obj({"fn": Const("expand"), "fn_digest": _SHA}, {
            "engine": _NE, "engine_code_sha256": _SHA, "limits_sha256": _SHA, "selection_sha256": _SHA,
            "dialects": _STRS, "methods": Arr(_INT), "patterns": MapOf(Ref("json"))}),
        "aer": Obj({"fn": Const("map"), "fn_digest": _SHA, "adapter": _NE, "adapter_code_sha256": _SHA, "profile": _NE,
                    "profile_sha256": _SHA, "rules": MapOf(_POS), "rules_sha256": MapOf(_SHA), "format": Const(aer_format)},
                   {"engine": _NE, "engine_code_sha256": _SHA, "limits_sha256": _SHA,
                    # D-623 (#5): a release-mode import only; agentprov-corpus/0.1 (aer/0.1) stays as released
                    **({} if aer_format == "aer/0.1" else {"mode": Const("release")})}),
        "sem": Obj({"fn": Const("semantics"), "fn_digest": _SHA, "format": Const("sem/0.1")},
                   {"profiles": MapOf(_SHA), "profile": _NE, "profile_sha256": _SHA, "rules": MapOf(_POS), "engine": _NE,
                    "engine_code_sha256": _SHA}),
        "prov": Obj({"fn": Const("provenance"), "fn_digest": _SHA, "spec": _NE},
                    {"rules_sha256": _SHA, "engine": _NE, "engine_code_sha256": _SHA, "options": MapOf(Ref("json")),
                     "serialisers": MapOf(_NE),
                     # D-640: the aprov catalogue version; agentprov-corpus/0.1 (aer/0.1) stays as released
                     **({} if aer_format == "aer/0.1" else {"rules": MapOf(_POS)})}),
        "validation": Obj({"fn": Const("validate"), "fn_digest": _SHA, "checks": _STRS},
                          {"mode": Enum(("dev", "release")), "engine": _NE, "engine_code_sha256": _SHA,
                           "libraries": MapOf(_NE),
                           # G2c-5: a skipped tier 4 is listed under `skipped` (pre-round verification V-7);
                           # agentprov-corpus/0.1 (aer/0.1) stays as released
                           **({} if aer_format == "aer/0.1" else {"skipped": _STRS})}),
        "views": Obj({"fn": _NE, "fn_digest": _SHA}, {"view": _NE, "engine": _NE, "engine_code_sha256": _SHA}),
    }), min_items=1),
    "lockfile_sha256": Nullable(_SHA),
    "python": Obj({"implementation": _NE, "version": _NE}),
    })  # fmt: skip


DERIVATION: Final = _derivation_shape(CORPUS_FORMATS[FORMAT])


class _AnyJson(Shape):
    """Any JSON value (the content of a verbatim copy such as the ``task`` facet)."""

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


def _defs(fmt: str) -> Mapping[str, Shape]:
    return {
        "json": _AnyJson(),
        "index_row": INDEX_ROW,
        "register_entry": REGISTER_ROW,
        "derivation": _derivation_shape(CORPUS_FORMATS[fmt]),
        "members_row": MEMBERS_ROW,
    }


#: The ``$defs`` of each corpus format's published schema (H.2.1(1)), keyed by name; :data:`MANIFESTS` are the roots.
DEFS_BY_FORMAT: Final[Mapping[str, Mapping[str, Shape]]] = {fmt: _defs(fmt) for fmt in CORPUS_FORMATS}
#: The ``$defs`` of the current format; :data:`MANIFEST` is the root.
DEFS: Final[Mapping[str, Shape]] = DEFS_BY_FORMAT[FORMAT]


def corpus_schema(fmt: str = FORMAT) -> dict[str, Any]:
    """The published JSON Schema (draft 2020-12) of corpus format ``fmt`` with its ``$defs`` (H.2.1(1))."""
    root = MANIFESTS[fmt].schema()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://w3id.org/agentprov/schemas/{schema_resource(fmt)}",
        "title": f"AgentPROV corpus manifest {fmt} (corpus.json) and its row formats",
        "description": "Generated from agentprov.corpus.manifest (HL H.2). $defs: index_row (agentprov-index/0.1), "
        "register_entry (agentprov-register/0.1), derivation (agentprov-derivation/0.1), members_row "
        "(raw/members.jsonl). The in-code validator agentprov.corpus.manifest.validate_manifest is authoritative "
        "(H.2.1(2)) and adds semantic checks this schema cannot express.",
        **root,
        "$defs": {name: shape.schema() for name, shape in DEFS_BY_FORMAT[fmt].items()},
    }


def schema_bytes(fmt: str = FORMAT) -> bytes:
    """The bytes of the published schema file: sorted keys, two-space indentation, final LF (H.1.4(2))."""
    return (json.dumps(corpus_schema(fmt), sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def load_published_schema(fmt: str = FORMAT) -> bytes:
    """The committed ``src/agentprov/schemas/corpus-<v>.schema.json`` package resource (copied into a sealed corpus of
    that format; D-163 freezes its bytes)."""
    return resources.files("agentprov").joinpath("schemas", schema_resource(fmt)).read_bytes()


# ================================================================================================ validator
def _structural(shape: Shape, value: Any, defs: Mapping[str, Shape] = DEFS) -> list[Issue]:
    issues: list[Issue] = []
    shape.check(value, "", issues, defs)
    return issues


def validate_def(name: str, value: Any) -> list[Issue]:
    """The structural check of one ``$defs`` entry (``index_row``, ``register_entry``, ``derivation``, ``members_row``)."""
    return _structural(DEFS[name], value)


def validate_row(name: str, value: Any) -> list[Issue]:
    """The authoritative check of one row-format document (``index_row``, ``register_entry``, ``members_row``): the
    structural check of its ``$defs`` entry (the published schema's verdict), then the row class's own validation
    (:class:`~agentprov.corpus.index.IndexRow`, :class:`~agentprov.corpus.register.RegisterEntry`,
    :class:`~agentprov.raw.members.MemberRow`), whose refusals are ``semantic`` issues (e.g. a logical key that does not
    recompute, an unsorted ``issues`` array)."""
    issues = validate_def(name, value)
    if issues:
        return issues
    parsers: dict[str, Callable[[Any], object]] = {"index_row": IndexRow.from_json, "register_entry": RegisterEntry.from_json,
                                                   "members_row": MemberRow.from_json}
    try:
        parsers[name](value)
    except AgentProvError as exc:
        issues.append(Issue("", exc.code, str(exc), "semantic"))
    return issues


def _semantic(issues: list[Issue], pointer: str, detail: str, code: str = "semantic") -> None:
    issues.append(Issue(pointer, code, detail, "semantic"))


def validate_manifest(obj: Mapping[str, Any]) -> list[Issue]:
    """Validate a ``corpus.json`` object (H.2.1(2)); an empty list means valid. See the module docstring."""
    fmt = obj.get("format") if isinstance(obj, Mapping) and obj.get("format") in MANIFESTS else FORMAT
    issues = _structural(MANIFESTS[str(fmt)], obj, DEFS_BY_FORMAT[str(fmt)])
    if issues or not isinstance(obj, Mapping):
        return issues
    try:
        check_corpus_json(obj)
    except ValueError as exc:
        _semantic(issues, "", str(exc), "corpus_json")
    sealed = obj["sealed"]
    if sealed and obj["release"]["status"] != "sealed":
        _semantic(issues, "/release/status", "a sealed manifest has release.status 'sealed'")
    if not sealed and obj["release"]["status"] == "sealed":
        _semantic(issues, "/sealed", "release.status 'sealed' needs sealed: true")
    created = obj["release"]["created"]
    if created is not None and obj["release"]["status"] == "dev":
        _semantic(issues, "/release/created", "dev builds write created: null (H.2.13)")
    if created is not None:
        try:
            datetime.datetime.fromisoformat(created.replace("Z", "+00:00"))
        except ValueError:
            _semantic(issues, "/release/created", "release.created names no real instant (H.2.13)")
    try:
        if content_digest(obj) != obj["content_digest"]:
            _semantic(issues, "/content_digest", "content_digest does not recompute (H.5.4)", "content_digest")
    except ValueError:
        pass
    counts = obj["counts"]
    if len(obj["sources"]) != 1:
        _semantic(issues, "/sources", "a corpus has exactly one source (H.1.1(1))")
    totals = Counter[str]()
    for s, source in enumerate(obj["sources"]):
        ids = [snap["snapshot_id"] for snap in source["snapshots"]]
        if len(set(ids)) != len(ids):
            _semantic(issues, f"/sources/{s}/snapshots", "snapshot ids are unique")
        for i, snap in enumerate(source["snapshots"]):
            c = snap["counts"]
            if c["candidates"] != c["executions"] + c["not_imported"]:
                _semantic(issues, f"/sources/{s}/snapshots/{i}/counts",
                          "candidates == executions + not_imported (H.2.3, H.6.1 R5)", "reconciliation")
            totals["not_imported"] += c["not_imported"]
            for code, n in c["selection_excluded"].items():
                totals[code] += n
        if source["profile"] not in obj["profiles"]["source"]:
            _semantic(issues, f"/sources/{s}/profile", "the source profile is listed in profiles.source")
    if counts["candidates"] != counts["executions"] + counts["not_imported"]:
        _semantic(issues, "/counts", "candidates == executions + not_imported", "reconciliation")
    if totals["not_imported"] != counts["not_imported"]:
        _semantic(issues, "/counts/not_imported", "the snapshots' not_imported add up to the corpus count", "reconciliation")
    excluded = {k: v for k, v in totals.items() if k != "not_imported"}
    if excluded != dict(counts["selection_excluded_by_code"]):
        _semantic(issues, "/counts/selection_excluded_by_code", "the snapshots' exclusions add up", "reconciliation")
    for group in ("by_unit", "by_status", "by_completeness", "execution_observed"):
        if sum(counts[group].values()) != counts["executions"]:
            _semantic(issues, f"/counts/{group}", "the tally adds up to counts.executions", "reconciliation")
    if sum(counts["not_imported_by_code"].values()) != counts["not_imported"] + sum(excluded.values()):
        _semantic(issues, "/counts/not_imported_by_code", "not_imported entries = not_imported + selection exclusions",
                  "reconciliation")
    if sum(fw["executions"] for fw in obj["framework_identities"]) > counts["executions"]:
        _semantic(issues, "/framework_identities", "more framework-identity executions than executions")
    expected_oracles = sorted(s for s in obj["prov_specs"] if s in ORACLE_SPECS)
    if sorted(o["spec"] for o in obj["oracle_specs"]) != expected_oracles:
        _semantic(issues, "/oracle_specs", "one entry per regression-oracle spec in prov_specs (R-55)")
    if len(set(obj["prov_specs"])) != len(obj["prov_specs"]) or "agentprov-prov/0.1" not in obj["prov_specs"]:
        _semantic(issues, "/prov_specs", "unique specs including agentprov-prov/0.1")
    licences = obj["licences"]
    if list(licences["restrictions"]) != sorted(set(licences["restrictions"])):
        _semantic(issues, "/licences/restrictions", "sorted and unique (H.2.10)")
    if licences["class"] != {"spdx": licences["derived"]["spdx"], "restrictions": licences["restrictions"]}:
        _semantic(issues, "/licences/class", "class = (derived.spdx, sorted restrictions) (AD-20(b))")
    if obj["producer"]["lockfile_sha256"] is None and "lockfile_absent_reason" not in obj["producer"]:
        _semantic(issues, "/producer/lockfile_sha256", "null only with lockfile_absent_reason (H.2.7)")
    for i, step in enumerate(obj["producer"].get("build_steps", ())):
        for problem in step_problems(step, with_stages=True):
            _semantic(issues, f"/producer/build_steps/{i}", problem + " (D-780)")
    if sealed and obj["producer"]["interpreter_advisory"] is not None:
        _semantic(issues, "/producer/interpreter_advisory", "a sealed corpus records no advisory (AD-16)")
    linkage = obj["validation"]["linkage"]
    if obj["validation"]["linkage_resolved_pct"] != (
            linkage_resolved_pct(linkage["resolved"], linkage["applicable"]) if linkage["resolved"] <= linkage["applicable"]
            else "invalid"):
        _semantic(issues, "/validation/linkage_resolved_pct", "does not recompute from validation.linkage (D-40)")
    if obj["validation"]["mode"] == "strict":
        for i, check in enumerate(obj["validation"]["checks"]):
            if check["skipped"]:
                _semantic(issues, f"/validation/checks/{i}", "strict mode: a gating check was skipped (H.2.12)")
    for i, ref in enumerate(obj["rule_catalogues"]):
        if any(not rid.startswith(ref["id"] + ".") for rid in ref["rules_used"]):
            _semantic(issues, f"/rule_catalogues/{i}/rules_used", "rule ids of this catalogue's namespace only")
        if list(ref["rules_used"]) != sorted(set(ref["rules_used"])):
            _semantic(issues, f"/rule_catalogues/{i}/rules_used", "sorted and unique")
    if obj["mode"] == "import" and obj["live"] is not None:
        _semantic(issues, "/live", "an import corpus has live: null")
    return issues


# ================================================================================================ builders: snapshot and counts
def glob_match(label: str, glob: str) -> bool:
    """The families' include/exclude matcher (equal to the importer's): ``fnmatch`` over a POSIX label, ``**/`` also
    matching zero directories."""
    if fnmatch.fnmatchcase(label, glob):
        return True
    return "**/" in glob and fnmatch.fnmatchcase(label, glob.replace("**/", "", 1))


def is_exclusion(entry: RegisterEntry, snapshot_id: str, exclude: Sequence[Mapping[str, Any]]) -> bool:
    """Whether a register entry records a selection exclusion of ``snapshot_id``: a ``select`` entry with a path subject
    of that snapshot whose path an exclude glob matches with the entry's own code (H.6.1 R1; D-33).

    A member of an archive input is registered as ``<archive>!/<chain label>``, but the importer matched the glob against
    the member's own label, the text after the last ``!/`` (``_glob_label``; D-380, D-560); that label is tried too."""
    subject = entry.subject
    if entry.stage != "select" or entry.disposition != "not_imported" or set(subject) != {"snapshot_id", "path"}:
        return False
    if subject["snapshot_id"] != snapshot_id:
        return False
    path = subject["path"]
    labels = (path, path.rsplit("!/", 1)[1]) if "!/" in path else (path,)
    return any(str(e["code"]) == entry.code and any(glob_match(label, str(e["glob"])) for label in labels) for e in exclude)


def _entry_snapshot(entry: RegisterEntry, rows_by_ex: Mapping[str, IndexRow], snapshot_ids: Sequence[str]) -> str | None:
    subject = entry.subject
    if "snapshot_id" in subject:
        return subject["snapshot_id"]
    if "ex" in subject and subject["ex"] in rows_by_ex:
        ids = rows_by_ex[subject["ex"]].snapshot_ids
        return ids[0] if len(ids) == 1 else None
    return snapshot_ids[0] if len(snapshot_ids) == 1 else None


def snapshot_counts(
    rows: Sequence[IndexRow], register: Sequence[RegisterEntry], snapshot_id: str, exclude: Sequence[Mapping[str, Any]],
    *, all_snapshots: Sequence[str],
) -> dict[str, Any]:
    """The H.2.3 snapshot ``counts`` recomputed from the index and the register (D-33; see the module docstring).

    A ``not_imported`` entry whose snapshot cannot be told (a source-key subject in a multi-snapshot corpus) is refused
    with :class:`ManifestError`: it would make the reconciliation unverifiable.
    """
    rows_by_ex = {r.ex: r for r in rows}
    executions = sum(1 for r in rows if snapshot_id in r.snapshot_ids)
    not_imported = 0
    excluded: Counter[str] = Counter()
    for entry in register:
        if entry.disposition != "not_imported":
            continue
        owner = _entry_snapshot(entry, rows_by_ex, all_snapshots)
        if owner is None:
            raise ManifestError("a not_imported register entry belongs to no single snapshot; counts cannot reconcile",
                                code="corpus.manifest.unattributed")
        if owner != snapshot_id:
            continue
        if is_exclusion(entry, snapshot_id, exclude):
            excluded[entry.code] += 1
        else:
            not_imported += 1
    return {"candidates": executions + not_imported, "executions": executions, "not_imported": not_imported,
            "selection_excluded": dict(sorted(excluded.items()))}  # fmt: skip


def _zero(keys: Iterable[str]) -> dict[str, int]:
    return dict.fromkeys(keys, 0)


def _stage_tally(values: Iterable[str]) -> dict[str, int]:
    out = _zero(STAGE_STATES)
    for value in values:
        out[value] += 1
    return out


def corpus_counts(
    rows: Sequence[IndexRow], register: Sequence[RegisterEntry], members: Sequence[MemberRow],
    snapshots: Sequence[Mapping[str, Any]], stats: AerStats,
) -> dict[str, Any]:
    """The H.2.9 ``counts`` from the index, the register, ``raw/members.jsonl``, the recomputed snapshot counts and one
    pass over the AERs (``stats``). Every value is an integer and every tally covers all index rows."""
    by_unit, by_status, by_completeness = _zero(UNITS), _zero(STATUSES), _zero(COMPLETENESS)
    observed = {"true": 0, "false": 0}
    for row in rows:
        by_unit[row.unit] += 1
        by_status[row.status] += 1
        by_completeness[row.completeness] += 1
        observed["true" if row.execution_observed else "false"] += 1
    sem_specs = sorted({p for r in rows for p in (r.sem or {})})
    prov_specs = sorted({p for r in rows for p in (r.prov or {})})
    containers = sorted({m.container for m in members})
    # A failed container writes no members.jsonl row, so ``containers`` holds only successes; failures are distinct
    # (snapshot, source key or path) pairs among the expand error entries.
    expand_failed = {(e.subject.get("snapshot_id", ""), e.subject.get("source_key", e.subject.get("path", "")))
                     for e in register if e.stage == "expand" and e.severity == "error"}  # fmt: skip
    by_stage = {
        "expand": {"ok": len(containers), "failed": len(expand_failed)},
        "aer": _stage_tally(r.stages["aer"] for r in rows),
        "sem": {p: _stage_tally(r.sem[p].state for r in rows if r.sem and p in r.sem) for p in sem_specs},
        "prov": {p: _stage_tally(r.prov[p].state for r in rows if r.prov and p in r.prov) for p in prov_specs},
        "validation": _stage_tally(r.validation.state for r in rows if r.validation is not None),
    }
    not_imported = sum(s["counts"]["not_imported"] for s in snapshots)
    excluded: Counter[str] = Counter()
    for s in snapshots:
        excluded.update(s["counts"]["selection_excluded"])
    member_counts = None
    if members:
        tally = Counter(m.disposition for m in members)
        member_counts = {"containers": len(containers), "not_selected": tally["not_selected"], "rejected": tally["rejected"],
                         "selected": tally["selected"]}  # fmt: skip
    attempts = None
    live_rows = [r for r in rows if r.attempt is not None]
    if live_rows:
        attempts = {"cells": len({r.ex for r in live_rows}), "executions": len(live_rows),
                    "max_attempt": max(r.attempt or 0 for r in live_rows)}  # fmt: skip
    return {
        "candidates": len(rows) + not_imported,
        "executions": len(rows),
        "not_imported": not_imported,
        "by_unit": by_unit,
        "by_status": by_status,
        "by_completeness": by_completeness,
        "execution_observed": observed,
        "by_stage": by_stage,
        "issues_by_code": dict(sorted(Counter(e.code for e in register).items())),
        "not_imported_by_code": dict(sorted(Counter(e.code for e in register if e.disposition == "not_imported").items())),
        "selection_excluded_by_code": dict(sorted(excluded.items())),
        "records_by_kind": {k: stats.records_by_kind[k] for k in RECORD_KINDS},
        "generic_types": {kind: dict(sorted(stats.generic_types[kind].items())) for kind in ("activity", "artefact")},
        "members": member_counts,
        "attempts": attempts,
    }


def duplicate_summary(rows: Sequence[IndexRow], register: Sequence[RegisterEntry]) -> dict[str, Any]:
    """The ``duplicates`` summary (H.7; D-41): computed tallies only; the declared duplicates themselves are the
    profile's ``[lineage]`` (``sources[].lineage``). ``content_dedup`` is ``never`` in v0.1 (AD-10 row 7)."""
    return {
        "collapsed": sum(1 for e in register if e.code == "dedup.collapsed"),
        "content_dedup": "never",
        "multi_origin_executions": sum(1 for r in rows if r.n_origins > 1),
        "multi_snapshot_executions": sum(1 for r in rows if len(r.snapshot_ids) > 1),
        "owned_elsewhere": sum(1 for e in register if e.code == "select.owned_elsewhere"),
    }


def snapshot_origin_from_pin(pin: Mapping[str, Any] | None, object_origins: Iterable[Mapping[str, Any]], *,
                             corpus_format: str = FORMAT) -> dict[str, Any]:
    """The sealed snapshot origin (H.2.3; D-33), built from the pin recorded in the working manifest and the object-level
    origins the pin vouched for (those of the snapshot's primary objects, with every ``member`` and ``carved``
    origin followed to the root of its chain: :func:`agentprov.corpus.package.snapshot_object_origins`).

    * objects with ``corpus`` origins (the AgentDojo-PROV release, R-26): ``{kind: corpus, corpus, version,
      producer_commit}``, whose producer commit must equal the pin's commit;
    * objects with ``git`` origins: ``{kind: git, repo, commit, subtree}`` (``subtree`` the pin's tree without a trailing
      ``/``, ``""`` for the whole commit; ``subtree_sha1`` when the pin records the tree id); the repository is the pin's,
      else the single repository of the objects at the pinned commit.

    * an archive input of a Zenodo pin (D-200): ``{kind: zenodo, doi, file, md5?}``, when the one non-member object is
      the pinned file (``zenodo`` origin with the pin's DOI and file) and every other object is one of its members;
    * an archive input of a Hugging Face pin (D-249): ``{kind: hf, dataset, revision, gated, path}``, with ``gated``
      recorded in the pin;
    * an archive input of a URL pin (D-455): ``{kind: url, url, retrieved_at}``, with ``retrieved_at`` the retrieval time
      the working pin records and the one non-member object the pinned URL's file (``url`` origin retrieved that day);
    * an archive input stored as byte parts (D-249) of a Hugging Face pin: ``{kind: hf, dataset, revision, gated, path}``
      with ``path`` the directory that holds every part (omitted when they share none), when the one non-member object is
      the split descriptor whose ``split`` origin lists the pin's part digests in order. The parts themselves are named
      by their object origins in ``raw/origins.jsonl``. Under ``agentprov-corpus/0.2`` (D-217) the origin also lists
      ``parts`` (``{file, bytes, sha256, md5?}`` in the pin's order), and a Zenodo split snapshot seals as ``{kind: zenodo,
      doi, file, parts}`` with ``file`` the logical archive; under the frozen ``agentprov-corpus/0.1`` (D-163) a Zenodo
      split snapshot is refused, as its schema has no ``parts``.

    :class:`ManifestError` without a pin, for an unpinned commit, for a ``local`` object origin (development only: the
    pin did not vouch for it), and for objects whose origins disagree with the pin.
    """
    if pin and pin.get("archive") == "split-zip" and pin.get("kind") in ("zenodo", "hf"):
        return _split_snapshot_origin(pin, object_origins, corpus_format=corpus_format)
    if pin and pin.get("kind") == "zenodo":
        return _zenodo_snapshot_origin(pin, object_origins)
    if pin and pin.get("kind") == "hf":
        return _hf_snapshot_origin(pin, object_origins)
    if pin and pin.get("kind") == "url":
        return _url_snapshot_origin(pin, object_origins)
    if not pin or pin.get("kind") != "git" or not isinstance(pin.get("commit"), str) or len(str(pin["commit"])) != 40:
        raise ManifestError("the working corpus records no pinned git commit; a sealed snapshot origin needs one (D-33)",
                            code="corpus.manifest.unpinned")
    commit = str(pin["commit"])
    kinds: Counter[str] = Counter()
    repos: set[str] = set()
    corpora: set[tuple[str, str, str]] = set()
    for origin in object_origins:
        kind = str(origin.get("kind"))
        kinds[kind] += 1
        if kind == "git":
            if origin.get("commit") != commit:
                raise ManifestError("an object's git origin names another commit than the pin", code="corpus.manifest.pin")
            repos.add(str(origin.get("repo")))
        elif kind == "corpus":
            corpora.add((str(origin.get("corpus")), str(origin.get("version")), str(origin.get("producer_commit"))))
    if kinds["local"]:
        raise ManifestError("an object origin is local: the pin did not vouch for it; release refuses local origins",
                            code="corpus.manifest.local_origin")
    if set(kinds) - {"git", "corpus", "member"} or (kinds["git"] and kinds["corpus"]):
        raise ManifestError("the snapshot's object origins are of mixed or unsupported kinds", code="corpus.manifest.pin")
    if kinds["corpus"]:
        if len(corpora) != 1 or next(iter(corpora))[2] != commit:
            raise ManifestError("the corpus origins disagree with each other or with the pin", code="corpus.manifest.pin")
        name, version, producer = next(iter(corpora))
        return {"corpus": name, "kind": "corpus", "producer_commit": producer, "version": version}
    repo = pin.get("repo")
    if repo is None:
        if len(repos) != 1:
            raise ManifestError("the pin names no repository and the objects do not name exactly one",
                                code="corpus.manifest.pin")
        repo = next(iter(repos))
    elif repos and repos != {repo}:
        raise ManifestError("an object's repository differs from the pin's", code="corpus.manifest.pin")
    out: dict[str, Any] = {"commit": commit, "kind": "git", "repo": str(repo),
                           "subtree": str(pin.get("tree") or "").strip("/")}  # fmt: skip
    if isinstance(pin.get("tree_sha1"), str):
        out["subtree_sha1"] = pin["tree_sha1"]
    return out


def origin_matches_pin(origin: Mapping[str, Any], pin: Mapping[str, Any] | None) -> bool:
    """Whether an object-level origin (``{"kind": ..., ...}``) was vouched for by a snapshot's recorded pin (D-202): a
    ``git`` origin at the pinned commit, a ``corpus`` origin whose producer commit is the pinned (listing) commit, a
    ``zenodo`` origin of the pinned DOI and file, an ``hf`` origin at the pinned revision. In a corpus with several
    snapshots this tells which snapshot an origin row belongs to (``raw/origins.jsonl`` rows carry no snapshot id)."""
    if not pin:
        return False
    kind = origin.get("kind")
    if kind == "git":
        return pin.get("kind") == "git" and origin.get("commit") == pin.get("commit")
    if kind == "corpus":
        return isinstance(pin.get("commit"), str) and origin.get("producer_commit") == pin.get("commit")
    # "split-zip" is the only split archive kind (D-249); parts of a tar (or any other format) would need a new value
    # here and in _split_snapshot_origin, as well as in raw.fetch.SPLIT_ZIP and the split origin's ``archive``.
    parts = pin.get("parts") if pin.get("archive") == "split-zip" else None
    part_files = {p.get("file") for p in parts if isinstance(p, Mapping)} if isinstance(parts, list) else set()
    if kind == "zenodo":
        if pin.get("kind") != "zenodo" or origin.get("doi") != pin.get("doi"):
            return False
        return origin.get("file") in part_files if parts is not None else origin.get("file") == pin.get("file")
    if kind == "hf":
        return pin.get("kind") == "hf" and origin.get("revision") == pin.get("revision")
    if kind == "url":  # D-455
        return pin.get("kind") == "url" and origin.get("url") == pin.get("url")
    if kind == "split":  # D-249: the split descriptor of exactly the pin's parts, in the pin's order
        return isinstance(parts, list) and origin.get("parts") == _pin_part_digests(parts)
    return False


def sealed_origin_pin(origin: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """The fields of a sealed snapshot origin (H.2.3) that :func:`origin_matches_pin` reads, as a pin-shaped mapping, or
    ``None`` for a kind it cannot match (D-221). A re-map of a sealed ``agentprov-corpus/0.2`` corpus tells a context
    tree's objects from the others by the role's sealed origin, and one snapshot's objects from another's (D-202) by the
    snapshot's sealed origin, because a sealed manifest records no pin; the mapping is used only for that match and is
    never recorded as a pin."""
    if not isinstance(origin, Mapping):
        return None
    kind = origin.get("kind")
    view: dict[str, Any]
    if kind == "git":
        view = {"kind": "git", "commit": origin.get("commit")}
    elif kind == "zenodo":
        view = {"kind": "zenodo", "doi": origin.get("doi"), "file": origin.get("file")}
    elif kind == "hf":
        view = {"kind": "hf", "revision": origin.get("revision")}
    elif kind == "corpus":
        view = {"commit": origin.get("producer_commit")}
    elif kind == "url":  # D-455: the pinned URL (its retrieval time is not part of the match)
        view = {"kind": "url", "url": origin.get("url")}
    else:
        return None
    parts = origin.get("parts")
    if isinstance(parts, list) and kind in ("zenodo", "hf"):  # D-217: a split archive's parts, in the pin's order
        view.update(archive="split-zip", parts=[{"file": p.get("file"), "sha256": p.get("sha256")} for p in parts
                                                if isinstance(p, Mapping)])
    return view


def _pin_part_digests(parts: Sequence[Any]) -> list[str]:
    return [str(p.get("sha256", "")).removeprefix("sha256:") if isinstance(p, Mapping) else "" for p in parts]


def _split_snapshot_origin(pin: Mapping[str, Any], object_origins: Iterable[Mapping[str, Any]], *,
                           corpus_format: str) -> dict[str, Any]:
    """The sealed origin of a snapshot imported from an archive stored as byte parts (D-249; H.2.3).

    Only ``archive = "split-zip"`` pins reach this (see :func:`origin_matches_pin`); parts of another archive format would
    need a new ``archive`` value here too.
    """
    parts, file = pin.get("parts"), pin.get("file")
    if not isinstance(parts, list) or len(parts) < 2 or not isinstance(file, str):
        raise ManifestError("the working corpus's split pin names no logical file and parts", code="corpus.manifest.unpinned")
    kinds: Counter[str] = Counter()
    for origin in object_origins:
        kind = str(origin.get("kind"))
        kinds[kind] += 1
        if kind == "split" and origin.get("parts") != _pin_part_digests(parts):
            raise ManifestError("the split descriptor's parts differ from the pin's", code="corpus.manifest.pin")
    if kinds["local"]:
        raise ManifestError("an object origin is local: the pin did not vouch for it; release refuses local origins",
                            code="corpus.manifest.local_origin")
    if set(kinds) - {"split", "member"} or kinds["split"] != 1:
        raise ManifestError("a split snapshot holds its descriptor and that archive's members only", code="corpus.manifest.pin")
    with_parts = corpus_format != "agentprov-corpus/0.1"  # D-217: corpus/0.2 names the parts
    if pin.get("kind") == "zenodo":
        if not with_parts:
            raise ManifestError("a Zenodo snapshot of an archive in byte parts cannot be sealed under corpus-0.1: the "
                                "sealed zenodo origin names one file and the frozen schema has no parts (D-163, D-249)",
                                code="corpus.manifest.pin")
        doi = pin.get("doi")
        if not isinstance(doi, str):
            raise ManifestError("the working corpus's Zenodo split pin names no DOI", code="corpus.manifest.unpinned")
        return {"doi": doi, "file": file, "kind": "zenodo", "parts": _sealed_parts(parts)}
    files = [str(p.get("file")) for p in parts if isinstance(p, Mapping)]
    common = posixpath.commonpath(files) if all("/" in f for f in files) else ""
    out = _hf_identity(pin)
    if common and common not in files:
        out["path"] = common
    if with_parts:
        out["parts"] = _sealed_parts(parts)
    return out


def _sealed_parts(parts: Sequence[Any]) -> list[dict[str, Any]]:
    """A split pin's parts as a sealed ``agentprov-corpus/0.2`` origin lists them (D-217): ``{file, bytes, sha256,
    md5?}`` in the pin's order, ``sha256`` prefixed."""
    out = []
    for part in parts:
        size = part.get("bytes", part.get("size")) if isinstance(part, Mapping) else None  # raw.fetch takes either key
        if not isinstance(part, Mapping) or not isinstance(part.get("file"), str) or not isinstance(size, int) \
                or isinstance(size, bool):
            raise ManifestError("a split pin's part names no file and size", code="corpus.manifest.pin")
        sealed = {"bytes": size, "file": part["file"],
                  "sha256": "sha256:" + str(part.get("sha256", "")).removeprefix("sha256:")}
        if isinstance(part.get("md5"), str):
            sealed["md5"] = part["md5"]
        out.append(sealed)
    return out


def _hf_identity(pin: Mapping[str, Any]) -> dict[str, Any]:
    dataset, revision, gated = pin.get("repo", pin.get("dataset")), pin.get("revision"), pin.get("gated")
    if not isinstance(dataset, str) or not isinstance(revision, str) or len(revision) != 40:
        raise ManifestError("the working corpus's Hugging Face pin names no dataset and revision", code="corpus.manifest.unpinned")
    if not isinstance(gated, bool):
        raise ManifestError("the Hugging Face pin does not record whether the dataset is gated (H.2.3 gated)",
                            code="corpus.manifest.pin")
    return {"dataset": dataset, "gated": gated, "kind": "hf", "revision": revision}


def _hf_snapshot_origin(pin: Mapping[str, Any], object_origins: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """The sealed origin of a snapshot imported from one Hugging Face file (D-200, D-249; H.2.3 ``hf``)."""
    identity = _hf_identity(pin)
    file = pin.get("file", pin.get("path"))
    if not isinstance(file, str):
        raise ManifestError("the working corpus's Hugging Face pin names no file", code="corpus.manifest.unpinned")
    kinds: Counter[str] = Counter()
    for origin in object_origins:
        kind = str(origin.get("kind"))
        kinds[kind] += 1
        if kind == "hf" and (origin.get("revision"), origin.get("path")) != (identity["revision"], file):
            raise ManifestError("an object's Hugging Face origin names another revision or file than the pin",
                                code="corpus.manifest.pin")
    if kinds["local"]:
        raise ManifestError("an object origin is local: the pin did not vouch for it; release refuses local origins",
                            code="corpus.manifest.local_origin")
    if set(kinds) - {"hf", "member"} or kinds["hf"] != 1:
        raise ManifestError("a Hugging Face snapshot holds its pinned file and that file's members only",
                            code="corpus.manifest.pin")
    return {**identity, "path": file}


def _zenodo_snapshot_origin(pin: Mapping[str, Any], object_origins: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """The sealed origin of a snapshot imported from one Zenodo file (D-200; H.2.3 ``zenodo``)."""
    doi, file = pin.get("doi"), pin.get("file")
    if not isinstance(doi, str) or not isinstance(file, str):
        raise ManifestError("the working corpus's Zenodo pin names no DOI and file", code="corpus.manifest.unpinned")
    kinds: Counter[str] = Counter()
    for origin in object_origins:
        kind = str(origin.get("kind"))
        kinds[kind] += 1
        if kind == "zenodo" and (origin.get("doi"), origin.get("file")) != (doi, file):
            raise ManifestError("an object's Zenodo origin names another DOI or file than the pin", code="corpus.manifest.pin")
    if kinds["local"]:
        raise ManifestError("an object origin is local: the pin did not vouch for it; release refuses local origins",
                            code="corpus.manifest.local_origin")
    if set(kinds) - {"zenodo", "member"} or kinds["zenodo"] != 1:
        raise ManifestError("a Zenodo snapshot holds its pinned file and that file's members only", code="corpus.manifest.pin")
    out: dict[str, Any] = {"doi": doi, "file": file, "kind": "zenodo"}
    if isinstance(pin.get("md5"), str):
        out["md5"] = pin["md5"]
    return out


def _url_snapshot_origin(pin: Mapping[str, Any], object_origins: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """The sealed origin of a snapshot imported from one URL file (D-455; H.2.3 ``url``: ``retrieved_at`` is REQUIRED
    because the origin is mutable). The retrieval time is the one the working pin recorded, never the time of the seal."""
    url, retrieved_at = pin.get("url"), pin.get("retrieved_at")
    if not isinstance(url, str) or not isinstance(retrieved_at, str) or re.fullmatch(RFC3339_UTC, retrieved_at) is None:
        raise ManifestError("the working corpus's URL pin names no URL and retrieval time", code="corpus.manifest.unpinned")
    kinds: Counter[str] = Counter()
    for origin in object_origins:
        kind = str(origin.get("kind"))
        kinds[kind] += 1
        if kind == "url" and (origin.get("url"), origin.get("retrieved")) != (url, retrieved_at[:10]):
            raise ManifestError("an object's URL origin names another URL or retrieval date than the pin",
                                code="corpus.manifest.pin")
    if kinds["local"]:
        raise ManifestError("an object origin is local: the pin did not vouch for it; release refuses local origins",
                            code="corpus.manifest.local_origin")
    if set(kinds) - {"url", "member"} or kinds["url"] != 1:
        raise ManifestError("a URL snapshot holds its pinned file and that file's members only", code="corpus.manifest.pin")
    return {"kind": "url", "retrieved_at": retrieved_at, "url": url}


# ================================================================================================ builders: one AER pass
@dataclass
class AerStats:
    """Accumulates, over every execution, what the manifest computes from AER, SEM and PROV (see the module docstring).

    Feed each execution once with :meth:`add` (its verified AER, its SEM documents and its parsed PROV documents);
    the results are independent of the order of the calls.
    """

    records_by_kind: Counter[str] = field(default_factory=Counter)
    generic_types: dict[str, Counter[str]] = field(default_factory=lambda: {"activity": Counter(), "artefact": Counter()})
    models: Counter[bytes] = field(default_factory=Counter)
    frameworks: dict[bytes, dict[str, Any]] = field(default_factory=dict)
    rules_used: set[str] = field(default_factory=set)

    def add(self, aer: AerDocument, sem: Mapping[str, SemDocument] | None = None, prov: Iterable[Any] = ()) -> None:
        for record in aer.records:  # the header (k: execution) and every record before the seal
            self.records_by_kind[str(record.get("k"))] += 1
            if record.get("k") in ("activity", "artefact") and isinstance(record.get("type"), str):
                self.generic_types[str(record["k"])][record["type"]] += 1
            _collect_rules(record, self.rules_used, ("rule",))
        self.records_by_kind["seal"] += 1
        _collect_rules(aer.seal, self.rules_used, ("rule", "id"))
        for doc in (sem or {}).values():
            for annotation in doc.records:
                _collect_rules(annotation, self.rules_used, ("rule",))
            _collect_rules(doc.seal, self.rules_used, ("rule",))
        for document in prov:
            _collect_rules(document, self.rules_used, _PROV_RULE_KEYS)
        for summary in _model_summaries(aer):
            self.models[jcs_bytes(summary)] += 1
        identity = framework_identity(aer)
        if identity is not None:
            entry = self.frameworks.setdefault(jcs_bytes(identity), {"executions": 0, "system_prompt_sha256": Counter(),
                                                                     "tool_definitions_sha256": Counter()})
            entry["executions"] += 1
            digests = _fw_digests(aer)
            for name in ("tool_definitions_sha256", "system_prompt_sha256"):
                value = digests[name]
                entry[name][(value, digests["_ev"].get(name)) if value else None] += 1

    def model_summaries(self) -> list[dict[str, Any]]:
        """H.2.8 summaries, one per distinct (requested, served, provider, ev), with their execution counts, sorted."""
        out = [{**json.loads(key), "executions": n} for key, n in self.models.items()]
        return sorted(out, key=jcs_bytes)

    def framework_identities(self) -> list[dict[str, Any]]:
        """H.2.4 identities, one per ``fw`` and observed core (distribution, reported version, source, suite set), with
        their execution counts. ``tool_definitions_sha256`` and ``system_prompt_sha256`` name the framework's default:
        they are set only when **every** execution of the identity records the same single digest (a corpus whose tasks
        offer different tool subsets, or whose runs use several prompts, has no single default: ``null``)."""
        out = []
        for key, entry in self.frameworks.items():
            identity = json.loads(key)
            ev = dict(identity["ev"])
            for name in ("tool_definitions_sha256", "system_prompt_sha256"):
                seen = entry[name]
                identity[name] = None
                if len(seen) == 1 and None not in seen:
                    (digest, cls), = seen
                    identity[name] = digest
                    if cls is not None:
                        ev[name] = cls
            identity["ev"] = dict(sorted(ev.items()))
            identity["executions"] = entry["executions"]
            out.append(identity)
        return sorted(out, key=lambda d: (d["fw"], jcs_bytes(d)))


_PROV_RULE_KEYS: Final = ("apv:rule", "apv:basisRule", "apv:method", "apv:policy", "apv:rulePointer")


def _collect_rules(value: Any, out: set[str], keys: Sequence[str]) -> None:
    """Every rule id under a member named in ``keys`` anywhere in ``value`` (iterative); the ``#…`` scope is dropped."""
    stack: list[Any] = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, Mapping):
            for key, child in item.items():
                if key in keys:
                    _take_rule(child, out)
                if isinstance(child, Mapping | list):
                    stack.append(child)
        elif isinstance(item, list):
            stack.extend(child for child in item if isinstance(child, Mapping | list))


def _take_rule(value: Any, out: set[str]) -> None:
    if isinstance(value, str):
        if RULE_REF_RE.fullmatch(value):
            out.add(value.split("#", 1)[0])
    elif isinstance(value, list):
        for v in value:
            _take_rule(v, out)
    elif isinstance(value, Mapping) and isinstance(value.get("$"), str):  # PROV-JSON typed literal
        _take_rule(value["$"], out)


def _tag(record: Mapping[str, Any], pointer: str) -> str:
    from agentprov.aer.evidence import effective_tag, tag_class

    return tag_class(effective_tag(record, pointer))


def _unknown(record: Mapping[str, Any], pointer: str) -> bool:
    unk = record.get("unk")
    return isinstance(unk, Mapping) and any(isinstance(k, str) and (k == pointer or pointer.startswith(k + "/")) for k in unk)


def _model_summaries(aer: AerDocument) -> list[dict[str, Any]]:
    """The H.2.8 keys of one execution: one per ``llm_agent`` actor (``executions`` is added by the aggregate). The served
    model is listed only when the AER records it (provider-reported, CAP-6)."""
    out: list[dict[str, Any]] = []
    seen: set[bytes] = set()
    for actor in aer.records:
        if actor.get("k") != "actor" or actor.get("kind") != "llm_agent":
            continue
        raw_model = actor.get("model")
        model: Mapping[str, Any] = raw_model if isinstance(raw_model, Mapping) else {}
        requested = model.get("requested") if isinstance(model.get("requested"), str) and not _unknown(actor, "/model/requested") else None
        served_value = model.get("served") if not _unknown(actor, "/model/served") else None
        served = sorted({served_value} if isinstance(served_value, str) else set())
        provider = model.get("provider") if isinstance(model.get("provider"), str) and not _unknown(actor, "/model/provider") else None
        summary = {
            "ev": {"requested": None if requested is None else _tag(actor, "/model/requested"),
                   "served": "O" if served else None},
            "provider": provider,
            "requested": requested,
            "served": served,
        }  # fmt: skip
        key = jcs_bytes(summary)
        if key not in seen:
            seen.add(key)
            out.append(summary)
    return out


def _content_digest(value: Any) -> str | None:
    """``sha256:`` of the JCS of a fixture's content; a blob reference is identified by its own digest."""
    if isinstance(value, Mapping) and set(value) >= {"$blob"} and isinstance(value.get("$blob"), str):
        blob = str(value["$blob"])
        return blob if blob.startswith("sha256:") else "sha256:" + blob
    try:
        return "sha256:" + sha256_hex(jcs_bytes(value))
    except (TypeError, ValueError):
        return None


def _single(values: Iterable[tuple[str, str]]) -> tuple[str, str] | None:
    distinct = {digest: cls for digest, cls in values}
    if len(distinct) != 1:
        return None
    return next(iter(distinct.items()))


def _fw_digests(aer: AerDocument) -> dict[str, Any]:
    """``tool_definitions_sha256`` and ``system_prompt_sha256`` of one execution (H.2.4), with their evidence classes.

    * tool definitions: the content of the ``tool_definitions`` fixtures (JCS digest; a blob by its digest);
    * system prompt: the content of a ``system_prompt`` fixture, else the parts of the ``system`` messages (JCS digest
      of the ``parts`` array).

    A value is set only when the execution records **exactly one** distinct digest (several distinct tool lists or
    prompts in one execution name no single default); ``null`` otherwise, never inferred.
    """
    tools: list[tuple[str, str]] = []
    prompts: list[tuple[str, str]] = []
    messages: list[tuple[str, str]] = []
    for record in aer.records:
        kind = record.get("k")
        if kind == "fixture" and "content" in record and not _unknown(record, "/content"):
            digest = _content_digest(record["content"])
            if digest is None:
                continue
            if record.get("kind") == "tool_definitions":
                tools.append((digest, _tag(record, "/content")))
            elif record.get("kind") == "system_prompt":
                prompts.append((digest, _tag(record, "/content")))
        elif kind == "message" and record.get("role") == "system" and isinstance(record.get("parts"), list):
            if not _unknown(record, "/parts"):
                messages.append(("sha256:" + sha256_hex(jcs_bytes(record["parts"])), _tag(record, "/parts")))
    out: dict[str, Any] = {"tool_definitions_sha256": None, "system_prompt_sha256": None}
    tool = _single(tools)
    prompt = _single(prompts) if prompts else _single(messages)
    ev: dict[str, str] = {}
    if tool is not None:
        out["tool_definitions_sha256"], ev["tool_definitions_sha256"] = tool
    if prompt is not None:
        out["system_prompt_sha256"], ev["system_prompt_sha256"] = prompt
    out["_ev"] = ev
    return out


# ================================================================================================ builders: digests, files
def file_ref(path: str, data: bytes, *, jsonl: bool) -> dict[str, Any]:
    """A ``FileRef`` (H.2.11): path, ``sha256:`` of the bytes, size, and the line count of a JSONL file."""
    return {"bytes": len(data), "lines": data.count(b"\n") if jsonl else None, "path": path,
            "sha256": "sha256:" + hashlib.sha256(data).hexdigest()}  # fmt: skip


def raw_dispositions(stored: Iterable[str], withheld: Iterable[str] = (), referenced: Iterable[str] = ()) -> list[
        tuple[str, str]]:
    """The ``(sha256:<hex>, disposition)`` pairs of ``digests.raw_set`` (H.2.11) from bare hex digests: every stored
    object ``included`` unless the corpus withholds it, every ``WITHHELD.json`` object ``withheld`` (H.4.5; D-230) and
    every ``raw/REFERENCES.json`` object ``referenced`` (H.4.3; D-237). Sealing and ``verify --level chain`` both use it."""
    held = set(withheld)
    return sorted([*(("sha256:" + sha, "included") for sha in set(stored) - held),
                   *(("sha256:" + sha, "withheld") for sha in held),
                   *(("sha256:" + sha, "referenced") for sha in set(referenced))])


def digests_of(
    rows: Sequence[IndexRow], raw_objects: Iterable[tuple[str, str]], *, index_bytes: bytes, register_bytes: bytes,
    members_bytes: bytes,
) -> dict[str, Any]:
    """H.2.11 ``digests``. ``raw_objects`` yields ``(sha256:<hex>, disposition)`` for every raw object (included,
    referenced, withheld; members and blobs included)."""
    sem_profiles = sorted({p for r in rows for p, out in (r.sem or {}).items() if out.digest is not None})
    prov_specs = sorted({p for r in rows for p, out in (r.prov or {}).items() if out.digest is not None})
    return {
        "aer_set": set_digest((r.ex, "sha256:" + r.aer_digest) for r in rows),
        "index": "sha256:" + hashlib.sha256(index_bytes).hexdigest(),
        "members": "sha256:" + hashlib.sha256(members_bytes).hexdigest(),
        "prov_set": {
            spec: {"json": set_digest((r.ex, "sha256:" + str(r.prov[spec].digest)) for r in rows
                                      if r.prov and spec in r.prov and r.prov[spec].digest is not None)}
            for spec in prov_specs
        },  # fmt: skip
        "raw_set": set_digest(raw_objects),
        "register": "sha256:" + hashlib.sha256(register_bytes).hexdigest(),
        "sem_set": {
            p: set_digest((r.ex, "sha256:" + str(r.sem[p].digest)) for r in rows if r.sem and p in r.sem and r.sem[p].digest)
            for p in sem_profiles
        },
        "validation_set": set_digest(
            (r.ex, "sha256:" + r.validation.digest) for r in rows if r.validation is not None and r.validation.digest
        ),
    }


def _check_meta(check_id: str, stage_checks: Sequence[str], aer_format: str = "aer/0.1") -> tuple[str, int]:
    """``(version, tier)`` of one validation check id (D-40): the AER validator is tier 2 at the corpus's AER format
    (``aer/0.1`` or ``aer/0.2``, D-212); a SEM check
    ``<profile>@<n>:<id>`` is tier 3 at its profile; every other check is a tier-4 check of the recorded PROV spec."""
    if check_id == "aer.validator":
        return aer_format, 2
    head, sep, _ = check_id.partition(":")
    if sep and "@" in head:
        return head, 3
    specs = [c.removeprefix("tier4:") for c in stage_checks if c.startswith("tier4:")]
    return (specs[0] if len(specs) == 1 else "agentprov-prov/0.1"), 4


LINKAGE_PREFIX: Final = "pv.linkage."
_PASSING: Final = frozenset({"pass", "not_applicable"})


def linkage_resolved_pct(resolved: int, applicable: int) -> dict[str, str] | None:
    """``{"$dec": "<pct>"}``: ``floor(10000 * resolved / applicable) / 100`` with two decimals (D-40), so that
    ``"100.00"`` is written exactly when every applicable execution resolves; ``None`` when nothing is applicable.
    A decimal string, not a float: corpus-layer JSON holds no floating-point number (H.1.4(3); D-34 ``$dec``)."""
    if applicable <= 0:
        return None
    if resolved < 0 or resolved > applicable:
        raise ValueError("resolved executions lie in [0, applicable]")
    hundredths = (10000 * resolved) // applicable
    return {"$dec": f"{hundredths // 100}.{hundredths % 100:02d}"}


def validation_summary(summary: Mapping[str, Any], stage: Mapping[str, Any],
                       results: Iterable[Mapping[str, Any]] = (), *, aer_format: str = "aer/0.2") -> dict[str, Any]:
    """The H.2.12 ``ValidationSummary`` (D-40).

    * ``mode``: ``strict`` when the validation stage of ``derivation.json`` ran in release mode, else ``dev``;
    * ``checks``: one entry per check id of ``validation/summary.json`` with its counts, its ``version`` and ``tier``
      (:func:`_check_meta`); ``libraries``: the stage's serialiser and validator versions;
    * ``tiers``: per tier, the check count, the summed check results, the executions with a result row and the executions
      whose every check of that tier is ``pass`` or ``not_applicable`` (``executions_passed``), from ``results`` (the rows
      of ``validation/results.jsonl``);
    * ``linkage`` and ``linkage_resolved_pct`` (claim ``c1-linkage``): an execution is *applicable* when at least one
      ``pv.linkage.*`` check is not ``not_applicable`` for it, and *resolved* when it is applicable and every
      ``pv.linkage.*`` check is ``pass`` or ``not_applicable``; ``linkage_resolved_pct`` is
      :func:`linkage_resolved_pct` of the two counts. A skipped linkage check never resolves (D8).
    """
    stage_checks = [str(c) for c in stage.get("checks", ())]
    checks: list[dict[str, Any]] = []
    tier_of: dict[str, int] = {}
    for entry in summary.get("checks", ()):
        version, tier = _check_meta(str(entry["id"]), stage_checks, aer_format)
        tier_of[str(entry["id"])] = tier
        checks.append({"fail": int(entry["fail"]), "id": str(entry["id"]), "not_applicable": int(entry["not_applicable"]),
                       "pass": int(entry["pass"]), "skipped": int(entry["skipped"]), "tier": tier, "version": version})
    tiers: dict[int, dict[str, int]] = {}
    for check in checks:
        t = tiers.setdefault(check["tier"], {"checks": 0, "executions": 0, "executions_passed": 0, "fail": 0,
                                             "not_applicable": 0, "pass": 0, "skipped": 0, "tier": check["tier"]})
        t["checks"] += 1
        for key in ("pass", "fail", "skipped", "not_applicable"):
            t[key] += check[key]
    applicable = resolved = 0
    for row in results:
        statuses = row.get("checks", {})
        if not isinstance(statuses, Mapping):
            continue
        by_tier: dict[int, list[str]] = {}
        for check_id, status in statuses.items():
            tier = tier_of.get(str(check_id)) or _check_meta(str(check_id), stage_checks)[1]
            by_tier.setdefault(tier, []).append(str(status))
        for tier, values in by_tier.items():
            t = tiers.setdefault(tier, {"checks": 0, "executions": 0, "executions_passed": 0, "fail": 0,
                                        "not_applicable": 0, "pass": 0, "skipped": 0, "tier": tier})
            t["executions"] += 1
            t["executions_passed"] += all(v in _PASSING for v in values)
        linkage = [str(v) for k, v in statuses.items() if str(k).startswith(LINKAGE_PREFIX)]
        if any(v != "not_applicable" for v in linkage):
            applicable += 1
            resolved += all(v in _PASSING for v in linkage)
    specs = [c.removeprefix("tier4:") for c in stage_checks if c.startswith("tier4:")]
    return {
        "checks": sorted(checks, key=lambda c: c["id"].encode("utf-8")),
        "libraries": dict(sorted({str(k): str(v) for k, v in dict(stage.get("libraries", {})).items()}.items())),
        "linkage": {"applicable": applicable, "resolved": resolved,
                    "spec": specs[0] if len(specs) == 1 else "agentprov-prov/0.1"},
        "linkage_resolved_pct": linkage_resolved_pct(resolved, applicable),
        "mode": "strict" if stage.get("mode") == "release" else "dev",
        "tiers": [tiers[k] for k in sorted(tiers)],
    }


def rule_catalogue_refs(catalogues: Mapping[str, tuple[int, str, int, str]], used: Iterable[str]) -> list[dict[str, Any]]:
    """``rule_catalogues`` (H.2.5): ``catalogues`` maps a namespace to ``(version, sha256 hex, n_rules, path)``; every used
    rule id is assigned to its namespace's catalogue. :class:`ManifestError` for a used rule whose namespace has no
    catalogue (a rule the corpus cites must be recorded)."""
    by_ns: dict[str, set[str]] = {ns: set() for ns in catalogues}
    for rule_id in used:
        if RULE_ID_RE.fullmatch(rule_id) is None:
            continue
        namespace = rule_id.split(".", 1)[0]
        if namespace not in by_ns:
            raise ManifestError(f"the corpus cites a rule of namespace {namespace!r} whose catalogue is not recorded",
                                code="corpus.manifest.catalogue")
        by_ns[namespace].add(rule_id)
    return [
        {"id": ns, "n_rules": n, "path": path, "rules_used": sorted(by_ns[ns]), "sha256": "sha256:" + digest, "version": version}
        for ns, (version, digest, n, path) in sorted(catalogues.items())
    ]
