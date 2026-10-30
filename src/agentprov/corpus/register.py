"""``register.jsonl``: the issue and disposition register (HL H.6; G.3.9; MN M.1.2).

One JCS line per entry, format ``agentprov-register/0.1``, sorted bytewise by ``(subject_key, code)``; an empty register is
a 0-byte file and the file is never absent (H.1.4(1)). There is one register for the whole corpus: G's former
``rejections.jsonl`` is merged into it (stage ``ingest``).

Row (all twelve members always present)::

    {"code": "ingest.archive.traversal", "detail": "container=…; size=1; member name rejected", "disposition": "not_imported",
     "ids": [], "owner": null, "previous": null, "rid": "r_…20 base32…", "rule": null, "severity": "error",
     "stage": "ingest", "subject": {"path": "x/y", "snapshot_id": "s1"}, "subject_key": "s1:x/y"}

``rid`` is ``"r_" + b32(sha256("agentprov-reg/1\\n" + JCS({subject, code, stage})))[:20]`` (H.6.2), so it is stable.
Resolutions of gaps in H.6 (recorded in AGENTS.md):

* the code registry is the closed set of H.6.3 (:func:`is_known_code`): the ``ingest.*`` codes of G.3.9, ``select.*``,
  ``map.<seal code>`` (an adapter code is ``map.<ns>.<code>``), ``expand.<kind>``, ``worker.limit.<cpu|rss|wall|output>``
  and the cross-stage codes; a stage-named code area must equal ``stage``;
* an entry whose ``(subject, code, stage)`` repeats collapses into one entry (the identity is ``rid``): the one with the
  smaller JCS bytes is kept, so the result does not depend on insertion order;
* ``detail`` is at most 200 characters of generated text without control characters; it never quotes source content.
"""

from __future__ import annotations

import io
import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from agentprov.aer.ids import EXECUTION_ID_RE
from agentprov.errors import INGEST_CODES, AgentProvError, IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import iter_jsonl
from agentprov.io.atomic import atomic_write_bytes
from agentprov.io.canonical import base32_lower_nopad, jcs_bytes, sha256_hex
if TYPE_CHECKING:  # GR-34: raw.members (and through it io.workers and host) is not loaded by readers of the register
    from agentprov.raw.members import ExpandEvent

__all__ = [
    "DISPOSITIONS",
    "FORMAT_ID",
    "SEVERITIES",
    "STAGES",
    "RegisterEntry",
    "RegisterError",
    "RegisterLog",
    "decode_register",
    "encode_register",
    "is_known_code",
]

FORMAT_ID: Final = "agentprov-register/0.1"
STAGES: Final = ("select", "ingest", "expand", "map", "sem", "prov", "validate", "capture", "package")
SEVERITIES: Final = ("info", "warning", "error")
DISPOSITIONS: Final = ("sealed", "not_imported", "failed", "withheld")
MAX_DETAIL: Final = 200

#: Cross-stage and stage-specific codes outside the ``ingest.*`` and pattern families (HL H.6.3), with the stage that
#: raises them (``None``: the stage of the job).
_FIXED_CODES: Final[Mapping[str, str | None]] = {
    "select.owned_elsewhere": "select",
    "select.not_execution_artefact": "select",
    "select.dialect_planned": "select",
    "select.licence_blocked": "select",
    "select.out_of_scope": "select",
    "select.redaction_pending": "select",  # D-324 (R-10p-5): held back until a pending redaction covers it (D-182)
    "dedup.collapsed": "select",
    "time.implausible": "validate",
    "capture.quarantined": "capture",
    "sem.failed": "sem",
    "prov.failed": "prov",
    "validate.failed": "validate",
    "release.withheld": "package",
    "rules.mismatch": "validate",
    "rules.unavailable": "validate",
    "raw.reference.unpinned_origin": "ingest",
    "raw.origin.unpinned": "ingest",
    "raw.origin.blob_mismatch": "ingest",
}
_PATTERNS: Final = (
    (re.compile(r"expand\.[a-z][a-z0-9_]*"), "expand"),
    (re.compile(r"map\.[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)?"), "map"),
    (re.compile(r"worker\.limit\.(?:cpu|rss|wall|output)"), None),
)
_RID_RE: Final = re.compile(r"r_[a-z2-7]{20}")


class RegisterError(AgentProvError):
    """A register entry is malformed (``corpus.register.invalid``)."""

    code = "corpus.register.invalid"
    exit_code = 1


def _stage_of_code(code: str) -> tuple[bool, str | None]:
    """``(known, expected stage or None)`` for a register code."""
    if code in INGEST_CODES:
        return True, "ingest"
    if code in _FIXED_CODES:
        return True, _FIXED_CODES[code]
    for pattern, stage in _PATTERNS:
        if pattern.fullmatch(code):
            return True, stage
    return False, None


def is_known_code(code: str) -> bool:
    """Whether ``code`` belongs to the register vocabulary of HL H.6.3."""
    return _stage_of_code(code)[0]


def _subject(subject: Mapping[str, Any]) -> dict[str, str]:
    keys = set(subject)
    if keys == {"ex"}:
        if not isinstance(subject["ex"], str) or EXECUTION_ID_RE.fullmatch(subject["ex"]) is None:
            raise RegisterError("subject.ex must be an execution id")
    elif keys == {"source_key"}:
        if not isinstance(subject["source_key"], str) or not subject["source_key"]:
            raise RegisterError("subject.source_key must be a non-empty string")
    elif keys == {"snapshot_id", "path"}:
        if not all(isinstance(subject[k], str) and subject[k] for k in keys):
            raise RegisterError("subject.snapshot_id and subject.path must be non-empty strings")
    else:
        raise RegisterError("a subject is {ex}, {source_key} or {snapshot_id, path}")
    return {k: str(v) for k, v in subject.items()}


@dataclass(frozen=True, slots=True)
class RegisterEntry:
    """One register entry (HL H.6.2). ``rid`` and ``subject_key`` are derived."""

    subject: Mapping[str, str]
    code: str
    severity: str
    stage: str
    disposition: str
    rule: str | None = None
    detail: str = ""
    owner: Mapping[str, str] | None = None
    ids: tuple[str, ...] = ()
    previous: Mapping[str, str] | None = None
    #: ``rid``, computed once at the end of ``__post_init__`` (D-416). It depends on ``code``, ``stage`` and ``subject``;
    #: ``subject`` is the private copy made by ``_subject`` and is never mutated, and ``dataclasses.replace`` recomputes it.
    _rid: str = field(default="", init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "subject", _subject(self.subject))
        # Type checks first: a register read back is untrusted JSON, and a value of the wrong type must be a
        # RegisterError, never a builtins.TypeError from a set lookup or a regex (CB-2).
        if not all(isinstance(v, str) for v in (self.code, self.stage, self.severity, self.disposition)):
            raise RegisterError("code, stage, severity and disposition are strings")
        known, expected = _stage_of_code(self.code)
        if not known:
            raise RegisterError("code is not in the register vocabulary (HL H.6.3)")
        if self.stage not in STAGES or self.severity not in SEVERITIES or self.disposition not in DISPOSITIONS:
            raise RegisterError("unknown stage, severity or disposition")
        if expected is not None and expected != self.stage:
            raise RegisterError("the code belongs to another stage")
        if (self.disposition == "withheld") != (self.code == "release.withheld"):
            raise RegisterError("disposition 'withheld' goes with the code 'release.withheld' only")
        if not isinstance(self.detail, str) or len(self.detail) > MAX_DETAIL or any(
            ord(c) < 0x20 or 0x7F <= ord(c) <= 0x9F for c in self.detail
        ):
            raise RegisterError("detail is generated text of at most 200 characters without control characters")
        if self.rule is not None and (not isinstance(self.rule, str) or not self.rule):
            raise RegisterError("rule is a rule reference or null")
        if self.owner is not None and (
            not isinstance(self.owner, Mapping) or set(self.owner) != {"corpus_id", "source_id"}
            or not all(isinstance(v, str) for v in self.owner.values())
        ):
            raise RegisterError("owner is {corpus_id, source_id} or null")
        if self.previous is not None and (
            not isinstance(self.previous, Mapping) or set(self.previous) != {"corpus_version", "rid"}
            or not all(isinstance(v, str) for v in self.previous.values())
        ):
            raise RegisterError("previous is {corpus_version, rid} or null")
        if self.previous is not None and _RID_RE.fullmatch(self.previous["rid"]) is None:
            raise RegisterError("previous.rid is a register id")
        if not all(isinstance(i, str) and i for i in self.ids):
            raise RegisterError("ids are non-empty strings (the published schema requires it)")
        object.__setattr__(self, "ids", tuple(sorted(set(self.ids))))
        preimage = b"agentprov-reg/1\n" + jcs_bytes({"code": self.code, "stage": self.stage, "subject": dict(self.subject)})
        object.__setattr__(self, "_rid", "r_" + base32_lower_nopad(bytes.fromhex(sha256_hex(preimage)))[:20])

    @property
    def subject_key(self) -> str:
        s = self.subject
        if "ex" in s:
            return s["ex"]
        if "source_key" in s:
            return s["source_key"]
        return f"{s['snapshot_id']}:{s['path']}"

    @property
    def rid(self) -> str:
        return self._rid

    def to_json(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "detail": self.detail,
            "disposition": self.disposition,
            "ids": list(self.ids),
            "owner": None if self.owner is None else dict(self.owner),
            "previous": None if self.previous is None else dict(self.previous),
            "rid": self.rid,
            "rule": self.rule,
            "severity": self.severity,
            "stage": self.stage,
            "subject": dict(self.subject),
            "subject_key": self.subject_key,
        }

    def canonical(self) -> bytes:
        return jcs_bytes(self.to_json())

    @property
    def sort_key(self) -> tuple[bytes, bytes, bytes]:
        return self._sort_key(self.canonical())

    def _sort_key(self, canonical: bytes) -> tuple[bytes, bytes, bytes]:
        return (self.subject_key.encode("utf-8"), self.code.encode("ascii"), canonical)

    @classmethod
    def from_json(cls, obj: object) -> RegisterEntry:
        keys = {"code", "detail", "disposition", "ids", "owner", "previous", "rid", "rule", "severity", "stage", "subject", "subject_key"}
        if not isinstance(obj, Mapping) or set(obj) != keys:
            raise RegisterError("a register entry has exactly the documented fields")
        ids = obj["ids"]
        if not isinstance(ids, list) or not all(isinstance(i, str) and i for i in ids):
            raise RegisterError("ids is a list of non-empty strings")
        if not isinstance(obj["subject"], Mapping):
            raise RegisterError("subject is an object")
        try:
            entry = cls(
                subject=obj["subject"],
                code=obj["code"],
                severity=obj["severity"],
                stage=obj["stage"],
                disposition=obj["disposition"],
                rule=obj["rule"],
                detail=obj["detail"],
                owner=obj["owner"],
                ids=tuple(ids),
                previous=obj["previous"],
            )
        except (TypeError, ValueError) as exc:  # belt and braces (CB-2): untrusted JSON never ends in an internal error
            raise RegisterError(f"a member has the wrong type ({type(exc).__name__})") from None
        if obj["rid"] != entry.rid or obj["subject_key"] != entry.subject_key:
            raise RegisterError("rid or subject_key does not match the entry")
        return entry

    @classmethod
    def from_event(cls, event: ExpandEvent) -> RegisterEntry:
        """The entry for an ``expand`` outcome (a rejected member or container, a finding, the interpreter advisory)."""
        return cls(
            subject={"snapshot_id": event.snapshot_id, "path": event.path},
            code=event.code,
            severity=event.severity,
            stage=event.stage,
            disposition=event.disposition,
            detail=event.detail,
        )


def _collapse_sorted(entries: Iterable[RegisterEntry]) -> list[RegisterEntry]:
    """Collapse repeats of one ``rid`` (keep the smaller JCS bytes) and sort by ``(subject_key, code)``."""
    return [entry for _, entry in _collapse_sorted_canonical(entries)]


def _collapse_sorted_canonical(entries: Iterable[RegisterEntry]) -> list[tuple[bytes, RegisterEntry]]:
    """:func:`_collapse_sorted` with each entry's canonical bytes, computed once per entry (D-416)."""
    best: dict[str, tuple[bytes, RegisterEntry]] = {}
    for entry in entries:
        canonical = entry.canonical()
        current = best.get(entry.rid)
        if current is None or canonical < current[0]:
            best[entry.rid] = (canonical, entry)
    return sorted(best.values(), key=lambda pair: pair[1]._sort_key(pair[0]))


def encode_register(entries: Iterable[RegisterEntry]) -> bytes:
    """The bytes of ``register.jsonl``: collapsed by ``rid``, sorted by ``(subject_key, code)``, LF-terminated."""
    return b"".join(canonical + b"\n" for canonical, _ in _collapse_sorted_canonical(entries))


def decode_register(data: bytes, limits: IngestLimits | None = None) -> list[RegisterEntry]:
    """Parse ``register.jsonl`` strictly; the order must be the canonical one."""
    entries: list[RegisterEntry] = []
    try:
        for _, _, value in iter_jsonl(io.BytesIO(data), limits):
            entries.append(RegisterEntry.from_json(value))
    except IngestError as exc:
        raise RegisterError(f"register.jsonl is not strict JSONL ({exc.code})") from None
    if encode_register(entries) != data:
        raise RegisterError("register.jsonl is not sorted, duplicate-free and canonical", code="corpus.register.unsorted")
    return entries


class RegisterLog:
    """The register of one corpus: accumulates entries, writes ``register.jsonl`` atomically (whole file)."""

    def __init__(self, entries: Iterable[RegisterEntry] = ()) -> None:
        self._entries: list[RegisterEntry] = []
        for entry in entries:
            self.add(entry)

    def add(self, entry: RegisterEntry) -> None:
        self._entries.append(entry)

    def extend(self, entries: Iterable[RegisterEntry]) -> None:
        for entry in entries:
            self.add(entry)

    def entries(self) -> list[RegisterEntry]:
        return _collapse_sorted(self._entries)

    def discard_execution(self, ex: str) -> None:
        """Forget every entry whose subject is ``ex`` (a working corpus re-processes a failed unit)."""
        self._entries = [e for e in self._entries if e.subject.get("ex") != ex]

    def discard_failure(self, subject: Mapping[str, str]) -> None:
        """Forget the ``map`` failures recorded for ``subject`` (``map.adapter_defect`` and ``worker.limit.*``, disposition
        ``failed``): a container whose plan job failed has no index row and is mapped again by the next run (RD-3,
        CD-9). Selection, dedup and not-imported entries are kept."""
        key = _subject(subject)
        self._entries = [e for e in self._entries if not (
            e.subject == key and e.stage == "map" and e.disposition == "failed"
            and (e.code == "map.adapter_defect" or e.code.startswith("worker.limit.")))]

    def for_execution(self, ex: str) -> list[RegisterEntry]:
        return [e for e in self.entries() if e.subject.get("ex") == ex]

    def severity_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for entry in self.entries():
            counts[entry.severity] = counts.get(entry.severity, 0) + 1
        return counts

    def serialise(self) -> bytes:
        return encode_register(self._entries)

    def write(self, path: str | os.PathLike[str]) -> None:
        atomic_write_bytes(Path(path), self.serialise())

    @classmethod
    def load(cls, path: str | os.PathLike[str], limits: IngestLimits | None = None) -> RegisterLog:
        return cls(decode_register(Path(path).read_bytes(), limits))
