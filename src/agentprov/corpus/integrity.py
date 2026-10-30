"""Checksums, set digests, the content digest and the root digest of a corpus (HL H.2.11, H.5.3, H.5.4, H.5.5).

Part 1 (phase 11, U1): the digest functions of H.5.4 and the ``checksums`` verification level in **tree mode**.

* :func:`set_digest` is H.2.11's ``"sha256:" + sha256("".join(sorted(f"{a} {b}\\n" for a, b in pairs)))``.
* :func:`content_digest` is the JCS digest of the manifest without ``content_digest``, ``release`` and ``sealed``: it does
  not depend on the release date or on formatting.
* :func:`root_digest` is the sha256 of the bytes of ``checksums.sha256``. It fingerprints a release tree and never
  appears inside the corpus.
* :func:`write_checksums` lists **every** regular file of the tree but itself, sorted bytewise by path, in ``sha256sum``
  format (``<64 hex>  <path>\\n``). It refuses a tree that is not closed-world (a stray file such as ``.DS_Store``, a
  link, an empty directory, ``raw/tmp/``; H.1.5(4)) and a tree that already has a ``checksums.sha256`` (see below).
* :func:`verify_checksums` checks that every listed file exists and matches and, in the closed world (the default), that
  nothing else exists (H.5.3, H.5.5 level ``checksums``). Every path is checked against the H.1.2/H.1.3 grammar
  (:func:`agentprov.corpus.layout.classify_relpath`) **before** it is opened, and is opened through
  :func:`agentprov.ingest.paths.open_evidence` (no link is followed, regular files only). Paths read from the
  checksums file are data; a finding never repeats one the grammar refused, it names its line instead.

**Sealed trees and the write guard.** H.5.3(4) writes the checksums *after* ``corpus.json`` holds ``"sealed": true``,
so :func:`agentprov.corpus.layout.assert_writable` would refuse the tree being sealed. :func:`write_checksums` therefore
guards the **parent** directory with ``assert_writable`` (no enclosing sealed corpus) and refuses a tree that already
has a ``checksums.sha256``: a sealed corpus always has one, so a sealed corpus is never rewritten.

**Extension points** (phase 11, U4). :class:`ChecksumSource` is the protocol :func:`verify_checksum_source` reads
through; :class:`TreeSource` is the tree-mode implementation and :class:`agentprov.corpus.archive.ArchiveSource` the
archive-mode one (deposit zips read extraction-free, D-38). The ``chain`` and ``rederive`` levels of H.5.5 live in
:mod:`agentprov.corpus.verify`; :func:`verify_corpus` here is H.8.5's name for its entry point.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any, Final, Protocol

from agentprov.corpus.index import check_corpus_json
from agentprov.corpus.layout import (
    CHECKSUMS,
    SealedCorpusError,
    TreeFinding,
    assert_writable,
    classify_relpath,
    iter_tree,
)
from agentprov.errors import AgentProvError, IngestError
from agentprov.ingest.paths import STORED_OBJECT_LIMITS, RootHandle, open_evidence, open_root
from agentprov.io.atomic import atomic_write_bytes
from agentprov.io.canonical import is_sha256_hex, jcs_bytes

__all__ = [
    "CONTENT_DIGEST_EXCLUDED",
    "VERIFY_LEVELS",
    "ChecksumEntry",
    "ChecksumFinding",
    "ChecksumReport",
    "ChecksumSource",
    "IntegrityError",
    "TreeSource",
    "content_digest",
    "file_sha256",
    "parse_checksums",
    "root_digest",
    "set_digest",
    "verify_checksum_source",
    "verify_checksums",
    "verify_corpus",
    "write_checksums",
]

#: The levels of ``agentprov verify`` (H.5.5); this module implements ``checksums`` (tree mode).
VERIFY_LEVELS: Final = ("checksums", "chain", "rederive")
#: Manifest members that the content digest leaves out (H.5.4).
CONTENT_DIGEST_EXCLUDED: Final = frozenset({"content_digest", "release", "sealed"})
_CHUNK: Final = 1 << 20
#: A checksums line is 64 hex + 2 spaces + a path of at most 200 characters + LF.
_MAX_LINE: Final = 64 + 2 + 200 + 1


class IntegrityError(AgentProvError):
    """A digest or checksums operation was refused or its input is malformed (``corpus.integrity.*``)."""

    code = "corpus.integrity.invalid"
    exit_code = 1


# ------------------------------------------------------------------------------------------------ digests
def set_digest(pairs: Iterable[tuple[str, str]]) -> str:
    """``"sha256:" + sha256("".join(sorted(f"{a} {b}\\n" for a, b in pairs)))`` (H.2.11), lines sorted bytewise.

    ``a`` (an execution id or an object digest) may not contain a space or a line break, ``b`` (a digest or a
    disposition) may not contain a line break, so every pair is exactly one line. Duplicate pairs are kept, as the
    definition does. ``ValueError`` for a malformed pair.
    """
    lines: list[bytes] = []
    for a, b in pairs:
        if not isinstance(a, str) or not isinstance(b, str) or not a or " " in a or "\n" in a or "\r" in a or "\n" in b or "\r" in b:
            raise ValueError("a set_digest pair is two strings without line breaks, the first without spaces")
        lines.append(f"{a} {b}\n".encode())
    digest = hashlib.sha256()
    for line in sorted(lines):
        digest.update(line)
    return "sha256:" + digest.hexdigest()


def content_digest(manifest: Mapping[str, Any]) -> str:
    """``"sha256:" + sha256(JCS(manifest without content_digest, release, sealed))`` (H.5.4).

    The manifest must be corpus-layer JSON (no floating-point number, H.1.4(3)); ``ValueError`` otherwise.
    """
    if not isinstance(manifest, Mapping):
        raise ValueError("a manifest is a JSON object")
    body = {k: v for k, v in manifest.items() if k not in CONTENT_DIGEST_EXCLUDED}
    check_corpus_json(body)
    return "sha256:" + hashlib.sha256(jcs_bytes(body)).hexdigest()


def _hash_stream(stream: IO[bytes]) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    while chunk := stream.read(_CHUNK):
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def file_sha256(root: str | os.PathLike[str], label: str) -> str:
    """The hex sha256 of the file ``label`` below ``root``, opened without following a link (G.3.6)."""
    with open_evidence(root, label, STORED_OBJECT_LIMITS, allow_hardlinks=True) as stream:
        return _hash_stream(stream)[0]


def root_digest(root: str | os.PathLike[str]) -> str:
    """``"sha256:" + sha256(bytes(checksums.sha256))`` (H.5.4). It is published outside the corpus, never inside it."""
    try:
        return "sha256:" + file_sha256(root, CHECKSUMS)
    except FileNotFoundError:
        raise IntegrityError("the corpus has no checksums.sha256", code="corpus.integrity.no_checksums") from None
    except IngestError as exc:
        raise IntegrityError(f"checksums.sha256 cannot be opened ({exc.code})", code="corpus.integrity.unreadable") from None


# ------------------------------------------------------------------------------------------------ checksums.sha256
@dataclass(frozen=True, slots=True)
class ChecksumEntry:
    """One line of ``checksums.sha256``: the bare hex digest and the corpus-relative path (grammar-checked)."""

    sha256: str
    path: str

    def line(self) -> bytes:
        return f"{self.sha256}  {self.path}\n".encode("ascii")


@dataclass(frozen=True, slots=True)
class ChecksumFinding:
    """One failed check. ``path`` is a grammar-checked corpus path or ``#<line>`` (a line whose path was refused).

    Codes: ``checksums.absent`` (no ``checksums.sha256``), ``checksums.malformed`` (a line that is not
    ``<64 hex>  <path>``, the file not LF-terminated, not sorted, or a duplicate path), ``checksums.path_invalid`` (a
    listed path outside the H.1.2 grammar, or the checksums file listing itself), ``checksums.missing`` (listed, not
    present), ``checksums.mismatch`` (digest differs), ``checksums.unreadable`` (a link, a special file, over a limit),
    ``checksums.unlisted`` (present, not listed: closed world) and the ``corpus.tree.*`` codes of the tree walk
    (:class:`agentprov.corpus.layout.TreeFinding`), also closed-world findings.
    """

    code: str
    path: str
    detail: str = ""


@dataclass(frozen=True, slots=True)
class ChecksumReport:
    """The result of the ``checksums`` level: how many files were listed and matched, and every finding (sorted)."""

    level: str
    closed_world: bool
    listed: int
    matched: int
    findings: tuple[ChecksumFinding, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        """True only when every requested check passed (H.5.5: ``verify`` exits 0 only then)."""
        return not self.findings

    def codes(self) -> dict[str, int]:
        """Findings counted by code (sorted)."""
        out: dict[str, int] = {}
        for finding in self.findings:
            out[finding.code] = out.get(finding.code, 0) + 1
        return dict(sorted(out.items()))


def parse_checksums(data: bytes) -> tuple[list[ChecksumEntry], list[ChecksumFinding]]:
    """Parse ``checksums.sha256`` strictly (H.5.3): ASCII, ``<64 lower-case hex><2 spaces><path>\\n`` per line, sorted
    bytewise by path, unique paths, every path in the H.1.2 grammar and not ``checksums.sha256`` itself.

    Returns the well-formed entries and the findings; a refused path is reported by line number, never repeated.
    """
    entries: list[ChecksumEntry] = []
    findings: list[ChecksumFinding] = []
    if data and not data.endswith(b"\n"):
        findings.append(ChecksumFinding("checksums.malformed", "#eof", "the file does not end with LF"))
    lines = data.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    previous: bytes | None = None
    for number, raw in enumerate(lines, start=1):
        where = f"#{number}"
        if len(raw) > _MAX_LINE or len(raw) < 67 or raw[64:66] != b"  " or b"\r" in raw:
            findings.append(ChecksumFinding("checksums.malformed", where, "not '<64 hex>  <path>'"))
            continue
        try:
            digest, path = raw[:64].decode("ascii"), raw[66:].decode("ascii")
        except UnicodeDecodeError:
            findings.append(ChecksumFinding("checksums.malformed", where, "not ASCII"))
            continue
        if not is_sha256_hex(digest):
            findings.append(ChecksumFinding("checksums.malformed", where, "the digest is not 64 lower-case hex digits"))
            continue
        if path == CHECKSUMS or classify_relpath(path) is None:
            findings.append(ChecksumFinding("checksums.path_invalid", where, "the path is not a file of the H.1.2 tree"))
            continue
        encoded = path.encode("ascii")
        if previous is not None and encoded <= previous:
            findings.append(ChecksumFinding(
                "checksums.malformed", where, "duplicate path" if encoded == previous else "lines are not sorted by path"))
            continue
        previous = encoded
        entries.append(ChecksumEntry(digest, path))
    return entries, findings


class ChecksumSource(Protocol):
    """What the ``checksums`` level reads: a listing of the files present and a no-follow opener (tree or archive)."""

    #: Why ``checksums.sha256`` was refused (an ``IngestError`` code or an ``OSError`` type name), else ``None``.
    checksums_refused: str | None

    def read_checksums(self) -> bytes | None:
        """The bytes of ``checksums.sha256``, or ``None`` when it is absent or refused (a link, a special file, over a
        limit: :attr:`checksums_refused` then says why). Never raises for a refused file, so every caller reports it."""
        ...

    def present(self) -> tuple[list[str], list[ChecksumFinding]]:
        """Every file present but ``checksums.sha256`` (grammar-admitted labels), and the closed-world findings."""
        ...

    def open(self, path: str) -> IO[bytes]:
        """Open a grammar-checked path for reading; ``FileNotFoundError`` when absent, ``IngestError`` when refused."""
        ...


class TreeSource:
    """A corpus tree on disk (H.5.5 tree mode): listed with :func:`agentprov.corpus.layout.iter_tree`, opened with
    :func:`agentprov.ingest.paths.open_evidence` (no link followed; hard links admitted, D-32)."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root)
        self._handle: RootHandle | None = None
        self.checksums_refused: str | None = None

    def __enter__(self) -> TreeSource:
        self._handle = open_root(self.root)
        return self

    def __exit__(self, *exc: object) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    def read_checksums(self) -> bytes | None:
        self.checksums_refused = None
        try:
            with self.open(CHECKSUMS) as stream:
                return stream.read()
        except FileNotFoundError:
            return None
        except IngestError as exc:  # a link, a special file, over STORED_OBJECT_LIMITS: a finding, never a crash
            self.checksums_refused = exc.code
            return None
        except OSError as exc:
            self.checksums_refused = type(exc).__name__
            return None

    def present(self) -> tuple[list[str], list[ChecksumFinding]]:
        scan = iter_tree(self.root)
        labels = [label for label in scan.labels() if label != CHECKSUMS]
        return labels, [_tree_finding(f) for f in scan.findings]

    def open(self, path: str) -> IO[bytes]:
        root: RootHandle | Path = self._handle if self._handle is not None else self.root
        return open_evidence(root, path, STORED_OBJECT_LIMITS, allow_hardlinks=True)


def _tree_finding(finding: TreeFinding) -> ChecksumFinding:
    return ChecksumFinding(finding.code, finding.label, finding.detail)


def verify_checksum_source(
    source: ChecksumSource,
    *,
    closed_world: bool = True,
    on_match: Callable[[str, str, int], None] | None = None,
) -> ChecksumReport:
    """The ``checksums`` level over any :class:`ChecksumSource` (see :func:`verify_checksums`). ``on_match(path, hex,
    size)`` is called for every listed file whose bytes matched (the ``chain`` level reuses the digests: a raw object
    whose listed digest equals its address need not be read again)."""
    data = source.read_checksums()
    entries: list[ChecksumEntry]
    findings: list[ChecksumFinding]
    if data is None:
        if source.checksums_refused is None:
            return ChecksumReport("checksums", closed_world, 0, 0, (ChecksumFinding("checksums.absent", CHECKSUMS),))
        # Refused, not absent: nothing listed can be checked, but the closed-world findings (the link itself) still are.
        entries, findings = [], [ChecksumFinding("checksums.unreadable", CHECKSUMS, source.checksums_refused)]
    else:
        entries, findings = parse_checksums(data)
    matched = 0
    for entry in entries:
        try:
            with source.open(entry.path) as stream:
                digest, size = _hash_stream(stream)
        except FileNotFoundError:
            findings.append(ChecksumFinding("checksums.missing", entry.path))
            continue
        except IngestError as exc:
            findings.append(ChecksumFinding("checksums.unreadable", entry.path, exc.code))
            continue
        except OSError as exc:
            findings.append(ChecksumFinding("checksums.unreadable", entry.path, type(exc).__name__))
            continue
        if digest == entry.sha256:
            matched += 1
            if on_match is not None:
                on_match(entry.path, digest, size)
        else:
            findings.append(ChecksumFinding("checksums.mismatch", entry.path))
    if closed_world:
        present, tree_findings = source.present()
        listed = {e.path for e in entries}
        findings.extend(ChecksumFinding("checksums.unlisted", label) for label in present if label not in listed)
        findings.extend(tree_findings)
    findings.sort(key=lambda f: (f.path.encode("utf-8"), f.code))
    return ChecksumReport("checksums", closed_world, len(entries), matched, tuple(findings))


def verify_corpus(root: str | os.PathLike[str], *, level: str = "chain", jobs: int = 0, sample: int | None = None,
                  seed: str | None = None, **options: Any) -> Any:
    """H.8.5's entry point: :func:`agentprov.corpus.verify.verify_corpus` (tree mode; every level of H.5.5)."""
    from agentprov.corpus.verify import verify_corpus as _verify

    return _verify(root, level=level, jobs=jobs, sample=sample, seed=seed, **options)


def verify_checksums(root: str | os.PathLike[str], *, closed_world: bool = True) -> ChecksumReport:
    """H.5.5 level ``checksums`` in tree mode: every listed file matches and, with ``closed_world`` (the default), no
    file is unlisted and the tree holds nothing outside the H.1.2 grammar (no dotfile, link, special file, empty
    directory or ``raw/tmp/``). Never follows a link; nothing is written."""
    with TreeSource(root) as source:
        return verify_checksum_source(source, closed_world=closed_world)


def _iter_entries(root: Path) -> Iterator[ChecksumEntry]:
    scan = iter_tree(root)
    if scan.findings:
        codes = ", ".join(sorted({f.code for f in scan.findings}))
        raise IntegrityError(f"the tree is not closed-world ({codes}); refusing to list it (H.1.5(4))",
                             code="corpus.integrity.not_closed")
    with TreeSource(root) as source:
        for label in scan.labels():
            if label == CHECKSUMS:
                continue
            with source.open(label) as stream:
                yield ChecksumEntry(_hash_stream(stream)[0], label)


def write_checksums(root: str | os.PathLike[str]) -> Path:
    """Write ``checksums.sha256`` for the tree at ``root`` and return its path (H.5.3).

    Every regular file but ``checksums.sha256`` is listed, sorted bytewise by path. Refused (``IntegrityError``, exit 1)
    when the tree is not closed-world; refused (``SealedCorpusError``, exit 4) inside an enclosing sealed corpus, and when
    ``checksums.sha256`` already exists (a sealed corpus always has one). The write is atomic.
    """
    path = Path(root)
    assert_writable(path.parent)
    target = path / CHECKSUMS
    if os.path.lexists(target):
        raise SealedCorpusError("checksums.sha256 already exists; a corpus is checksummed once, when it is sealed",
                                code="corpus.sealed.checksums_exist")
    entries = sorted(_iter_entries(path), key=lambda e: e.path.encode("ascii"))
    atomic_write_bytes(target, b"".join(e.line() for e in entries))
    return target
