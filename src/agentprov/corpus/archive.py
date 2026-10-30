"""Archive mode: a corpus read from deposit zips, extraction-free (HL H.5.5 archive mode, H.10.3(1); G.3.5; D-38).

The archives of one corpus are an image of its sealed tree: every member is ``<corpus_id>-v<version>/<corpus path>``
(H.10.3(1), D-42 item 9). :class:`ArchiveSet` opens them through the G.3.5 gate of :mod:`agentprov.ingest.archives`
(size pre-check, warnings as errors, member count, prefix and overlap checks, the per-member gate) and maps each member to
its corpus label. **Nothing is written to the filesystem**: members are streamed with ``ZipFile.open`` (which stops at
the declared size and checks the CRC) and hashed in memory.

* :class:`ArchiveSource` is the archive-mode :class:`~agentprov.corpus.integrity.ChecksumSource`: the closed world is the
  **union** of the archives' members (a member outside the prefix, a name the H.1.2 grammar refuses, a member the gate
  rejected and a label present in two archives are findings).
* :class:`ArchiveCorpusReader` is a :class:`~agentprov.corpus.reader.CorpusReader` whose files are archive members, so the
  ``chain`` level runs unchanged over a deposit (HL-T9).

Member names are labels, never paths (G.3.6): the prefix is stripped, the rest must pass
:func:`agentprov.corpus.layout.classify_relpath`; a refused name is reported by archive and member index, never echoed.

**Where it runs** (D-38). G.3.5 places archive reading in a T1 worker. ``verify`` reads the archives in the CLI process
with the same ingest gate and limits instead: adding a T1 job kind belongs to phase 12 (``io/workers.py``,
``worker.py``). Reading stays bounded: the pre-check bounds what ``zipfile`` allocates for the central directory, members
are streamed in 64 KiB chunks and never held whole, and the declared-size stop and CRC check are ``zipfile``'s own.
"""

from __future__ import annotations

import hashlib
import io
import zlib
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any, Final

from agentprov.corpus.integrity import ChecksumFinding
from agentprov.corpus.layout import CHECKSUMS, classify_relpath
from agentprov.corpus.reader import SEALED, CorpusReader, CorpusReadError
from agentprov.envinfo import InterpreterAdvisory
from agentprov.errors import IngestError
from agentprov.ingest.archives import OpenedZip, ZipMember, iter_zip_members, open_zip
from agentprov.ingest.limits import GIB, IngestLimits
from agentprov.ingest.paths import open_evidence

__all__ = [
    "ARCHIVE_LIMITS",
    "ArchiveCorpusReader",
    "ArchiveMember",
    "ArchiveSet",
    "ArchiveSource",
    "member_digest",
]

#: The deposit format's own member bound (D-42 item 9: no ZIP64, so a member stays below 2**31 - 1 bytes; the builder
#: refuses larger files). The G.3.2 default of 256 MiB would refuse a legitimate raw object of a deposit.
_DEPOSIT_MEMBER_BYTES: Final = int(((1 << 31) - 1) / 1.05) - 1
#: The ingest limits of archive mode (D-38): the G.3.2 defaults, with ``max_member_bytes`` raised to the deposit format's
#: bound and ``max_total_bytes`` to 64 GiB per archive (members are streamed and hashed, never held; the ratio cap of
#: G.3.2 still bounds what one member may expand to).
ARCHIVE_LIMITS: Final = IngestLimits().replace(max_member_bytes=_DEPOSIT_MEMBER_BYTES, max_total_bytes=64 * GIB)
_CHUNK: Final = 1 << 20


@dataclass(frozen=True, slots=True)
class ArchiveMember:
    """One member of one archive mapped to a corpus label."""

    archive: str  # the archive's file name
    index: int  # the member's central-directory index (how a refused member is named)
    name: str  # the member name as recorded: data, never shown unescaped
    label: str  # the corpus label (prefix stripped, grammar-checked)
    size: int
    crc32: int


class _MemberStream(io.RawIOBase):
    """A read-only stream over a member's chunks; records the digest and size once the member was read to its end."""

    def __init__(self, chunks: Iterator[bytes], on_end: Any) -> None:
        self._chunks = chunks
        self._buffer = b""
        self._sha = hashlib.sha256()
        self._size = 0
        self._done = False
        self._on_end = on_end

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: Any) -> int:
        while not self._buffer and not self._done:
            try:
                chunk = next(self._chunks)
            except StopIteration:
                self._done = True
                self._on_end(self._sha.hexdigest(), self._size)
                break
            self._sha.update(chunk)
            self._size += len(chunk)
            self._buffer = chunk
        n = min(len(buffer), len(self._buffer))
        buffer[:n] = self._buffer[:n]
        self._buffer = self._buffer[n:]
        return n


class ArchiveSet:
    """The archives of one corpus, opened through the G.3.5 gate (see the module docstring).

    ``prefix`` is ``"<corpus_id>-v<version>/"``. ``findings`` holds what the closed world and the gate refused (codes
    ``archive.*`` and the gate's ``ingest.archive.*``); a structural defect that rejects a whole archive is a finding
    with the archive's name as its path, and that archive contributes no member.
    """

    def __init__(self, directory: Path, names: Sequence[str], prefix: str, *, release: bool,
                 limits: IngestLimits = ARCHIVE_LIMITS) -> None:
        self.directory = Path(directory)
        self.prefix = prefix
        self.limits = limits
        self.findings: list[ChecksumFinding] = []
        self.members: dict[str, tuple[OpenedZip, ZipMember, ArchiveMember]] = {}
        self.by_archive: dict[str, list[ArchiveMember]] = {}
        self.advisory: InterpreterAdvisory | None = None
        self._handles: list[Any] = []
        self._opened: list[OpenedZip] = []
        self._digests: dict[str, tuple[str, int]] = {}
        self._seen_twice: set[str] = set()
        try:
            for name in names:
                self._open(name, release)
        except BaseException:
            self.close()
            raise

    def _open(self, name: str, release: bool) -> None:
        self.by_archive[name] = []
        try:
            handle = open_evidence(self.directory, name, self.limits)
        except FileNotFoundError:
            self.findings.append(ChecksumFinding("archive.missing", name, "the archive is not in the deposit"))
            return
        except (IngestError, OSError) as exc:
            code = exc.code if isinstance(exc, IngestError) else type(exc).__name__
            self.findings.append(ChecksumFinding("archive.unreadable", name, code))
            return
        self._handles.append(handle)
        try:
            opened = open_zip(handle, self.limits, release=release)
        except IngestError as exc:
            self.findings.append(ChecksumFinding(exc.code, name, "the archive is rejected whole (G.3.5)"))
            return
        self._opened.append(opened)
        if opened.advisory is not None:
            self.advisory = opened.advisory
        for finding in opened.findings:
            if finding.code == "ingest.archive.trailing":
                self.findings.append(ChecksumFinding("archive.trailing", name, "bytes after the end record"))
        for member in iter_zip_members(opened, None, self.limits):
            where = f"{name}#{member.index}"
            if member.disposition != "selected":
                self.findings.append(ChecksumFinding(member.code or "archive.member.rejected", where,
                                                     "the member is rejected by the G.3.5 gate"))
                continue
            label = member.label or ""
            if not label.startswith(self.prefix):
                self.findings.append(ChecksumFinding("archive.member.prefix", where,
                                                     "the member is not under the corpus prefix"))
                continue
            relative = label[len(self.prefix):]
            if classify_relpath(relative) is None:
                self.findings.append(ChecksumFinding("archive.member.path", where,
                                                     "the member name is not a file of the H.1.2 tree"))
                continue
            if relative in self.members:
                self._seen_twice.add(relative)
                self.findings.append(ChecksumFinding("archive.member.duplicate", relative,
                                                     "the label is a member of more than one archive"))
                continue
            entry = ArchiveMember(name, member.index, member.raw_name, relative, member.file_size, member.crc32)
            self.members[relative] = (opened, member, entry)
            self.by_archive[name].append(entry)

    def close(self) -> None:
        for opened in self._opened:
            opened.close()
        for handle in self._handles:
            handle.close()
        self._opened, self._handles = [], []

    def __enter__(self) -> ArchiveSet:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -------------------------------------------------------------------------------------- access
    def labels(self) -> list[str]:
        return sorted(self.members, key=lambda label: label.encode("ascii"))

    def has(self, label: str) -> bool:
        return label in self.members and label not in self._seen_twice

    def size(self, label: str) -> int:
        return self.members[label][2].size

    def open(self, label: str) -> IO[bytes]:
        """Stream a member (``FileNotFoundError`` when absent). The digest is recorded once it was read to its end."""
        if label not in self.members or label in self._seen_twice:
            raise FileNotFoundError(label)
        opened, member, _ = self.members[label]

        def done(hex_digest: str, size: int) -> None:
            self._digests[label] = (hex_digest, size)

        return io.BufferedReader(_MemberStream(opened.stream_member(member, _CHUNK), done), _CHUNK)

    def digest(self, label: str) -> tuple[str, int]:
        """``(sha256 hex, size)`` of a member, read once (``IngestError`` from the gate's stream checks)."""
        if label not in self._digests:
            with self.open(label) as stream:
                while stream.read(_CHUNK):
                    pass
        return self._digests[label]


def member_digest(archive: ArchiveSet, label: str) -> tuple[str, int, str]:
    """``(sha256 hex, size, crc32 hex)`` of one member, streamed."""
    sha, crc, size = hashlib.sha256(), 0, 0
    with archive.open(label) as stream:
        while chunk := stream.read(_CHUNK):
            sha.update(chunk)
            crc = zlib.crc32(chunk, crc)
            size += len(chunk)
    return sha.hexdigest(), size, f"{crc:08x}"


class ArchiveSource:
    """The archive-mode :class:`~agentprov.corpus.integrity.ChecksumSource`: the union of an :class:`ArchiveSet`'s
    members is the closed world."""

    def __init__(self, archives: ArchiveSet) -> None:
        self.archives = archives
        self.checksums_refused: str | None = None

    def read_checksums(self) -> bytes | None:
        self.checksums_refused = None
        if not self.archives.has(CHECKSUMS):
            return None
        try:
            with self.archives.open(CHECKSUMS) as stream:
                return stream.read()
        except IngestError as exc:  # over a limit, a bad member: a finding (checksums.unreadable), never a crash
            self.checksums_refused = exc.code
            return None
        except OSError as exc:
            self.checksums_refused = type(exc).__name__
            return None

    def present(self) -> tuple[list[str], list[ChecksumFinding]]:
        labels = [label for label in self.archives.labels() if label != CHECKSUMS]
        return labels, list(self.archives.findings)

    def open(self, path: str) -> IO[bytes]:
        return self.archives.open(path)


class ArchiveCorpusReader(CorpusReader):
    """A sealed corpus whose files are the members of an :class:`ArchiveSet` (read-only; no raw store directory).

    ``root`` names the deposit directory plus the corpus prefix, for messages only: nothing below it is ever opened."""

    def __init__(self, archives: ArchiveSet, *, limits: IngestLimits | None = None) -> None:
        super().__init__(archives.directory / archives.prefix.rstrip("/"), state=SEALED, limits=limits)
        self.archives = archives

    def open_file(self, label: str, *, stored: bool = False, json_document: bool = False) -> IO[bytes]:
        self._check_label(label)
        try:
            if json_document and self.archives.has(label) and self.archives.size(label) > self.limits.max_json_bytes:  # GR-35
                raise CorpusReadError(f"{label}: cannot be opened (ingest.size.file)", code="corpus.read.unreadable")
            return self.archives.open(label)
        except FileNotFoundError:
            raise CorpusReadError(f"{label}: missing", code="corpus.read.missing") from None

    def read_bytes(self, label: str, *, stored: bool = False) -> bytes:
        try:
            with self.open_file(label, stored=stored) as stream:
                return stream.read()
        except IngestError as exc:
            raise CorpusReadError(f"{label}: cannot be read ({exc.code})", code="corpus.read.unreadable") from None

    def exists(self, label: str) -> bool:
        self._check_label(label)
        return self.archives.has(label)

    def raw_store(self) -> Any:
        raise CorpusReadError("an archive-mode corpus has no raw store directory; its objects are archive members",
                              code="corpus.read.archive")
