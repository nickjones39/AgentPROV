"""``agentprov verify``: the verification levels of HL H.5.5 (``checksums``, ``chain``, ``rederive``; MN N.2.6; D-38, D-39).

:func:`verify_corpus` reads a corpus **read-only** (tree mode, or archive mode through
:class:`agentprov.corpus.archive.ArchiveCorpusReader`) and returns a :class:`VerifyReport`. Nothing is written into the
corpus; ``rederive`` derives into a private scratch tree that is removed afterwards.

**checksums.** The closed-world ``checksums.sha256`` check of :mod:`agentprov.corpus.integrity` (every listed file
matches, nothing unlisted). A working tree has no ``checksums.sha256`` (it is written at sealing): the check is reported
``unverified`` (``checksums.absent``), never passed. ``--root-digest`` (D-39) compares the root digest (the sha256 of
``checksums.sha256``) with digests published outside the corpus (``root_digest.mismatch``); it is what detects a
``checksums.sha256`` an attacker regenerated over tampered files that no other check covers (K.12.5).

**chain** (``checksums`` plus):

* the manifest: schema and semantic validation (:func:`agentprov.corpus.manifest.validate_manifest`, which recomputes the
  content digest; ``manifest.content_digest``), and every member sealing computes from the corpus recomputed and
  compared: ``files`` (FileRefs), ``digests`` (set digests, index, register, members), ``counts`` and each snapshot's
  counts (register, index and counts reconciled, H.6.1 R5), ``duplicates``, ``validation`` (D-40, incl.
  ``linkage_resolved_pct``), ``models``, ``framework_identities``, ``facet_schema`` and each catalogue's ``rules_used``;
* the index: strict, canonical, sorted rows whose paths recompute from the layout (:class:`CorpusReader`); every code in a
  row's ``issues`` has a register entry for that execution (R5); every snapshot a row names is declared in the manifest's
  ``sources[].snapshots`` (``index.snapshot.undeclared``) and a row's ``n_origins`` equals the ``raw/origins.jsonl``
  lines of its primary artefact (``index.n_origins``; H.3.1, H.7.2(1); F-12C-02; also on a working tree);
* raw objects: every stored object hashes to its address (``raw.digest.mismatch``; a sealed object whose listed digest
  matched and equals its address is not read again), every listed object is stored, tombstoned (``raw.tombstoned``,
  reported with its reason and date, never as silently missing) or referenced (``raw/REFERENCES.json``), and a
  referenced object must belong to a snapshot whose declared raw policy is ``reference`` (``raw.reference.not_permitted``,
  failed; H.4.1; F-12C-01, D-160; a working manifest declares no raw policy, so the check is a sealed one); every selected
  member object's CRC-32 and size equal its ``raw/members.jsonl`` row (``raw.member.crc32`` / ``raw.member.size``,
  AD-12; HL-T14);
* per execution: the AER seal re-hashed (``aer.seal.*``) and its execution digest equal to the index's; the header's
  ``artifacts`` equal to the row's ``raw`` and each artefact's size to its object's; each SEM document's digest, execution
  and AER digest (``sem.input.aer``); each PROV file's sha256 and, for ``agentprov-prov/0.1``, the raw, AER and SEM digests
  its top level records (``prov.input.*``); the validation row's JCS digest; the full-row facets, completeness and unit
  re-derived from AER and SEM (``index.facets``);
* files present (sealed corpora): every execution file under ``aer/``, ``sem/`` and ``prov/`` is named by an index row
  (``index.orphan``; P-1); ``schemas/**`` equal the package's published schemas (``schemas.mismatch``,
  ``schemas.unavailable``), ``WITHHELD.json`` is declared in ``files`` (``withheld.undeclared``), so is
  ``raw/REFERENCES.json`` (``references.undeclared``; D-237), and a ``views/`` file has a ``views`` stage and an index row
  (``views.undeclared``; P-2);
* withholding (sealed corpora; H.4.5, G.9.5; D-230..D-236, D-311): ``WITHHELD.json`` parses as ``agentprov-withheld/0.1``
  or ``/0.2`` (``withheld.invalid``) and comes with the schema of its version; a tombstoned object is accepted exactly when
  ``WITHHELD.json`` lists it (otherwise ``raw.tombstoned`` as before), and a listed object that is not stored counts as
  withheld, never as missing; a listed object or a file of a listed execution that *is* in the tree is
  ``withheld.present``; a listed execution has no index row (``withheld.row``) and a ``release.withheld`` register entry
  (``withheld.unregistered``), and every ``release.withheld`` entry names a listed execution (``withheld.unlisted``); an
  entry's origins are the object's ``raw/origins.jsonl`` origins (``withheld.origins``); no index row names a snapshot
  whose raw policy is ``withhold`` (``withheld.policy``); and no released file matches a rule of the source profile's
  ``[withhold]`` policy (``withheld.rule_hit``, the backstop; ``rules/`` and ``schemas/`` are not scanned); for an issue
  rule of that policy (D-311), no released execution carries its code in its index row, its register entries or its
  AER seal (``withheld.issue_released``), and a finding that names the rule names an execution the register records
  with the code (``withheld.issue_unsupported``); a split descriptor and its byte parts are listed all or none
  (``withheld.split_part``), and so are a carved blob and its source (``withheld.carved``; D-315); and no container of
  a withheld object, at any level of ``raw/members.jsonl``, is released (``withheld.container``; AD-12, D-461); the rule
  rescan also reads every released stored archive decoded, and one it cannot read is ``withheld.unscanned`` (D-450);
* catalogue authority (AD-14): the recorded catalogues and profiles, and the ``rules/`` copies a sealed manifest names,
  against the installed package at the recorded versions (``rules.mismatch``; ``rules.unavailable`` is ``unverified``);
* ``--against-pins``: every ``git`` origin's blob id recomputed from the object bytes, its commit among the in-package
  profile's pins, and its path's blob in the pinned tree listing when a listing is available
  (``raw.origin.blob_mismatch``; no listing: ``unverified``).

**rederive** (``chain`` plus): ``recompute --dry-run`` over the selection through U2's engine
(:class:`agentprov.corpus.derive.Derivation`), including the re-map from the stored raw objects (and so the ``expand``
stage) with package catalogues only (AD-14), into a private scratch tree; every output must be byte-identical. The
re-map needs the import pipeline (``adapters.runner``, L6), which is injected (:class:`ImportHooks`, M.5.2(1)); without
it the re-map is ``unverified``. A declared version that differs from the package's makes an output
``changed_explained``: reported ``unverified`` (identity cannot be confirmed), never passed.

**Sampling** (``--sample N --seed S``; N.1.7): a seeded uniform sample without replacement over the sorted execution ids
(:func:`sample_executions`); the per-execution checks of ``chain`` and the ``rederive`` level run on the sample, the
corpus-level checks on everything. The manifest members that need every AER (``records_by_kind``, ``generic_types``,
``models``, ``framework_identities``, ``rules_used``) are not compared under a sample (a notice says so). Release mode
forbids sampling.

**Outcome.** A finding is ``failed``, ``unverified`` or ``tombstoned``. :meth:`VerifyReport.exit_code`: 1 when anything
failed, or, in release mode, when anything is unverified or tombstoned (H.5.5; N.1.3); else 0. A tombstoned object that
``WITHHELD.json`` lists is no finding (it is counted, ``tombstoned_withheld``): the corpus version withheld it (P-3).
"""

from __future__ import annotations

import hashlib
import os
import shutil
import zlib
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from agentprov.aer.reader import load_aer_bytes
from agentprov.corpus.authority import (
    DRIFT,
    DRIFT_DETAIL,
    MISMATCH,
    PackageResources,
    check_sealed_rules,
    catalogue_drift,
    check_stage_rules,
    package_resources,
)
from agentprov.corpus.facets import completeness_of, facet_members, facet_schema
from agentprov.corpus.index import IndexRow, primary_role, row_status
from agentprov.corpus.integrity import (
    VERIFY_LEVELS,
    ChecksumSource,
    TreeSource,
    parse_checksums,
    verify_checksum_source,
)
from agentprov.corpus.layout import (
    CHECKSUMS,
    EXECUTIONS,
    MANIFEST,
    REGISTER,
    SCHEMA_FILES,
    WITHHELD,
    WORKING_ONLY_CODES,
    classify_relpath,
    iter_tree,
)
from agentprov.corpus.manifest import (
    CORPUS_FORMATS,
    AerStats,
    ManifestError,
    aer_schema_resource,
    corpus_counts,
    digests_of,
    duplicate_summary,
    file_ref,
    raw_dispositions,
    rule_catalogue_refs,
    schema_resource,
    snapshot_counts,
    validate_manifest,
    validation_summary,
)
from agentprov.corpus.reader import CorpusReader, CorpusReadError
from agentprov.corpus.register import RegisterEntry
from agentprov.corpus.scratch import scratch_tree
from agentprov.corpus.stages import StageKey, stage_map
from agentprov.corpus.withheld import SCHEMA_RESOURCE as WITHHELD_SCHEMA
from agentprov.corpus.withheld import WithheldDocument, decode_withheld
from agentprov.errors import AgentProvError
from agentprov.io.canonical import jcs_bytes, sha256_hex
from agentprov.progress import NULL_PROGRESS, Progress
from agentprov.raw.members import MemberRow
from agentprov.raw.origins import OriginRow
from agentprov.sem.reader import load_sem_bytes
from agentprov.sem.types import SemDocument

__all__ = [
    "FAILED",
    "LEVELS",
    "TOMBSTONED",
    "UNVERIFIED",
    "Finding",
    "ImportHooks",
    "VerifyError",
    "VerifyReport",
    "VerifyUsageError",
    "git_blob_sha1",
    "sample_executions",
    "verify_corpus",
]

LEVELS: Final = VERIFY_LEVELS
FAILED: Final = "failed"
UNVERIFIED: Final = "unverified"
TOMBSTONED: Final = "tombstoned"
PROV_SPEC: Final = "agentprov-prov/0.1"
REFERENCES: Final = "raw/REFERENCES.json"
TOMBSTONES: Final = "raw/tombstones.jsonl"
_CHUNK: Final = 1 << 20
_SHA_REF: Final = "sha256:"
#: The published schemas every sealed corpus holds (``corpus.package.seal`` writes these two; H.1.2, AD-10 row 13).
_SEALED_SCHEMAS: Final = ("aer-0.1.schema.json", "corpus-0.1.schema.json")
#: Manifest members that need a pass over every AER (not compared under ``--sample``).
_FULL_PASS_COUNTS: Final = ("records_by_kind", "generic_types")


class VerifyError(AgentProvError):
    """``verify`` could not run (exit 1)."""

    code = "verify.failed"
    exit_code = 1


class VerifyUsageError(AgentProvError):
    """An invalid combination of options (exit 2): ``--sample`` in release mode, a sample without a seed, release mode
    without a root digest in tree mode (D-39), an unknown level."""

    code = "verify.usage"
    exit_code = 2


@dataclass(frozen=True, slots=True)
class Finding:
    """One check that did not pass. ``subject`` is ``{"path": <corpus path or generated label>}`` or ``{"ex": <id>}``;
    ``detail`` is generated text (never corpus content); ``level`` names the level whose check found it."""

    code: str
    subject: Mapping[str, str]
    status: str  # failed | unverified | tombstoned
    level: str  # checksums | chain | rederive
    detail: str = ""

    def to_json(self) -> dict[str, Any]:
        return {"code": self.code, "detail": self.detail, "level": self.level, "status": self.status,
                "subject": dict(self.subject)}  # fmt: skip


@dataclass(frozen=True)
class ImportHooks:
    """The import pipeline a ``rederive`` re-map needs (``adapters.runner``, L6), injected by the caller (M.5.2(1)):
    ``import_source`` (``adapters.runner.importer.import_source``), ``candidate_type``
    (``adapters.types.CandidateArtefact``) and ``filters_type`` (``adapters.runner.importer.ImportFilters``)."""

    import_source: Callable[..., Any]
    candidate_type: Callable[..., Any]
    filters_type: Callable[..., Any]


@dataclass
class VerifyReport:
    """The outcome of :func:`verify_corpus` (see the module docstring)."""

    level: str
    mode: str  # tree | archive
    state: str  # sealed | working
    corpus_id: str | None = None
    corpus_version: str | None = None
    content_digest: str | None = None
    root_digest: str | None = None
    findings: list[Finding] = field(default_factory=list)
    counters: dict[str, int] = field(default_factory=dict)
    notices: list[str] = field(default_factory=list)
    sample: dict[str, Any] | None = None
    release: bool = False

    @property
    def failures(self) -> list[Finding]:
        return [f for f in self.findings if f.status == FAILED]

    @property
    def unverified(self) -> list[Finding]:
        return [f for f in self.findings if f.status != FAILED]

    @property
    def ok(self) -> bool:
        """Every requested check passed: nothing failed, nothing unverified or tombstoned."""
        return not self.findings

    def passed(self, release: bool | None = None) -> bool:
        """H.5.5: nothing failed and, in release mode, nothing unverified or tombstoned."""
        strict = self.release if release is None else release
        return not self.failures and not (strict and self.unverified)

    @property
    def exit_code(self) -> int:
        return 0 if self.passed() else 1

    def codes(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for finding in self.findings:
            out[finding.code] = out.get(finding.code, 0) + 1
        return dict(sorted(out.items()))

    def to_json(self) -> dict[str, Any]:
        return {
            "content_digest": self.content_digest, "corpus_id": self.corpus_id, "corpus_version": self.corpus_version,
            "counters": dict(sorted(self.counters.items())), "findings": [f.to_json() for f in self.findings],
            "level": self.level, "mode": self.mode, "notices": list(self.notices), "ok": self.ok,
            "passed": self.passed(), "release": self.release, "root_digest": self.root_digest, "sample": self.sample,
            "state": self.state,
        }  # fmt: skip


# ================================================================================================ helpers
def sample_executions(exs: Iterable[str], n: int, seed: str) -> list[str]:
    """A seeded uniform sample of ``n`` execution ids without replacement (N.1.7), sorted.

    The ids are ordered by ``sha256("agentprov-sample/1\\n" + seed + "\\n" + ex)`` (a seeded random permutation that does
    not depend on Python's ``random`` implementation or the hash seed) and the first ``n`` are taken."""
    if n < 0:
        raise ValueError("a sample size is >= 0")
    ordered = sorted(set(exs), key=lambda ex: (hashlib.sha256(f"agentprov-sample/1\n{seed}\n{ex}".encode()).digest(), ex))
    return sorted(ordered[:n], key=lambda ex: ex.encode("ascii"))


def git_blob_sha1(stream_chunks: Iterable[bytes], size: int) -> str:
    """The git blob id of ``size`` bytes given as chunks: ``sha1("blob <size>\\0" + bytes)``."""
    digest = hashlib.sha1(f"blob {size}\0".encode(), usedforsecurity=False)
    for chunk in stream_chunks:
        digest.update(chunk)
    return digest.hexdigest()


def _hex(value: object) -> str | None:
    return value[len(_SHA_REF):] if isinstance(value, str) and value.startswith(_SHA_REF) else None


def _obj(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _seq(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _object_sha(label: str) -> str:
    return label.rsplit("/", 1)[-1].split(".", 1)[0]


def _stages(derivation: Mapping[str, Any] | None) -> dict[StageKey, dict[str, Any]]:
    """The stage definitions by name; ``expand`` by ``("expand", fn_digest)`` (several expansions are all kept, D-380)."""
    return stage_map(derivation)


# ================================================================================================ the verifier
class _Verifier:
    def __init__(self, reader: CorpusReader, source: ChecksumSource | None, *, level: str, mode: str, release: bool,
                 sample: Sequence[str] | None, package: PackageResources, absent_unverified: bool) -> None:
        self.reader = reader
        self.source = source
        self.level = level
        self.release = release
        self.sample = None if sample is None else frozenset(sample)
        self.package = package
        self.absent_unverified = absent_unverified
        self.report = VerifyReport(level=level, mode=mode, state=reader.state, release=release)
        self.counters = self.report.counters
        self.matched: dict[str, tuple[str, int]] = {}
        self.checksum_entries: list[str] = []
        self.rows: list[IndexRow] = []
        self.register: list[RegisterEntry] = []
        self.members: list[MemberRow] = []
        self.origins: list[OriginRow] = []
        self.loaded: set[str] = set()  # the JSONL documents read and parsed (register, origins, members)
        self.manifest: dict[str, Any] | None = None
        self.stages: dict[StageKey, dict[str, Any]] = {}
        self.objects: dict[str, tuple[str, int]] = {}  # sha -> (label, size) of every object present
        self.tombstones: dict[str, Any] = {}
        self.referenced: set[str] = set()
        self.withheld: WithheldDocument | None = None
        self._object_snapshots: dict[str, set[str]] | None = None  # archive root -> snapshot ids (F-12C-01), lazily
        self._containers: dict[str, str] | None = None  # member sha -> container sha
        self._crc: dict[str, str] = {}  # sha -> CRC-32 hex of the objects that were read
        self.stats_added = 0  # executions that reached the statistics pass
        self.seal_codes: dict[str, frozenset[str]] = {}  # ex -> the issue codes of its AER seal (when it has any)

    # -------------------------------------------------------------------------------------- findings
    def add(self, code: str, subject: Mapping[str, str] | str, *, status: str = FAILED, level: str = "chain",
            detail: str = "") -> None:
        if isinstance(subject, str):
            subject = {"path": subject}
        self.report.findings.append(Finding(code, dict(subject), status, level, detail[:300]))

    def absent(self, code: str, subject: Mapping[str, str] | str, detail: str) -> None:
        """A file the check needs is absent: failed, or ``unverified`` for a lone meta archive (D-38)."""
        if self.absent_unverified:
            self.add("archive.not_present", subject, status=UNVERIFIED, detail="not in the archives given")
        else:
            self.add(code, subject, detail=detail)

    def count(self, name: str, n: int = 1) -> None:
        self.counters[name] = self.counters.get(name, 0) + n

    # -------------------------------------------------------------------------------------- checksums
    def checksums(self, root_digests: Sequence[str]) -> None:
        reader = self.reader
        if reader.sealed and self.source is not None:
            def matched(path: str, digest: str, size: int) -> None:
                self.matched[path] = (digest, size)

            report = verify_checksum_source(self.source, on_match=matched)
            self.counters["files_listed"] = report.listed
            self.counters["files_matched"] = report.matched
            for f in report.findings:
                if f.code == "checksums.missing" and self.absent_unverified:
                    self.add("archive.not_present", f.path, status=UNVERIFIED, level="checksums",
                             detail="listed, not in the archives given")
                    continue
                self.add(f.code, f.path, level="checksums", detail=f.detail)
            data = self.source.read_checksums()
            if data is not None:
                self.report.root_digest = _SHA_REF + sha256_hex(data)
                self.checksum_entries = [e.path for e in parse_checksums(data)[0]]
        else:
            self.add("checksums.absent", CHECKSUMS, status=UNVERIFIED, level="checksums",
                     detail="a working tree has no checksums.sha256 (it is written at sealing)")
            scan = iter_tree(reader.root)
            for finding in scan.findings:
                if finding.code not in WORKING_ONLY_CODES:  # a working tree need not be closed-world until it is sealed
                    self.add(finding.code, finding.label, status=UNVERIFIED, level="checksums",
                             detail=f"{finding.detail}; sealing refuses a tree that is not closed-world (H.1.5(4))")
        for given in root_digests:
            if self.report.root_digest is None:
                self.add("root_digest.unverifiable", CHECKSUMS, level="checksums",
                         detail="no checksums.sha256 to compare the published root digest with")
            elif given != self.report.root_digest:
                self.add("root_digest.mismatch", CHECKSUMS, level="checksums",
                         detail="the root digest differs from the one published outside the corpus (D-39)")
        if root_digests:
            self.counters["root_digests_compared"] = len(root_digests)

    # -------------------------------------------------------------------------------------- chain: documents
    def _read(self, label: str) -> bytes | None:
        try:
            if not self.reader.exists(label):
                return None
            return self.reader.read_bytes(label, stored=True)
        except (CorpusReadError, AgentProvError):
            return None

    def identity(self) -> None:
        """The corpus id, version and recorded content digest (the ``checksums`` level reads nothing else)."""
        try:
            manifest = self.reader.manifest() or {}
        except AgentProvError:
            return
        for attr, key in (("corpus_id", "corpus_id"), ("corpus_version", "corpus_version"),
                          ("content_digest", "content_digest")):
            value = manifest.get(key)
            setattr(self.report, attr, value if isinstance(value, str) else None)

    def documents(self) -> bool:
        reader = self.reader
        try:
            self.manifest = reader.manifest()
        except AgentProvError as exc:
            self.add("corpus.read.manifest", MANIFEST, detail=f"corpus.json cannot be read ({exc.code})")
            return False
        manifest = self.manifest or {}
        self.report.corpus_id = manifest.get("corpus_id") if isinstance(manifest.get("corpus_id"), str) else None
        self.report.corpus_version = manifest.get("corpus_version") if isinstance(manifest.get("corpus_version"), str) else None
        self.report.content_digest = manifest.get("content_digest") if isinstance(manifest.get("content_digest"), str) else None
        if reader.sealed:
            for issue in validate_manifest(manifest):
                code = "manifest.content_digest" if issue.code == "content_digest" else "manifest.invalid"
                self.add(code, MANIFEST, detail=f"{issue.pointer or '/'} {issue.code}")
        try:
            self.stages = _stages(reader.derivation())
        except AgentProvError as exc:
            self.add("corpus.read.derivation", "derivation.json", detail=f"derivation.json cannot be read ({exc.code})")
        try:
            self.rows = list(reader.iter_index())
        except AgentProvError as exc:
            self.absent("index.invalid", EXECUTIONS, f"executions.jsonl is not a valid index ({exc.code})")
            self.rows = []
        else:
            self.loaded.add(EXECUTIONS)
        self.counters["executions"] = len(self.rows)
        for name, loader, attr in (("register.jsonl", reader.register, "register"),
                                   ("raw/origins.jsonl", reader.origins, "origins"),
                                   ("raw/members.jsonl", reader.members, "members")):
            if not reader.exists(name):
                if reader.sealed:
                    self.absent("corpus.read.missing", name, f"{name} is absent")
                continue
            try:
                setattr(self, attr, loader())
                self.loaded.add(name)
            except AgentProvError as exc:
                self.add("corpus.read.invalid", name, detail=f"{name} is not valid ({exc.code})")
        if reader.exists(TOMBSTONES):
            from agentprov.corpus.purge import decode_tombstones

            try:
                self.tombstones = {t.sha256: t for t in decode_tombstones(reader.read_bytes(TOMBSTONES), reader.limits)}
            except AgentProvError as exc:
                self.add("corpus.read.invalid", TOMBSTONES, detail=f"the tombstones file is not valid ({exc.code})")
        if reader.exists(REFERENCES):
            from agentprov.raw.references import parse_references

            try:
                self.referenced = {r.sha256 for r in parse_references(reader.read_bytes(REFERENCES), reader.limits)}
            except AgentProvError as exc:
                self.add("corpus.read.invalid", REFERENCES, detail=f"REFERENCES.json is not valid ({exc.code})")
        if reader.exists(WITHHELD):
            try:
                self.withheld = decode_withheld(reader.read_bytes(WITHHELD), reader.limits)
            except AgentProvError as exc:
                self.add("withheld.invalid", WITHHELD, detail=f"WITHHELD.json is not a valid agentprov-withheld "
                                                              f"document ({exc.code})")
        return True

    def _withheld_object(self, sha: str) -> bool:
        return self.withheld is not None and sha in self.withheld.objects

    # -------------------------------------------------------------------------------------- chain: raw objects
    def _object_labels(self) -> dict[str, int | None]:
        """Every raw object present (label -> size, or ``None`` when unknown)."""
        archives = getattr(self.reader, "archives", None)
        if archives is not None:
            return {label: archives.size(label) for label in archives.labels() if classify_relpath(label) == "raw_object"}
        return {label: size for label, role, size in iter_tree(self.reader.root).files if role == "raw_object"}

    def _stream(self, label: str) -> Iterable[bytes]:
        with self.reader.open_file(label, stored=True) as stream:
            while chunk := stream.read(_CHUNK):
                yield chunk

    def raw_objects(self, member_objects: set[str]) -> None:
        for label in sorted(self._object_labels()):
            sha = _object_sha(label)
            known = self.matched.get(label)
            if known is not None and sha not in member_objects:
                if known[0] != sha:
                    self.add("raw.digest.mismatch", label, detail="the object does not hash to its address")
                self.objects[sha] = (label, known[1])
                self.count("raw_objects")
                continue
            digest, crc, n = hashlib.sha256(), 0, 0
            try:
                for chunk in self._stream(label):
                    digest.update(chunk)
                    crc = zlib.crc32(chunk, crc)
                    n += len(chunk)
            except AgentProvError as exc:
                self.add("raw.object.unreadable", label, detail=f"the object cannot be read ({exc.code})")
                continue
            self.count("raw_objects")
            self.count("raw_rehashed")
            if digest.hexdigest() != sha:
                self.add("raw.digest.mismatch", label, detail="the object does not hash to its address")
            self.objects[sha] = (label, n)
            self._crc[sha] = f"{crc:08x}"

    def _missing_object(self, sha: str, why: str) -> None:
        tomb = self.tombstones.get(sha)
        subject = {"path": f"raw/objects/{sha[:2]}/{sha}"}
        if self._withheld_object(sha):
            self.count("raw_withheld")
            return  # withheld by this corpus version (WITHHELD.json; H.4.5)
        if tomb is not None:
            return  # reported once per tombstone (tombstoned)
        if sha in self.referenced:
            if self._reference_permitted(sha):
                self.count("raw_referenced")
            else:
                self.add("raw.reference.not_permitted", subject,
                         detail="the object is referenced, not stored, but the raw policy of its snapshot(s) is include "
                                "(H.4.1); its bytes and its AER artifacts link were not checked")
            return
        self.absent("raw.object.missing", subject, why)

    def _snapshot_policies(self) -> dict[str, str]:
        """``snapshot_id -> raw_policy`` as the manifest declares it (a sealed manifest; a working one records none)."""
        out: dict[str, str] = {}
        for src in _seq((self.manifest or {}).get("sources")):
            for snapshot in _seq(src.get("snapshots")) if isinstance(src, Mapping) else ():
                if isinstance(snapshot, Mapping) and isinstance(snapshot.get("raw_policy"), str):
                    out[str(snapshot.get("snapshot_id"))] = snapshot["raw_policy"]
        return out

    def _reference_permitted(self, sha: str) -> bool:
        """F-12C-01 (H.4.1): a not-stored object may stand behind a ``raw/REFERENCES.json`` entry only when a snapshot it
        belongs to has raw policy ``reference``. Its snapshots are those of the rows that list it, of the rows that list
        its container (a member object) and of the rows that list its members (a container); an object no row lists
        belongs to every snapshot. A manifest that declares no raw policy (a working tree; the policy is set at sealing)
        permits the reference, as before."""
        policies = self._snapshot_policies()
        if not policies:
            return True
        if self._object_snapshots is None:
            by_root: dict[str, set[str]] = {}  # an archive and every member under it share their snapshots
            for row in self.rows:
                for ref in row.raw:
                    by_root.setdefault(self._archive_root(ref.sha256), set()).update(row.snapshot_ids)
            self._object_snapshots = by_root
        snapshots = self._object_snapshots.get(self._archive_root(sha)) or set(policies)
        return any(policies.get(sid) == "reference" for sid in snapshots)

    def _archive_root(self, sha: str) -> str:
        """The outermost container of a member object (``raw/members.jsonl``), or the object itself."""
        if self._containers is None:
            self._containers = {m.sha256: m.container for m in self.members if m.sha256 is not None}
        seen: set[str] = set()
        while sha in self._containers and sha not in seen:
            seen.add(sha)
            sha = self._containers[sha]
        return sha

    def raw_chain(self) -> None:
        member_objects = {m.sha256 for m in self.members if m.sha256 is not None}
        self.raw_objects(member_objects)
        for sha, tomb in sorted(self.tombstones.items()):
            if self._withheld_object(sha):
                self.count("tombstoned_withheld")  # P-3: the corpus version withheld it (WITHHELD.json)
                continue
            self.add("raw.tombstoned", {"path": f"raw/objects/{sha[:2]}/{sha}"}, status=TOMBSTONED,
                     detail=f"purged {tomb.date} ({tomb.reason}); checks that need its bytes are skipped")
            self.count("tombstoned")
        if self.withheld is not None:
            for sha in sorted(self.withheld.objects):
                if sha in self.objects:
                    self.add("withheld.present", self.objects[sha][0],
                             detail="WITHHELD.json lists the object, but its bytes are in the corpus (H.4.5)")
        for member in self.members:
            if member.disposition != "selected" or member.sha256 is None:
                continue
            self.count("members_checked")
            if member.sha256 not in self.objects:
                self._missing_object(member.sha256, "a selected member object is not stored")
                continue
            label, size = self.objects[member.sha256]
            if member.size != size:
                self.add("raw.member.size", label, detail="the member object's size differs from raw/members.jsonl (AD-12)")
            if self._crc.get(member.sha256) not in (None, member.crc32):
                self.add("raw.member.crc32", label, detail="the member object's CRC-32 differs from raw/members.jsonl (AD-12)")
        for container in sorted({m.container for m in self.members}):
            if container not in self.objects:
                self._missing_object(container, "an expanded container is not stored")
        for origin_row in self.origins:  # D-218: a carved blob is re-carved from its source by a re-map (rederive, recompute)
            if origin_row.origin.kind == "carved":
                self.count("carved_checked")
                source = str(origin_row.origin.data["from"])
                if source not in self.objects:
                    self._missing_object(source, "the source object of a carved blob is not stored")
        listed = {o.sha256 for o in self.origins}
        for row in self.rows:
            listed.update(r.sha256 for r in row.raw)
        for sha in sorted(listed - set(self.objects) - member_objects - {m.container for m in self.members}):
            self._missing_object(sha, "a raw object the corpus lists is not stored")

    def _source_tables(self) -> list[Mapping[str, Any]]:
        """The ``[source]`` tables of the in-package source profiles the corpus records (AD-14: never its copies)."""
        manifest = self.manifest or {}
        refs: list[tuple[str, int]] = []
        for source in manifest.get("sources") or ():
            profile = source.get("profile") if isinstance(source, Mapping) else None
            if isinstance(profile, Mapping) and isinstance(profile.get("id"), str) and isinstance(profile.get("version"), int):
                refs.append((profile["id"], profile["version"]))
        aer = self.stages.get("aer") or {}
        if isinstance(aer.get("profile"), str) and "@" in aer["profile"] and aer["profile"].rpartition("@")[2].isdigit():
            pid, _, number = aer["profile"].rpartition("@")
            refs.append((pid, int(number)))
        tables: list[Mapping[str, Any]] = []
        for pid, version in sorted(set(refs)):
            found = self.package.source_profile(pid, version)
            if found is None:
                self.add("rules.unavailable", f"source profile {pid}@{version}", status=UNVERIFIED,
                         detail="the pins of a profile the package does not ship cannot be compared")
                continue
            tables.append(found[1])
        return tables

    def references(self) -> None:
        """Every ``raw/REFERENCES.json`` entry must resolve to an in-package profile pin (R-43; HL-T16). Nothing is
        contacted; the bytes of a referenced object are checked by ``fetch`` and ``rederive``."""
        if not self.reader.exists(REFERENCES):
            return
        from agentprov.raw.fetch import recipes_from_source
        from agentprov.raw.references import parse_references, resolve_reference

        try:
            references = parse_references(self.reader.read_bytes(REFERENCES), self.reader.limits)
        except AgentProvError:
            return  # reported by documents()
        recipes = [r for table in self._source_tables() for r in recipes_from_source(table)[0]]
        for reference in references:
            self.count("references_checked")
            if resolve_reference(reference, recipes).status == "unpinned":
                self.add("raw.reference.unpinned_origin", {"path": f"raw/objects/{reference.sha256[:2]}/{reference.sha256}"},
                         detail="no origin of the reference matches an in-package profile pin (R-43); never contacted")

    def against_pins(self, pin_listing: Callable[[str, str], Mapping[str, str] | None] | None) -> None:
        pins: set[str] = set()
        for table in self._source_tables():
            for pin in table.get("pins", ()) if isinstance(table.get("pins"), (list, tuple)) else ():
                if isinstance(pin, Mapping) and pin.get("kind") == "git" and isinstance(pin.get("commit"), str):
                    pins.add(str(pin["commit"]))
        listings: dict[tuple[str, str], Mapping[str, str] | None] = {}
        for row in self.origins:
            if row.origin.kind != "git":
                continue
            data = row.origin.data
            subject = {"path": f"raw/objects/{row.sha256[:2]}/{row.sha256}"}
            self.count("origins_checked")
            if row.sha256 not in self.objects:
                continue  # missing or tombstoned: reported by the chain
            label, size = self.objects[row.sha256]
            try:
                blob = git_blob_sha1(self._stream(label), size)
            except AgentProvError as exc:
                self.add("raw.object.unreadable", label, detail=f"the object cannot be read ({exc.code})")
                continue
            if blob != data["blob_sha1"]:
                self.add("raw.origin.blob_mismatch", subject, detail="the recorded git blob id does not match the bytes")
                continue
            if data["commit"] not in pins:
                self.add("raw.origin.blob_mismatch", subject, detail="the origin's commit is not a pin of the in-package profile")
                continue
            key = (str(data["repo"]), str(data["commit"]))
            if key not in listings:
                listings[key] = pin_listing(*key) if pin_listing is not None else None
                if listings[key] is None:
                    self.add("raw.origin.listing_unavailable", {"path": f"git {key[1][:12]}"}, status=UNVERIFIED,
                             detail="the pinned tree listing is not available (fetch cache, or --allow-network)")
            listing = listings[key]
            if listing is not None and listing.get(str(data["path"])) != blob:
                self.add("raw.origin.blob_mismatch", subject, detail="the pinned tree has another blob at the origin's path")

    # -------------------------------------------------------------------------------------- chain: executions
    def executions(self, gate_reports: Mapping[str, str | None], stats: AerStats | None) -> None:
        by_ex: dict[str, set[str]] = {}
        severities: dict[str, list[tuple[str, str]]] = {}
        for entry in self.register:
            ex = entry.subject.get("ex")
            if ex is not None:
                by_ex.setdefault(ex, set()).add(entry.code)
                severities.setdefault(ex, []).append((entry.code, entry.severity))
        validation_rows: dict[str, dict[str, Any]] = {}
        try:
            validation_rows = {r["ex"]: r for r in self.reader.validation_results()}
        except AgentProvError as exc:
            self.add("corpus.read.validation", "validation/results.jsonl", detail=f"not valid ({exc.code})")
        declared = self._declared_snapshots()
        origin_lines = Counter(o.sha256 for o in self.origins) if "raw/origins.jsonl" in self.loaded else None
        for row in self.rows:
            missing = sorted(set(row.issues) - by_ex.get(row.ex, set()))
            if missing:
                self.add("register.reconcile", {"ex": row.ex},
                         detail=f"{len(missing)} issue code(s) of the row have no register entry (H.6.1 R5)")
            if not missing and row_status(row, severities.get(row.ex, ())) != row.status:
                self.add("index.status", {"ex": row.ex},
                         detail="the row's status differs from the one its stages and its issues' register severities give "
                                "(H.3.2(1); CB-11)")
            if declared is not None and not set(row.snapshot_ids) <= declared:
                self.add("index.snapshot.undeclared", {"ex": row.ex},
                         detail=f"{len(set(row.snapshot_ids) - declared)} snapshot id(s) of the row are not declared in "
                                "corpus.json sources[].snapshots (H.7.2(1); F-12C-02)")
            primary = [r.sha256 for r in row.raw if r.role == primary_role(row.mode)]
            if origin_lines is not None and len(primary) == 1 and origin_lines[primary[0]] != row.n_origins:
                self.add("index.n_origins", {"ex": row.ex},
                         detail="the row's n_origins differs from the raw/origins.jsonl lines of its primary artefact "
                                "(H.3.1, H.7.2(1); F-12C-02)")
            if self.sample is not None and row.ex not in self.sample:
                continue
            self.count("executions_checked")
            self._execution(row, gate_reports, stats, validation_rows.get(row.ex))

    def _declared_snapshots(self) -> set[str] | None:
        """The snapshot ids ``corpus.json`` declares (``sources[].snapshots[].snapshot_id``), or ``None`` when it
        declares none (no readable manifest, or no ``sources``)."""
        ids = {str(s.get("snapshot_id")) for src in _seq((self.manifest or {}).get("sources")) if isinstance(src, Mapping)
               for s in _seq(src.get("snapshots")) if isinstance(s, Mapping) and isinstance(s.get("snapshot_id"), str)}
        return ids or None

    def _execution(self, row: IndexRow, gate_reports: Mapping[str, str | None], stats: AerStats | None,
                   validation_row: Mapping[str, Any] | None) -> None:
        ex = {"ex": row.ex}
        reader = self.reader
        layout = reader.layout
        try:
            label = layout.aer_relpath(row.ex)
            if row.aer_path != label:
                self.add("index.path", ex, detail="the recorded AER path differs from the layout's (H.1.3(6))")
                return
            if not reader.exists(label):
                self.absent("corpus.read.missing", ex, "the AER file is absent")
                return
            data = reader.read_bytes(label)
        except AgentProvError as exc:
            self.add("corpus.read.aer", ex, detail=f"the AER cannot be read ({exc.code})")
            return
        try:
            aer = load_aer_bytes(data, verify=True)
        except AgentProvError as exc:
            self.add(exc.code if exc.code.startswith("aer.") else "aer.invalid", ex, detail="the AER seal does not verify")
            return
        if aer.execution_digest != row.aer_digest or aer.ex != row.ex:
            self.add("index.digest.aer", ex, detail="the AER's execution digest differs from the index (D9 chain)")
            return
        codes = frozenset(str(i.get("code")) for i in aer.seal.get("issues", ()) if isinstance(i, Mapping))
        if codes:
            self.seal_codes[row.ex] = codes
        header = aer.header
        artefacts = [a for a in header.get("artifacts", ()) if isinstance(a, Mapping)]
        if {(str(a.get("sha256")), str(a.get("role"))) for a in artefacts} != {(r.sha256, r.role) for r in row.raw}:
            self.add("index.raw", ex, detail="the AER header's artifacts differ from the row's raw entries")
        for art in artefacts:
            sha = str(art.get("sha256"))
            if sha in self.objects and isinstance(art.get("bytes"), int) and art["bytes"] != self.objects[sha][1]:
                self.add("raw.size", ex, detail="an artefact's recorded size differs from its stored object")
        if header.get("unit") != row.unit:
            self.add("index.unit", ex, detail="the row's unit differs from the AER header's")
        if completeness_of(aer) != row.completeness:
            self.add("index.completeness", ex, detail="the row's completeness does not recompute from the AER (H.3.2)")
        sems: dict[str, SemDocument] = {}
        for profile, stage in sorted((row.sem or {}).items()):
            if stage.digest is None:
                continue
            doc = self._sem(row, profile, stage.digest)
            if doc is not None:
                sems[profile] = doc
        provs: list[Any] = []
        for spec, stage in sorted((row.prov or {}).items()):
            if stage.digest is None:
                continue
            document = self._prov(row, spec, stage.digest, artefacts, sems)
            if document is not None:
                provs.append(document)
        if row.validation is not None and row.validation.digest is not None:
            if validation_row is None:
                self.absent("index.digest.validation", ex, "the row has a validation digest but no validation row")
            elif sha256_hex(jcs_bytes(validation_row)) != row.validation.digest:
                self.add("index.digest.validation", ex, detail="the validation row's JCS digest differs from the index")
        if row.facet_members is not None:
            try:
                members = facet_members(aer, sems, prov_specs=sorted(row.prov_paths or {}), gate_reports=gate_reports)
            except AgentProvError as exc:
                self.add("index.facets", ex, detail=f"the facets cannot be recomputed ({exc.code})")
            else:
                if members.to_json() != row.facet_members.to_json():
                    self.add("index.facets", ex, detail="the row's facets do not recompute from its AER and SEM (H.3.3(3))")
        if stats is not None:
            stats.add(aer, sems, provs)
            self.stats_added += 1

    def _sem(self, row: IndexRow, profile: str, digest: str) -> SemDocument | None:
        ex = {"ex": row.ex}
        label = self.reader.layout.sem_relpath(profile, row.ex)
        if (row.sem_paths or {}).get(profile) != label:
            self.add("index.path", ex, detail="a recorded SEM path differs from the layout's (H.1.3(6))")
            return None
        if not self.reader.exists(label):
            self.absent("corpus.read.missing", ex, "a SEM file is absent")
            return None
        try:
            doc = load_sem_bytes(self.reader.read_bytes(label), verify=True)
        except AgentProvError as exc:
            self.add(exc.code if exc.code.startswith("sem.") else "sem.invalid", ex, detail="the SEM document does not verify")
            return None
        if doc.digest != digest or doc.ex != row.ex:
            self.add("index.digest.sem", ex, detail="the SEM digest differs from the index (D9 chain)")
            return None
        if doc.aer_digest != row.aer_digest:
            self.add("sem.input.aer", ex, detail="the SEM document annotates another AER than the row's (D6)")
        return doc

    def _prov(self, row: IndexRow, spec: str, digest: str, artefacts: Sequence[Mapping[str, Any]],
              sems: Mapping[str, SemDocument]) -> Any:
        ex = {"ex": row.ex}
        label = self.reader.layout.prov_relpath(spec, row.ex)
        if (row.prov_paths or {}).get(spec) != label:
            self.add("index.path", ex, detail="a recorded PROV path differs from the layout's (H.1.3(6))")
            return None
        try:
            if not self.reader.exists(label):
                self.absent("corpus.read.missing", ex, "a PROV file is absent")
                return None
            data = self.reader.read_bytes(label)
        except AgentProvError as exc:  # a link, a member over the limits, a corrupt stream: a finding, as for the AER
            self.add("corpus.read.prov", ex, detail=f"the PROV file cannot be read ({exc.code})")
            return None
        if sha256_hex(data) != digest:
            self.add("index.digest.prov", ex, detail=f"the {spec} file's sha256 differs from the index (D9 chain)")
            return None
        from agentprov.ingest.limits import prov_document_limits
        from agentprov.ingest.loaders import strict_json_loads

        try:
            document = strict_json_loads(data, prov_document_limits(self.reader.limits))  # D-935: the PROV-document limit
        except AgentProvError as exc:
            self.add("prov.invalid", ex, detail=f"the PROV file is not strict JSON ({exc.code})")
            return None
        if spec != PROV_SPEC or not isinstance(document, Mapping):
            return document
        entities = document.get("entity")
        entities = entities if isinstance(entities, Mapping) else {}
        aers = {k[len("xd:aer."):] for k in entities if isinstance(k, str) and k.startswith("xd:aer.")}
        raws = {k[len("raw:sha256-"):] for k in entities if isinstance(k, str) and k.startswith("raw:sha256-")}
        sem_digests = {k.rsplit(".", 1)[-1] for k in entities if isinstance(k, str) and k.startswith("xd:sem.")}
        if aers != {row.aer_digest} or any(
                isinstance(v, Mapping) and v.get("apv:sha256") != row.aer_digest for k, v in entities.items()
                if isinstance(k, str) and k.startswith("xd:aer.")):
            self.add("prov.input.aer", ex, detail="the PROV top level records another AER digest (H.5.2)")
        if raws != {str(a.get("sha256")) for a in artefacts}:
            self.add("prov.input.raw", ex, detail="the PROV top level records other raw digests than the AER header (H.5.2)")
        if sem_digests != {doc.digest for doc in sems.values()}:
            self.add("prov.input.sem", ex, detail="the PROV top level records other SEM digests than the row's (H.5.2)")
        return document

    # -------------------------------------------------------------------------------------- chain: files present
    def _present_labels(self) -> list[str]:
        """Every corpus file present: the archives' labels (archive mode), the closed-world ``checksums.sha256`` entries
        (a sealed tree, whose unlisted files the checksums level reports), else a scan of the tree."""
        archives = getattr(self.reader, "archives", None)
        if archives is not None:
            return list(archives.labels())
        if self.checksum_entries:
            return list(self.checksum_entries)
        return [label for label, _role, _size in iter_tree(self.reader.root).files]

    def orphans(self) -> None:
        """P-1 (sealed corpora): every execution file present under ``aer/``, ``sem/`` and ``prov/`` is named by an index
        row (``index.orphan``, failed). Skipped when the index could not be read (``index.invalid`` is reported)."""
        if EXECUTIONS not in self.loaded:
            return
        named: set[str] = set()
        for row in self.rows:
            named.add(row.aer_path)
            named.update((row.sem_paths or {}).values())
            named.update((row.prov_paths or {}).values())
        for label in sorted(self._present_labels()):
            if classify_relpath(label) in ("aer", "sem", "prov") and label not in named:
                self.count("orphans")
                self.add("index.orphan", label, detail="an execution file no index row names (H.1.3; P-1)")

    def copies_and_optional_files(self) -> None:
        """P-2 (sealed corpora). ``schemas/**`` are byte copies of package resources (H.1.2): each present schema and each
        schema sealing writes must equal the installed package's resource of that name (``schemas.mismatch``, failed;
        ``schemas.unavailable``, unverified, when the package does not ship it). ``WITHHELD.json`` must be declared in
        the manifest's ``files`` (``withheld.undeclared``; once declared, ``manifest.files`` checks its bytes). A file
        under ``views/`` needs a ``views`` stage in ``derivation.json`` and an index row for its execution
        (``views.undeclared``)."""
        from importlib import resources

        labels = self._present_labels()
        present = {label for label in labels if classify_relpath(label) == "schema"}
        fmt = str((self.manifest or {}).get("format"))
        sealed_schemas = ({aer_schema_resource(fmt), schema_resource(fmt)} if fmt in CORPUS_FORMATS
                          else set(_SEALED_SCHEMAS))  # D-212: the schemas of the corpus's own format
        withheld_schema = self.withheld.schema_resource if self.withheld is not None else WITHHELD_SCHEMA
        required = sealed_schemas | ({withheld_schema} if WITHHELD in labels else set())
        for label in sorted(present | {f"schemas/{name}" for name in required}):
            name = label.split("/", 1)[1]
            if name not in SCHEMA_FILES:
                self.add("schemas.mismatch", label, detail="not one of the published schemas (AD-10 row 13)")
                continue
            resource = resources.files("agentprov").joinpath("schemas", name)
            expected = resource.read_bytes() if resource.is_file() else None
            if expected is None:
                self.add("schemas.unavailable", label, status=UNVERIFIED,
                         detail="the installed package does not ship this schema, so its copy cannot be compared")
                continue
            data = self._read(label) if label in present else None
            if data is None:
                self.absent("schemas.mismatch", label, "a published schema sealing writes is absent (H.1.2)")
            elif data != expected:
                self.add("schemas.mismatch", label, detail="the schema copy differs from the package resource (H.1.2)")
            self.count("schemas_checked")
        files = _obj((self.manifest or {}).get("files"))
        if WITHHELD in labels and "withheld" not in files:
            self.add("withheld.undeclared", WITHHELD, detail="WITHHELD.json is present but corpus.json files declares none "
                                                             "(H.4.5; P-2)")
        if REFERENCES in labels and "references" not in files:
            self.add("references.undeclared", REFERENCES, detail="raw/REFERENCES.json is present but corpus.json files "
                                                                 "declares none (H.4.3; D-237)")
        views = [label for label in labels if classify_relpath(label) == "view"]
        if views:
            staged = "views" in self.stages
            rows = {row.ex for row in self.rows}
            for label in sorted(views):
                ex = label.rsplit("/", 1)[-1].split(".", 1)[0]
                if not staged:
                    self.add("views.undeclared", label, detail="a view file, but derivation.json has no views stage (P-2)")
                elif ex not in rows:
                    self.add("views.undeclared", label, detail="a view of an execution no index row names (P-2)")

    # -------------------------------------------------------------------------------------- chain: withholding
    def withholding(self) -> None:
        """The withholding checks of the module docstring (sealed corpora; H.4.5, G.9.5; D-230..D-236)."""
        rows = {row.ex for row in self.rows}
        registered = {e.subject["ex"] for e in self.register if e.code == "release.withheld" and "ex" in e.subject}
        document = self.withheld
        listed = set(document.execution_map) if document is not None else set()
        for ex in sorted(registered - listed):
            self.add("withheld.unlisted", {"ex": ex}, detail="the register withholds the execution but WITHHELD.json does "
                                                             "not list it (H.4.5)")
        if document is not None:
            labels = set(self._present_labels())
            layout = self.reader.layout
            from agentprov.corpus.withhold import execution_labels

            for execution in document.executions:
                subject = {"ex": execution.ex}
                self.count("withheld_executions")
                if execution.ex in rows:
                    self.add("withheld.row", subject, detail="WITHHELD.json lists the execution, but the index has its row")
                if execution.ex not in registered:
                    self.add("withheld.unregistered", subject, detail="a withheld execution has no release.withheld "
                                                                      "register entry (H.4.5)")
                for label in execution_labels(layout, execution):
                    if label in labels:
                        self.add("withheld.present", label, detail="a file of a withheld execution is in the corpus")
            by_sha: dict[str, list[bytes]] = {}
            for origin in self.origins:
                by_sha.setdefault(origin.sha256, []).append(jcs_bytes(origin.origin.to_json()))
            for sha, entry in sorted(document.objects.items()):
                self.count("withheld_objects")
                if "raw/origins.jsonl" in self.loaded and sorted(by_sha.get(sha, ())) != sorted(jcs_bytes(dict(o))
                                                                                                 for o in entry.origins):
                    self.add("withheld.origins", {"path": f"raw/objects/{sha[:2]}/{sha}"},
                             detail="the entry's origins differ from the object's raw/origins.jsonl origins (H.4.5)")
            from agentprov.corpus.withhold import linked_objects

            for kind, group in linked_objects(self.origins):  # D-315: a split archive or a carved pair leaves as one unit
                listed_here = [sha for sha in group if sha in document.objects]
                if listed_here and len(listed_here) != len(group):
                    code = "withheld.split_part" if kind == "split" else "withheld.carved"
                    for sha in sorted(set(group) - set(listed_here)):
                        self.add(code, {"path": f"raw/objects/{sha[:2]}/{sha}"},
                                 detail="WITHHELD.json lists a linked object but not this one; a split archive and its "
                                        "parts, and a carved value and its source, are withheld together (D-315)")
            self._container_closure(document)
        held = {sid for sid, policy in self._snapshot_policies().items() if policy == "withhold"}
        for row in self.rows:
            if held & set(row.snapshot_ids):
                self.add("withheld.policy", {"ex": row.ex}, detail="the row belongs to a snapshot whose raw policy is "
                                                                   "withhold, but it was released (H.4.1)")
        self._rule_backstop()

    def _container_closure(self, document: WithheldDocument) -> None:
        """AD-12 / D-232 (BF-19, D-461): an archive holds its members' bytes, so every container of a withheld object, at
        every level (``raw/members.jsonl``, transitively), must be withheld too. A released container that holds a
        withheld member is ``withheld.container``: a deflated container hides the member's bytes from the rule rescan."""
        if "raw/members.jsonl" not in self.loaded:
            return
        containers_of: dict[str, set[str]] = {}
        for member in self.members:
            if member.disposition == "selected" and member.sha256 is not None:
                containers_of.setdefault(member.sha256, set()).add(member.container)
        pending = sorted(document.objects)
        seen = set(pending)
        while pending:
            sha = pending.pop()
            for container in sorted(containers_of.get(sha, ())):
                if container in seen:
                    continue
                seen.add(container)
                pending.append(container)
                if container not in document.objects and container in self.objects:
                    self.count("withheld_container_released")
                    self.add("withheld.container", {"path": f"raw/objects/{container[:2]}/{container}"},
                             detail="a released archive holds a withheld member object (AD-12): it must be withheld "
                                    "with it (D-232, D-461)")

    def _rule_backstop(self) -> None:
        """No released file matches a rule of the source profile's ``[withhold]`` policy (``withheld.rule_hit``), and no
        released execution carries the code of one of its issue rules (``withheld.issue_released``, D-311)."""
        from agentprov.corpus.withhold import (issue_backstop, issue_carriers, listed_backstop, load_policy, rescan,
                                               withhold_addresses, withhold_listed)

        catalogues = {str(e.get("id")): e["version"] for e in _seq((self.manifest or {}).get("rule_catalogues"))
                      if isinstance(e, Mapping) and isinstance(e.get("version"), int)}  # fmt: skip

        for ref in _seq(_obj((self.manifest or {}).get("profiles")).get("source")):
            path, pid, version = _obj(ref).get("path"), _obj(ref).get("id"), _obj(ref).get("version")
            if not isinstance(path, str) or not isinstance(pid, str) or not isinstance(version, int):
                continue
            data = self._read(path)
            if data is None:
                continue  # reported by the files and rules checks
            try:
                spec_bytes = self._read("rules/corpus-spec.toml")
                addresses = (withhold_addresses(spec_bytes, lambda name: self._read(f"rules/personas/{name}"))
                             if spec_bytes is not None else frozenset())
                listed = withhold_listed(spec_bytes) if spec_bytes is not None else (frozenset(), frozenset())
                policy = load_policy(data, profile_id=pid, profile_version=version, catalogues=catalogues,
                                     addresses=addresses, listed=listed)
            except AgentProvError as exc:
                self.add("withheld.policy_invalid", path, detail=f"the profile's [withhold] policy is not valid ({exc.code})")
                continue
            if policy is None:
                continue
            labels = [label for label in self._present_labels() if self.reader.exists(label)]
            unread: list[tuple[str, str]] = []
            for label, rule in rescan(labels, self._stream, policy, unscanned=unread):
                self.count("withheld_rule_hits")
                self.add("withheld.rule_hit", label, detail=f"rule {rule} of the source profile's [withhold] policy "
                                                            "matches a released file (H.4.5)")
            for label, code in unread:  # D-450: a released archive the decoded scan cannot read holds unread bytes
                self.count("withheld_unscanned")
                self.add("withheld.unscanned", label, detail=f"a released stored archive cannot be read in decoded form "
                                                             f"({code}) for the [withhold] policy's byte rules (D-450)")
            for kind, ident in listed_backstop(policy, labels, self.rows):  # D-964
                self.count("withheld_listed_released")
                self.add("withheld.listed_released", {"ex": ident} if kind == "execution" else
                         {"path": f"raw/objects/{ident[:2]}/{ident}"},
                         detail=f"the corpus spec's [withhold] lists this {kind}, but it is released (D-964)")
            if not policy.issue_rules:
                continue
            for ex, rule in issue_backstop(policy, self.register, self.rows, self.seal_codes):
                self.count("withheld_issue_hits")
                self.add("withheld.issue_released", {"ex": ex}, detail=f"the execution carries the issue code of rule "
                                                                        f"{rule} of the [withhold] policy but was released "
                                                                        "(D-311)")
            carriers = issue_carriers(policy, self.register)
            layout = self.reader.layout
            for entry in (self.withheld.entries if self.withheld is not None else ()):
                finding = entry.finding
                rid = finding.rule.rsplit(":", 1)[-1] if finding is not None else ""
                if finding is None or finding.rule != f"{policy.ref}:{rid}" or rid not in carriers:
                    continue
                label = finding.fingerprint.rsplit(":", 1)[0]
                if label not in {layout.aer_relpath(ex) for ex in carriers[rid]}:
                    self.add("withheld.issue_unsupported", WITHHELD,
                             detail=f"a finding of issue rule {rid} names an execution the register does not record "
                                    "with its code (D-311)")

    # -------------------------------------------------------------------------------------- chain: the sealed manifest
    def manifest_members(self, stats: AerStats | None) -> None:
        manifest = self.manifest or {}
        reader = self.reader

        def differs(member: str, why: str) -> None:
            self.add(f"manifest.{member}", MANIFEST, detail=why)

        files = _obj(manifest.get("files"))
        for role, ref in sorted(files.items()):
            if not isinstance(ref, Mapping) or not isinstance(ref.get("path"), str) or classify_relpath(ref["path"]) is None:
                differs("files", f"files.{role} names no corpus file")
                continue
            data = self._read(ref["path"])
            if data is None:
                self.absent("manifest.files", {"path": ref["path"]}, f"files.{role} names an absent file")
            elif file_ref(ref["path"], data, jsonl=ref.get("lines") is not None) != dict(ref):
                differs("files", f"files.{role} does not match its file")
        index_bytes, register_bytes, members_bytes = (self._read(n) for n in (EXECUTIONS, REGISTER, "raw/members.jsonl"))
        if index_bytes is not None and register_bytes is not None and members_bytes is not None:
            labels = self.checksum_entries or list(self._object_labels())
            raw_objects = raw_dispositions([_object_sha(label) for label in labels if classify_relpath(label) == "raw_object"],
                                           self.withheld.objects if self.withheld else (), self.referenced)
            recomputed = digests_of(self.rows, raw_objects, index_bytes=index_bytes, register_bytes=register_bytes,
                                    members_bytes=members_bytes)
            recorded = _obj(manifest.get("digests"))
            for key in sorted(set(recomputed) | set(recorded)):
                if recomputed.get(key) != recorded.get(key):
                    differs("digests", f"digests.{key} does not recompute from the files (H.2.11)")
        sources = _seq(manifest.get("sources"))
        snapshots_out: list[dict[str, Any]] = []
        all_ids = [str(s.get("snapshot_id")) for src in sources if isinstance(src, Mapping)
                   for s in src.get("snapshots") or () if isinstance(s, Mapping)]
        for src in sources:
            for snapshot in (src.get("snapshots") or ()) if isinstance(src, Mapping) else ():
                if not isinstance(snapshot, Mapping):
                    continue
                sid = str(snapshot.get("snapshot_id"))
                exclude = (snapshot.get("selection") or {}).get("exclude") or ()
                try:
                    counts = snapshot_counts(self.rows, self.register, sid, exclude, all_snapshots=all_ids)
                except ManifestError as exc:
                    differs("counts", f"snapshot {sid}: the counts cannot be reconciled ({exc.code})")
                    continue
                snapshots_out.append({"counts": counts})
                if counts != snapshot.get("counts"):
                    differs("counts", f"snapshot {sid}: counts do not reconcile with the index and register (H.6.1 R5)")
        full = stats is not None and self.stats_added == len(self.rows)
        try:
            counts = corpus_counts(self.rows, self.register, self.members, snapshots_out, stats or AerStats())
        except (AgentProvError, KeyError, TypeError) as exc:
            differs("counts", f"counts cannot be recomputed ({type(exc).__name__})")
        else:
            recorded_counts = _obj(manifest.get("counts"))
            for key in sorted(set(counts) | set(recorded_counts)):
                if not full and key in _FULL_PASS_COUNTS:
                    continue
                if counts.get(key) != recorded_counts.get(key):
                    differs("counts", f"counts.{key} does not recompute (H.2.9; H.6.1 R5)")
        if duplicate_summary(self.rows, self.register) != manifest.get("duplicates"):
            differs("duplicates", "duplicates does not recompute (H.7)")
        try:
            summary = reader.validation_summary() or {}
            results = reader.validation_results()
            computed = validation_summary(summary, self.stages.get("validation") or {}, results,
                                          aer_format=CORPUS_FORMATS.get(str(manifest.get("format")), "aer/0.2"))
        except (AgentProvError, KeyError, TypeError, ValueError) as exc:
            differs("validation", f"validation cannot be recomputed ({type(exc).__name__})")
        else:
            if computed != manifest.get("validation"):
                differs("validation", "validation does not recompute from validation/ (H.2.12; D-40)")
        if facet_schema() != manifest.get("facet_schema"):
            differs("facet_schema", "facet_schema differs from the package's (H.3.3)")
        if not full or stats is None:
            why = ("for a lone meta archive" if self.absent_unverified else "under --sample" if stats is None
                   else "as an execution could not be read")
            self.report.notices.append(f"{why}, records_by_kind, generic_types, models, framework_identities and "
                                       "rules_used were not compared (they need every AER)")
            return
        if stats.model_summaries() != manifest.get("models"):
            differs("models", "models does not recompute from the AERs (H.2.8)")
        if stats.framework_identities() != manifest.get("framework_identities"):
            differs("framework_identities", "framework_identities does not recompute from the AERs (H.2.4)")
        catalogues: dict[str, tuple[int, str, int, str]] = {}
        for entry in manifest.get("rule_catalogues") or ():
            if isinstance(entry, Mapping) and isinstance(entry.get("version"), int) and _hex(entry.get("sha256")):
                catalogues[str(entry.get("id"))] = (entry["version"], str(_hex(entry["sha256"])), int(entry.get("n_rules", 0)),
                                                    str(entry.get("path")))
        used = set(stats.rules_used) | {str(d["from"]) for d in facet_schema() if "@" in str(d["from"])}
        try:
            refs = rule_catalogue_refs(catalogues, used)
        except ManifestError as exc:
            differs("rule_catalogues", f"a used rule's catalogue is not recorded ({exc.code})")
        else:
            if refs != manifest.get("rule_catalogues"):
                differs("rule_catalogues", "rules_used does not recompute from the AER, SEM and PROV files (H.2.5)")

    def rules(self) -> None:
        findings = list(check_stage_rules(self.stages, self.package))
        if self.reader.sealed and self.manifest is not None:
            findings += check_sealed_rules(self.manifest, self._read, self.package)
        for finding in sorted(set(findings), key=lambda f: (f.subject, f.code)):
            self.add(finding.code, finding.subject, status=FAILED if finding.code in (MISMATCH, DRIFT) else UNVERIFIED,
                     detail=finding.detail)

    def chain(self, against_pins: bool, pin_listing: Callable[[str, str], Mapping[str, str] | None] | None) -> None:
        if not self.documents():
            return
        manifest = self.manifest or {}
        gate_reports = {str(o.get("spec")): o.get("gate_report") for o in manifest.get("oracle_specs") or ()
                        if isinstance(o, Mapping)}
        self.raw_chain()
        self.references()
        if against_pins:
            self.against_pins(pin_listing)
        stats = AerStats() if self.sample is None and self.reader.sealed and not self.absent_unverified else None
        self.executions(gate_reports, stats)
        if self.reader.sealed:
            self.orphans()
            self.copies_and_optional_files()
            self.withholding()
            self.manifest_members(stats)
        else:
            self.report.notices.append("working tree: the manifest reconciliation applies to sealed corpora only")
        self.rules()

    # -------------------------------------------------------------------------------------- rederive
    def rederive(self, *, jobs: int, in_process: bool, catalogues: Any, hooks: ImportHooks | None,
                 progress: Progress, validation_cache: Any = None) -> None:
        from agentprov.corpus.derive import Derivation, DeriveError, RawDigestError, resolve_plan
        from agentprov.corpus.writer import CorpusWriter

        reader = self.reader
        drifted = catalogue_drift(_stages(reader.derivation()))
        if drifted:  # D-460: this package cannot reproduce it; the chain level already reported aer.rules.drift
            for ns, version in drifted.items():
                self.add("rederive.unavailable", f"catalogue {ns}@{version}", status=UNVERIFIED, level="rederive",
                         detail=DRIFT_DETAIL.format(version=version))
            return
        try:
            plan = resolve_plan(reader, "recompute", jobs=jobs, in_process=in_process, link_raw=True, reuse=False,
                                strict=self.release, catalogues=catalogues)
        except (ValueError, AgentProvError) as exc:
            self.add("rederive.unavailable", MANIFEST, status=UNVERIFIED, level="rederive",
                     detail=f"no re-derivation plan ({getattr(exc, 'code', type(exc).__name__)})")
            return
        if plan.remap and hooks is None:
            self.add("rederive.unavailable", "raw/objects", status=UNVERIFIED, level="rederive",
                     detail="the re-map needs the import pipeline, which was not supplied")
            return
        derivation = Derivation(reader, plan, catalogues=catalogues, progress=progress, scope=self.sample,
                                package=self.package)
        derivation.validation_cache = validation_cache  # D-550; the caller passes an audit-mode cache under --release
        try:
            derivation.check_inputs()
        except RawDigestError as exc:
            self.add(exc.code, "raw/objects", level="rederive", detail="the inputs of the re-derivation do not verify")
            return
        tmp = scratch_tree("agentprov-verify-", reader.root)  # on the source's filesystem: raw objects link
        try:
            with CorpusWriter(tmp / "corpus", limits=reader.limits, release=plan.mode == "release",
                              command="verify") as writer:
                if plan.remap:
                    assert hooks is not None
                    self._remap(derivation, writer, hooks, progress)
                else:
                    derivation.prepare(writer)
                    derivation.rederive(writer)
                report = derivation.finish(writer)
        except DeriveError as exc:
            self.add(exc.code, "raw/objects", level="rederive", detail="the re-derivation failed")
            return
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        for key, value in report.counters.items():
            self.counters[f"rederive_{key}"] = int(value)
        refreshed = int(report.counters.get("index_refreshed", 0))
        if refreshed and reader.sealed:  # CB-11: a sealed row's status, issues or completeness does not re-derive
            explained = any(report.stage_changes.values())
            self.add("rederive.index_refreshed", "executions.jsonl", status=UNVERIFIED if explained else FAILED,
                     level="rederive", detail=f"{refreshed} index row(s) differ from a re-derivation outside their outputs "
                     "(status, issues, completeness)" + ("; a declared version differs" if explained else ""))
        for change in report.changes:
            outputs = ", ".join(change["outputs"])
            cls = change["class"]
            if cls in ("unexplained_change", "failed"):
                self.add(f"rederive.{cls}", {"ex": change["ex"]}, level="rederive", detail=f"outputs: {outputs}")
            elif cls in ("changed_explained", "unverified"):
                self.add(f"rederive.{cls}", {"ex": change["ex"]}, status=UNVERIFIED, level="rederive",
                         detail=f"outputs: {outputs}; a declared version differs from the package's or is not shipped")
        for change in report.corpus_changes:
            self.add("rederive.corpus_file", change["file"], status=FAILED if not change["explained"] else UNVERIFIED,
                     level="rederive", detail=f"{change['removed']} line(s) removed, {change['added']} added")
        if report.counters.get("referenced_unavailable", 0):
            self.add("raw.reference.unavailable", REFERENCES, status=UNVERIFIED, level="rederive",
                     detail=f"{report.counters['referenced_unavailable']} referenced object(s) are not in the fetch cache")
        self.report.notices.extend(n for n in report.notices if not n.startswith("rules."))

    def _remap(self, derivation: Any, writer: Any, hooks: ImportHooks, progress: Progress) -> None:
        from agentprov.corpus.rawtree import StoredRawTree
        from agentprov.ingest.limits import IngestLimits

        reader = self.reader
        # D-202: one tree per recorded snapshot, replayed in import order (a single-snapshot corpus has one)
        trees = [StoredRawTree(reader, snapshot_id=sid, candidate_type=hooks.candidate_type)
                 for sid in derivation.snapshot_ids()] or [StoredRawTree(reader, candidate_type=hooks.candidate_type)]
        derivation.exclude_absent(trees)  # BF-20, CB-6: inputs absent on purpose are not re-mapped
        if self.sample is not None:
            containers = {m.sha256: m.container for m in self.members if m.sha256 is not None}
            roots: set[str] = set()
            for row in self.rows:
                if row.ex not in self.sample:
                    continue
                for ref in row.raw:
                    sha = ref.sha256
                    while sha in containers:
                        sha = containers[sha]
                    roots.add(sha)
            for tree in trees:
                tree.restrict({label for sha in roots for label in tree.labels_of(sha)})
        register = reader.register()
        derivation.prepare(writer, unreproducible=[e for tree in trees for e in tree.unreproducible(register)])

        def filters_of(snapshot_id: str | None) -> Any:  # NF-36: each snapshot's own recorded filters
            recorded = derivation.recorded_selection(snapshot_id)
            variants = recorded.get("variants")
            chosen = recorded.get("select")
            select: Mapping[str, Any] = chosen if isinstance(chosen, Mapping) else {}
            return hooks.filters_type(
                include_paths=tuple(str(g) for g in recorded.get("include_paths") or ()),
                variants=None if variants is None else frozenset(str(v) for v in variants),
                select={str(k): frozenset(str(v) for v in values) for k, values in sorted(select.items())},
            )

        overrides = {k: tuple(v) if isinstance(v, list) else v for k, v in derivation.recorded_limit_overrides().items()}
        limits = IngestLimits().replace(**overrides) if overrides else IngestLimits()
        plan = derivation.plan
        try:
            for tree in trees:
                arguments = derivation.import_arguments(tree.snapshot_id)  # until "aer" for a re-map (D-623 nit #9)
                hooks.import_source(derivation.source_id(), tree, corpus=writer, filters=filters_of(tree.snapshot_id),
                                    limits=limits, workers=plan.jobs, in_process=plan.in_process, progress=progress,
                                    **arguments)
        finally:
            derivation.restamp(writer)
        derivation.complete_remap(writer)


# ================================================================================================ entry point
def default_catalogues() -> Any:
    """The profile and catalogue lookups of :class:`agentprov.corpus.derive.Catalogues` over the installed package
    (``adapters`` package data, L4)."""
    from agentprov.adapters.profiles import load_profile
    from agentprov.adapters.semantics_profiles import load_semantics_profile
    from agentprov.corpus.derive import Catalogues, SemanticsInfo
    from agentprov.sem.profiles import parse_profile_ref

    def source_profile(profile_id: str, version: int) -> str | None:
        try:
            profile = load_profile(profile_id, version)  # an archived version too (D-31)
        except AgentProvError:
            return None
        return profile.sha256 if profile.version == version else None

    def semantics(ref: str) -> SemanticsInfo | None:
        try:
            profile = load_semantics_profile(*parse_profile_ref(ref))
        except (AgentProvError, ValueError, KeyError):
            return None
        family = str(type(profile).__module__).split(".")[2]
        return SemanticsInfo(ref=f"{profile.id}@{profile.version}", sha256=profile.sha256, rules=dict(profile.rules),
                             family=family)

    def current_profile_version(profile_id: str) -> int | None:
        try:
            return load_profile(profile_id).version
        except AgentProvError:
            return None

    def profile_family(profile_id: str) -> str | None:
        try:
            return load_profile(profile_id).family
        except AgentProvError:
            return None

    return Catalogues(source_profile_sha256=source_profile, semantics=semantics,
                      current_profile_version=current_profile_version, profile_family=profile_family)


def verify_corpus(
    root: str | os.PathLike[str] | None = None,
    *,
    level: str = "chain",
    jobs: int = 0,
    sample: int | None = None,
    seed: str | int | None = None,
    release: bool = False,
    root_digests: Sequence[str] = (),
    against_pins: bool = False,
    pin_listing: Callable[[str, str], Mapping[str, str] | None] | None = None,
    package: PackageResources | None = None,
    catalogues: Any = None,
    import_hooks: ImportHooks | None = None,
    in_process: bool = False,
    progress: Progress = NULL_PROGRESS,
    reader: CorpusReader | None = None,
    source: ChecksumSource | None = None,
    absent_unverified: bool = False,
    deposit_manifest: bool = False,
    validation_cache: Any = None,
) -> VerifyReport:
    """Verify the corpus at ``root`` (N.1.5 resolution; sealed, working or ``.partial``) at ``level`` (H.5.5).

    Archive mode passes ``reader`` (an :class:`~agentprov.corpus.archive.ArchiveCorpusReader`) and ``source`` (its
    :class:`~agentprov.corpus.archive.ArchiveSource`) instead of ``root``; ``absent_unverified`` makes an absent file
    ``unverified`` (a lone meta archive, D-38) and ``deposit_manifest`` says the caller is deposit verification, which
    compares the root digests across the deposit's corpora itself and requires them in release mode (D-39, D-620).
    ``validation_cache`` (D-550) is the tier-4 round-trip cache the ``rederive`` level's jobs use (the CLI
    passes an audit-mode cache under ``--release``, which serves nothing). Raises :class:`VerifyUsageError` (exit 2) for an invalid combination and the interpreter guard's error
    (exit 3) for ``rederive`` in release mode below CPython 3.14.8."""
    if level not in LEVELS:
        raise VerifyUsageError(f"the level is one of {', '.join(LEVELS)}")
    if sample is not None:
        if release:
            raise VerifyUsageError("--sample is forbidden in release mode (N.1.7; H.8.5)")
        if seed is None:
            raise VerifyUsageError("--sample needs --seed (a seeded sample, N.1.7)")
        if isinstance(sample, bool) or not isinstance(sample, int) or sample < 0:
            raise VerifyUsageError("--sample is an integer >= 0")
    elif seed is not None:
        raise VerifyUsageError("--seed goes with --sample")
    for digest in root_digests:
        if not isinstance(digest, str) or not digest.startswith(_SHA_REF) or len(digest) != 71 or not all(
                c in "0123456789abcdef" for c in digest[7:]):
            raise VerifyUsageError("--root-digest is sha256:<64 lower-case hex>")
    if release and not root_digests and not deposit_manifest:
        raise VerifyUsageError("release-mode verification needs --root-digest sha256:... (the root digest published "
                               "outside the corpus; D-39)")
    if release and level == "rederive":
        from agentprov.envinfo import require_patched_for_archive

        require_patched_for_archive(release=True)  # AD-16: before any member is opened (exit 3)
    owned: TreeSource | None = None
    if reader is None:
        if root is None:
            raise VerifyUsageError("a corpus path is required")
        reader = CorpusReader.open(root)
    mode = "tree" if source is None else "archive"
    if source is None and reader.sealed:
        owned = TreeSource(reader.root)
        owned.__enter__()
        source = owned
    try:
        chosen: list[str] | None = None
        if sample is not None:
            try:
                every = [row.ex for row in reader.iter_index()]
            except AgentProvError:
                every = []
            chosen = sample_executions(every, sample, str(seed))
        verifier = _Verifier(reader, source, level=level, mode=mode, release=release, sample=chosen,
                             package=package or package_resources(), absent_unverified=absent_unverified)
        verifier.checksums(tuple(root_digests))
        verifier.identity()
        if level in ("chain", "rederive"):
            verifier.chain(against_pins, pin_listing)
        if level == "rederive":
            if mode == "archive":
                verifier.add("rederive.unavailable", "raw/objects", status=UNVERIFIED, level="rederive",
                             detail="archive mode never extracts a deposit; re-derive a sealed tree")
            else:
                verifier.rederive(jobs=jobs, in_process=in_process, catalogues=catalogues or default_catalogues(),
                                  hooks=import_hooks, progress=progress, validation_cache=validation_cache)
    finally:
        if owned is not None:
            owned.__exit__(None, None, None)
    report = verifier.report
    if chosen is not None:
        report.sample = {"n": len(chosen), "of": report.counters.get("executions", 0), "seed": str(seed)}
    report.findings.sort(key=lambda f: (jcs_bytes(dict(f.subject)), f.code, f.level, f.detail))
    report.counters["findings"] = len(report.findings)
    report.counters["failed"] = len(report.failures)
    report.counters["unverified"] = sum(1 for f in report.findings if f.status == UNVERIFIED)
    report.counters["tombstoned"] = sum(1 for f in report.findings if f.status == TOMBSTONED)
    return report
