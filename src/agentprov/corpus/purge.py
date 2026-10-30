"""Purge: remove one leaked raw object from a working store and leave a tombstone (MN N.2.15; G.9.6; HL H.1.2, H.6.3; D-46).

``agentprov purge sha256:<hex> --reason secret|personal_data (--corpus DIR | --cache)`` deletes one object from a *working*
corpus's raw store, or one downloaded file from the fetch cache, and records that fact without recording the value:

* **Tombstone** (HL H.1.2). A row ``{"date": "YYYY-MM-DD", "reason": "secret"|"personal_data", "sha256": "sha256:<hex>"}``
  in ``raw/tombstones.jsonl`` (working corpus) or ``<cache>/tombstones.jsonl`` (fetch cache): JCS lines, sorted by
  ``sha256``, LF-terminated, written atomically. No row holds the purged bytes or any fragment of them. Purging the same
  object again changes nothing (the first row, with its date, is kept).
* **Register** (G.9.5; HL H.6.3). Every execution of the corpus that cites the object gets the register entry
  ``release.withheld`` (stage ``package``, disposition ``withheld``, severity ``info``), so that packaging withholds it. An
  execution cites the object when its index row's ``raw`` array names it, or names an object that was expanded from it at
  any nesting level (the object is an archive container of ``raw/members.jsonl``; the same closure as the seal planner's,
  :func:`agentprov.corpus.withhold.member_closure`, CB-1). The entry's ``detail`` is fixed text, so repeating a purge
  reproduces the same file. ``corpus.json`` and ``executions.jsonl`` are not rewritten: the working manifest's counts and the
  rows' ``issues`` are refreshed when the corpus is next derived or sealed.
* **Order and resumption.** Tombstone, then register, then the unlink. A crash in between leaves the object present and the
  tombstone written, and running the same purge again finishes the job. Everything runs under the working tree's single
  writer lock (guard G6); a dry run takes no lock and writes nothing.

**Where the logic lives (D-46).** The spec names ``agentprov.raw.purge``, but ``raw/`` belongs to phase 12 during phase 11,
so purge is built here from the public, read-only API of ``raw`` (``RawObjectStore``, ``decode_members``) plus filesystem
operations. The command module is :mod:`agentprov.cli.purge`.

**What is not purged.** A sealed corpus is never modified (``SealedCorpusError``, exit 4; build a new version with the
object withheld, G.9.5). Member objects of a purged container stay stored and are listed, so the caller can purge them too.
So do the objects linked to it by D-315 (``raw/origins.jsonl``): the rest of a split archive (its descriptor and byte
parts) and a carved blob or the source it was carved from. They can hold the same bytes, so they are listed with the
seal planner's own groups (:func:`agentprov.corpus.withhold.linked_objects`), but a purge removes one object only: the
caller purges each listed object whose bytes hold the value, and the next seal withholds every group whole anyway. A
linked object withholds no execution (the seal's D-315 closure neither), so ``affected`` is unchanged.
Git objects inside the fetch cache's bare repositories are not searched: ``--cache`` removes downloaded files (Zenodo,
Hugging Face, URL pins) only, but every cached copy of the bytes (the same file pinned twice, as a Zenodo file and its
mirror or under two HF revisions, is cached at two paths).
"""

from __future__ import annotations

import hashlib
import io
import os
import stat
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Final

from agentprov.corpus.index import IndexRow
from agentprov.corpus.layout import (
    MANIFEST,
    PARTIAL_SUFFIX,
    REGISTER,
    CorpusLayout,
    assert_writable,
)
from agentprov.corpus.reader import CorpusReader
from agentprov.corpus.register import RegisterEntry, RegisterLog
from agentprov.errors import AgentProvError, IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import iter_jsonl
from agentprov.ingest.paths import open_evidence
from agentprov.io.atomic import LockFile, _fsync_dir, atomic_write_bytes
from agentprov.io.canonical import is_sha256_hex, jcs_bytes
from agentprov.raw.members import MemberRow
from agentprov.raw.origins import OriginRow
from agentprov.raw.store import EXTENSIONS, RawObjectStore

__all__ = [
    "REASONS",
    "TOMBSTONES_NAME",
    "WITHHELD_DETAIL",
    "PurgeError",
    "PurgePlan",
    "PurgeResult",
    "Tombstone",
    "UnknownObjectError",
    "UsageError",
    "apply",
    "decode_tombstones",
    "encode_tombstones",
    "parse_digest",
    "plan_cache",
    "plan_corpus",
    "resolve_working_corpus",
]

REASONS: Final = ("secret", "personal_data")
TOMBSTONES_NAME: Final = "tombstones.jsonl"
#: The fixed ``detail`` of the ``release.withheld`` entry a purge adds (HL H.6.2: generated text, never source content).
WITHHELD_DETAIL: Final = "a cited raw object was purged (G.9.6)"
#: Fetch-cache subtrees that hold downloaded files; the bare git repositories are not searched.
_CACHE_FILE_TREES: Final = ("zenodo", "hf", "url")
_CHUNK: Final = 1 << 20
#: Cache files are hashed whole (a downloaded archive can exceed the per-artefact import cap).
_HASH_LIMITS: Final = IngestLimits(max_artefact_bytes=1 << 50)
_ROW_KEYS: Final = frozenset({"date", "reason", "sha256"})


class PurgeError(AgentProvError):
    """A purge cannot proceed (``purge.*``); nothing was changed."""

    code = "purge.error"
    exit_code = 1


class UnknownObjectError(PurgeError):
    """No object with this digest is in the store (exit 2: an unknown object, N.2.15)."""

    code = "purge.unknown_object"
    exit_code = 2


class UsageError(PurgeError):
    """A malformed digest or reason, or a corpus that does not exist (exit 2)."""

    code = "purge.usage"
    exit_code = 2


# --------------------------------------------------------------------------------------------------------------
# Tombstones
# --------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Tombstone:
    """One purged object: digest (bare hex), reason and the UTC date of the purge."""

    sha256: str
    reason: str
    date: str

    def __post_init__(self) -> None:
        if not is_sha256_hex(self.sha256):
            raise PurgeError("a tombstone names a sha256 digest", code="purge.tombstone.invalid")
        if self.reason not in REASONS:
            raise PurgeError("a tombstone reason is secret or personal_data", code="purge.tombstone.invalid")
        try:
            parsed = date.fromisoformat(self.date)
        except ValueError:
            raise PurgeError("a tombstone date is YYYY-MM-DD", code="purge.tombstone.invalid") from None
        if parsed.isoformat() != self.date:
            raise PurgeError("a tombstone date is YYYY-MM-DD", code="purge.tombstone.invalid")

    def to_json(self) -> dict[str, str]:
        return {"date": self.date, "reason": self.reason, "sha256": "sha256:" + self.sha256}


def encode_tombstones(rows: Iterable[Tombstone]) -> bytes:
    """The bytes of a ``tombstones.jsonl``: one row per digest (the first one given wins), sorted by ``sha256``."""
    best: dict[str, Tombstone] = {}
    for row in rows:
        best.setdefault(row.sha256, row)
    return b"".join(jcs_bytes(best[k].to_json()) + b"\n" for k in sorted(best))


def decode_tombstones(data: bytes, limits: IngestLimits | None = None) -> list[Tombstone]:
    """Parse a ``tombstones.jsonl`` strictly; the file must be in canonical order (sorted, unique digests)."""
    out: list[Tombstone] = []
    try:
        for _, _, value in iter_jsonl(io.BytesIO(data), limits):
            if not isinstance(value, dict) or set(value) != _ROW_KEYS:
                raise PurgeError("a tombstone row is {date, reason, sha256}", code="purge.tombstone.invalid")
            digest = value["sha256"]
            if not isinstance(digest, str) or not digest.startswith("sha256:"):
                raise PurgeError("a tombstone digest is sha256:<hex>", code="purge.tombstone.invalid")
            out.append(Tombstone(digest[7:], str(value["reason"]), str(value["date"])))
    except IngestError as exc:
        raise PurgeError(f"{TOMBSTONES_NAME} is not strict JSONL ({exc.code})", code="purge.tombstone.invalid") from None
    if encode_tombstones(out) != data:
        raise PurgeError(f"{TOMBSTONES_NAME} is not sorted, duplicate-free and canonical", code="purge.tombstone.invalid")
    return out


def _read_tombstones(path: Path, limits: IngestLimits) -> list[Tombstone]:
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError:
        return []
    if not stat.S_ISREG(mode):
        raise PurgeError(f"{TOMBSTONES_NAME} is not a regular file", code="purge.tombstone.invalid")
    return decode_tombstones(path.read_bytes(), limits)


def parse_digest(text: str) -> str:
    """``sha256:<64 lower-case hex>`` to the bare hex digest; :class:`UsageError` (exit 2) otherwise."""
    if not isinstance(text, str) or not text.startswith("sha256:") or not is_sha256_hex(text[7:]):
        raise UsageError("the object is named sha256:<64 lower-case hex digits>")
    return text[7:]


# --------------------------------------------------------------------------------------------------------------
# Plans
# --------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PurgePlan:
    """What a purge will do (and, for ``--dry-run``, what it would do). All digests are bare hex.

    ``kind`` is ``corpus`` or ``cache``; ``root`` is the working tree or the cache directory; ``object_label`` is the
    store-relative label of the file to remove (``None`` when the object is already gone and only tombstoned).
    """

    kind: str
    root: Path
    digest: str
    reason: str
    date: str
    object_label: str | None
    size: int | None
    already_tombstoned: bool
    affected: tuple[str, ...] = ()  # execution ids that cite the object (corpus kind)
    new_register_entries: int = 0
    member_objects: tuple[str, ...] = ()  # stored member objects of the purged container, at every nesting level
    container_objects: tuple[str, ...] = ()  # stored containers whose members include this object
    #: stored objects that hold the same bytes through a D-315 link: the rest of a split archive (descriptor, parts) and
    #: a carved blob or its source (the seal planner's groups, :func:`agentprov.corpus.withhold.linked_objects`)
    linked_objects: tuple[str, ...] = ()
    #: cache kind: the further cache paths that hold the same bytes (another pin of the same file); removed too
    other_labels: tuple[str, ...] = ()
    notices: tuple[str, ...] = field(default=())

    @property
    def tombstone_label(self) -> str:
        return f"raw/{TOMBSTONES_NAME}" if self.kind == "corpus" else TOMBSTONES_NAME


@dataclass(frozen=True, slots=True)
class PurgeResult:
    plan: PurgePlan
    removed: bool  # the file was unlinked
    tombstone_written: bool
    register_entries_written: int


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


# ------------------------------------------------------------------------------------------------ corpus
def resolve_working_corpus(path: str | os.PathLike[str]) -> Path:
    """The working tree ``<DIR>.partial`` a writer acts on (N.1.5): a sealed ``DIR`` is refused (exit 4), a missing corpus
    is a usage error (exit 2). A path given as ``DIR.partial`` is normalised to ``DIR`` first."""
    given = Path(os.fspath(path))
    final = given.with_name(given.name[: -len(PARTIAL_SUFFIX)]) if given.name.endswith(PARTIAL_SUFFIX) else given
    if not final.name:
        raise UsageError("a corpus path names a directory")
    partial = final.with_name(final.name + PARTIAL_SUFFIX)
    if os.path.lexists(final / MANIFEST):
        assert_writable(final)  # raises SealedCorpusError (exit 4) for "sealed": true; fails closed on an unreadable manifest
    if partial.is_dir() and not partial.is_symlink():
        assert_writable(partial)  # also refuses a working tree inside a sealed ancestor
        return partial
    if final.is_dir():
        raise PurgeError(
            "the directory is not a sealed corpus and has no .partial working tree beside it (N.1.5)",
            code="purge.corpus.not_working",
        )
    raise UsageError("neither a sealed corpus nor a .partial working tree exists at this path (N.1.5)")


def _find_object(store: RawObjectStore, digest: str) -> tuple[str, int] | None:
    """``(store-relative label, size)`` of the stored object, whatever its extension; ``None`` when absent."""
    if not store.has(digest):
        return None
    for ext in sorted(EXTENSIONS):
        path = store.path_for(digest, ext)
        try:
            st = os.lstat(path)
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(st.st_mode):
            raise PurgeError("the stored object is not a regular file", code="purge.object.invalid")
        return f"objects/{digest[:2]}/{digest}.{ext}", st.st_size
    return None  # pragma: no cover - has() found it, so one extension matches


def _containers_of(members: Iterable[MemberRow], digest: str) -> tuple[set[str], set[str]]:
    """``(member digests selected from digest as a container, containers that selected digest as a member)``."""
    selected: set[str] = set()
    containers: set[str] = set()
    for row in members:
        if row.container == digest and row.sha256 is not None:
            selected.add(row.sha256)
        if row.sha256 == digest:
            containers.add(row.container)
    return selected, containers


def _linked(origins: Iterable[OriginRow], digest: str) -> set[str]:
    """Every object joined to ``digest`` through the D-315 groups of ``raw/origins.jsonl`` (a split descriptor and its
    parts; a carved blob and its source), transitively; the seal planner withholds each group whole, so the purge
    lists them all. ``digest`` itself is not included."""
    from agentprov.corpus.withhold import linked_objects  # the seal planner's groups, so the two agree

    groups_of: dict[str, list[tuple[str, ...]]] = {}
    for _kind, group in linked_objects(origins):
        for sha in group:
            groups_of.setdefault(sha, []).append(group)
    out = {digest}
    pending = [digest]
    while pending:
        for group in groups_of.get(pending.pop(), ()):
            for sha in group:
                if sha not in out:
                    out.add(sha)
                    pending.append(sha)
    out.discard(digest)
    return out


def _cites(row: IndexRow, digests: set[str]) -> bool:
    return any(ref.sha256 in digests for ref in row.raw)


def plan_corpus(
    working: str | os.PathLike[str],
    digest: str,
    reason: str,
    *,
    today: Callable[[], str] = _today,
    limits: IngestLimits | None = None,
) -> PurgePlan:
    """Plan the purge of ``digest`` from the working tree ``working`` (see :func:`resolve_working_corpus`). Read-only."""
    limits = limits or IngestLimits()
    if reason not in REASONS:
        raise UsageError("the reason is secret or personal_data")
    root = Path(os.fspath(working))
    layout = CorpusLayout(root)
    store = RawObjectStore(layout.raw, limits=limits, create=False)
    found = _find_object(store, digest)
    known = next((t for t in _read_tombstones(layout.tombstones, limits) if t.sha256 == digest), None)
    if found is None and known is None:
        raise UnknownObjectError("no object with this digest is in the corpus's raw store")
    reader = CorpusReader(root, state="working", used_partial=True, limits=limits)
    members = reader.members() if reader.exists("raw/members.jsonl") else []
    _direct, containers = _containers_of(members, digest)
    from agentprov.corpus.withhold import member_closure  # the seal's closure too, so the two sets agree (CB-1)

    member_digests = member_closure(members, digest)
    linked = _linked(reader.origins(), digest) if reader.exists("raw/origins.jsonl") else set()
    cited = {digest, *member_digests}  # a linked object withholds no execution (the seal's D-315 closure neither)
    affected = tuple(row.ex for row in reader.iter_index() if _cites(row, cited)) if reader.exists("executions.jsonl") else ()
    register = reader.register() if reader.exists(REGISTER) else []
    withheld = {e.subject["ex"] for e in register if e.code == "release.withheld" and "ex" in e.subject}
    notices: list[str] = []
    if known is not None and found is None:
        notices.append("the object is already purged (tombstone present); only the register entries are checked")
    return PurgePlan(
        kind="corpus",
        root=root,
        digest=digest,
        reason=reason if known is None else known.reason,
        date=today() if known is None else known.date,
        object_label=None if found is None else found[0],
        size=None if found is None else found[1],
        already_tombstoned=known is not None,
        affected=affected,
        new_register_entries=sum(1 for ex in affected if ex not in withheld),
        member_objects=tuple(sorted(d for d in member_digests if store.has(d))),
        container_objects=tuple(sorted(c for c in containers if store.has(c))),
        linked_objects=tuple(sorted(d for d in linked if store.has(d))),
        notices=tuple(notices),
    )


# ------------------------------------------------------------------------------------------------ cache
def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open_evidence(path.parent, path.name, _HASH_LIMITS, allow_hardlinks=True) as stream:  # no-follow (D-7, G.3.10)
        while chunk := stream.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _cache_files(cache: Path) -> Iterable[Path]:
    """Every regular file below the downloaded-file subtrees of the cache, sorted; links are never followed."""
    for tree in _CACHE_FILE_TREES:
        top = cache / tree
        try:
            if not stat.S_ISDIR(os.lstat(top).st_mode):
                continue
        except FileNotFoundError:
            continue
        pending = [top]
        while pending:
            directory = pending.pop()
            with os.scandir(directory) as it:
                entries = sorted(it, key=lambda e: e.name)
            for entry in entries:
                mode = entry.stat(follow_symlinks=False).st_mode
                if stat.S_ISDIR(mode):
                    pending.append(Path(entry.path))
                elif stat.S_ISREG(mode):
                    yield Path(entry.path)


def plan_cache(
    cache: str | os.PathLike[str],
    digest: str,
    reason: str,
    *,
    today: Callable[[], str] = _today,
    limits: IngestLimits | None = None,
) -> PurgePlan:
    """Plan the purge of the downloaded file with sha256 ``digest`` from the fetch cache. Read-only."""
    limits = limits or IngestLimits()
    if reason not in REASONS:
        raise UsageError("the reason is secret or personal_data")
    root = Path(os.fspath(cache))
    if not root.is_dir() or root.is_symlink():
        raise UsageError("the fetch cache directory does not exist")
    known = next((t for t in _read_tombstones(root / TOMBSTONES_NAME, limits) if t.sha256 == digest), None)
    # every cached copy: the same bytes can be pinned twice (a Zenodo file and its HF or URL mirror, two HF revisions)
    matches = [path for path in _cache_files(root)
               if (path.parent == root / "url" and path.name == digest) or _hash_file(path) == digest]  # fmt: skip
    match = matches[0] if matches else None
    if match is None and known is None:
        raise UnknownObjectError(
            "no downloaded file with this digest is in the fetch cache (git objects in the bare repositories are not searched)"
        )
    return PurgePlan(
        kind="cache",
        root=root,
        digest=digest,
        reason=reason if known is None else known.reason,
        date=today() if known is None else known.date,
        object_label=None if match is None else match.relative_to(root).as_posix(),
        size=None if match is None else match.stat().st_size,
        already_tombstoned=known is not None,
        other_labels=tuple(path.relative_to(root).as_posix() for path in matches[1:]),
        notices=("the object is already purged (tombstone present)",) if known is not None and match is None else (),
    )


# --------------------------------------------------------------------------------------------------------------
# Apply
# --------------------------------------------------------------------------------------------------------------


def _unlink_object(root: Path, label: str, *, prune: bool = False) -> None:
    """Unlink the object; with ``prune``, also remove the shard directories it leaves empty, never ``root`` itself or
    its first level (a sealed tree is closed-world, H.5.3, and refuses an empty directory)."""
    path = root.joinpath(*label.split("/"))
    if not stat.S_ISREG(os.lstat(path).st_mode):
        raise PurgeError("the stored object is not a regular file", code="purge.object.invalid")
    os.unlink(path)
    _fsync_dir(path.parent)
    if not prune:
        return
    parts = label.split("/")[:-1]
    while len(parts) > 1:
        directory = root.joinpath(*parts)
        try:
            os.rmdir(directory)  # only an empty directory is removed
        except OSError:
            return
        parts.pop()
        _fsync_dir(root.joinpath(*parts))


def _write_tombstone(path: Path, plan: PurgePlan, limits: IngestLimits) -> bool:
    rows = _read_tombstones(path, limits)
    if any(t.sha256 == plan.digest for t in rows):
        return False
    rows.append(Tombstone(plan.digest, plan.reason, plan.date))
    atomic_write_bytes(path, encode_tombstones(rows))
    return True


def _write_register(layout: CorpusLayout, affected: Iterable[str], limits: IngestLimits) -> int:
    log = RegisterLog.load(layout.register, limits) if layout.register.exists() else RegisterLog()
    present = {e.subject["ex"] for e in log.entries() if e.code == "release.withheld" and "ex" in e.subject}
    added = 0
    for ex in affected:
        if ex in present:
            continue
        log.add(
            RegisterEntry(
                subject={"ex": ex},
                code="release.withheld",
                severity="info",
                stage="package",
                disposition="withheld",
                detail=WITHHELD_DETAIL,
            )
        )
        added += 1
    if added:
        log.write(layout.register)
    return added


def apply(plan: PurgePlan, *, break_stale_lock: bool = False, limits: IngestLimits | None = None) -> PurgeResult:
    """Carry out ``plan``: tombstone, register entries, then the unlink. Idempotent (see the module docstring).

    A corpus purge holds the working tree's writer lock and re-plans under it, so the plan it executes is the current one.
    """
    limits = limits or IngestLimits()
    if plan.kind == "cache":
        current_cache = plan_cache(plan.root, plan.digest, plan.reason, limits=limits, today=lambda: plan.date)
        wrote = _write_tombstone(plan.root / TOMBSTONES_NAME, current_cache, limits)
        removed = False
        if current_cache.object_label is not None:
            for label in (current_cache.object_label, *current_cache.other_labels):
                _unlink_object(plan.root, label)
            removed = True
        return PurgeResult(current_cache, removed, wrote, 0)
    layout = CorpusLayout(plan.root)
    assert_writable(plan.root)  # re-check just before writing (H.1.5(2))
    with LockFile(layout.lock, command="purge", break_stale=break_stale_lock):
        current = plan_corpus(plan.root, plan.digest, plan.reason, limits=limits, today=lambda: plan.date)
        wrote = _write_tombstone(layout.tombstones, current, limits)
        added = _write_register(layout, current.affected, limits)
        removed = False
        if current.object_label is not None:
            _unlink_object(layout.raw, current.object_label, prune=True)
            removed = True
    return PurgeResult(current, removed, wrote, added)
