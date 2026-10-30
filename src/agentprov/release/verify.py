"""Archive-mode ``verify`` of a deposit draft (HL H.5.5 archive mode, H.10.3; G.3.5, G.5.7; DECISIONS D-38, D-39).

``agentprov verify --corpus PATH`` reads a deposit **without extracting it** when ``PATH`` is

* a **deposit directory** (it holds ``DEPOSIT-MANIFEST.json``): every check below; or
* a lone **meta archive** ``<corpus_id>-v<version>.meta.zip``: the members it holds are checked against the corpus's own
  ``checksums.sha256`` (inside it) and the manifest is validated; every other file the checksums list, and every check
  that needs one, is reported ``unverified``, never passed (D-38).

Deposit checks (finding codes ``deposit.*``):

1. ``DEPOSIT-MANIFEST.json`` is strict JSON of format ``agentprov-deposit-manifest/0.1`` whose names are plain file
   names; ``documents`` is exactly ``README.md``, ``CHANGELOG.md``, ``deposit-metadata.json`` and one
   ``DATASHEET-<corpus_id>.md`` per ``corpora`` entry, each once, and ``mixed_licence_classes`` is a boolean
   (``deposit.manifest.invalid``; D-490);
2. the deposit directory is closed-world: exactly the archives, the documents and the deposit manifest, regular files
   only (no link, no directory);
3. every archive's and document's size, ``sha256`` and ``md5`` equal the deposit manifest's;
4. every listed archive belongs to exactly one corpus entry and carries its ``<corpus_id>-v<version>.`` name prefix
   (``deposit.archive.orphan``: named by none, by more than one, or listed twice; an empty ``corpora`` list is
   ``deposit.manifest.invalid``); per archive: its corpus, ``n_members``, ``uncompressed_bytes`` and
   ``members_sha256`` (the sha256 of the sha256sum-format listing of its members, D-42 item 10) recompute from its
   members, and every member lies in the archive's stage;
5. per corpus: the union of its archives is the closed world of its ``checksums.sha256`` (every member under the
   corpus prefix, no label twice) and every member matches it (:mod:`agentprov.corpus.archive`); the root digest and the
   content digest equal the deposit manifest's; then the requested level (``checksums`` or ``chain``,
   :func:`agentprov.corpus.verify.verify_corpus`) runs over the archives. ``rederive`` is refused in archive mode
   (exit 5): no AgentPROV command extracts a deposit (H.10.3(1)); re-derive a sealed tree instead;
6. per corpus: the deposit copy ``DATASHEET-<corpus_id>.md`` is compared in full with the copy rebuilt from the
   archived ``DATASHEET.md`` and the licence classes of the archived ``corpus.json`` files, which the archived checksums
   and the root digest cover (``deposit.document.datasheet``; D-490, D-620). Without mixed licence classes it is a byte
   copy; with them it is the sealed datasheet (trailing line feeds folded into one) followed by the builder's deposit
   note, rebuilt by the builder's own function (:func:`agentprov.release.metadata.datasheet_copy`). The deposit
   manifest's ``mixed_licence_classes`` must agree with those classes (``deposit.manifest.invalid``). ``README.md``,
   ``CHANGELOG.md`` and ``deposit-metadata.json`` have no sealed counterpart: they stay covered only by the deposit
   manifest (check 3).

``root_digests`` (``--root-digest``, D-39): each must equal the computed root digest of a corpus of the deposit
(``root_digest.mismatch``). The deposit manifest is part of the deposit, so a consistent forgery of archives, checksums
and deposit manifest is caught only by a root digest published outside the deposit. Release mode therefore requires at
least one, for a deposit directory as for a lone meta archive and a tree (exit 2 before anything is read; D-620), and
for a deposit, one for **every** corpus (``root_digest.missing``, naming the corpus; D-641): a corpus no given digest
matches would be anchored only by the deposit manifest. A lone meta archive and a tree hold one corpus, which the
required digest anchors already. Without ``--release`` the option stays optional.

Archives are read in the CLI process with the G.3.5 gate and the archive-mode ingest limits
(:data:`agentprov.corpus.archive.ARCHIVE_LIMITS`), not in a T1 worker (D-38). Release mode below CPython 3.14.8 is
refused before any archive is opened (exit 3; AD-16).
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from agentprov.corpus.archive import ARCHIVE_LIMITS, ArchiveCorpusReader, ArchiveSet, ArchiveSource
from agentprov.corpus.authority import PackageResources
from agentprov.corpus.layout import DATASHEET
from agentprov.corpus.reader import CorpusReadError
from agentprov.corpus.verify import (
    FAILED,
    Finding,
    VerifyReport,
    VerifyUsageError,
    verify_corpus,
)
from agentprov.envinfo import require_patched_for_archive
from agentprov.errors import AgentProvError, IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads
from agentprov.ingest.paths import open_evidence
from agentprov.release.builder import (
    DEPOSIT_MANIFEST,
    DEPOSIT_MANIFEST_FORMAT,
    DEPOSIT_METADATA,
    _stage_of,
    members_sha256,
)
from agentprov.release.index import INDEX_MANIFEST_FORMAT
from agentprov.release.metadata import LicenceClass, datasheet_copy, licence_class

__all__ = ["DepositVerification", "VerifyUnsupportedError", "is_archive_input", "verify_deposit"]

# A plain file name: every character the builder puts in an archive or document name (``<corpus_id>-v<SemVer>.<stage>
# [.<nnn>].zip``, the SemVer with ``+`` build metadata; the fixed documents), no separator, no leading dot, ``+`` or ``-``.
_NAME: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,254}")
_PREFIX: Final = re.compile(r"(?P<prefix>[a-z0-9]+(?:-[a-z0-9]+)*-v[0-9A-Za-z.+-]+)/")
_META: Final = re.compile(r"(?P<prefix>[a-z0-9]+(?:-[a-z0-9]+)*-v[0-9A-Za-z.+-]+?)\.meta\.zip")
_CHUNK: Final = 1 << 20
# The deposit documents besides the per-corpus datasheet copies (H.10.3; D-490).
_DOCUMENTS: Final = ("CHANGELOG.md", "README.md", DEPOSIT_METADATA)


class VerifyUnsupportedError(AgentProvError):
    """A level archive mode does not offer (``rederive``: a deposit is never extracted; exit 5)."""

    code = "verify.archive.unsupported"
    exit_code = 5


@dataclass
class DepositVerification:
    """The outcome of :func:`verify_deposit`: deposit-level findings and one :class:`VerifyReport` per corpus."""

    mode: str  # deposit | meta
    level: str
    release: bool
    findings: list[Finding] = field(default_factory=list)
    corpora: list[VerifyReport] = field(default_factory=list)
    counters: dict[str, int] = field(default_factory=dict)
    notices: list[str] = field(default_factory=list)

    def all_findings(self) -> list[Finding]:
        """Deposit findings, then each corpus's findings with path subjects prefixed by the corpus prefix."""
        out = list(self.findings)
        for report in self.corpora:
            prefix = f"{report.corpus_id}-v{report.corpus_version}/" if report.corpus_id else ""
            for finding in report.findings:
                subject = dict(finding.subject)
                if "path" in subject:
                    subject["path"] = prefix + subject["path"]
                out.append(Finding(finding.code, subject, finding.status, finding.level, finding.detail))
        return out

    @property
    def ok(self) -> bool:
        return not self.all_findings()

    def passed(self) -> bool:
        findings = self.all_findings()
        return not any(f.status == FAILED for f in findings) and not (self.release and findings)

    @property
    def exit_code(self) -> int:
        return 0 if self.passed() else 1

    def codes(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for finding in self.all_findings():
            out[finding.code] = out.get(finding.code, 0) + 1
        return dict(sorted(out.items()))


def is_archive_input(path: str | os.PathLike[str]) -> str | None:
    """``"deposit"`` for a directory holding ``DEPOSIT-MANIFEST.json``, ``"meta"`` for a ``*.meta.zip`` file, else
    ``None`` (a corpus tree). Nothing is followed: a link is neither."""
    target = Path(path)
    try:
        mode = os.lstat(target).st_mode
    except OSError:
        return None
    if stat.S_ISDIR(mode):
        try:
            inner = os.lstat(target / DEPOSIT_MANIFEST).st_mode
        except OSError:
            return None
        return "deposit" if stat.S_ISREG(inner) else None
    if stat.S_ISREG(mode) and target.name.endswith(".zip"):
        return "meta"
    return None


def _hash_file(directory: Path, name: str, limits: IngestLimits) -> tuple[str, str, int]:
    sha, md5, size = hashlib.sha256(), hashlib.md5(usedforsecurity=False), 0
    with open_evidence(directory, name, limits) as stream:
        while chunk := stream.read(_CHUNK):
            sha.update(chunk)
            md5.update(chunk)
            size += len(chunk)
    return "sha256:" + sha.hexdigest(), md5.hexdigest(), size


def _datasheet_name(entry: Mapping[str, Any]) -> str:
    """``DATASHEET-<corpus_id>.md``: the deposit copy of a corpus entry's datasheet (H.10.3)."""
    return f"DATASHEET-{entry.get('corpus_id')}.md"


class _Deposit:
    def __init__(self, directory: Path, *, level: str, release: bool, root_digests: Sequence[str],
                 package: PackageResources | None, limits: IngestLimits) -> None:
        self.directory = directory
        self.level = level
        self.release = release
        self.root_digests = list(root_digests)
        self.package = package
        self.limits = limits
        self.result = DepositVerification("deposit", level, release)
        # Per corpus entry, for the datasheet check after every corpus is read (D-620): the copy's name, the archived
        # DATASHEET.md (None: already reported) and the licence class of the archived corpus.json (or why it is unknown).
        self.sheets: list[tuple[str, bytes | None, LicenceClass | str]] = []

    def add(self, code: str, path: str, detail: str, status: str = FAILED) -> None:
        self.result.findings.append(Finding(code, {"path": path}, status, "deposit", detail[:300]))

    def manifest(self) -> Mapping[str, Any] | None:
        try:
            with open_evidence(self.directory, DEPOSIT_MANIFEST, IngestLimits()) as stream:
                document = strict_json_loads(stream.read(), IngestLimits())
        except (IngestError, OSError) as exc:
            code = exc.code if isinstance(exc, IngestError) else type(exc).__name__
            self.add("deposit.manifest.invalid", DEPOSIT_MANIFEST, f"the deposit manifest cannot be read ({code})")
            return None
        if isinstance(document, Mapping) and document.get("format") == INDEX_MANIFEST_FORMAT:
            self.add("deposit.manifest.invalid", DEPOSIT_MANIFEST, "an index deposit (package --index, D-947) holds no "
                     "corpus archive, so archive-mode verify does not apply; verify each part record's deposit with the "
                     "root digests COLLECTION-INDEX.json lists")
            return None
        if not isinstance(document, Mapping) or document.get("format") != DEPOSIT_MANIFEST_FORMAT:
            self.add("deposit.manifest.invalid", DEPOSIT_MANIFEST, f"not an {DEPOSIT_MANIFEST_FORMAT} document")
            return None
        for key in ("archives", "corpora", "documents"):
            if not isinstance(document.get(key), list) or not all(isinstance(e, Mapping) for e in document[key]):
                self.add("deposit.manifest.invalid", DEPOSIT_MANIFEST, f"{key} is not a list of objects")
                return None
        if not document["corpora"]:
            self.add("deposit.manifest.invalid", DEPOSIT_MANIFEST, "the deposit lists no corpus (nothing would be verified)")
            return None
        for entry in [*document["archives"], *document["documents"]]:
            name = entry.get("name")
            if not isinstance(name, str) or _NAME.fullmatch(name) is None or name == DEPOSIT_MANIFEST:
                self.add("deposit.manifest.invalid", DEPOSIT_MANIFEST, "an archive or document name is not a plain file name")
                return None
        if not isinstance(document.get("mixed_licence_classes"), bool):
            self.add("deposit.manifest.invalid", DEPOSIT_MANIFEST, "mixed_licence_classes is not a boolean")
            return None
        expected = sorted([*_DOCUMENTS, *(_datasheet_name(e) for e in document["corpora"])])
        if sorted(str(e["name"]) for e in document["documents"]) != expected:
            self.add("deposit.manifest.invalid", DEPOSIT_MANIFEST, "documents is not exactly README.md, CHANGELOG.md, "
                     "deposit-metadata.json and one DATASHEET-<corpus_id>.md per corpus (D-490)")
            return None
        return document

    def files(self, document: Mapping[str, Any]) -> None:
        expected = {DEPOSIT_MANIFEST} | {str(e["name"]) for e in [*document["archives"], *document["documents"]]}
        present: set[str] = set()
        try:
            with os.scandir(self.directory) as entries:
                for entry in entries:
                    if not entry.is_file(follow_symlinks=False):
                        self.add("deposit.unlisted", f"#{len(present)}", "an entry of the deposit directory is not a "
                                 "regular file (a link, a directory or a special file)")
                        continue
                    present.add(entry.name)
        except OSError as exc:
            self.add("deposit.unreadable", ".", f"the deposit directory cannot be listed ({type(exc).__name__})")
            return
        for name in sorted(present - expected):
            if _NAME.fullmatch(name):
                self.add("deposit.unlisted", name, "a file the deposit manifest does not list (closed world)")
            else:
                self.add("deposit.unlisted", "#unnamed", "a file the deposit manifest does not list (closed world)")
        for name in sorted(expected - present):
            self.add("deposit.missing", name, "a file the deposit manifest lists is absent")
        for entry in [*document["archives"], *document["documents"]]:
            name = str(entry["name"])
            if name not in present:
                continue
            try:
                sha, md5, size = _hash_file(self.directory, name, self.limits)
            except (IngestError, OSError) as exc:
                code = exc.code if isinstance(exc, IngestError) else type(exc).__name__
                self.add("deposit.unreadable", name, f"the file cannot be read ({code})")
                continue
            self.result.counters["files_hashed"] = self.result.counters.get("files_hashed", 0) + 1
            if entry.get("bytes") != size:
                self.add("deposit.bytes", name, "the size differs from the deposit manifest")
            if entry.get("sha256") != sha:
                self.add("deposit.sha256", name, "the sha256 differs from the deposit manifest")
            if entry.get("md5") != md5:
                self.add("deposit.md5", name, "the md5 differs from the deposit manifest")

    def corpus(self, document: Mapping[str, Any], entry: Mapping[str, Any]) -> None:
        prefix = entry.get("member_prefix")
        match = _PREFIX.fullmatch(prefix) if isinstance(prefix, str) else None
        if match is None or prefix != f"{entry.get('corpus_id')}-v{entry.get('corpus_version')}/":
            self.add("deposit.manifest.invalid", DEPOSIT_MANIFEST, "a corpus's member prefix is not <corpus_id>-v<version>/")
            self.sheets.append((_datasheet_name(entry), None, "a corpus entry was not read"))
            return
        assert isinstance(prefix, str)
        names = list(dict.fromkeys(n for n in entry.get("archives") or () if isinstance(n, str)))  # twice: run()
        listed = {str(a["name"]): a for a in document["archives"]}
        for name in names:
            if name not in listed or listed[name].get("corpus_id") != entry.get("corpus_id"):
                self.add("deposit.manifest.invalid", name, "a corpus names an archive the deposit lists for another corpus")
            elif not name.startswith(prefix.rstrip("/") + "."):
                self.add("deposit.manifest.invalid", name, "a corpus names an archive without its <corpus_id>-v<version>. "
                         "name prefix")
        names = [n for n in names if n in listed and _NAME.fullmatch(n)]
        with ArchiveSet(self.directory, names, prefix, release=self.release, limits=self.limits) as archives:
            report = verify_corpus(level=self.level, release=self.release, reader=ArchiveCorpusReader(archives),
                                   source=ArchiveSource(archives), package=self.package, deposit_manifest=True)
            if archives.advisory is not None:
                self.result.notices.append("an archive was read below CPython 3.14.8 (dev mode; G.3.8)")
            for name in names:
                self.archive(archives, listed[name], prefix)
            self.sheets.append(self.sealed_datasheet(entry, ArchiveCorpusReader(archives)))
        self.result.corpora.append(report)
        if report.root_digest != entry.get("root_digest"):
            self.add("deposit.root_digest", prefix.rstrip("/"), "the root digest of the archived checksums.sha256 differs "
                     "from the deposit manifest's")
        if report.content_digest != entry.get("content_digest"):
            self.add("deposit.content_digest", prefix.rstrip("/"), "the archived corpus.json's content digest differs from "
                     "the deposit manifest's")
        recorded = entry.get("coverage")
        coverage: Mapping[str, Any] = recorded if isinstance(recorded, Mapping) else {}
        if coverage.get("files") != report.counters.get("files_listed", -2) + 1:
            self.add("deposit.coverage", prefix.rstrip("/"), "the coverage differs from the archived checksums.sha256")

    def sealed_datasheet(self, entry: Mapping[str, Any],
                         reader: ArchiveCorpusReader) -> tuple[str, bytes | None, LicenceClass | str]:
        """The archived ``DATASHEET.md`` and the licence class of the archived ``corpus.json`` of one corpus: both are
        covered by the archived checksums and the root digest, the deposit manifest is not (D-490, D-620)."""
        name = _datasheet_name(entry)
        try:
            sealed: bytes | None = reader.read_bytes(DATASHEET)
        except CorpusReadError as exc:
            self.add("deposit.document.datasheet", name, f"the archived {DATASHEET} cannot be read ({exc.code}), so the "
                     "copy cannot be compared")
            sealed = None
        try:
            manifest = reader.manifest()
            cls: LicenceClass | str = licence_class(manifest) if manifest is not None else "no corpus.json"
        except AgentProvError as exc:
            cls = exc.code
        except (AttributeError, TypeError):  # a licences block of the wrong shape (licence_class expects a valid manifest)
            cls = "licences.malformed"
        return name, sealed, cls

    def datasheets(self, document: Mapping[str, Any]) -> None:
        """Each deposit copy ``DATASHEET-<corpus_id>.md`` against the copy rebuilt from the archived ``DATASHEET.md``
        (D-490), compared in full (D-620): with mixed licence classes the builder's note names the corpus's own class and
        the deposit's classes, both recomputed from the archived ``corpus.json`` files
        (:func:`agentprov.release.metadata.datasheet_copy`, the builder's own function). A copy that is absent or
        unreadable is already reported by :meth:`files`."""
        known = [cls for _, _, cls in self.sheets if isinstance(cls, LicenceClass)]
        unknown = sorted({cls for _, _, cls in self.sheets if isinstance(cls, str)})
        classes = sorted(set(known))
        mixed = len(classes) > 1
        if not unknown and document["mixed_licence_classes"] != mixed:
            self.add("deposit.manifest.invalid", DEPOSIT_MANIFEST, "mixed_licence_classes differs from the licence "
                     "classes of the archived corpus.json files (D-620)")
        for name, sealed, cls in self.sheets:
            if sealed is None:
                continue
            try:
                with open_evidence(self.directory, name, self.limits) as stream:
                    copy = stream.read()
            except (IngestError, OSError):
                continue
            if unknown:
                self.add("deposit.document.datasheet", name, "the licence class of an archived corpus.json cannot be "
                         f"read ({', '.join(unknown)}), so the copy cannot be rebuilt and compared")
                continue
            assert isinstance(cls, LicenceClass)
            if copy != datasheet_copy(sealed, cls, classes, mixed):
                what = "followed by the deposit note of a mixed-licence-class deposit" if mixed else "byte for byte"
                self.add("deposit.document.datasheet", name, f"the copy is not the archived {DATASHEET} {what}, as "
                         "rebuilt from the archived corpus.json licence classes")

    def archive(self, archives: ArchiveSet, entry: Mapping[str, Any], prefix: str) -> None:
        name = str(entry["name"])
        members = archives.by_archive.get(name, [])
        listing: list[tuple[str, str]] = []
        for member in members:
            try:
                digest, _ = archives.digest(member.label)
            except (IngestError, FileNotFoundError):
                continue  # reported by the checksums level
            listing.append((digest, prefix + member.label))
            stage, _shard = _stage_of(member.label)
            if stage != entry.get("stage"):
                self.add("deposit.archive.stage", name, "a member does not belong to the archive's stage")
        self.result.counters["archives"] = self.result.counters.get("archives", 0) + 1
        self.result.counters["members"] = self.result.counters.get("members", 0) + len(members)
        if entry.get("n_members") != len(members):
            self.add("deposit.archive.members", name, "n_members differs from the archive")
        if entry.get("uncompressed_bytes") != sum(m.size for m in members):
            self.add("deposit.archive.members", name, "uncompressed_bytes differs from the archive")
        if len(listing) == len(members) and entry.get("members_sha256") != members_sha256(listing):
            self.add("deposit.archive.members_sha256", name, "members_sha256 does not recompute from the members")

    def claims(self, document: Mapping[str, Any]) -> None:
        """Every listed archive belongs to exactly one corpus: an archive no corpus names is never opened, so its members
        (a second ``corpus.json``, say) would pass unchecked; one named twice, or listed twice, is ambiguous."""
        claimed: dict[str, int] = {}
        for entry in document["corpora"]:
            for name in entry.get("archives") or ():
                if isinstance(name, str):
                    claimed[name] = claimed.get(name, 0) + 1
        listed: dict[str, int] = {}
        for entry in document["archives"]:
            listed[str(entry["name"])] = listed.get(str(entry["name"]), 0) + 1
        for name in sorted(listed):
            if listed[name] > 1:
                self.add("deposit.archive.orphan", name, "the deposit manifest lists the archive more than once")
            elif claimed.get(name, 0) == 0:
                self.add("deposit.archive.orphan", name, "no corpus of the deposit names the archive, so it is never "
                         "verified")
            elif claimed[name] > 1:
                self.add("deposit.archive.orphan", name, "more than one corpus entry names the archive")

    def run(self) -> DepositVerification:
        document = self.manifest()
        if document is None:
            return self.result
        self.files(document)
        for entry in document["corpora"]:
            self.corpus(document, entry)
        self.datasheets(document)
        self.claims(document)
        computed = {r.root_digest for r in self.result.corpora if r.root_digest is not None}
        for given in self.root_digests:
            if given not in computed:
                self.add("root_digest.mismatch", DEPOSIT_MANIFEST, "a published root digest matches no corpus of the "
                         "deposit (D-39)")
        if self.release:  # D-641: every corpus is anchored by its own published root digest, never by the deposit
            for report in self.result.corpora:  # manifest (circular, D-620), so one digest no longer covers the rest
                if report.root_digest is None or report.root_digest not in self.root_digests:
                    self.add("root_digest.missing", report.corpus_id or DEPOSIT_MANIFEST, "no published root digest "
                             "(--root-digest) anchors this corpus of the deposit; release mode needs one per corpus "
                             "(D-641)")
        if self.root_digests:
            self.result.counters["root_digests_compared"] = len(self.root_digests)
        return self.result


def verify_deposit(
    path: str | os.PathLike[str],
    *,
    level: str = "chain",
    release: bool = False,
    root_digests: Sequence[str] = (),
    package: PackageResources | None = None,
    limits: IngestLimits = ARCHIVE_LIMITS,
) -> DepositVerification:
    """Verify a deposit directory or a lone meta archive extraction-free (see the module docstring)."""
    if level == "rederive":
        raise VerifyUnsupportedError("archive mode verifies at the checksums or chain level; rederive needs a sealed tree "
                                     "(a deposit is never extracted, H.10.3(1))")
    if level not in ("checksums", "chain"):
        raise VerifyUsageError("the level is checksums, chain or rederive")
    for digest in root_digests:
        if not isinstance(digest, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None:
            raise VerifyUsageError("--root-digest is sha256:<64 lower-case hex>")
    kind = is_archive_input(path)
    if kind is None:
        raise VerifyUsageError("not a deposit directory (with DEPOSIT-MANIFEST.json) or a .meta.zip archive")
    if release and not root_digests:
        # D-620 (amends D-39 item 3): DEPOSIT-MANIFEST.json lies beside the archives it describes and anchors nothing.
        what = "a deposit directory" if kind == "deposit" else "a lone meta archive"
        raise VerifyUsageError(f"release-mode verification of {what} needs --root-digest sha256:... (the root digest "
                               "published outside the deposit; the deposit manifest anchors nothing; D-39, D-620)")
    require_patched_for_archive(release=release)  # AD-16: before any archive is opened (exit 3 in release mode)
    target = Path(path)
    if kind == "deposit":
        return _Deposit(target, level=level, release=release, root_digests=root_digests, package=package,
                        limits=limits).run()
    match = _META.fullmatch(target.name)
    result = DepositVerification("meta", level, release)
    if match is None:
        raise VerifyUsageError("a lone archive is verified only as <corpus_id>-v<version>.meta.zip")
    prefix = match["prefix"] + "/"
    with ArchiveSet(target.parent, [target.name], prefix, release=release, limits=limits) as archives:
        report = verify_corpus(level=level, release=release, root_digests=root_digests,
                               reader=ArchiveCorpusReader(archives), source=ArchiveSource(archives), package=package,
                               absent_unverified=True, deposit_manifest=False)
    result.corpora.append(report)
    absent = sum(1 for f in report.findings if f.code == "archive.not_present")
    result.counters["not_present"] = absent
    result.notices.append(f"a lone meta archive: {absent} check(s) need files of the other archives and are unverified, "
                          "never passed (D-38)")
    return result
