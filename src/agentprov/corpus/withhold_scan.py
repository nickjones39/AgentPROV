"""The decoded scan of stored archives for the ``[withhold]`` byte rules (D-450, D-452; HL H.4.5; G.9.5).

A byte rule is searched in every stored raw object as stored. Inside an archive that is not enough: a member the profile
did not select is never decompressed (R-40) and has no object of its own, and a deflated (or tar.gz / tar.zst) member's
bytes never contain the marker literally, so a canary there would ship inside the released container. This module reads
the stored archives **in decoded form** and reports which rules match in them, and which archives it could not read.

**What is an archive.** Each stored object is classified from its first 512 bytes and its last 64 KiB only, in this
process (nothing is parsed or decompressed here). It is *opened* when it is a zip (``PK 03 04`` at offset 0), a gzip or
zstd stream (a tar inside, or :func:`agentprov.ingest.archives.open_archive` refuses it), or a split descriptor (D-243,
through its parts). It is *unscanned*, failing closed, when it looks like any other archive or compressed stream: xz,
bzip2, 7z, rar, lz4, cab, a spanned zip (``PK 07 08``), an uncompressed tar (``ustar`` at 257; refused in v0.1), or a zip
end record near its end without a local header at offset 0 (a prefixed or self-extracting zip; an empty zip, an end
record alone, is a document). Everything else is a document, scanned as stored.

**How an archive is read.** Its bytes are copied by digest into a scratch raw store (checked against the digest) and
expanded by :func:`agentprov.raw.members.expand_containers` through T1 workers: the same bounded, extraction-free
``expand`` job and G.3.5 gate as at import, under the default :class:`IngestLimits`. It selects exactly the members the
corpus does **not** store as objects of their own (``members``: the rows of the corpus's ``raw/members.jsonl``), by their
escaped labels; an archive the import never expanded has every member selected. A member the corpus stores is scanned as its own root, as stored or decoded (D-452), never again through its
container, and it counts as covered only when the expansion sees the same size and CRC-32 (or the same digest). Every
member's label and contents are scanned with :func:`agentprov.corpus.withhold.scan_chunks`; a member that is itself an
archive is read in turn, depth first, up to ``max_archive_depth`` or the deeper level the profile's ``[[import.nested]]``
declarations allow (``max_depth``, clamped by the ceiling; D-452). A scanned member is deleted at once; at most
``max_total_bytes`` of decoded members are stored per root (``corpus.withhold.scan_budget`` past it). The scratch store
lies under ``$AGENTPROV_HOME/tmp`` and is removed at the end. Only rule ids and closed codes leave this module.

**Roots in parallel (perf round 2).** Up to ``workers`` roots are read at once, each by a reader with its own scratch
store and its own one-worker pool; one root's walk stays sequential. Split descriptors are read first, as a part is
skipped only once its descriptor was read cleanly. The results are recorded in the serial order (descriptors, then every
other object, each sorted), so a :class:`DecodedScan` is the same, iteration order included, at any worker count.

**A zip without a usable central directory (D-453).** When ``expand`` rejects a zip whole for its central directory
(:data:`_STRUCTURAL`: none, as in a zip cut at a size cap, a damaged one, overlapping entries) and the zip has a local
header at offset 0, the T1 job ``zip_local`` (:mod:`agentprov.corpus.zip_local`) reads it by its local headers instead:
stored entries by size, deflated ones up to their stream's end or the cut. Its entries are members as above (names and
data scanned, archives queued), and the root is reported in :attr:`DecodedScan.partial`. An entry that job cannot read
(encrypted, another method, a stored entry of unknown length), or no entry at all, keeps the archive unscanned. Content past a cut does not
exist, and compressed bytes no valid header introduces are presented as content by no zip reader; every byte is
raw-scanned as stored in any case.

**Unscanned** (the first closed code is reported): any of the above, a structural or limit rejection of the archive or a
nested one (``ingest.*``, ``worker.limit.*``, ``expand.failed``) that the local-header read does not cover, bytes after a zip's end record
(``ingest.archive.trailing``: they are only stored bytes), a rejected or unexpected member, nesting beyond the allowance
(``ingest.archive.depth``), a missing split part, bytes that do not match their digest, or a worker pool that cannot be
started (isolation, the interpreter guard). Sealing withholds an unscanned archive that no other cause withholds (basis
``unscanned``, D-454; :mod:`agentprov.corpus.withhold`); the ``chain`` and deposit-builder backstops report a released
one.

**Member scan (D-491).** By default each member's label and contents are searched for ``rules``. A caller that needs to
know *where* a hit lies (the release scan's home-path and host-name search, ``tools/release_scan.py``) passes
``member_scan``: it is called as ``member_scan(root, locator, part, chunks)`` for every member read, where ``root`` is
the stored archive (bare hex), ``locator`` the member's 0-based position in its archive's member list (``"3"``; a
member of a nested archive is ``"<parent locator>!<position>"``, e.g. ``"3!0"``), ``part`` is ``"name"`` (``chunks`` is
the label) or ``"data"`` (its decoded bytes), and it returns the rule ids it found. Which members are read, and the
unscanned codes, do not change. Calls are serialised (never two at once, so a callback may keep state between its own
statements), but with several workers their order across roots is not fixed: a caller gathers what it needs in sets.

**Not read:** a tar's header fields and block padding, which the ``expand`` job does not return (a D-453 follow-up).
"""

from __future__ import annotations

import glob
import os
import queue
import shutil
import sys
import tempfile
import threading
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from agentprov.errors import AgentProvError
from agentprov.ingest.limits import IngestLimits
from agentprov.corpus.zip_local import LOCAL_HEADER as _LOCAL_HEADER
from agentprov.io.workers import Job, MemberOutput, WorkerPool, resolve_worker_count
from agentprov.raw.members import (
    ContainerSpec,
    MemberRow,
    MembersError,
    Selection,
    decode_split_descriptor,
    expand_containers,
)
from agentprov.raw.store import RawObjectStore, ext_for_label

if TYPE_CHECKING:
    from agentprov.corpus.withhold import Rule

__all__ = ["DECODED_DETECTOR", "DecodedScan", "MemberScan", "scan_archives"]

#: The ``finding.detector`` of a hit found in an archive's decoded members (this module, version 1).
DECODED_DETECTOR: Final = "agentprov-withhold-decoded/1"
_SNAPSHOT: Final = "withhold-scan"  # the register subject of expand events; never written anywhere
_HEAD: Final = 512
_TAIL: Final = 65557  # the largest zip end record: 22 bytes and a 65,535-byte comment
#: A split descriptor is canonical JSON (JCS: sorted keys), so it starts with this; at most 64 KiB (raw.members).
_DESCRIPTOR_HEAD: Final = b'{"archive":'
_DESCRIPTOR_MAX: Final = 64 * 1024
#: Archives and streams this scan cannot open: (magic at offset 0, the code an object so marked is unscanned with).
_UNREADABLE: Final = (
    (b"\xfd7zXZ\x00", "ingest.stream.codec"),  # xz
    (b"7z\xbc\xaf\x27\x1c", "ingest.archive.format"),  # 7z
    (b"Rar!\x1a\x07", "ingest.archive.format"),  # rar 4 and 5
    (b"\x04\x22\x4d\x18", "ingest.stream.codec"),  # lz4 frame
    (b"MSCF\x00\x00\x00\x00", "ingest.archive.format"),  # cab
    (b"PK\x07\x08", "ingest.archive.format"),  # a spanned zip
)
#: More selection patterns than this (after whole directories are folded into ``dir/**``): every member is selected
#: instead, bounded by the budget. The job tests each label against an alternation of the patterns, so the cost grows
#: with members times patterns.
_SELECTION_PATTERNS: Final = 2_000
#: The container codes with which ``expand`` rejects a zip whole for its central directory (none, damaged, or entries
#: that overlap): such a zip, with a local header at offset 0, is read by its local headers instead (D-453).
_STRUCTURAL: Final = frozenset({"ingest.archive.format", "ingest.archive.cd", "ingest.archive.overlap"})
#: ``(root archive, member locator, "name" | "data", chunks) -> rule ids`` (D-491; see the module docstring).
MemberScan = Callable[[str, str, str, Iterable[bytes]], frozenset[str]]


@dataclass(frozen=True)
class DecodedScan:
    """``hits``: archive object (bare hex) -> the ids of the rules that match in its decoded members; ``unscanned``:
    archive object -> the first closed code that kept part of it from being read; ``partial``: the archive objects read,
    wholly or in part, by their local headers (D-453; a seal-report count, ``scanned_partial``)."""

    hits: Mapping[str, frozenset[str]]
    unscanned: Mapping[str, str]
    partial: frozenset[str] = frozenset()


def _ends(chunks: Iterable[bytes]) -> tuple[bytes, bytes, int]:
    """The first :data:`_HEAD` and last :data:`_TAIL` bytes of ``chunks`` and their total size."""
    head, tail, size = b"", b"", 0
    for chunk in chunks:
        size += len(chunk)
        if len(head) < _HEAD:
            head += chunk[: _HEAD - len(head)]
        tail = (tail + chunk)[-_TAIL:]
    return head, tail, size


def _classify(head: bytes, tail: bytes, size: int) -> str | None:
    """``"open"`` (an archive the expand job opens), ``None`` (a document) or the code of an archive it cannot read."""
    if head.startswith(b"PK\x03\x04") or head.startswith((b"\x1f\x8b", b"\x28\xb5\x2f\xfd")):
        return "open"
    for magic, code in _UNREADABLE:
        if head.startswith(magic):
            return code
    if head[:3] == b"BZh" and head[3:4].isdigit() and head[4:10] in (b"1AY&SY", b"\x17rE8P\x90"):
        return "ingest.stream.codec"  # bzip2 (a block or an empty stream), not just any text starting "BZh"
    if head[257:262] == b"ustar":
        return "ingest.archive.format"  # an uncompressed tar is refused in v0.1, so it is never read decoded
    if b"PK\x05\x06" in tail and not _empty_zip(head, size):
        return "ingest.archive.prefix"  # a zip end record without a local header at 0: prefixed or self-extracting
    return None


def _empty_zip(head: bytes, size: int) -> bool:
    """An end record alone (an empty zip): nothing but its 22 bytes and a comment that holds no archive or stream."""
    if not head.startswith(b"PK\x05\x06") or len(head) < 22:
        return False
    comment = int.from_bytes(head[20:22], "little")
    return size == 22 + comment and comment <= len(head) - 22 and not any(
        magic in head[22:] for magic in (b"PK", b"\x1f\x8b", b"\x28\xb5\x2f\xfd"))


def _store_chunks(store: RawObjectStore, sha: str) -> Iterator[bytes]:
    with store.open(sha) as handle:
        while chunk := handle.read(1 << 20):
            yield chunk


def _drop(store: RawObjectStore, sha: str) -> None:
    for path in (store.objects_dir / sha[:2]).glob(sha + ".*"):
        path.unlink()


def _scratch_dir() -> Path:
    home = Path(os.environ.get("AGENTPROV_HOME") or Path.home() / ".agentprov").expanduser()
    (home / "tmp").mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="withhold-scan-", dir=home / "tmp"))


def scan_archives(
    objects: Mapping[str, str],
    stream: Callable[[str], Iterable[bytes]],
    rules: Sequence[Rule],
    *,
    limits: IngestLimits | None = None,
    release: bool = True,
    workers: int | None = None,
    in_process: bool = False,
    max_depth: int | None = None,
    members: Iterable[MemberRow] = (),
    member_scan: MemberScan | None = None,
) -> DecodedScan:
    """Scan every archive among ``objects`` (bare hex -> corpus label of a stored raw object, read through ``stream``) in
    decoded form for ``rules`` (see the module docstring). ``release`` applies the interpreter guard of a release
    (G.3.8); ``workers``, the number of roots read at once (:func:`root_readers`), defaults to the host default
    (:func:`agentprov.io.workers.resolve_worker_count`);
    ``max_depth`` is the declared nesting allowance (D-382, D-452); ``members`` are the rows of the corpus's
    ``raw/members.jsonl``; ``member_scan`` replaces the search of each member (D-491; default:
    :func:`agentprov.corpus.withhold.scan_chunks` for ``rules``)."""
    if not rules:
        return DecodedScan({}, {})
    if member_scan is None:
        from agentprov.corpus.withhold import scan_chunks

        def member_scan(_root: str, _locator: str, _part: str, chunks: Iterable[bytes]) -> frozenset[str]:
            return scan_chunks(chunks, rules)

    limits = limits or IngestLimits()
    unscanned: dict[str, str] = {}
    descriptors: dict[str, tuple[tuple[str, int], ...]] = {}
    kinds: dict[str, str | None] = {}
    for sha, label in sorted(objects.items()):
        head, tail, size = _ends(stream(label))
        kinds[sha] = _classify(head, tail, size)
        if head.startswith(_DESCRIPTOR_HEAD) and size <= _DESCRIPTOR_MAX:
            try:
                descriptors[sha] = decode_split_descriptor(b"".join(stream(label)), limits)
            except AgentProvError:
                pass  # a JSON document, not a split descriptor
    hits: dict[str, frozenset[str]] = {}
    partial: set[str] = set()
    one_at_a_time = threading.Lock()
    serial_scan = member_scan

    def locked_scan(root: str, locator: str, part: str, chunks: Iterable[bytes]) -> frozenset[str]:
        with one_at_a_time:
            return serial_scan(root, locator, part, chunks)

    scratch = _scratch_dir()
    try:
        readers: queue.SimpleQueue[_Reader] = queue.SimpleQueue()
        count = root_readers(workers, in_process=in_process)
        failure: str | None = None
        for i in range(count):
            store = RawObjectStore(scratch / f"raw-{i}", limits=limits)
            try:
                pool = WorkerPool(store_root=store.objects_dir, workers=1, in_process=in_process, release=release)
            except AgentProvError as exc:  # isolation or the interpreter guard: nothing can be read decoded
                failure = exc.code
                break
            readers.put(_Reader(store, _Walk(objects, stream, rules, store, pool, limits, release, locked_scan,
                                             max_depth, members)))  # fmt: skip

        def read(sha: str, parts: tuple[tuple[str, int], ...] = ()) -> tuple[frozenset[str], str | None, bool]:
            """One root on a free reader: its rule ids, its first problem and whether it was read by local headers."""
            reader = readers.get()
            try:
                reader.walk.partial = False  # a root whose bytes cannot be stored never reaches its local-header read
                found, problem = reader.walk.root(sha, parts)
                return found, problem, reader.walk.partial
            finally:
                for child in reader.store.objects_dir.iterdir():
                    shutil.rmtree(child)
                readers.put(reader)

        def scan_all(roots: Sequence[tuple[str, tuple[tuple[str, int], ...]]]) -> dict[str, _Outcome]:
            """Read ``roots``, up to ``count`` at once."""
            if failure is not None:
                return {sha: (frozenset(), failure, False) for sha, _parts in roots}
            if count == 1 or len(roots) < 2:
                return {sha: read(sha, parts) for sha, parts in roots}
            with ThreadPoolExecutor(max_workers=min(count, len(roots)), thread_name_prefix="withhold-scan") as ex:
                futures = [ex.submit(read, sha, parts) for sha, parts in roots]
                try:
                    return {sha: f.result() for (sha, _parts), f in zip(roots, futures, strict=True)}
                except BaseException:  # the first error in root order is raised; roots not started are dropped
                    for f in futures:
                        f.cancel()
                    raise

        outcomes = scan_all([(sha, descriptors[sha]) for sha in sorted(descriptors)  # a split archive first, through
                             if all(p in objects for p, _size in descriptors[sha])])  # its parts  # fmt: skip
        read_parts: set[str] = set()
        for sha in sorted(descriptors):
            if sha not in outcomes:
                outcomes[sha] = (frozenset(), "raw.object.missing", False)
            elif outcomes[sha][1] is None:
                read_parts.update(p for p, _size in descriptors[sha])
        # a part is skipped only once a descriptor listing it was read without problems
        rest = [sha for sha in sorted(objects) if sha not in descriptors and sha not in read_parts]
        outcomes.update(scan_all([(sha, ()) for sha in rest if kinds[sha] == "open"]))
        for sha in rest:
            kind = kinds[sha]
            if kind is not None and kind != "open":
                outcomes[sha] = (frozenset(), kind, False)
        for sha in (*sorted(descriptors), *rest):  # recorded in the serial order: the same result at any worker count
            if sha not in outcomes:
                continue
            found, problem, was_partial = outcomes[sha]
            if was_partial:
                partial.add(sha)
            if found:
                hits[sha] = found
            if problem is not None:
                unscanned[sha] = problem
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return DecodedScan(hits, unscanned, frozenset(partial))


#: One root's rule ids, its first problem (``None``: read cleanly) and whether it was read by its local headers.
_Outcome = tuple[frozenset[str], str | None, bool]


@dataclass(frozen=True)
class _Reader:
    """A root reader: its own scratch store and a walk over its own one-worker pool (reused root after root)."""

    store: RawObjectStore
    walk: _Walk


def root_readers(workers: int | None, *, in_process: bool) -> int:
    """How many roots are read at once: ``workers`` (``None``: the host default, :func:`resolve_worker_count`), each
    with a one-worker pool of its own; one when ``in_process`` (the debugging dispatch never runs concurrently)."""
    return 1 if in_process else max(1, workers or resolve_worker_count(0))


class _Walk:
    """The depth-first read of one stored archive (a root) and the archives inside it."""

    def __init__(self, objects: Mapping[str, str], stream: Callable[[str], Iterable[bytes]], rules: Sequence[Rule],
                 store: RawObjectStore, pool: WorkerPool | None, limits: IngestLimits, release: bool,
                 member_scan: MemberScan, max_depth: int | None,
                 members: Iterable[MemberRow]) -> None:  # fmt: skip
        self.objects, self.stream, self.rules, self.store, self.pool = objects, stream, rules, store, pool
        self.limits, self.release, self.member_scan, self.max_depth = limits, release, member_scan, max_depth
        self.listed: dict[str, set[str]] = {}  # container -> every label raw/members.jsonl lists for it
        self.stored: dict[str, dict[str, MemberRow]] = {}  # container -> label -> its row, stored in this corpus
        for m in members:
            if m.label is None:
                continue
            self.listed.setdefault(m.container, set()).add(m.label)
            if m.disposition == "selected" and m.sha256 is not None and m.sha256 in objects:
                self.stored.setdefault(m.container, {})[m.label] = m

    def _selection(self, container: str, known: set[str] | None) -> Selection:
        """Every member, or (for an archive the corpus expanded) exactly the members it does not store: their escaped
        labels, a directory none of whose members is stored folded into ``dir/**``. A selection that cannot be
        expressed (too many patterns, or a label the pattern rules refuse) selects every member, bounded by the budget."""
        if known is None:
            return Selection(include=("**",))
        stored = set(self.stored.get(container, {}))
        patterns = _fold(sorted(known - stored), stored)
        if len(patterns) > _SELECTION_PATTERNS:
            return Selection(include=("**",))
        try:
            return Selection(include=tuple(patterns)) if patterns else Selection()
        except MembersError:
            return Selection(include=("**",))

    def root(self, sha: str, parts: tuple[tuple[str, int], ...]) -> tuple[frozenset[str], str | None]:
        """The rule ids found in one stored archive's decoded members, and the first code that kept part of it unread."""
        assert self.pool is not None
        label = self.objects[sha]
        try:
            for digest in (*(p for p, _size in parts), sha):
                self.store.put_chunks(self.stream(self.objects[digest]), ext=ext_for_label(self.objects[digest]),
                                      max_bytes=sys.maxsize, expected_sha256=digest)  # fmt: skip
        except AgentProvError as exc:
            return frozenset(), exc.code
        self.found: set[str] = set()
        self.problems: list[str] = []
        self.partial = False
        self.budget = self.limits.max_total_bytes
        self.done: set[str] = {sha}  # digests read in this root: the same bytes give the same result, deleted once read
        known_labels = self._known(sha)
        self.pending = [(ContainerSpec(sha, _SNAPSHOT, label, (self._selection(sha, known_labels),), parts=parts,
                                       max_depth=self.max_depth), known_labels, "")]  # fmt: skip
        while self.pending and not self.problems:
            spec, known, prefix = self.pending.pop()
            try:
                outcome = expand_containers(self.store, [spec], pool=self.pool, limits=self.limits, release=self.release)
            except AgentProvError as exc:
                self.problems.append(exc.code)
                break
            # container-level outcomes; a rejected member is also a row, judged below (it may be stored on its own)
            container = [e.code for e in outcome.events
                         if e.path == spec.path and (e.disposition != "sealed" or e.code == "ingest.archive.trailing")]
            if container and container[0] in _STRUCTURAL and not spec.parts and self._local_zip(spec.sha256):
                self._local(sha, spec, prefix)  # D-453: expand rejected the zip whole; read its local headers instead
                continue
            self.problems += container
            if spec.sha256 != sha:
                _drop(self.store, spec.sha256)
            mine = self.stored.get(spec.sha256, {})
            for position, row in enumerate(outcome.rows):  # one container per call: its members, in archive order
                locator = f"{prefix}{position}"
                if row.label is not None:
                    self.found |= self.member_scan(sha, locator, "name", [row.label.encode("utf-8")])
                member = mine.get(row.label) if row.label is not None else None
                if member is not None and (row.sha256 == member.sha256 if row.sha256 is not None
                                           else (row.size, row.crc32) == (member.size, member.crc32)):
                    continue  # stored as a corpus object of its own, the same bytes: scanned as its own root
                if row.disposition != "selected" or row.sha256 is None:
                    self.problems.append(row.code or "expand.not_selected")
                    continue
                if not self._member(sha, spec, locator, row.label or "", row.sha256, row.size or 0):
                    break
        return frozenset(self.found), (self.problems[0] if self.problems else None)

    def _member(self, sha: str, spec: ContainerSpec, locator: str, label: str, digest: str, size: int) -> bool:
        """Read one decoded member already in the scratch store: queue it when it is an archive, else scan its bytes.
        ``False`` once the budget is spent (the walk stops)."""
        if digest in self.done:
            return True
        self.done.add(digest)
        self.budget -= size
        if self.budget < 0:
            self.problems.append("corpus.withhold.scan_budget")
            return False
        head, tail, total = _ends(_store_chunks(self.store, digest))
        kind = _classify(head, tail, total)
        if kind == "open":
            child_known = self._known(digest)
            self.pending.append((ContainerSpec(digest, _SNAPSHOT, f"{spec.path}!{label}",
                                               (self._selection(digest, child_known),), depth=spec.depth + 1,
                                               max_depth=self.max_depth), child_known, f"{locator}!"))  # fmt: skip
            return True
        if kind is not None:
            self.problems.append(kind)
        else:
            self.found |= self.member_scan(sha, locator, "data", _store_chunks(self.store, digest))
        _drop(self.store, digest)
        return True

    def _local_zip(self, digest: str) -> bool:
        head, _tail, _size = _ends(_store_chunks(self.store, digest))
        return head.startswith(_LOCAL_HEADER)

    def _local(self, sha: str, spec: ContainerSpec, prefix: str) -> None:
        """D-453: the ``zip_local`` job over a zip ``expand`` rejected whole. Each entry it decodes is a member (name and
        data scanned, an archive queued); an entry it cannot read is a problem, so the root stays unscanned."""
        assert self.pool is not None
        self.partial = True
        result = self.pool.run_one(Job(f"zip_local:{spec.sha256}", "zip_local",
                                       ({"sha256": spec.sha256, "role": "container"},),
                                       {"limits": self.limits.to_json()}))  # fmt: skip
        try:
            if not result.ok:
                assert result.error is not None
                self.problems.append(result.error.code)
                return
            position = 0
            for out in result.iter_outputs():
                locator = f"{prefix}{position}"
                if isinstance(out, MemberOutput):
                    label = out.header.get("label")
                    if not isinstance(label, str) or out.header.get("size") != out.size:
                        self.problems.append("expand.protocol")
                        return
                    position += 1
                    self.found |= self.member_scan(sha, locator, "name", [label.encode("utf-8")])
                    put = self.store.put_chunks(out.iter_chunks(), ext=ext_for_label(label), max_bytes=sys.maxsize)
                    if not self._member(sha, spec, locator, label, put.sha256, out.size):
                        return
                elif "row" in out and isinstance(out["row"], Mapping):
                    position += 1
                    row_label = out["row"].get("label")
                    if isinstance(row_label, str):
                        self.found |= self.member_scan(sha, locator, "name", [row_label.encode("utf-8")])
                    code = out["row"].get("code")
                    self.problems.append(code if isinstance(code, str) and code.startswith("ingest.") else "expand.protocol")
                else:
                    self.problems.append("expand.protocol")
                    return
            if position == 0:
                self.problems.append("ingest.archive.format")  # no entry at all: its structure is unknown, fail closed
        finally:
            result.close()
            if spec.sha256 != sha:
                _drop(self.store, spec.sha256)

    def _known(self, container: str) -> set[str] | None:
        """The labels ``raw/members.jsonl`` lists for ``container`` (stored or not), or ``None`` if it lists none."""
        return self.listed.get(container)


def _fold(wanted: Sequence[str], stored: set[str]) -> list[str]:
    """Glob patterns that match exactly the ``wanted`` labels, with each directory none of whose labels is ``stored``
    written once as ``<dir>/**`` (it may then also match an unlisted member there: read, so never laxer)."""
    blocked = {label.rsplit("/", i)[0] for label in stored for i in range(1, label.count("/") + 1)}
    out: set[str] = set()
    for label in wanted:
        parts = label.split("/")
        top = next(("/".join(parts[:i]) for i in range(1, len(parts)) if "/".join(parts[:i]) not in blocked), None)
        out.add(glob.escape(top) + "/**" if top is not None else glob.escape(label))
    return sorted(out)
