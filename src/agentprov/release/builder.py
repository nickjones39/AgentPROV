"""The deposit builder: ``agentprov package --deposit`` (HL H.10; MN N.2.11 deposit mode; D-42).

:func:`build_deposit` turns one or more **sealed** corpora into a deposit *draft* directory. It is offline: this package
imports no network module and starts no process (H.10.1(1), G.9.4; a static test checks it). Nothing is uploaded or
published; publishing is always the user's manual action (H.10.1(2), D9).

**Preconditions** (each refuses before anything is written):

* release mode (Q.15a, AD-16): below CPython 3.14.8 the builder refuses to run (exit 3); a corpus whose manifest records
  an ``interpreter_advisory`` is refused (exit 4);
* every corpus is sealed (``corpus.json`` ``sealed: true``, ``release.status == "sealed"``); a working or ``.partial``
  tree is refused (exit 4); its manifest validates (exit 1 otherwise);
* strict validation (``validation.mode == "strict"``); no ``test_only`` live corpus; a corpus whose raw policy is
  ``withhold`` (every snapshot withheld) is refused, and a ``withhold`` snapshot is accepted only in a corpus whose
  ``WITHHELD.json`` lists what it withheld (D-233); the licence rules of D-42
  (:func:`agentprov.release.metadata.licence_class`) (exit 4);
* the corpus verifies: the built-in check is the ``checksums`` level in closed-world tree mode plus the manifest
  validator; a ``chain`` verifier (U4) can be injected (``verify=``) and its level is recorded (exit 1 on failure);
* a release scan for the corpus's root digest with every finding triaged and none ``real`` outside ``WITHHELD.json``
  (G.9.4): read from ``<corpus>.release-scan.json`` beside the sealed tree (written by ``tools/release_scan.py``), or
  from an injected ``scan`` callable; without a scan result the builder refuses (exit 4; no silent skip);
* the withholding backstop (D-236): when the source profile (its byte copy under ``rules/``, digest-checked) declares a
  ``[withhold]`` policy, no released file may match one of its rules (``release.refused.withhold_rule``; a stored
  archive is read decoded, and one that cannot be is refused, ``release.refused.withhold_unscanned``, D-450), and a
  release-scan finding of a rule the policy's ``scan_rules`` names must be triaged ``false-positive``
  (``release.refused.withhold_scan``): a canary that the policy missed never passes as ``synthetic-benchmark``; and no
  released execution carries the code of one of the policy's issue rules in its index row or a register entry
  (``release.refused.withhold_issue``, D-311);
* one licence class per deposit unless ``allow_mixed_licence_classes`` (recorded); an ``-nc`` class never mixed (D-42);
* a corpus with a ``views/`` tree is refused (exit 5): views are not deposited in v0.1 (AD-10 row 12), and a deposit
  without them could not pass the closed-world check of archive-mode ``verify``.

**Composition** (H.10.3): ``README.md``, ``CHANGELOG.md``, ``DATASHEET-<corpus_id>.md`` (byte copies, plus a deposit
note when classes are mixed), the archives, ``DEPOSIT-MANIFEST.json`` (``agentprov-deposit-manifest/0.1``) and
``deposit-metadata.json`` (``agentprov-deposit/0.1``). The draft is built in ``OUT.partial`` and renamed to ``OUT``.

**Archives** (H.10.4; the format U4's archive-mode ``verify`` reads):

* names ``<corpus_id>-v<ver>.meta.zip`` and ``<corpus_id>-v<ver>.<stage>.<nnn>.zip`` with stage ``raw`` (``raw/objects``),
  ``aer``, ``sem-<profile_dir>``, ``prov-<spec_dir>`` and ``nnn`` from ``001``; the meta archive holds every other file
  of the tree, ``checksums.sha256``, ``schemas/`` and ``rules/`` included;
* every member is ``<corpus_id>-v<ver>/<corpus-relative path>``; only regular files, no directory entries; members
  sorted bytewise by name; ``date_time`` = the release date at 00:00:00, clamped to 1980-01-01; ``create_system = 3``;
  ``external_attr = 0o100644 << 16``; DEFLATE at level 6; no extra field, no comment, no data descriptor, no ZIP64
  (an archive and a member stay below 2^31 - 1 bytes; at most 65,535 members);
* split on shard boundaries (``raw/objects/<h0h1>``, ``<ss>`` of the execution files), never inside a shard. The plan
  uses a deterministic upper bound of each member's stored size (``size + size // 2048 + 16`` for DEFLATE, plus the
  local and central headers), so which member lands in which archive depends only on the corpus, never on the zlib
  version; archive *bytes* are reproducible given the same zlib (recorded);
* every member's sha256 is recomputed while it is written and compared with ``checksums.sha256`` (exit 1 on a change).

``DEPOSIT-MANIFEST.json`` lists per archive ``name``, ``bytes``, ``sha256``, ``md5`` (Zenodo shows md5), ``corpus_id``,
``corpus_version``, ``stage``, ``shards`` (``{first, last}`` or null for meta), ``n_members``, ``uncompressed_bytes``
and ``members_sha256`` = ``"sha256:" + sha256`` of the archive's sha256sum-format member listing (``<hex>  <member
name>\\n`` per member, sorted by name); per corpus the content and root digests (H.5.4), licence class, verification
level, release-scan summary and the archive names; and the README, changelog, datasheet copies and metadata file with
their digests. Two builds of the same sealed corpora with the same inputs are byte-identical (Q.20).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import shutil
import tomllib
import zipfile
import zlib
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Final

from agentprov.corpus.integrity import parse_checksums, root_digest, verify_checksums
from agentprov.corpus.layout import (
    CHECKSUMS,
    DATASHEET,
    PARTIAL_SUFFIX,
    WITHHELD,
    assert_writable,
    iter_tree,
)
from agentprov.corpus.manifest import validate_manifest
from agentprov.corpus.package import parse_changes
from agentprov.corpus.reader import CorpusReader
from agentprov.envinfo import refuse_advisory_manifest, require_patched_for_archive
from agentprov.errors import AgentProvError, IngestError
from agentprov.ingest.limits import GIB, IngestLimits
from agentprov.ingest.loaders import strict_json_loads
from agentprov.io.atomic import atomic_swap_dir
from agentprov.io.canonical import jcs_bytes
from agentprov.release.metadata import (
    DEPOSIT_METADATA_FORMAT,
    DepositMetadataError,
    LicenceClass,
    Related,
    ReleaseMetadata,
    ScanRefusedError,
    ScanSummary,
    check_licence_classes,
    check_release_scan,
    check_withhold_scan,
    class_text,
    corpus_related,
    datasheet_copy,
    licence_class,
    merge_related,
)

__all__ = [
    "COMPRESS_LEVEL",
    "DEFAULT_MAX_ARCHIVE_BYTES",
    "DEPOSIT_MANIFEST",
    "DEPOSIT_MANIFEST_FORMAT",
    "DEPOSIT_METADATA",
    "EXTERNAL_ATTR",
    "MAX_MEMBERS",
    "RELEASE_SCAN_JSON_BYTES",
    "CorpusVerification",
    "DepositError",
    "DepositProducer",
    "DepositRefusedError",
    "DepositReport",
    "archive_date_time",
    "build_deposit",
    "members_sha256",
    "release_scan_limits",
    "scan_path_for",
    "verify_sealed",
]

DEPOSIT_MANIFEST_FORMAT: Final = "agentprov-deposit-manifest/0.1"
DEPOSIT_MANIFEST: Final = "DEPOSIT-MANIFEST.json"
DEPOSIT_METADATA: Final = "deposit-metadata.json"
#: No ZIP64: an archive, a member offset and a member stay below this (zipfile's ZIP64_LIMIT).
ZIP64_LIMIT: Final = (1 << 31) - 1
#: The default ``--max-archive-bytes``: H.10.4's 2 GiB proposal, lowered by one byte so that no ZIP64 record is needed.
DEFAULT_MAX_ARCHIVE_BYTES: Final = ZIP64_LIMIT
MIN_MAX_ARCHIVE_BYTES: Final = 4096
#: zipfile's ZIP_FILECOUNT_LIMIT: more members need a ZIP64 end record.
MAX_MEMBERS: Final = 0xFFFF
#: zipfile decides ZIP64 for a member when ``file_size * 1.05 > ZIP64_LIMIT``.
MAX_MEMBER_BYTES: Final = int(ZIP64_LIMIT / 1.05) - 1
COMPRESS_LEVEL: Final = 6
CREATE_SYSTEM: Final = 3  # Unix
EXTERNAL_ATTR: Final = 0o100644 << 16  # regular file, rw-r--r--
_LOCAL_HEADER: Final = 30
_CENTRAL_HEADER: Final = 46
_END_RECORD: Final = 22
_CHUNK: Final = 1 << 20
_SCAN_SUFFIX: Final = ".release-scan.json"
#: D-990: the JSON size limit for a corpus's release-scan document, which ``tools/release_scan.py`` writes beside the
#: sealed tree (not raw source input). It grows with the scan's findings: 167 MB for ``agentdyn-a`` 0.1.0, past the
#: 64 MiB raw-input limit. The parse stays bounded (strict loader, depth and digit limits unchanged), as D-935's PROV
#: documents.
RELEASE_SCAN_JSON_BYTES: Final = 1 * GIB


def release_scan_limits(limits: IngestLimits | None = None) -> IngestLimits:
    """``limits`` (default: the defaults) with ``max_json_bytes`` at least :data:`RELEASE_SCAN_JSON_BYTES` (D-990): the
    limits for parsing a release-scan document, never for raw source input."""
    base = limits or IngestLimits()
    return dataclasses.replace(base, max_json_bytes=max(base.max_json_bytes, RELEASE_SCAN_JSON_BYTES))


class DepositRefusedError(AgentProvError):
    """A deposit precondition refused (N.2.11; exit 4). Nothing was written."""

    code = "release.refused"
    exit_code = 4


class DepositError(AgentProvError):
    """The deposit could not be built: a corpus failed verification, changed while it was archived, or a generated
    text failed the claims lint (exit 1). The partial output is removed."""

    code = "release.failed"
    exit_code = 1


@dataclass(frozen=True)
class DepositProducer:
    """What the building process knows about itself (supplied by the CLI: ``release/`` runs no subprocess)."""

    agentprov_version: str
    git_commit: str | None
    git_tree_clean: bool
    python: str
    zlib_version: str = zlib.ZLIB_RUNTIME_VERSION

    def to_json(self) -> dict[str, Any]:
        return {"agentprov_version": self.agentprov_version, "git_commit": self.git_commit,
                "git_tree_clean": self.git_tree_clean, "python": self.python, "zlib_version": self.zlib_version}  # fmt: skip


@dataclass(frozen=True)
class CorpusVerification:
    """The outcome of verifying one sealed corpus before it is archived."""

    level: str
    ok: bool
    detail: str = ""


#: ``verify(root) -> CorpusVerification`` (the built-in :func:`verify_sealed`, or U4's ``chain`` level).
Verifier = Callable[[Path], CorpusVerification]
#: ``scan(root, root_digest) -> agentprov-release-scan/0.1 document`` (or ``None``: no scan result, refused).
Scanner = Callable[[Path, str], Mapping[str, Any] | None]
#: ``lint(location, text) -> [(code, location, detail)]``: the claims text lint, injected by the CLI (M.5.2(1)).
Lint = Callable[[str, str], Sequence[tuple[str, str, str]]]


@dataclass
class DepositReport:
    """The outcome of :func:`build_deposit`."""

    out: Path
    corpora: list[dict[str, Any]]
    archives: list[dict[str, Any]]
    licence_classes: list[LicenceClass]
    mixed_licence_classes: bool
    notices: list[str] = field(default_factory=list)
    dry_run: bool = False

    @property
    def counters(self) -> dict[str, int]:
        return {"archives": len(self.archives), "bytes": sum(a["bytes"] for a in self.archives),
                "corpora": len(self.corpora), "files": sum(a["n_members"] for a in self.archives)}  # fmt: skip


def _refuse(message: str, code: str, exit_code: int = 4) -> DepositRefusedError:
    return DepositRefusedError(message, code=f"release.refused.{code}", exit_code=exit_code)


# ================================================================================================ helpers
def scan_path_for(root: str | os.PathLike[str]) -> Path:
    """``<corpus>.release-scan.json``: beside the sealed tree, outside the checksummed tree (G.9.4)."""
    path = Path(root)
    return path.with_name(path.name + _SCAN_SUFFIX)


def archive_date_time(release_date: date) -> tuple[int, int, int, int, int, int]:
    """The member timestamp: the release date at midnight; ZIP cannot hold dates before 1980 (H.10.4), and
    :func:`build_deposit` refuses one after 2107."""
    if (release_date.year, release_date.month, release_date.day) < (1980, 1, 1):
        return (1980, 1, 1, 0, 0, 0)
    return (release_date.year, release_date.month, release_date.day, 0, 0, 0)


def members_sha256(listing: Iterable[tuple[str, str]]) -> str:
    """``"sha256:" + sha256`` of the sha256sum-format listing ``<hex>  <member>\\n`` of ``(hex, member)`` pairs sorted by
    member name (bytewise)."""
    digest = hashlib.sha256()
    for hex_digest, name in sorted(listing, key=lambda item: item[1].encode("utf-8")):
        digest.update(f"{hex_digest}  {name}\n".encode())
    return "sha256:" + digest.hexdigest()


def _member_bound(name_bytes: int, size: int) -> int:
    """An upper bound of the bytes one member adds to an archive (local header + name + DEFLATE output + central
    header + name). zlib's raw-deflate bound is ``size + (size >> 12) + (size >> 14) + (size >> 25) + 7``."""
    return _LOCAL_HEADER + _CENTRAL_HEADER + 2 * name_bytes + size + (size >> 11) + 16


def _document_bytes(document: Mapping[str, Any]) -> bytes:
    """A deposit JSON document: sorted keys, two-space indentation, UTF-8, final LF (H.1.4(2))."""
    return (json.dumps(document, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def verify_sealed(root: Path) -> CorpusVerification:
    """The built-in pre-archive check: H.5.5 level ``checksums`` in closed-world tree mode (the manifest validator runs
    separately). U4's ``chain`` level replaces it through ``build_deposit(verify=…)``."""
    report = verify_checksums(root)
    if report.ok:
        return CorpusVerification("checksums", True)
    return CorpusVerification("checksums", False, ", ".join(f"{k}: {v}" for k, v in report.codes().items()))


# ================================================================================================ one corpus
@dataclass
class _Member:
    label: str  # corpus-relative path
    size: int
    sha256: str  # from checksums.sha256 (checksums.sha256 itself: computed when listed)


@dataclass
class _Corpus:
    root: Path
    reader: CorpusReader
    manifest: dict[str, Any]
    corpus_id: str
    version: str
    root_digest: str
    cls: LicenceClass
    verification: CorpusVerification
    scan: ScanSummary
    members: list[_Member]
    datasheet: bytes
    changes: list[dict[str, str]]
    related: list[Related]

    @property
    def prefix(self) -> str:
        return f"{self.corpus_id}-v{self.version}"


def _stage_of(label: str) -> tuple[str, str | None]:
    """``(stage, shard)`` of a corpus-relative path; the meta stage has no shard."""
    parts = label.split("/")
    if parts[0] == "raw" and len(parts) >= 4 and parts[1] == "objects":
        return "raw", "/".join(parts[2:-1])
    if parts[0] == "aer" and len(parts) >= 3:
        return "aer", "/".join(parts[1:-1])
    if parts[0] in ("sem", "prov") and len(parts) >= 4:
        return f"{parts[0]}-{parts[1]}", "/".join(parts[2:-1])
    return "meta", None


def _scan_document(root: Path, digest: str, scan: Scanner | None, limits: IngestLimits) -> Mapping[str, Any] | None:
    if scan is not None:
        return scan(root, digest)
    limits = release_scan_limits(limits)
    path = scan_path_for(root)
    try:
        with open(path, "rb") as stream:
            data = stream.read(limits.max_json_bytes + 1)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise _refuse(f"the release scan beside the corpus cannot be read ({type(exc).__name__})", "scan") from None
    if len(data) > limits.max_json_bytes:
        raise _refuse("the release scan is larger than the file limit", "scan")
    try:
        value = strict_json_loads(data, limits)
    except IngestError as exc:
        raise _refuse(f"the release scan is not strict JSON ({exc.code})", "scan") from None
    return value if isinstance(value, Mapping) else {}


def _withheld_fingerprints(reader: CorpusReader) -> list[str]:
    document = reader.read_document(WITHHELD, required=False)
    out = []
    for entry in (document or {}).get("entries") or ():
        finding = entry.get("finding") if isinstance(entry, Mapping) else None
        if isinstance(finding, Mapping) and isinstance(finding.get("fingerprint"), str):
            out.append(finding["fingerprint"])
    return out


def _withhold_backstop(reader: CorpusReader, manifest: Mapping[str, Any], corpus_id: str, scan_document: Mapping[str, Any],
                       labels: Sequence[str]) -> None:
    """D-236: the source profile's ``[withhold]`` policy, re-applied to the sealed tree before anything is deposited."""
    from agentprov.corpus.withhold import (WithholdError, issue_backstop, listed_backstop, load_policy, rescan,
                                           withhold_addresses, withhold_listed)

    catalogues = {str(e.get("id")): e["version"] for e in manifest.get("rule_catalogues") or ()
                  if isinstance(e, Mapping) and isinstance(e.get("version"), int)}  # fmt: skip

    for source in manifest.get("sources") or ():
        profile = source.get("profile") or {}
        path, recorded = profile.get("path"), profile.get("sha256")
        if not isinstance(path, str) or not isinstance(recorded, str):
            continue
        data = reader.read_bytes(path)
        if "sha256:" + hashlib.sha256(data).hexdigest() != recorded:
            raise DepositError(f"{corpus_id}: the source profile copy under rules/ does not match the manifest's digest",
                               code="release.failed.profile")
        try:
            spec_bytes = reader.read_bytes("rules/corpus-spec.toml") if reader.exists("rules/corpus-spec.toml") else None
            addresses = (withhold_addresses(spec_bytes, lambda name: reader.read_bytes(f"rules/personas/{name}")
                                            if reader.exists(f"rules/personas/{name}") else None)
                         if spec_bytes is not None else frozenset())
            listed = withhold_listed(spec_bytes) if spec_bytes is not None else (frozenset(), frozenset())
            policy = load_policy(data, profile_id=str(profile.get("id")), profile_version=int(profile.get("version", 0)),
                                 catalogues=catalogues, addresses=addresses, listed=listed)
        except WithholdError as exc:
            raise _refuse(f"{corpus_id}: the source profile's [withhold] policy is not valid ({exc.code})", "withhold_policy") from None
        if policy is None:
            continue

        def stream(label: str) -> Iterable[bytes]:
            with reader.open_file(label, stored=True) as handle:
                while chunk := handle.read(1 << 20):
                    yield chunk

        unread: list[tuple[str, str]] = []
        hits = rescan(labels, stream, policy, unscanned=unread)
        if hits:
            raise _refuse(f"{corpus_id}: {len(hits)} released file(s) match a rule of the source profile's [withhold] "
                          "policy; build a new corpus version that withholds them (H.4.5; D-236)", "withhold_rule")
        if unread:
            raise _refuse(f"{corpus_id}: {len(unread)} released archive(s) could not be read in decoded form "
                          f"({', '.join(sorted({code for _label, code in unread}))}) for the [withhold] policy's byte "
                          "rules; build a new corpus version that withholds them (D-450)", "withhold_unscanned")
        released_listed = listed_backstop(policy, labels, reader.index())
        if released_listed:
            raise _refuse(f"{corpus_id}: {len(released_listed)} object(s) or execution(s) the corpus spec's [withhold] lists are "
                          "released; build a new corpus version that withholds them (D-964)", "withhold_listed")
        if policy.issue_rules:
            released = issue_backstop(policy, reader.register(), reader.index())
            if released:
                raise _refuse(f"{corpus_id}: {len(released)} released execution(s) carry the issue code of a rule of the "
                              "source profile's [withhold] policy; build a new corpus version that withholds them (D-311)",
                              "withhold_issue")
        if policy.scan_rules:
            missed = check_withhold_scan(scan_document, policy.scan_rules)
            if missed:
                raise ScanRefusedError(f"{corpus_id}: {missed} release-scan finding(s) of a rule the [withhold] policy "
                                       "names are not triaged false-positive (D-236)", code="release.refused.withhold_scan")


def _source_tables(reader: CorpusReader, manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    """``[source]`` of each source profile copy under ``rules/``, read only after its sha256 matched the manifest's."""
    out: dict[str, Mapping[str, Any]] = {}
    for source in manifest.get("sources") or ():
        profile = source.get("profile") or {}
        path, recorded = profile.get("path"), profile.get("sha256")
        if not isinstance(path, str) or not isinstance(recorded, str):
            continue
        data = reader.read_bytes(path)
        if "sha256:" + hashlib.sha256(data).hexdigest() != recorded:
            raise DepositError(f"{manifest.get('corpus_id')}: the source profile copy under rules/ does not match the "
                               "manifest's digest", code="release.failed.profile")
        try:
            table = tomllib.loads(data.decode("utf-8")).get("source")
        except (tomllib.TOMLDecodeError, UnicodeDecodeError):
            raise DepositError("a source profile copy under rules/ is not valid TOML", code="release.failed.profile") from None
        if isinstance(table, Mapping):
            out[str(source.get("source_id"))] = table
    return out


def _open_corpus(path: Path, *, verify: Verifier, scan: Scanner | None, limits: IngestLimits) -> _Corpus:
    try:
        reader = CorpusReader.open(path, limits=limits)
    except AgentProvError as exc:
        raise _refuse(f"{path.name}: not a readable sealed corpus ({exc.code})", "unsealed") from None
    if not reader.sealed or reader.used_partial:
        raise _refuse(f"{path.name}: only sealed corpora are deposited; seal it with package --corpus first", "unsealed")
    manifest = reader.manifest()
    assert manifest is not None
    corpus_id, version = str(manifest.get("corpus_id")), str(manifest.get("corpus_version"))
    if (manifest.get("release") or {}).get("status") != "sealed":
        raise _refuse(f"{corpus_id}: release.status is not sealed", "unsealed")
    refuse_advisory_manifest(manifest)  # AD-16: exit 4
    live = manifest.get("live")
    if manifest.get("mode") == "live" and (not isinstance(live, Mapping) or live.get("test_only") is not False):
        raise _refuse(f"{corpus_id}: a test_only live corpus is never deposited (H.1.1(2))", "test_only")
    if (manifest.get("validation") or {}).get("mode") != "strict":
        raise _refuse(f"{corpus_id}: only corpora validated strict are deposited (H.10.1(3))", "dev_validation")
    for source in manifest.get("sources") or ():
        for snapshot in source.get("snapshots") or ():
            if snapshot.get("raw_policy") == "withhold" and not reader.exists(WITHHELD):
                raise _refuse(f"{corpus_id}: snapshot raw policy withhold but no WITHHELD.json: the corpus is not "
                              "releasable (H.4.1; D-233)", "withhold")
    issues = validate_manifest(manifest)
    if issues:
        shown = "; ".join(f"{i.pointer or '/'} {i.code}" for i in issues[:5])
        raise DepositError(f"{corpus_id}: the manifest does not validate ({len(issues)} issue(s)): {shown}",
                           code="release.failed.manifest")
    cls = licence_class(manifest)

    scan_tree = iter_tree(reader.root)
    if scan_tree.findings:
        raise DepositError(f"{corpus_id}: the sealed tree is not closed-world "
                           f"({', '.join(sorted({f.code for f in scan_tree.findings}))})", code="release.failed.verify")
    if any(label.startswith("views/") for label in scan_tree.labels()):
        raise _refuse(f"{corpus_id}: the corpus has a views/ tree; views are not deposited in v0.1 (AD-10 row 12)",
                      "views", exit_code=5)
    verification = verify(reader.root)
    if not verification.ok:
        raise DepositError(f"{corpus_id}: verification level {verification.level} failed ({verification.detail})",
                           code="release.failed.verify")
    digest = root_digest(reader.root)
    document = _scan_document(reader.root, digest, scan, limits)
    if document is None:
        raise ScanRefusedError(f"{corpus_id}: no release scan for this corpus; run tools/release_scan.py on the sealed "
                               "corpus and triage every finding (G.9.4)", code="release.refused.scan_missing")
    summary = check_release_scan(document, corpus_id=corpus_id, root_digest=digest,
                                 withheld_fingerprints=_withheld_fingerprints(reader),
                                 spec_sha256=((manifest.get("files") or {}).get("spec") or {}).get("sha256"),
                                 scan_sha256="sha256:" + hashlib.sha256(jcs_bytes(document)).hexdigest())
    _withhold_backstop(reader, manifest, corpus_id, document, [label for label, _, _ in scan_tree.files])

    checksums = reader.checksums_bytes()
    assert checksums is not None
    entries, findings = parse_checksums(checksums)
    if findings:
        raise DepositError(f"{corpus_id}: checksums.sha256 is malformed", code="release.failed.verify")
    sizes = {label: size for label, _, size in scan_tree.files}
    members = [_Member(e.path, sizes.get(e.path, -1), e.sha256) for e in entries]
    members.append(_Member(CHECKSUMS, len(checksums), hashlib.sha256(checksums).hexdigest()))
    if {m.label for m in members} != set(sizes) or any(m.size < 0 for m in members):
        raise DepositError(f"{corpus_id}: the tree and checksums.sha256 list different files", code="release.failed.verify")
    changes = parse_changes(reader.read_bytes("rules/CHANGES.toml"))
    related = corpus_related(manifest, _source_tables(reader, manifest))
    return _Corpus(path, reader, manifest, corpus_id, version, digest, cls, verification, summary,
                   sorted(members, key=lambda m: m.label.encode("ascii")), reader.read_bytes(DATASHEET), changes, related)


# ================================================================================================ archive plan
@dataclass
class _Archive:
    name: str
    corpus: _Corpus
    stage: str
    shards: list[str]
    members: list[_Member]


def _plan(corpus: _Corpus, max_bytes: int) -> list[_Archive]:
    by_stage: dict[str, dict[str | None, list[_Member]]] = {}
    for member in corpus.members:
        if member.size > MAX_MEMBER_BYTES:
            raise _refuse(f"{corpus.corpus_id}: a file is too large for an archive without ZIP64", "member_too_large")
        stage, shard = _stage_of(member.label)
        by_stage.setdefault(stage, {}).setdefault(shard, []).append(member)
    prefix_bytes = len(corpus.prefix) + 1

    def bound(members: Sequence[_Member]) -> int:
        return sum(_member_bound(prefix_bytes + len(m.label), m.size) for m in members)

    archives: list[_Archive] = []
    meta = by_stage.pop("meta", {}).get(None, [])
    if bound(meta) + _END_RECORD > max_bytes or len(meta) > MAX_MEMBERS:
        raise _refuse(f"{corpus.corpus_id}: the meta archive would exceed --max-archive-bytes", "archive_too_large")
    archives.append(_Archive(f"{corpus.prefix}.meta.zip", corpus, "meta", [], meta))
    stage_order = sorted(by_stage, key=lambda s: (("raw", "aer").index(s) if s in ("raw", "aer") else 2, s))
    for stage in stage_order:
        shards = by_stage[stage]
        current: _Archive | None = None
        size = count = 0
        number = 0
        for shard in sorted(shards, key=lambda s: str(s)):
            members = shards[shard]
            shard_bound = bound(members)
            if shard_bound + _END_RECORD > max_bytes or len(members) > MAX_MEMBERS:
                raise _refuse(f"{corpus.corpus_id}: shard {shard} of stage {stage} alone exceeds --max-archive-bytes; "
                              "archives are never split inside a shard (H.10.4)", "shard_too_large")
            if current is None or size + shard_bound + _END_RECORD > max_bytes or count + len(members) > MAX_MEMBERS:
                number += 1
                if number > 999:
                    raise _refuse(f"{corpus.corpus_id}: stage {stage} needs more than 999 archives", "archive_count")
                current = _Archive(f"{corpus.prefix}.{stage}.{number:03d}.zip", corpus, stage, [], [])
                archives.append(current)
                size = count = 0
            current.shards.append(str(shard))
            current.members.extend(members)
            size += shard_bound
            count += len(members)
    for archive in archives:
        archive.members.sort(key=lambda m: m.label.encode("ascii"))
    return archives


def _write_archive(archive: _Archive, path: Path, date_time: tuple[int, int, int, int, int, int]) -> dict[str, Any]:
    corpus = archive.corpus
    listing: list[tuple[str, str]] = []
    with open(path, "xb") as handle, zipfile.ZipFile(handle, "w", compression=zipfile.ZIP_DEFLATED,
                                                     compresslevel=COMPRESS_LEVEL, allowZip64=False) as zf:
        for member in archive.members:
            name = f"{corpus.prefix}/{member.label}"
            info = zipfile.ZipInfo(name, date_time=date_time)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.compress_level = COMPRESS_LEVEL
            info.create_system = CREATE_SYSTEM
            info.external_attr = EXTERNAL_ATTR
            info.file_size = member.size
            digest = hashlib.sha256()
            written = 0
            with corpus.reader.open_file(member.label, stored=True) as source, zf.open(info, "w") as sink:
                while chunk := source.read(_CHUNK):
                    digest.update(chunk)
                    sink.write(chunk)
                    written += len(chunk)
            if digest.hexdigest() != member.sha256 or written != member.size:
                raise DepositError(f"{corpus.corpus_id}: a file changed while it was archived (checksums.sha256 no longer "
                                   "matches)", code="release.failed.changed")
            listing.append((member.sha256, name))
    sha, md5, size = _file_digests(path)
    return {
        "bytes": size,
        "corpus_id": corpus.corpus_id,
        "corpus_version": corpus.version,
        "md5": md5,
        "members_sha256": members_sha256(listing),
        "n_members": len(listing),
        "name": archive.name,
        "sha256": sha,
        "shards": None if archive.stage == "meta" else {"first": archive.shards[0], "last": archive.shards[-1]},
        "stage": archive.stage,
        "uncompressed_bytes": sum(m.size for m in archive.members),
    }


def _file_digests(path: Path) -> tuple[str, str, int]:
    sha, md5 = hashlib.sha256(), hashlib.md5(usedforsecurity=False)
    size = 0
    with open(path, "rb") as stream:
        while chunk := stream.read(_CHUNK):
            sha.update(chunk)
            md5.update(chunk)
            size += len(chunk)
    return "sha256:" + sha.hexdigest(), md5.hexdigest(), size


# ================================================================================================ documents
_NOT_PUBLISHED: Final = "Nothing has been uploaded or published."


def _class_text(cls: LicenceClass) -> str:
    return class_text(cls)  # one definition with archive-mode verify (D-620)


def _description(metadata: ReleaseMetadata, corpora: Sequence[_Corpus], release_date: date) -> str:
    lines = []
    if metadata.description_preamble.strip():
        lines += [metadata.description_preamble.strip(), ""]
    lines.append(f"This deposit draft holds {len(corpora)} AgentPROV corpus version(s), prepared offline by agentprov "
                 f"package --deposit for the release date {release_date.isoformat()}. {_NOT_PUBLISHED}")
    for corpus in corpora:
        counts = corpus.manifest.get("counts") or {}
        units = counts.get("by_unit") or {}
        # plain text, one paragraph per corpus: the description is sent to repositories as HTML paragraphs, where a leading
        # "- " would show as a literal hyphen (sandbox trial 2026-10-23, D-800)
        lines += ["", f"Corpus {corpus.corpus_id} {corpus.version}: {corpus.manifest.get('title')}. "
                      f"{counts.get('executions')} execution records, of which {units.get('outcome_only', 0)} are "
                      f"outcome-only records. Licence class: {_class_text(corpus.cls)}. Content digest "
                      f"{corpus.manifest.get('content_digest')}; root digest {corpus.root_digest}."]
    lines += ["", "Counts are computed from each corpus manifest at sealing. Each DATASHEET states what the records do "
                  "and do not establish; a statement about the data is scoped as it is there.",
              "", "To verify: compare each archive's sha256 or md5 with DEPOSIT-MANIFEST.json, run agentprov verify on "
                  "the archives (archive mode, no extraction; H.5.5), and compare each root digest with the one "
                  "published outside the deposit (the corpus tag annotation and the paper)."]
    return "\n".join(lines) + "\n"


def _readme(metadata: ReleaseMetadata, corpora: Sequence[_Corpus], archives: Sequence[Mapping[str, Any]],
            documents: Sequence[str], producer: DepositProducer, release_date: date, mixed: bool) -> bytes:
    lines = [f"# {metadata.title}", "",
             f"Deposit draft (unpublished) for the release date {release_date.isoformat()}, prepared offline by "
             f"AgentPROV {producer.agentprov_version} (commit `{producer.git_commit or 'unknown'}`) with "
             f"`agentprov package --deposit`. {_NOT_PUBLISHED} Publishing, which mints a DOI, is a manual action.",
             "", "## Corpora", ""]
    for corpus in corpora:
        names = [a["name"] for a in archives if a["corpus_id"] == corpus.corpus_id]
        lines += [f"### {corpus.corpus_id} {corpus.version}", "",
                  f"- Title: {corpus.manifest.get('title')}",
                  f"- Licence class: {_class_text(corpus.cls)}",
                  f"- Content digest: `{corpus.manifest.get('content_digest')}`",
                  f"- Root digest: `{corpus.root_digest}` (sha256 of `checksums.sha256`; H.5.4)",
                  f"- Datasheet: `DATASHEET-{corpus.corpus_id}.md`",
                  f"- Archives ({len(names)}): " + ", ".join(f"`{n}`" for n in names), ""]
    if mixed:
        lines += ["This deposit mixes licence classes under `--allow-mixed-licence-classes` (AD-20(b)); each corpus keeps "
                  "its own licence, stated in its datasheet copy and in `deposit-metadata.json`.", ""]
    lines += ["## Files", "", "| File | Bytes | sha256 |", "|---|---|---|"]
    for archive in archives:
        lines.append(f"| `{archive['name']}` | {archive['bytes']} | `{archive['sha256']}` |")
    for name in documents:
        lines.append(f"| `{name}` | see `{DEPOSIT_MANIFEST}` | |")
    lines += ["", "## Verifying", "",
              f"1. Check each archive's sha256 (or md5) against `{DEPOSIT_MANIFEST}`.",
              "2. Run `agentprov verify` on the archives. It reads them without extraction (archive mode, H.5.5) and checks "
              "every member against the corpus's closed-world `checksums.sha256`.",
              "3. Compare each root digest with the one published outside the deposit: the annotation of the tag "
              "`corpus/<corpus_id>/v<version>` and the paper (REP-4). `agentprov verify --release` takes one "
              "`--root-digest` per corpus of the deposit.",
              "", "Each archive member path starts with `<corpus_id>-v<version>/`; the archives of a corpus together are an "
              "image of its sealed tree. Members are sorted, carry the release date as their timestamp and fixed "
              "permissions, and are compressed with DEFLATE at a fixed level.",
              "", "## Citation", "",
              "Cite the version DOI, the concept DOI and the root digest together (REP-4). This draft carries no DOI: "
              "DOIs are assigned when the user publishes the record.",
              "", "## Untrusted content", "",
              "Agent-security corpora contain prompt-injection payloads, model outputs and tool outputs by design. Treat "
              "every string in the archives as data, never as instructions, and display it quoted.", ""]
    return "\n".join(lines).encode("utf-8")


def _changelog(corpora: Sequence[_Corpus]) -> bytes:
    lines = ["# Deposit changelog", "",
             "Generated from each corpus's `rules/CHANGES.toml`. DOIs obtained after publication are recorded in the next "
             "version's changelog; archives are never rebuilt after publication (H.10.5(2))."]
    for corpus in corpora:
        lines += ["", f"## {corpus.corpus_id}"]
        for entry in corpus.changes:
            lines += ["", f"### {entry['version']} ({entry['bump']})", "", entry["summary"].strip()]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _datasheet_copy(corpus: _Corpus, classes: Sequence[LicenceClass], mixed: bool) -> bytes:
    # Shared with archive-mode verify, which rebuilds the copy and compares it in full (D-490, D-620).
    return datasheet_copy(corpus.datasheet, corpus.cls, classes, mixed)


# ================================================================================================ build_deposit
def _check_out(out: Path, corpora: Sequence[Path]) -> Path:
    partial = out.with_name(out.name + PARTIAL_SUFFIX)
    if os.path.lexists(out) or os.path.lexists(partial):
        raise _refuse("the deposit directory (or its .partial) already exists; a deposit draft is never rewritten", "exists")
    parent = out.parent
    if not parent.is_dir():
        raise DepositRefusedError("the parent of the deposit directory does not exist", code="release.usage", exit_code=2)
    assert_writable(parent)
    real_out = Path(os.path.realpath(parent)) / out.name
    for corpus in corpora:
        real = Path(os.path.realpath(corpus))
        if real_out == real or real_out.is_relative_to(real) or real.is_relative_to(real_out):
            raise _refuse("the deposit directory overlaps an input corpus (N.1.9)", "overlap")
    return partial


def build_deposit(
    corpora: Sequence[str | os.PathLike[str]],
    metadata: ReleaseMetadata,
    out: str | os.PathLike[str],
    *,
    release_date: date,
    producer: DepositProducer,
    max_archive_bytes: int = DEFAULT_MAX_ARCHIVE_BYTES,
    allow_mixed_licence_classes: bool = False,
    scan: Scanner | None = None,
    verify: Verifier | None = None,
    lint: Lint | None = None,
    limits: IngestLimits | None = None,
    dry_run: bool = False,
) -> DepositReport:
    """Build a deposit draft at ``out`` from sealed ``corpora`` (see the module docstring).

    Raises :class:`DepositRefusedError` / :class:`agentprov.release.metadata.LicenceClassError` /
    :class:`agentprov.release.metadata.ScanRefusedError` (exit 4; ``views/`` exit 5), the interpreter guard's errors
    (exit 3 below 3.14.8, exit 4 for an advisory corpus), :class:`DepositError` (exit 1) and
    :class:`agentprov.release.metadata.DepositMetadataError` (exit 2). ``dry_run`` runs every check and plans the
    archives (names, members, uncompressed bytes) but writes nothing (N.1.6).
    """
    require_patched_for_archive(release=True)  # Q.15a: release mode; no override
    if not corpora:
        raise DepositRefusedError("no corpus given", code="release.usage", exit_code=2)
    if not MIN_MAX_ARCHIVE_BYTES <= max_archive_bytes <= ZIP64_LIMIT:
        raise DepositRefusedError(f"--max-archive-bytes is between {MIN_MAX_ARCHIVE_BYTES} and {ZIP64_LIMIT} (no ZIP64)",
                                  code="release.usage", exit_code=2)
    if release_date > date(2107, 12, 31):  # ZIP member timestamps end at 2107 (CB-19: struct.error, exit 70, mid-build)
        raise DepositRefusedError("--release-date is at most 2107-12-31 (ZIP timestamps, H.10.4)", code="release.usage",
                                  exit_code=2)
    paths = [Path(p) for p in corpora]
    out_path = Path(out)
    partial = _check_out(out_path, paths)
    limits = limits or IngestLimits()
    opened = [_open_corpus(p, verify=verify or verify_sealed, scan=scan, limits=limits) for p in paths]
    keys = [(c.corpus_id, c.version) for c in opened]
    if len(set(keys)) != len(keys) or len({c.corpus_id for c in opened}) != len(opened):
        raise DepositRefusedError("a corpus id appears twice in one deposit", code="release.usage", exit_code=2)
    opened.sort(key=lambda c: c.corpus_id)
    classes = check_licence_classes({c.corpus_id: c.cls for c in opened}, allow_mixed=allow_mixed_licence_classes)
    mixed = len(classes) > 1
    versions = {c.version for c in opened}
    if metadata.version is None and len(versions) > 1:
        raise DepositMetadataError("release.toml: version is required when the corpora carry different versions")
    version = metadata.version or next(iter(versions))
    plans = [archive for corpus in opened for archive in _plan(corpus, max_archive_bytes)]
    date_time = archive_date_time(release_date)
    notices = [f"{c.corpus_id}: verified at level {c.verification.level}" + (
        "; the chain level (U4) was not available to this build" if c.verification.level == "checksums" else "")
        for c in opened]
    if dry_run:
        planned = [{"bytes": 0, "corpus_id": a.corpus.corpus_id, "corpus_version": a.corpus.version,
                    "n_members": len(a.members), "name": a.name, "stage": a.stage,
                    "uncompressed_bytes": sum(m.size for m in a.members)} for a in plans]  # fmt: skip
        return DepositReport(out_path, [_corpus_entry(c, planned) for c in opened], planned, classes, mixed, notices,
                             dry_run=True)

    partial.mkdir()
    try:
        archives = [_write_archive(a, partial / a.name, date_time) for a in plans]
        docs: dict[str, bytes] = {}
        for corpus in opened:
            docs[f"DATASHEET-{corpus.corpus_id}.md"] = _datasheet_copy(corpus, classes, mixed)
        docs["CHANGELOG.md"] = _changelog(opened)
        description = _description(metadata, opened, release_date)
        related = merge_related([metadata.related, *(c.related for c in opened)])
        docs[DEPOSIT_METADATA] = _document_bytes(_metadata_document(
            metadata, opened, archives, classes, mixed, related, description, release_date, version, producer))
        docs["README.md"] = _readme(metadata, opened, archives, sorted([*docs, DEPOSIT_MANIFEST]), producer,
                                    release_date, mixed)
        if lint is not None:
            violations = [v for name in ("README.md",) for v in lint(name, docs[name].decode("utf-8"))]
            violations += list(lint(f"{DEPOSIT_METADATA}#description", description))
            if violations:
                shown = "; ".join(f"{code} at {where}: {detail}" for code, where, detail in violations[:5])
                raise DepositError(f"a generated deposit text fails the claims lint ({len(violations)}): {shown}",
                                   code="release.failed.lint")
        for name in sorted(docs):
            with open(partial / name, "xb") as handle:
                handle.write(docs[name])
        manifest = _deposit_manifest(opened, archives, docs, classes, mixed, release_date, max_archive_bytes, producer,
                                     date_time)
        with open(partial / DEPOSIT_MANIFEST, "xb") as handle:
            handle.write(_document_bytes(manifest))
        atomic_swap_dir(partial, out_path)
    except BaseException:
        shutil.rmtree(partial, ignore_errors=True)
        raise
    corpora_json = manifest["corpora"]
    return DepositReport(out_path, corpora_json, archives, classes, mixed, notices)


def _corpus_entry(corpus: _Corpus, archives: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    names = [a["name"] for a in archives if a["corpus_id"] == corpus.corpus_id]
    archived = sum(a["n_members"] for a in archives if a["corpus_id"] == corpus.corpus_id)
    return {
        "archives": names,
        "content_digest": corpus.manifest.get("content_digest"),
        "corpus_id": corpus.corpus_id,
        "corpus_version": corpus.version,
        "coverage": {"archived": archived, "files": len(corpus.members)},
        "licence_class": corpus.cls.to_json(),
        "member_prefix": f"{corpus.prefix}/",
        "release_scan": corpus.scan.to_json(),
        "root_digest": corpus.root_digest,
        "title": corpus.manifest.get("title"),
        "verification": {"level": corpus.verification.level},
    }


def _deposit_manifest(corpora: Sequence[_Corpus], archives: Sequence[Mapping[str, Any]], docs: Mapping[str, bytes],
                      classes: Sequence[LicenceClass], mixed: bool, release_date: date, max_bytes: int,
                      producer: DepositProducer, date_time: tuple[int, ...]) -> dict[str, Any]:
    documents = []
    for name in sorted(docs):
        data = docs[name]
        documents.append({"bytes": len(data), "md5": hashlib.md5(data, usedforsecurity=False).hexdigest(), "name": name,
                          "sha256": "sha256:" + hashlib.sha256(data).hexdigest()})
    entries = [_corpus_entry(c, archives) for c in corpora]
    for entry in entries:
        if entry["coverage"]["archived"] != entry["coverage"]["files"]:
            raise DepositError(f"{entry['corpus_id']}: not every file of the tree was archived", code="release.failed.coverage")
    return {
        "archive_policy": {
            "compress_level": COMPRESS_LEVEL, "compression": "deflate", "create_system": CREATE_SYSTEM,
            "date_time": list(date_time), "external_attr": EXTERNAL_ATTR, "max_archive_bytes": max_bytes,
            "max_members": MAX_MEMBERS, "split": "shard", "zip64": False,
        },
        "archives": list(archives),
        "corpora": entries,
        "documents": documents,
        "format": DEPOSIT_MANIFEST_FORMAT,
        "licence_classes": [{**c.to_json(), "corpora": [x.corpus_id for x in corpora if x.cls == c]} for c in classes],
        "mixed_licence_classes": mixed,
        "producer": producer.to_json(),
        "release_date": release_date.isoformat(),
        "status": "draft-unpublished",
    }  # fmt: skip


def _metadata_document(metadata: ReleaseMetadata, corpora: Sequence[_Corpus], archives: Sequence[Mapping[str, Any]],
                       classes: Sequence[LicenceClass], mixed: bool, related: Sequence[Related], description: str,
                       release_date: date, version: str, producer: DepositProducer) -> dict[str, Any]:
    """``deposit-metadata.json`` (``agentprov-deposit/0.1``; H.10.5). DOIs: ``concept_doi`` only when the user gave it
    in ``release.toml``; ``version_doi`` is always null (assigned at publication, never invented)."""
    licences = []
    for cls in classes:
        members = [c for c in corpora if c.cls == cls]
        licences.append({**cls.to_json(),
                         "archives": [a["name"] for a in archives if a["corpus_id"] in {c.corpus_id for c in members}],
                         "corpora": [c.corpus_id for c in members],
                         "documents": [f"DATASHEET-{c.corpus_id}.md" for c in members]})  # fmt: skip
    return {
        "concept_doi": metadata.concept_doi,
        "creators": [c.to_json() for c in metadata.creators],
        "description": description,
        "format": DEPOSIT_METADATA_FORMAT,
        "keywords": list(metadata.keywords),
        "licences": licences,
        "mixed_licence_classes": {"allowed": mixed, "classes": len(classes), "flag": "--allow-mixed-licence-classes" if mixed
                                  else None},
        "notice": f"Prepared offline by agentprov package --deposit. {_NOT_PUBLISHED} The user maps this file onto the "
                  "repository's deposit form; it does not claim fidelity to any repository API (H.10.5).",
        "publication_date": release_date.isoformat(),
        "related_identifiers": [r.to_json() for r in related],
        "release_scans": [c.scan.to_json() for c in corpora],
        "resource_type": "dataset",
        "root_digests": {c.corpus_id: c.root_digest for c in corpora},
        "software": {"name": "agentprov", **producer.to_json()},
        "status": "draft-unpublished",
        "title": metadata.title,
        "version": version,
        "version_doi": None,
    }  # fmt: skip
