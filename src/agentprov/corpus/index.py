"""``executions.jsonl``: the execution index ``agentprov-index/0.1`` (HL H.3; MN M.1.2): working rows and full rows.

One JCS line per execution, sorted by ``ex``; an empty index is a 0-byte file. A phase-3 row holds exactly the members
that raw ingest and the AER stage determine::

    {"adapter": "agentdojo.tracelogger@0.1.0", "attempt": null, "completeness": "unverifiable",
     "digests": {"aer": "sha256:…"}, "ex": "ex_…", "execution_observed": true, "issues": ["map.accounting_unverifiable"],
     "mode": "import", "n_origins": 1, "paths": {"aer": "aer/3f/ex_….aer.jsonl"}, "profile": "agentdojo-upstream@1",
     "raw": [{"included": true, "role": "primary", "sha256": "sha256:…"}], "snapshot_ids": ["2024-06"],
     "source_id": "agentdojo", "source_key": "sha256:…#{\"p\":\"\"}", "stages": {"aer": "ok", "raw": "ok"},
     "status": "ok_with_issues", "unit": "agent_execution"}

Members that depend on later stages are **omitted, never written as placeholders**: ``logical_key`` and ``cell`` (the
adapter's cell coordinates, H.7.4), ``facets`` and ``ev`` (a pure function of AER *and SEM*, H.3.3), ``digests.sem``,
``paths.sem``, ``oracles`` and the ``sem`` entry of ``stages``. Later phases add them to this same row type.

Phase 6 (the import pipeline, MN N.2.2) adds the PROV and validation stages, **only when they ran** (``import --until
aer`` writes rows without them)::

    "digests": {"aer": "sha256:…", "prov": {"agentprov-prov/0.1": {"json": "sha256:…"}}, "validation": "sha256:…"},
    "paths": {"aer": "aer/3f/ex_….aer.jsonl", "prov": {"agentprov-prov/0.1": {"json": "prov/agentprov-prov-0.1/3f/ex_….prov.json"}}},
    "stages": {"aer": "ok", "prov": {"agentprov-prov/0.1": "ok"}, "raw": "ok", "validation": "ok"}

Phase 7 adds the SEM stage, keyed by semantics profile ``<id>@<version>`` (H.3.4), only when it ran::

    "digests": {"sem": {"agentdojo.suites@1": "sha256:…"}}, "paths": {"sem": {"agentdojo.suites@1": "sem/agentdojo.suites-1/3f/ex_….sem.jsonl"}},
    "stages": {"sem": {"agentdojo.suites@1": "ok"}}

``digests.sem.<profile>`` is the SEM digest (the seal's ``records_sha256``, C.14.4; ``null``, with no path, when the
stage failed). ``digests.prov.<spec>.json`` is the sha256 of the PROV-JSON file bytes (``null``, with no path, when derivation failed);
``digests.validation`` is the sha256 of the JCS bytes of the execution's ``validation/results.jsonl`` row (H.2.11).

**Full rows** (phase 11; H.3.1). A row produced by a phase-11 code path (``derive``/``recompute`` index rebuild, sealing)
carries the five members the working rows omit: ``logical_key``, ``cell``, ``facets``, ``ev`` and ``oracles``
(:class:`FacetMembers`, computed by :mod:`agentprov.corpus.facets`), and records every stage (``sem``, ``prov`` and
``validation`` present). The importer keeps writing working rows, and :func:`decode_index` reads both kinds, so the
phase-10 working corpora stay readable. A row holds one kind or the other, never a mixture: the member set is exactly the
working set, or the working set plus all five.

* ``logical_key`` is ``"lk_" + b32(sha256("aer-lk/1\\n" + JCS(cell)))[:26]`` (:func:`logical_key`, H.7.4), or ``null``
  when a cell member is unknown (``{"$unk": <C.7.1 reason>}``) or the cell is empty.
* ``facets`` is flat (``"model.requested"`` is one member name): the H.3.3 core facets, always present, plus adapter
  facets ``x.<ns>.<name>`` (deferred, D-34). ``ev`` maps a facet name, or ``cell.<member>``, to ``O``/``D``/``I``.
* ``oracles`` has one entry ``{"gate_report": "sha256:…"|null, "status": "apv:RegressionOracle"}`` per regression-oracle
  spec with output in ``paths.prov`` (``adprov-v2.3-compat``, R-55); ``{}`` otherwise.
* Corpus-layer JSON holds no floating-point number (H.1.4(3)). A non-integral number copied from an AER value (a judgement
  score, an outcome ``score``) is written ``{"$dec": "<its JCS spelling>"}``, which keeps it exactly (D-34).

Derived members (never taken from the caller): ``paths.aer`` is computed from ``ex`` and the layout (H.1.3(6)),
``n_origins`` is the number of ``raw/origins.jsonl`` lines of the primary artefact, and ``status`` is computed by H.3.2
from the stages and the severities of the register entries named in ``issues``.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Final

from agentprov.aer.ids import EXECUTION_ID_RE
from agentprov.aer.types import UNKNOWN_REASON_SET
from agentprov.corpus.layout import CorpusLayout
from agentprov.corpus.register import is_known_code
from agentprov.errors import AgentProvError, IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import iter_jsonl, strict_json_loads
from agentprov.io.atomic import atomic_write_bytes
from agentprov.io.canonical import base32_lower_nopad, is_sha256_hex, jcs_bytes

__all__ = [
    "CORE_FACET_TYPES",
    "COUNT_FACETS",
    "ORACLE_SPECS",
    "ORACLE_STATUS",
    "ExecutionEntry",
    "FacetMembers",
    "IndexError_",
    "IndexLog",
    "IndexRow",
    "RawRef",
    "StageOutput",
    "check_corpus_json",
    "compute_status",
    "decode_index",
    "encode_index",
    "logical_key",
    "row_status",
]

MODES: Final = ("import", "live")
UNITS: Final = ("agent_execution", "outcome_only", "scenario")
COMPLETENESS: Final = ("verified_complete", "known_incomplete", "unverifiable")
STAGE_STATES: Final = ("ok", "failed", "skipped", "not_applicable")
RAW_ROLES: Final = ("primary", "capture_log", "native_log", "supporting")
STATUSES: Final = ("ok", "ok_with_issues", "failed")
_ADAPTER_RE: Final = re.compile(r"[a-z][a-z0-9_.]*@[0-9]+\.[0-9]+\.[0-9]+")
_PROFILE_RE: Final = re.compile(r"[a-z][a-z0-9_.-]*@[1-9][0-9]*")
_SEM_REF_RE: Final = re.compile(r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*@[1-9][0-9]*")
_ID_RE: Final = re.compile(r"[a-z0-9][a-z0-9_.-]*")
_SOURCE_KEY_RE: Final = re.compile(r"sha256:[0-9a-f]{64}#(.*)", re.DOTALL)
_RELPATH_RE: Final = re.compile(r"[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*")  # the corpus-0.1 schema RELPATH
_PHASE3_STAGES: Final = ("aer", "raw")
_WORKING_KEYS: Final = frozenset({
    "adapter", "attempt", "completeness", "digests", "ex", "execution_observed", "issues", "mode", "n_origins", "paths",
    "profile", "raw", "snapshot_ids", "source_id", "source_key", "stages", "status", "unit"})  # fmt: skip
_FULL_KEYS: Final = frozenset({"cell", "ev", "facets", "logical_key", "oracles"})

#: Regression-oracle provenance specs (R-55): their output is flagged in the row's ``oracles`` (H.3.1) and the manifest's
#: ``oracle_specs`` (H.2.2). ``adprov-v2.3-compat`` is the only one in v0.1.
ORACLE_SPECS: Final = frozenset({"adprov-v2.3-compat"})
ORACLE_STATUS: Final = "apv:RegressionOracle"
EVIDENCE_LETTERS: Final = ("O", "D", "I")
#: The H.3.3 count facets; the last two count the generic ``activity`` and ``artefact`` records (Addendum B AD-15).
COUNT_FACETS: Final = (
    "n.messages", "n.model_calls", "n.tool_executions", "n.decisions", "n.judgements", "n.state_changes", "n.activities",
    "n.artefacts")  # fmt: skip
#: The H.3.3 core facets and their ``FacetDecl`` types. ``outcome`` is an array of objects; H.3.3(1)'s type list has no
#: such type, so ``object[]`` is added (D-34).
CORE_FACET_TYPES: Final[Mapping[str, str]] = {
    "task": "object",
    "framework": "string",
    "model.requested": "string[]",
    "model.served": "string[]",
    **dict.fromkeys(COUNT_FACETS, "integer"),
    "generic_types": "string[]",
    "outcome": "object[]",
}
#: The members of one ``outcome`` facet element (H.3.3(2)).
OUTCOME_MEMBERS: Final = frozenset({"name", "value", "origin", "claim", "holds", "score", "scale", "ev"})
UNKNOWN_KEY: Final = "$unk"
DECIMAL_KEY: Final = "$dec"
_LK_RE: Final = re.compile(r"lk_[a-z2-7]{26}")
_FW_RE: Final = re.compile(r"fw_[a-z2-7]{16}")
_X_FACET_RE: Final = re.compile(r"x\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_.]*")
_CELL_MEMBER_RE: Final = re.compile(r"[a-z][a-z0-9_]*")
_GENERIC_TYPE_RE: Final = re.compile(r"[a-z][a-z0-9_]*:[A-Za-z_][A-Za-z0-9_.-]*")
_DECIMAL_RE: Final = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")
_I_JSON_MAX: Final = 2**53 - 1


def primary_role(mode: str) -> str:
    """The raw role of the artefact a row's ``source_key`` and ``n_origins`` name (H.3.1, H.7.1): ``primary`` for an
    import, the ``capture_log`` for a live execution (a live AER has no ``primary`` artefact, D.10.4)."""
    return "capture_log" if mode == "live" else "primary"


class IndexError_(AgentProvError):  # noqa: N801 - ``IndexError`` is a builtin; the trailing underscore avoids shadowing it
    """An index row is malformed (``corpus.index.invalid``)."""

    code = "corpus.index.invalid"
    exit_code = 1


def _ref(digest: str) -> str:
    return "sha256:" + digest


def _unref(value: object, what: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:") or not is_sha256_hex(value[7:]):
        raise IndexError_(f"{what} must be 'sha256:<64 hex>'")
    return value[7:]


@dataclass(frozen=True, slots=True)
class RawRef:
    """One entry of an index row's ``raw`` array: an AER header artefact (HL H.3.1)."""

    sha256: str
    role: str
    included: bool

    def __post_init__(self) -> None:
        if not is_sha256_hex(self.sha256) or self.role not in RAW_ROLES or not isinstance(self.included, bool):
            raise IndexError_("a raw entry is {sha256, role, included}")

    def to_json(self) -> dict[str, Any]:
        return {"included": self.included, "role": self.role, "sha256": _ref(self.sha256)}


def _stage_states(stages: Mapping[str, Any]) -> list[str]:
    """Every state of a ``stages`` object, nested per-spec maps (``prov``, ``sem``) flattened."""
    out: list[str] = []
    for value in stages.values():
        if isinstance(value, Mapping):
            out.extend(str(v) for v in value.values())
        else:
            out.append(str(value))
    return out


def compute_status(stages: Mapping[str, Any], severities: Iterable[str]) -> str:
    """H.3.2(1): ``failed`` if any stage failed or any issue is an error; else ``ok_with_issues`` on a warning; else ``ok``."""
    levels = set(severities)
    if "failed" in _stage_states(stages) or "error" in levels:
        return "failed"
    return "ok_with_issues" if "warning" in levels else "ok"


def row_status(row: IndexRow, registered: Iterable[tuple[str, str]]) -> str:
    """H.3.2(1) recomputed from an index row and the ``(code, severity)`` register pairs of its execution, as the writer
    computes it when it builds the row: the stages with the SEM, PROV and validation states added, and the severities of
    the register entries whose code is one of the row's issues (CB-11)."""
    stages: dict[str, Any] = dict(row.stages)
    if row.sem is not None:
        stages["sem"] = {profile: out.state for profile, out in row.sem.items()}
    if row.prov is not None:
        stages["prov"] = {spec: out.state for spec, out in row.prov.items()}
    if row.validation is not None:
        stages["validation"] = row.validation.state
    issues = set(row.issues)
    return compute_status(stages, [severity for code, severity in registered if code in issues])


@dataclass(frozen=True, slots=True)
class StageOutput:
    """The state of one derived stage of one execution and the digest of its output (``None``: no output)."""

    state: str
    digest: str | None = None

    def __post_init__(self) -> None:
        if self.state not in STAGE_STATES:
            raise IndexError_("unknown stage state")
        if self.digest is not None and not is_sha256_hex(self.digest):
            raise IndexError_("a stage digest is 64 hex digits")


def logical_key(cell: Mapping[str, Any]) -> str:
    """``"lk_" + b32(sha256("aer-lk/1\\n" + JCS(cell)))[:26]`` (HL H.7.4), over a cell with every member known.

    ``ValueError`` when a member is unknown (``{"$unk": …}``: the key is then ``null``, H.7.4(3)), when the cell is empty,
    or when it is not corpus-layer JSON (:func:`check_corpus_json`). The key links replicates and re-runs; it is never
    used to deduplicate (H.7.4(2)).
    """
    if not isinstance(cell, Mapping) or not cell:
        raise ValueError("a logical key needs a non-empty cell")
    if any(_is_unknown(v) for v in cell.values()):
        raise ValueError("a cell with an unknown member has no logical key")
    check_corpus_json(cell)
    digest = hashlib.sha256(b"aer-lk/1\n" + jcs_bytes(dict(cell))).digest()
    return "lk_" + base32_lower_nopad(digest)[:26]


def _is_unknown(value: object) -> bool:
    return isinstance(value, Mapping) and set(value) == {UNKNOWN_KEY}


def check_corpus_json(value: object) -> None:
    """Corpus-layer JSON (H.1.4(3)): no floating-point number anywhere and integers within +-(2^53 - 1).

    A ``{"$dec": "<decimal>"}`` object (the exact spelling of a non-integral number copied from an AER value, D-34) must
    hold a JSON number literal. ``ValueError`` otherwise. Iterative, so a deep value cannot exhaust the stack.
    """
    stack: list[object] = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, bool) or item is None or isinstance(item, str):
            continue
        if isinstance(item, int):
            if abs(item) > _I_JSON_MAX:
                raise ValueError("an integer outside +-(2^53 - 1) in corpus-layer JSON")
        elif isinstance(item, float):
            raise ValueError("a floating-point number in corpus-layer JSON (H.1.4(3))")
        elif isinstance(item, Mapping):
            if DECIMAL_KEY in item and (
                set(item) != {DECIMAL_KEY} or not isinstance(item[DECIMAL_KEY], str)
                or _DECIMAL_RE.fullmatch(item[DECIMAL_KEY]) is None
            ):
                raise ValueError("a $dec object holds exactly one JSON number literal")
            if not all(isinstance(k, str) for k in item):
                raise ValueError("an object member name is not a string")
            stack.extend(item.values())
        elif isinstance(item, list | tuple):
            stack.extend(item)
        else:
            raise ValueError("not a JSON value")


def _check_string_array(value: object, what: str, pattern: re.Pattern[str] | None = None, *, non_empty: bool = False) -> None:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value) or value != sorted(set(value)):
        raise IndexError_(f"facet {what} is a sorted array of unique strings")
    if non_empty and not all(value):
        raise IndexError_(f"facet {what} holds an empty string (the published schema requires non-empty strings)")
    if pattern is not None and not all(pattern.fullmatch(v) for v in value):
        raise IndexError_(f"facet {what} holds a malformed value")


def _check_evidence_map(value: object, what: str, allowed: Iterable[str]) -> None:
    if not isinstance(value, Mapping) or not all(isinstance(k, str) and k in allowed for k in value):
        raise IndexError_(f"{what} maps known member names to evidence classes")
    if not all(v in EVIDENCE_LETTERS for v in value.values()):
        raise IndexError_(f"{what} values are O, D or I")


def _check_core_facet(name: str, value: object) -> None:
    if name == "task":
        if value is not None and not isinstance(value, Mapping):
            raise IndexError_("facet task is the AER header task object or null")
    elif name == "framework":
        if value is not None and (not isinstance(value, str) or _FW_RE.fullmatch(value) is None):
            raise IndexError_("facet framework is a framework id fw_<16 base32> or null")
    elif name in ("model.requested", "model.served"):
        _check_string_array(value, name, non_empty=True)
    elif name in COUNT_FACETS:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise IndexError_(f"facet {name} is a non-negative integer")
    elif name == "generic_types":
        _check_string_array(value, name, _GENERIC_TYPE_RE)
    elif name == "outcome":
        if not isinstance(value, list):
            raise IndexError_("facet outcome is an array")
        for element in value:
            if not isinstance(element, Mapping) or set(element) != OUTCOME_MEMBERS:
                raise IndexError_("an outcome element has exactly the H.3.3 members")
            if element["name"] is not None and not isinstance(element["name"], str):
                raise IndexError_("an outcome name is a string or null")
            present = {k for k, v in element.items() if k != "ev" and v is not None}
            _check_evidence_map(element["ev"], "an outcome element's ev", present)
            if element["origin"] is not None and not isinstance(element["origin"], str):
                raise IndexError_("an outcome origin is a string or null")
            if element["holds"] is not None and not isinstance(element["holds"], bool):
                raise IndexError_("an outcome holds is a boolean or null")


@dataclass(frozen=True, slots=True)
class FacetMembers:
    """The five H.3.1 members that only a full row carries (see the module docstring); validated on construction."""

    logical_key: str | None
    cell: Mapping[str, Any]
    facets: Mapping[str, Any]
    ev: Mapping[str, str]
    oracles: Mapping[str, Mapping[str, Any]]

    def __post_init__(self) -> None:
        if not isinstance(self.cell, Mapping) or not all(isinstance(k, str) and _CELL_MEMBER_RE.fullmatch(k) for k in self.cell):
            raise IndexError_("cell maps member names to values")
        unknown = False
        for value in self.cell.values():
            if _is_unknown(value):
                unknown = True
                if value[UNKNOWN_KEY] not in UNKNOWN_REASON_SET:
                    raise IndexError_("an unknown cell member names a C.7.1 reason")
        try:
            check_corpus_json(self.cell)
            check_corpus_json(self.facets)
        except ValueError as exc:
            raise IndexError_(f"cell or facets: {exc}") from None
        if self.logical_key is None:
            if self.cell and not unknown:
                raise IndexError_("logical_key is null only when a cell member is unknown or the cell is empty (H.7.4)")
        elif not isinstance(self.logical_key, str) or _LK_RE.fullmatch(self.logical_key) is None:
            raise IndexError_("logical_key is lk_<26 base32> or null")
        elif unknown or not self.cell or self.logical_key != logical_key(self.cell):
            raise IndexError_("logical_key differs from the key computed from cell (H.7.4)")
        if not isinstance(self.facets, Mapping) or not set(CORE_FACET_TYPES) <= set(self.facets):
            raise IndexError_("facets hold every core facet (H.3.3(2))")
        for name, value in self.facets.items():
            if name in CORE_FACET_TYPES:
                _check_core_facet(name, value)
            elif not isinstance(name, str) or _X_FACET_RE.fullmatch(name) is None:
                raise IndexError_("a facet that is not core is named x.<ns>.<name> (H.3.3(1))")
        _check_evidence_map(self.ev, "ev", {*self.facets, *(f"cell.{k}" for k in self.cell)})
        if not isinstance(self.oracles, Mapping) or not all(k in ORACLE_SPECS for k in self.oracles):
            raise IndexError_("oracles are keyed by regression-oracle specs")
        for entry in self.oracles.values():
            if not isinstance(entry, Mapping) or set(entry) != {"gate_report", "status"} or entry["status"] != ORACLE_STATUS:
                raise IndexError_("an oracle entry is {gate_report, status: apv:RegressionOracle}")
            report = entry["gate_report"]
            if report is not None and (not isinstance(report, str) or not report.startswith("sha256:") or not is_sha256_hex(report[7:])):
                raise IndexError_("an oracle gate_report is 'sha256:<hex>' or null")

    def to_json(self) -> dict[str, Any]:
        return {
            "cell": dict(self.cell),
            "ev": dict(self.ev),
            "facets": dict(self.facets),
            "logical_key": self.logical_key,
            "oracles": {spec: dict(entry) for spec, entry in self.oracles.items()},
        }

    @classmethod
    def from_json(cls, obj: Mapping[str, Any]) -> FacetMembers:
        for name in ("cell", "ev", "facets", "oracles"):
            if not isinstance(obj[name], Mapping):
                raise IndexError_(f"{name} is an object")
        return cls(obj["logical_key"], dict(obj["cell"]), dict(obj["facets"]), dict(obj["ev"]),
                   {str(k): dict(v) if isinstance(v, Mapping) else v for k, v in obj["oracles"].items()})


@dataclass(frozen=True, slots=True)
class ExecutionEntry:
    """What the importer knows about one execution; the writer derives ``paths``, ``n_origins`` and ``status``.

    ``aer_digest`` is the AER execution digest, ``seal.records_sha256`` (64 hex; not the file's byte hash).
    ``issues`` are register codes (AER seal issues as ``map.<code>``); each needs a register entry for this ``ex``.
    """

    ex: str
    mode: str
    unit: str
    source_id: str
    snapshot_ids: Sequence[str]
    source_key: str
    raw: Sequence[RawRef]
    adapter: str
    profile: str
    aer_digest: str
    stages: Mapping[str, str]
    completeness: str
    execution_observed: bool
    issues: Sequence[str] = ()
    attempt: int | None = None
    prov: Mapping[str, StageOutput] | None = None  # spec id -> PROV stage (phase 6); None: the stage did not run
    validation: StageOutput | None = None  # the validation stage (phase 6); None: it did not run
    sem: Mapping[str, StageOutput] | None = None  # "<profile id>@<version>" -> SEM stage (phase 7; digest = SEM digest)
    facet_members: FacetMembers | None = None  # phase 11: the five full-row members; None writes a working row


@dataclass(frozen=True, slots=True)
class IndexRow:
    """One validated row of ``executions.jsonl``: a working row, or a full H.3.1 row (``facet_members`` set)."""

    ex: str
    mode: str
    unit: str
    source_id: str
    snapshot_ids: tuple[str, ...]
    source_key: str
    raw: tuple[RawRef, ...]
    n_origins: int
    adapter: str
    profile: str
    aer_digest: str
    aer_path: str
    stages: Mapping[str, str]
    status: str
    completeness: str
    execution_observed: bool
    issues: tuple[str, ...]
    attempt: int | None
    prov: Mapping[str, StageOutput] | None = None
    prov_paths: Mapping[str, str] | None = None  # spec -> relative path, for the specs with output (computed)
    validation: StageOutput | None = None
    sem: Mapping[str, StageOutput] | None = None  # profile ref -> SEM stage; the digest is the SEM digest (C.14.4)
    sem_paths: Mapping[str, str] | None = None  # profile ref -> relative path, for the profiles with output (computed)
    facet_members: FacetMembers | None = None  # phase 11 full rows (H.3.1); None for a working row

    def __post_init__(self) -> None:
        # Type checks first: a row read back is untrusted JSON, and a value of the wrong type must be an IndexError_,
        # never a builtins.TypeError from a regex, set() or sorted() (CB-2).
        scalars = (self.ex, self.mode, self.unit, self.source_id, self.source_key, self.adapter, self.profile, self.status,
                   self.completeness)  # fmt: skip
        if not all(isinstance(v, str) for v in scalars):
            raise IndexError_("ex, mode, unit, source_id, source_key, adapter, profile, status and completeness are strings")
        if not all(isinstance(v, str) for v in (*self.snapshot_ids, *self.issues)):
            raise IndexError_("snapshot_ids and issues hold strings")
        if EXECUTION_ID_RE.fullmatch(self.ex) is None:
            raise IndexError_("ex is not an execution id")
        if self.mode not in MODES or self.unit not in UNITS or self.completeness not in COMPLETENESS:
            raise IndexError_("unknown mode, unit or completeness")
        if self.status not in STATUSES:
            raise IndexError_("unknown status")
        if not _ID_RE.fullmatch(self.source_id) or not self.snapshot_ids or not all(_ID_RE.fullmatch(s) for s in self.snapshot_ids):
            raise IndexError_("source_id and snapshot_ids are registry ids; at least one snapshot")
        if list(self.snapshot_ids) != sorted(set(self.snapshot_ids)):
            raise IndexError_("snapshot_ids are sorted and unique")
        match = _SOURCE_KEY_RE.fullmatch(self.source_key)
        if match is None:
            raise IndexError_("source_key is 'sha256:<hex>#<JCS locator>'")
        try:
            loc = strict_json_loads(match.group(1).encode("utf-8"), record=True)
        except IngestError:
            raise IndexError_("source_key locator is not JSON") from None
        if not isinstance(loc, dict) or jcs_bytes(loc).decode("utf-8") != match.group(1):
            raise IndexError_("source_key locator is not in JCS form")
        if not self.raw or sum(1 for r in self.raw if r.role == primary_role(self.mode)) != 1:
            raise IndexError_("exactly one raw entry is primary (the capture log for a live execution)")
        if isinstance(self.n_origins, bool) or not isinstance(self.n_origins, int) or self.n_origins < 1:
            raise IndexError_("n_origins counts the primary artefact's origin lines (at least one)")
        if not _ADAPTER_RE.fullmatch(self.adapter) or not _PROFILE_RE.fullmatch(self.profile):
            raise IndexError_("adapter is '<id>@<semver>', profile is '<id>@<int>'")
        if not is_sha256_hex(self.aer_digest):
            raise IndexError_("aer_digest is 64 hex digits")
        if not isinstance(self.aer_path, str) or _RELPATH_RE.fullmatch(self.aer_path) is None:
            raise IndexError_("paths.aer is a relative path (the published schema has no null)")
        if set(self.stages) != set(_PHASE3_STAGES) or not all(v in STAGE_STATES for v in self.stages.values()):
            raise IndexError_("stages hold raw and aer (sem, prov and validation are separate members)")
        if self.prov is not None:
            if not self.prov or not all(isinstance(k, str) and k for k in self.prov):
                raise IndexError_("prov maps at least one spec id to its stage")
            if set(self.prov_paths or {}) != {k for k, v in self.prov.items() if v.digest is not None}:
                raise IndexError_("a prov path is recorded exactly for the specs with output")
        elif self.prov_paths:
            raise IndexError_("prov paths without a prov stage")
        if self.sem is not None:
            if not self.sem or not all(isinstance(k, str) and _SEM_REF_RE.fullmatch(k) for k in self.sem):
                raise IndexError_("sem maps at least one semantics profile '<id>@<int>' to its stage")
            if set(self.sem_paths or {}) != {k for k, v in self.sem.items() if v.digest is not None}:
                raise IndexError_("a sem path is recorded exactly for the profiles with output")
        elif self.sem_paths:
            raise IndexError_("sem paths without a sem stage")
        if not isinstance(self.execution_observed, bool):
            raise IndexError_("execution_observed is a boolean")
        if list(self.issues) != sorted(set(self.issues)) or not all(is_known_code(c) for c in self.issues):
            raise IndexError_("issues are sorted, unique register codes")
        if self.attempt is not None and (isinstance(self.attempt, bool) or not isinstance(self.attempt, int) or self.attempt < 0):
            raise IndexError_("attempt is null or a non-negative integer")
        if (self.mode == "live") != (self.attempt is not None):
            raise IndexError_("attempt is set for live executions and null for imports")
        if self.facet_members is not None:
            if not isinstance(self.facet_members, FacetMembers):
                raise IndexError_("facet_members is a FacetMembers")
            if self.sem is None or self.prov is None or self.validation is None:
                raise IndexError_("a full row records the sem, prov and validation stages (H.3.1)")
            oracle_outputs = {spec for spec in (self.prov_paths or {}) if spec in ORACLE_SPECS}
            if set(self.facet_members.oracles) != oracle_outputs:
                raise IndexError_("oracles has one entry per regression-oracle spec with output in paths.prov (R-55)")

    @property
    def is_full(self) -> bool:
        """Whether this is a full H.3.1 row (phase 11) rather than a working row."""
        return self.facet_members is not None

    def with_facets(self, members: FacetMembers | None) -> IndexRow:
        """This row with the full-row members set (or removed with ``None``); validated again."""
        return replace(self, facet_members=members)

    def all_stages(self) -> dict[str, Any]:
        """The ``stages`` object as written: ``raw`` and ``aer``, plus ``prov`` and ``validation`` when they ran."""
        stages: dict[str, Any] = dict(self.stages)
        if self.sem is not None:
            stages["sem"] = {profile: out.state for profile, out in sorted(self.sem.items())}
        if self.prov is not None:
            stages["prov"] = {spec: out.state for spec, out in sorted(self.prov.items())}
        if self.validation is not None:
            stages["validation"] = self.validation.state
        return stages

    def to_json(self) -> dict[str, Any]:
        out = self._working_json()
        if self.facet_members is not None:
            out.update(self.facet_members.to_json())
        return out

    def _working_json(self) -> dict[str, Any]:
        digests: dict[str, Any] = {"aer": _ref(self.aer_digest)}
        paths: dict[str, Any] = {"aer": self.aer_path}
        if self.prov is not None:
            digests["prov"] = {
                spec: {"json": None if out.digest is None else _ref(out.digest)} for spec, out in sorted(self.prov.items())
            }
            if self.prov_paths:
                paths["prov"] = {spec: {"json": path} for spec, path in sorted(self.prov_paths.items())}
        if self.sem is not None:
            digests["sem"] = {p: None if out.digest is None else _ref(out.digest) for p, out in sorted(self.sem.items())}
            if self.sem_paths:
                paths["sem"] = dict(sorted(self.sem_paths.items()))
        if self.validation is not None:
            digests["validation"] = None if self.validation.digest is None else _ref(self.validation.digest)
        return {
            "adapter": self.adapter,
            "attempt": self.attempt,
            "completeness": self.completeness,
            "digests": digests,
            "ex": self.ex,
            "execution_observed": self.execution_observed,
            "issues": list(self.issues),
            "mode": self.mode,
            "n_origins": self.n_origins,
            "paths": paths,
            "profile": self.profile,
            "raw": [r.to_json() for r in self.raw],
            "snapshot_ids": list(self.snapshot_ids),
            "source_id": self.source_id,
            "source_key": self.source_key,
            "stages": self.all_stages(),
            "status": self.status,
            "unit": self.unit,
        }

    def line(self) -> bytes:
        return jcs_bytes(self.to_json()) + b"\n"

    @classmethod
    def from_json(cls, obj: object, layout: CorpusLayout | None = None) -> IndexRow:
        if not isinstance(obj, Mapping) or set(obj) not in (_WORKING_KEYS, _WORKING_KEYS | _FULL_KEYS):
            raise IndexError_("an index row has exactly the working-row members, or those and the five full-row members")
        try:
            return cls._from_json(obj, layout)
        except (TypeError, ValueError) as exc:  # belt and braces (CB-2): untrusted JSON never ends in an internal error
            raise IndexError_(f"a member has the wrong type ({type(exc).__name__})") from None

    @classmethod
    def _from_json(cls, obj: Mapping[str, Any], layout: CorpusLayout | None) -> IndexRow:
        facet_members = FacetMembers.from_json(obj) if _FULL_KEYS <= set(obj) else None
        digests, paths, raw = obj["digests"], obj["paths"], obj["raw"]
        if not (isinstance(digests, Mapping) and {"aer"} <= set(digests) <= {"aer", "sem", "prov", "validation"}):
            raise IndexError_("digests hold aer, and sem, prov and validation when those stages ran")
        if not (isinstance(paths, Mapping) and {"aer"} <= set(paths) <= {"aer", "sem", "prov"}):
            raise IndexError_("paths hold aer, and sem and prov when those stages produced output")
        if not isinstance(raw, list) or not all(isinstance(r, Mapping) and set(r) == {"included", "role", "sha256"} for r in raw):
            raise IndexError_("raw is a list of {included, role, sha256}")
        if not isinstance(obj["snapshot_ids"], list) or not isinstance(obj["issues"], list) or not isinstance(obj["stages"], Mapping):
            raise IndexError_("snapshot_ids, issues and stages have the documented types")
        stages = dict(obj["stages"])
        sem_states = stages.pop("sem", None)
        sem, sem_paths = _sem_from_json(sem_states, digests.get("sem"), paths.get("sem"))
        prov_states = stages.pop("prov", None)
        validation_state = stages.pop("validation", None)
        prov, prov_paths = _prov_from_json(prov_states, digests.get("prov"), paths.get("prov"))
        if (validation_state is None) != ("validation" not in digests):
            raise IndexError_("stages.validation and digests.validation go together")
        validation = None
        if validation_state is not None:
            vd = digests["validation"]
            validation = StageOutput(str(validation_state), None if vd is None else _unref(vd, "digests.validation"))
        row = cls(
            ex=obj["ex"],
            mode=obj["mode"],
            unit=obj["unit"],
            source_id=obj["source_id"],
            snapshot_ids=tuple(obj["snapshot_ids"]),
            source_key=obj["source_key"],
            raw=tuple(RawRef(_unref(r["sha256"], "raw.sha256"), r["role"], r["included"]) for r in raw),
            n_origins=obj["n_origins"],
            adapter=obj["adapter"],
            profile=obj["profile"],
            aer_digest=_unref(digests["aer"], "digests.aer"),
            aer_path=paths["aer"],
            stages=stages,
            status=obj["status"],
            completeness=obj["completeness"],
            execution_observed=obj["execution_observed"],
            issues=tuple(obj["issues"]),
            attempt=obj["attempt"],
            prov=prov,
            prov_paths=prov_paths,
            validation=validation,
            sem=sem,
            sem_paths=sem_paths,
            facet_members=facet_members,
        )
        if layout is not None and row.aer_path != layout.aer_relpath(row.ex):
            raise IndexError_("paths.aer differs from the path computed from ex and the layout (H.1.3(6))", code="corpus.index.path")
        if layout is not None and any(path != layout.prov_relpath(spec, row.ex) for spec, path in (row.prov_paths or {}).items()):
            raise IndexError_("paths.prov differs from the path computed from ex and the layout (H.1.3(6))", code="corpus.index.path")
        if layout is not None and any(path != layout.sem_relpath(p, row.ex) for p, path in (row.sem_paths or {}).items()):
            raise IndexError_("paths.sem differs from the path computed from ex and the layout (H.1.3(6))", code="corpus.index.path")
        return row


def _sem_from_json(
    states: object, digests: object, paths: object
) -> tuple[dict[str, StageOutput] | None, dict[str, str] | None]:
    """The ``sem`` stage of a row read back: ``stages.sem``, ``digests.sem`` and ``paths.sem`` must agree (H.3.4)."""
    if states is None:
        if digests is not None or paths is not None:
            raise IndexError_("digests.sem or paths.sem without stages.sem")
        return None, None
    if not isinstance(states, Mapping) or not isinstance(digests, Mapping) or set(states) != set(digests):
        raise IndexError_("stages.sem and digests.sem name the same profiles")
    sem = {
        str(p): StageOutput(str(state), None if digests[p] is None else _unref(digests[p], "digests.sem"))
        for p, state in states.items()
    }
    out_paths: dict[str, str] = {}
    if paths is not None:
        if not isinstance(paths, Mapping) or not all(isinstance(v, str) for v in paths.values()):
            raise IndexError_("paths.sem maps a profile to a path")
        out_paths = {str(p): str(v) for p, v in paths.items()}
    return sem, out_paths


def _prov_from_json(
    states: object, digests: object, paths: object
) -> tuple[dict[str, StageOutput] | None, dict[str, str] | None]:
    """The ``prov`` stage of a row read back: ``stages.prov``, ``digests.prov`` and ``paths.prov`` must agree."""
    if states is None:
        if digests is not None or paths is not None:
            raise IndexError_("digests.prov or paths.prov without stages.prov")
        return None, None
    if not isinstance(states, Mapping) or not isinstance(digests, Mapping) or set(states) != set(digests):
        raise IndexError_("stages.prov and digests.prov name the same specs")
    prov: dict[str, StageOutput] = {}
    for spec, state in states.items():
        entry = digests[spec]
        if not isinstance(entry, Mapping) or set(entry) != {"json"}:
            raise IndexError_("digests.prov.<spec> is {json}")
        prov[str(spec)] = StageOutput(str(state), None if entry["json"] is None else _unref(entry["json"], "digests.prov"))
    out_paths: dict[str, str] = {}
    if paths is not None:
        if not isinstance(paths, Mapping):
            raise IndexError_("paths.prov is an object")
        for spec, entry in paths.items():
            if not isinstance(entry, Mapping) or set(entry) != {"json"} or not isinstance(entry["json"], str):
                raise IndexError_("paths.prov.<spec> is {json: path}")
            out_paths[str(spec)] = entry["json"]
    return prov, out_paths


def encode_index(rows: Iterable[IndexRow]) -> bytes:
    """The bytes of ``executions.jsonl``: sorted by ``ex`` (bytewise), one row per execution, LF-terminated."""
    ordered = sorted(rows, key=lambda r: r.ex.encode("ascii"))
    keys = [r.ex for r in ordered]
    if len(set(keys)) != len(keys):
        raise IndexError_("two index rows for one execution", code="corpus.index.duplicate")
    return b"".join(r.line() for r in ordered)


def decode_index(data: bytes, layout: CorpusLayout | None = None, limits: IngestLimits | None = None) -> list[IndexRow]:
    """Parse ``executions.jsonl`` strictly; with ``layout``, every recorded path is checked against the layout."""
    rows: list[IndexRow] = []
    try:
        for _, _, value in iter_jsonl(io.BytesIO(data), limits):
            rows.append(IndexRow.from_json(value, layout))
    except IngestError as exc:
        raise IndexError_(f"executions.jsonl is not strict JSONL ({exc.code})") from None
    if encode_index(rows) != data:
        raise IndexError_("executions.jsonl is not sorted by ex", code="corpus.index.unsorted")
    return rows


class IndexLog:
    """The execution index of one corpus; one row per execution (a second row for an ``ex`` replaces nothing: it is an error)."""

    def __init__(self, rows: Iterable[IndexRow] = ()) -> None:
        self._rows: dict[str, IndexRow] = {}
        for row in rows:
            self.add(row)

    def add(self, row: IndexRow) -> None:
        if row.ex in self._rows:
            if self._rows[row.ex] == row:
                return
            raise IndexError_("two different index rows for one execution", code="corpus.index.duplicate")
        self._rows[row.ex] = row

    def rows(self) -> list[IndexRow]:
        return [self._rows[k] for k in sorted(self._rows, key=lambda e: e.encode("ascii"))]

    def get(self, ex: str) -> IndexRow | None:
        return self._rows.get(ex)

    def discard(self, ex: str) -> None:
        """Forget the row of ``ex`` (a working corpus re-processes a failed unit; never used on a sealed corpus)."""
        self._rows.pop(ex, None)

    def __len__(self) -> int:
        return len(self._rows)

    def serialise(self) -> bytes:
        return encode_index(self._rows.values())

    def write(self, path: str | os.PathLike[str]) -> None:
        atomic_write_bytes(Path(path), self.serialise())

    @classmethod
    def load(cls, path: str | os.PathLike[str], layout: CorpusLayout | None = None, limits: IngestLimits | None = None) -> IndexLog:
        return cls(decode_index(Path(path).read_bytes(), layout, limits))
