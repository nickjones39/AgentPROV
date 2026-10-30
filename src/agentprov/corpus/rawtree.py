"""``StoredRawTree``: a source corpus's own raw store as the input tree of a re-map (HL H.8.5 ``recompute``; DECISIONS D-30).

``recompute --stages expand,aer`` re-runs the import pipeline over the raw objects a corpus already holds, with **no
network and no upstream checkout**: the bytes come from the source corpus's content-addressed store, digest-checked on
every read, and their origins are the recorded pinned origins. The tree is handed by the CLI layer to the public
``agentprov.adapters.runner.importer.import_source`` (``corpus/`` is below ``adapters.runner`` in M.5.1, so nothing
here imports an adapter module; the candidate type is injected).

* **Candidates.** One per *non-member* origin row of ``raw/origins.jsonl`` (``member`` origins are re-derived by the
  ``expand`` stage, AD-12). Its label is the path the import walked: a ``git`` origin's ``path`` (the pin check matched
  the label against that path), a ``corpus`` origin's ``path`` without the leaf of the snapshot pin's ``tree`` (the
  frozen-corpus listing origin, D.7; a sealed manifest records no pin, so the pin is found among the recorded source
  profile's pins), or, for any other kind, what ``label_of`` returns. Candidates are yielded sorted
  by label bytes. Two origins of one object at two labels are two candidates, so the importer collapses the second
  (``dedup.collapsed``) exactly as the first import did. A label claimed by two different objects is refused.
* **Reading.** :meth:`StoredRawTree.open` reads the object of a label from the source store (no link followed, regular
  files only) and re-hashes it; a mismatch raises :class:`StoredTreeError` ``raw.digest.mismatch``, which stops the
  re-map (``corpus.derive`` verified every object before it started, so this is a change during the run).
* **Origins.** The candidate's origin is the recorded origin itself, so the importer runs without a pin check
  (``pin_check=None``) and records exactly the origins the source recorded.
* **Snapshot origin.** :meth:`snapshot_origin` returns the snapshot origin recorded in the source manifest, never a new
  ``local`` path.
* **Several snapshots** (D-202). In a corpus with more than one snapshot, the tree of one snapshot holds the objects
  with an origin its recorded pin vouched for (:func:`agentprov.corpus.manifest.origin_matches_pin`; in a sealed
  manifest, which records no pin, its sealed origin: :func:`agentprov.corpus.manifest.sealed_origin_pin`), with that origin;
  the re-map replays the snapshots in their recorded (import) order, so an object two snapshots share is mapped by the
  first and collapsed by the second, exactly as the import did.
* **Archive inputs** (D-200). A snapshot whose manifest records ``input.kind == "archive"`` was imported from one
  downloaded archive: its one non-member object is the container, and :attr:`archive_input` tells the importer to expand
  it again (the ``expand`` stage re-derives the member objects and their origins) instead of mapping it as a file. The
  container is found by its recorded digest (its label is the recorded one). An archive input stored as byte parts
  (D-249) records ``input.parts``: the container is the split descriptor (``split`` origin) and :attr:`archive_parts`
  hands the parts, with the origins their pin vouched for, back to the importer, which stores and expands them again.

* **Per-unit inputs** (D-530; runner items R2/R3 of D.16.14). A snapshot that recorded context trees
  (``snapshot.context[]``) or pinned objects (``snapshot.pinned_objects``) keeps as primary inputs only the origins its
  own pin vouched for, as a snapshot of a multi-snapshot corpus does: a context file of a second pinned tree or an LFS
  object's ``hf`` origin is never a primary label (an LFS pointer and its object used to collide on one label).
  :attr:`StoredRawTree.recorded_context` rebuilds each recorded context tree from the stored objects (a
  :class:`StoredArchive` for an archive context, re-expanded by the importer; :class:`StoredFiles` otherwise), and
  :attr:`StoredRawTree.recorded_pinned_objects` the pinned objects; ``import_source`` uses them when it is given none.

Files the first import walked but never stored (profile excludes, files the pin did not vouch for) cannot be walked
again; their register rows are carried over by ``corpus.derive`` (:meth:`StoredRawTree.unreproducible`).
"""

from __future__ import annotations

import hashlib
import os
import tomllib
from collections.abc import Callable, Collection, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from agentprov.corpus.manifest import origin_matches_pin, sealed_origin_pin
from agentprov.corpus.reader import CorpusReader, CorpusReadError
from agentprov.corpus.register import RegisterEntry
from agentprov.corpus.stages import stage_map, stages_named
from agentprov.errors import AgentProvError, IngestError
from agentprov.raw.origins import Origin

__all__ = ["StoredArchive", "StoredCandidate", "StoredContext", "StoredFiles", "StoredRawTree", "StoredTreeError"]

MEMBER_SEPARATOR: Final = "!/"


class StoredTreeError(AgentProvError):
    """The source corpus's origins cannot be turned into an input tree (``corpus.rawtree.invalid``; exit 1)."""

    code = "corpus.rawtree.invalid"
    exit_code = 1


@dataclass(frozen=True, slots=True)
class StoredCandidate:
    """A candidate artefact (``label``, ``size``, ``origin``): the shape of ``adapters.types.CandidateArtefact``."""

    label: str
    size: int
    origin: Origin


def _pin_leaf(manifest: Mapping[str, Any] | None, snapshot_id: str | None) -> str | None:
    snapshot = _snapshot(manifest, snapshot_id)
    pin = snapshot.get("pin") if snapshot else None
    tree = pin.get("tree") if isinstance(pin, Mapping) else None
    if not isinstance(tree, str) or not tree.strip("/"):
        return None
    return tree.rstrip("/").rsplit("/", 1)[-1]


def _snapshots(manifest: Mapping[str, Any] | None) -> list[Any]:
    """The recorded snapshots of the corpus's one source, in their recorded order (``[]`` when none is recorded)."""
    if not manifest:
        return []
    sources = manifest.get("sources")
    if not isinstance(sources, list) or not sources or not isinstance(sources[0], Mapping):
        return []
    snapshots = sources[0].get("snapshots")
    return list(snapshots) if isinstance(snapshots, list) else []


def snapshot_ids(manifest: Mapping[str, Any] | None) -> list[str]:
    """The recorded snapshot ids in import order (D-202): the order a re-map replays them in."""
    return [str(s["snapshot_id"]) for s in _snapshots(manifest) if isinstance(s, Mapping) and isinstance(s.get("snapshot_id"), str)]


def _snapshot(manifest: Mapping[str, Any] | None, snapshot_id: str | None) -> dict[str, Any] | None:
    snapshots = _snapshots(manifest)
    if not snapshots:
        return None
    for snapshot in snapshots:
        if isinstance(snapshot, Mapping) and (snapshot_id is None or snapshot.get("snapshot_id") == snapshot_id):
            return dict(snapshot)
    return None


@dataclass(frozen=True, slots=True)
class StoredPart:
    """One byte part of a split archive input, read back from the source store (D-249): the importer's part interface."""

    file: str
    sha256: str
    size: int
    origin: Origin


class StoredFiles:
    """A recorded context tree of stored files (D-530): candidates under their recorded labels and origins, re-hashed on
    every read."""

    kind: Final = "stored"
    explicit: Final = False

    def __init__(self, store: Any, entries: Mapping[str, tuple[str, Origin]], candidate_type: Callable[[str, int, Origin], Any],
                 snapshot_origin: Mapping[str, Any] | None) -> None:
        self._store, self._entries, self._candidate_type = store, dict(entries), candidate_type
        self._snapshot_origin = dict(snapshot_origin) if snapshot_origin is not None else None
        self.rejections: list[Any] = []

    def walk(self) -> Iterator[Any]:
        for label in sorted(self._entries, key=lambda item: item.encode("utf-8")):
            sha, origin = self._entries[label]
            yield self._candidate_type(label, self._store.size(sha), origin)

    def read(self, batch: Sequence[Any]) -> Iterator[tuple[Any, bytes | IngestError]]:
        for candidate in batch:
            sha, _origin = self._entries[candidate.label]
            yield candidate, _read_checked(self._store, sha)

    def snapshot_origin(self) -> dict[str, Any] | None:
        return None if self._snapshot_origin is None else dict(self._snapshot_origin)

    def drop(self, absent: Collection[str]) -> None:
        """Leave out the files whose objects are absent on purpose (PR-5)."""
        self._entries = {label: entry for label, entry in self._entries.items() if entry[0] not in absent}


class StoredArchive:
    """A recorded archive context (D-530): the stored container, which the importer stores and expands again exactly as
    an ``ArchiveTree`` (``archive_input``, ``sha256``, ``stream``)."""

    kind: Final = "archive"
    explicit: Final = False
    archive_input: Final = True

    def __init__(self, store: Any, label: str, sha256: str, origin: Origin, candidate_type: Callable[[str, int, Origin], Any],
                 snapshot_origin: Mapping[str, Any] | None) -> None:
        self._store, self.label, self.sha256, self.origin = store, label, sha256, origin
        self._candidate_type = candidate_type
        self._snapshot_origin = dict(snapshot_origin) if snapshot_origin is not None else None
        self.rejections: list[Any] = []

    @property
    def size(self) -> int:
        """Read when the archive is walked or stored, never at construction: a container absent on purpose (purged,
        withheld) is dropped by :meth:`StoredRawTree.drop_absent` before that (PR-5)."""
        return int(self._store.size(self.sha256))

    def walk(self) -> Iterator[Any]:
        yield self._candidate_type(self.label, self.size, self.origin)

    def stream(self, label: str) -> Any:
        return self._store.open(self.sha256)

    def read(self, batch: Sequence[Any]) -> Iterator[tuple[Any, bytes | IngestError]]:
        for candidate in batch:
            yield candidate, _read_checked(self._store, self.sha256)

    def snapshot_origin(self) -> dict[str, Any] | None:
        return None if self._snapshot_origin is None else dict(self._snapshot_origin)


@dataclass(frozen=True, slots=True)
class StoredContext:
    """One recorded context tree of a snapshot (D-530): its role, the profile pin it stood for (``None`` in a manifest
    written before D-530) and the tree rebuilt from the stored objects."""

    role: str
    pin: Mapping[str, Any] | None
    tree: StoredFiles | StoredArchive


def _read_checked(store: Any, sha: str) -> bytes:
    try:
        with store.open(sha) as stream:
            data = stream.read()
    except KeyError:
        raise StoredTreeError("a listed object is not in the source store", code="raw.object.missing") from None
    if hashlib.sha256(data).hexdigest() != sha:
        raise StoredTreeError("a stored object does not hash to its address", code="raw.digest.mismatch")
    return bytes(data)


class StoredRawTree:
    """The raw store of a source corpus as an import ``SourceTree`` (see the module docstring)."""

    kind: Final = "stored"
    explicit: Final = False

    def __init__(
        self,
        reader: CorpusReader,
        *,
        snapshot_id: str | None = None,
        label_of: Callable[[Origin], str | None] | None = None,
        candidate_type: Callable[[str, int, Origin], Any] = StoredCandidate,
    ) -> None:
        self.reader = reader
        self.manifest = reader.manifest()
        snapshot = _snapshot(self.manifest, snapshot_id)
        self.snapshot_id = snapshot_id or (str(snapshot["snapshot_id"]) if snapshot and "snapshot_id" in snapshot else None)
        self._snapshot = snapshot
        self._leaf = _pin_leaf(self.manifest, self.snapshot_id)
        self._label_of = label_of
        self._candidate_type = candidate_type
        self._store = reader.raw_store()
        self.rejections: list[Any] = []
        #: D-380 review: the ``selection_sha256`` of every recorded ``expand`` stage and the recorded source-profile digest;
        #: the importer refuses to re-expand an archive input with a selection the source did not record
        stages = stage_map(reader.derivation())
        self.recorded_expand_selections = frozenset(
            str(d.get("selection_sha256")) for d in stages_named(stages, "expand") if d.get("selection_sha256"))
        aer = stages.get("aer")
        self.recorded_profile_sha256 = aer.get("profile_sha256") if isinstance(aer, Mapping) else None
        entries: dict[str, tuple[str, Origin]] = {}
        pin = snapshot.get("pin") if snapshot else None
        several = len(_snapshots(self.manifest)) > 1
        # D-530: a snapshot with context trees or pinned objects keeps out of its primary inputs the exact origins of
        # its pinned objects, the origins a recorded context pin vouched for, and (when it records a pin) every origin
        # its own pin did not vouch for
        per_unit = bool(snapshot and (snapshot.get("context") or snapshot.get("pinned_objects")))
        pinned_keys = {Origin.from_json(o["origin"]).canonical() for o in (snapshot or {}).get("pinned_objects") or ()
                       if isinstance(o, Mapping) and isinstance(o.get("origin"), Mapping)}
        #: D-221: a sealed manifest records no pins; a context tree's objects are then told apart by its sealed origin
        self._sealed = bool((self.manifest or {}).get("sealed"))
        if not isinstance(pin, Mapping) and self._sealed and snapshot:
            # ultra raw-withhold #2: so is the snapshot's own (D-202: a multi-snapshot corpus kept no candidates)
            pin = sealed_origin_pin(snapshot.get("origin"))
            sealed_origin = snapshot.get("origin")
            if isinstance(sealed_origin, Mapping) and sealed_origin.get("kind") == "corpus":
                self._leaf = self._sealed_corpus_leaf(sealed_origin)
        role_pins = [match for c in (snapshot or {}).get("context") or () if isinstance(c, Mapping)
                     for match in (self._role_match(c),) if match is not None]
        by_pin = several or (per_unit and isinstance(pin, Mapping))
        others: list[tuple[str, Origin]] = []  # (sha256, origin) of the non-member origins kept out of the primary inputs
        vouched: dict[str, list[Origin]] = {}  # sha256 -> the non-member origins this snapshot's pin vouched for
        for row in reader.origins():
            origin = row.origin
            if origin.kind in ("member", "carved"):  # derived objects: re-derived by expand / the mapper, never walked
                continue
            data = {"kind": origin.kind, **origin.data}
            if (origin.canonical() in pinned_keys or any(origin_matches_pin(data, rp) for rp in role_pins)
                    or (by_pin and not origin_matches_pin(data, pin if isinstance(pin, Mapping) else None))):
                others.append((row.sha256, origin))
                continue  # D-202: an origin of another snapshot; D-530: a context file or a pinned object
            vouched.setdefault(row.sha256, []).append(origin)
            label = self.label_for(origin)
            if label is None:
                raise StoredTreeError(f"an origin of kind {origin.kind} names no input label; the corpus cannot be re-mapped")
            previous = entries.get(label)
            if previous is not None and previous[0] != row.sha256:
                raise StoredTreeError("two stored objects claim one input label; the corpus cannot be re-mapped")
            if previous is None or origin.canonical() < previous[1].canonical():
                entries[label] = (row.sha256, origin)
        self._entries = dict(sorted(entries.items(), key=lambda item: item[0].encode("utf-8")))
        self.recorded_pinned_objects = self._pinned(snapshot)
        self.recorded_context = self._context(snapshot, others) if per_unit else []
        #: D-221 (NF-29): the context roles the recorded import skipped (``--no-context``); a re-map skips them too.
        self.recorded_context_skipped = sorted(str(r) for r in (snapshot or {}).get("context_skipped") or ())
        recorded = (snapshot or {}).get("input")
        #: D-200: the snapshot was imported from one archive input (``import_source`` expands it again).
        self.archive_input = isinstance(recorded, Mapping) and recorded.get("kind") == "archive"
        #: D-249: the byte parts of a split archive input, in their recorded order (``None`` otherwise).
        self.archive_parts: list[StoredPart] | None = None
        if self.archive_input:
            assert isinstance(recorded, Mapping)
            label, digest = recorded.get("label"), str(recorded.get("sha256", "")).removeprefix("sha256:")
            found = next((entry for entry in self._entries.values() if entry[0] == digest), None)
            if not isinstance(label, str) or found is None:
                raise StoredTreeError("the recorded archive input is not a stored object; the corpus cannot be re-mapped")
            self._entries = {label: found}
            if recorded.get("parts") is not None:
                self.archive_parts = self._parts(recorded["parts"], vouched)

    def _parts(self, recorded: object, vouched: Mapping[str, Sequence[Origin]]) -> list[StoredPart]:
        """The recorded parts of a split archive input, each a stored object with an origin its pin vouched for."""
        if not isinstance(recorded, Sequence) or isinstance(recorded, str) or len(recorded) < 2:
            raise StoredTreeError("the recorded split archive input lists no parts; the corpus cannot be re-mapped")
        parts = []
        for part in recorded:
            sha = str(part.get("sha256", "")).removeprefix("sha256:") if isinstance(part, Mapping) else ""
            origins = sorted(vouched.get(sha, ()), key=lambda o: o.canonical())
            if not isinstance(part, Mapping) or not origins or not isinstance(part.get("file"), str):
                raise StoredTreeError("a recorded split part has no stored object with a pinned origin; the corpus cannot "
                                      "be re-mapped")
            parts.append(StoredPart(str(part["file"]), sha, self._store.size(sha), origins[0]))
        return parts

    def _pinned(self, snapshot: Mapping[str, Any] | None) -> list[dict[str, Any]]:
        """D-530: the recorded pinned objects (runner item R3) as ``{label, origin, sha256, size, path}`` rows. ``path`` is
        ``None`` for an object the store lacks: :meth:`drop_absent` drops it when it is absent on purpose and refuses it
        otherwise (PR-5)."""
        out = []
        for row in (snapshot or {}).get("pinned_objects") or ():
            sha = str(row.get("sha256", "")).removeprefix("sha256:") if isinstance(row, Mapping) else ""
            if not isinstance(row, Mapping) or not sha or not isinstance(row.get("origin"), Mapping):
                raise StoredTreeError("a recorded pinned object names no stored object; the corpus cannot be re-mapped")
            path = self._locate(sha)
            out.append({"label": str(row["label"]), "origin": Origin.from_json(row["origin"]), "sha256": sha,
                        "size": int(row["bytes"]), "path": None if path is None else str(path)})
        return out

    def drop_absent(self, absent: Collection[str]) -> None:
        """PR-5 (BF-20, CB-6 for per-unit inputs): leave out the context files, context archives and pinned objects that
        are absent on purpose (``absent``: hex digests), so the re-map runs without them; the executions that need them
        are reported unverified by ``corpus.derive``. An object that is missing and not accounted for is refused."""
        self.recorded_pinned_objects = [o for o in self.recorded_pinned_objects if o["sha256"] not in absent]
        if any(o["path"] is None for o in self.recorded_pinned_objects):
            raise StoredTreeError("a recorded pinned object is not in the source store", code="raw.object.missing")
        kept: list[StoredContext] = []
        for context in self.recorded_context:
            tree = context.tree
            if isinstance(tree, StoredArchive):
                if tree.sha256 in absent:
                    # the role's units are re-mapped without it (they need the container, so they are unverified); the
                    # re-mapped snapshot records the role as skipped (D-221 context_skipped; RC-13)
                    self.recorded_context_skipped = sorted({*self.recorded_context_skipped, context.role})
                    continue
            else:
                tree.drop(absent)
            kept.append(context)
        self.recorded_context = kept

    def _locate(self, sha: str) -> Any:
        """The path of the stored object ``sha`` (a regular file of its shard, never a link), or ``None``. Read here and not
        through ``raw.store`` so that no ``expand`` stage digest moves (``raw/store.py`` is an ``EXPAND_MODULES`` file)."""
        shard = Path(self._store.objects_dir) / sha[:2]
        if len(sha) != 64 or not shard.is_dir() or shard.is_symlink():
            return None
        with os.scandir(shard) as it:
            names = sorted(e.name for e in it if e.name.startswith(sha + ".") and e.is_file(follow_symlinks=False))
        return shard / names[0] if len(names) == 1 else None

    def _sealed_corpus_leaf(self, origin: Mapping[str, Any]) -> str | None:
        """Ultra raw-withhold #3: the pin tree's leaf of a sealed snapshot with a ``corpus`` origin. The working pin is
        not sealed (D-221) and the sealed ``corpus`` origin keeps no tree (H.2.3), but the pin is one of the
        ``[[source.pins]]`` of the source profile the corpus records (``rules/<profile>.profile.toml``, whose digest
        ``package`` checked against the working manifest's): the pins at the origin's producer commit, narrowed to the
        one whose ``part`` or ``role`` is the snapshot id, else the corpus's recorded parts (the import's pin choice).
        Pins that leave more than one leaf cannot be told apart: refused, never guessed."""
        sources = (self.manifest or {}).get("sources")
        source = sources[0] if isinstance(sources, list) and sources and isinstance(sources[0], Mapping) else {}
        ref = source.get("profile")
        path, digest = (ref.get("path"), ref.get("sha256")) if isinstance(ref, Mapping) else (None, None)
        if not isinstance(path, str) or not isinstance(digest, str):
            raise StoredTreeError("the sealed corpus records no source profile, so the tree of its corpus origins is unknown")
        try:
            data = self.reader.read_bytes(path)
        except AgentProvError as exc:
            raise StoredTreeError(f"the recorded source profile cannot be read ({exc.code})") from None
        if "sha256:" + hashlib.sha256(data).hexdigest() != digest:
            raise StoredTreeError("the recorded source profile does not match its recorded digest")
        try:
            doc = tomllib.loads(data.decode("utf-8"))
        except (tomllib.TOMLDecodeError, UnicodeDecodeError):
            raise StoredTreeError("the recorded source profile is not valid UTF-8 TOML") from None
        table = doc.get("source")
        pins = table.get("pins") if isinstance(table, Mapping) else None
        commit = origin.get("producer_commit")
        vouching = [p for p in pins if isinstance(p, Mapping) and p.get("commit") == commit] if isinstance(pins, list) else []
        parts = {p for p in source.get("parts") or () if isinstance(p, str)}
        chosen = ([p for p in vouching if self.snapshot_id in (p.get("part"), p.get("role"))]
                  or [p for p in vouching if p.get("part") in parts or p.get("role") in parts] or vouching)
        leaves = {tree.rstrip("/").rsplit("/", 1)[-1] for p in chosen for tree in (p.get("tree"),)
                  if isinstance(tree, str) and tree.strip("/")}
        if len(leaves) > 1:
            raise StoredTreeError("the recorded source profile pins several trees at the snapshot's commit; the corpus "
                                  "cannot be re-mapped")
        return next(iter(leaves), None)

    def _role_match(self, entry: Mapping[str, Any]) -> Mapping[str, Any] | None:
        """What a context tree's objects are matched by: its recorded pin, or, in a sealed manifest (which records none;
        D-221), the fields of its sealed origin (:func:`agentprov.corpus.manifest.sealed_origin_pin`)."""
        if isinstance(entry.get("pin"), Mapping):
            return entry["pin"]
        return sealed_origin_pin(entry.get("origin")) if self._sealed else None

    def _context(self, snapshot: Mapping[str, Any] | None, others: Sequence[tuple[str, Origin]]) -> list[StoredContext]:
        """D-530: each recorded context tree rebuilt from the stored objects. A role's objects are the origins its
        recorded pin vouched for; a manifest written before D-530 records no pin, and then the one recorded role takes
        every origin that neither the snapshot's pin nor a pinned object accounts for (several roles cannot be told
        apart: refused)."""
        recorded = [c for c in (snapshot or {}).get("context") or () if isinstance(c, Mapping) and isinstance(c.get("role"), str)]
        pinned = {(row["sha256"], row["origin"].canonical()) for row in self.recorded_pinned_objects}
        loose = [(sha, o) for sha, o in others if (sha, o.canonical()) not in pinned]
        out: list[StoredContext] = []
        for entry in recorded:
            role_pin = entry.get("pin") if isinstance(entry.get("pin"), Mapping) else None
            match = self._role_match(entry)
            if match is None and len(recorded) > 1:
                raise StoredTreeError("several recorded context trees name no pin; the corpus cannot be re-mapped")
            mine = loose if match is None else [
                (sha, o) for sha, o in others if origin_matches_pin({"kind": o.kind, **o.data}, match)]
            origin = entry.get("origin") if isinstance(entry.get("origin"), Mapping) else None
            archive = entry.get("input") if isinstance(entry.get("input"), Mapping) else None
            if archive is not None and archive.get("kind") == "archive":
                digest = str(archive.get("sha256", "")).removeprefix("sha256:")
                found = next((o for sha, o in mine if sha == digest), None)
                if found is None or not isinstance(archive.get("label"), str):
                    raise StoredTreeError("a recorded context archive is not a stored object; the corpus cannot be re-mapped")
                tree: StoredFiles | StoredArchive = StoredArchive(self._store, str(archive["label"]), digest, found,
                                                                  self._candidate_type, origin)
            else:
                files: dict[str, tuple[str, Origin]] = {}
                for sha, o in mine:
                    label = self.label_for(o)
                    if label is None or (label in files and files[label][0] != sha):
                        raise StoredTreeError("a recorded context file has no label of its own; the corpus cannot be re-mapped")
                    if label not in files or o.canonical() < files[label][1].canonical():
                        files[label] = (sha, o)
                tree = StoredFiles(self._store, files, self._candidate_type, origin)
            out.append(StoredContext(str(entry["role"]), role_pin, tree))
        return out

    def open_part(self, part: StoredPart) -> Any:
        """A part's stored bytes (the importer re-hashes them while storing and compares the digest)."""
        try:
            return self._store.open(part.sha256)
        except KeyError:
            raise StoredTreeError("a recorded split part is not in the source store", code="raw.object.missing") from None

    # -------------------------------------------------------------------------------------- labels
    def label_for(self, origin: Origin) -> str | None:
        """The input label of a stored object with ``origin`` (see the module docstring)."""
        if self._label_of is not None:
            label = self._label_of(origin)
            if label is not None:
                return label
        data = origin.data
        if origin.kind == "git":
            return str(data["path"])
        if origin.kind == "corpus":
            path = str(data["path"])
            if self._leaf is not None and path.startswith(self._leaf + "/"):
                return path[len(self._leaf) + 1 :]
            return path
        if origin.kind in ("hf", "zenodo"):
            return str(data.get("path") or data.get("file"))
        if origin.kind == "split":  # D-249: a split descriptor is labelled with its logical archive
            return str(data["label"])
        if origin.kind == "url":  # D-455: a URL archive input (relabelled with its recorded label below)
            return str(data["url"])
        return None

    @property
    def labels(self) -> tuple[str, ...]:
        return tuple(self._entries)

    def restrict(self, labels: Collection[str]) -> None:
        """Keep only the candidates ``labels`` (``verify --level rederive --sample``: the inputs of the sampled
        executions). The order stays the sorted label order; an unknown label is ignored."""
        wanted = set(labels)
        self._entries = {label: entry for label, entry in self._entries.items() if label in wanted}

    def labels_of(self, sha256: str) -> tuple[str, ...]:
        """The input labels whose stored object is ``sha256`` (hex)."""
        return tuple(label for label, (sha, _) in self._entries.items() if sha == sha256)

    def sha256_of(self, label: str) -> str:
        return self._entries[label][0]

    # -------------------------------------------------------------------------------------- SourceTree
    def walk(self) -> Iterator[Any]:
        for label, (sha, origin) in self._entries.items():
            try:
                size = self._store.size(sha)
            except KeyError:
                raise StoredTreeError("an object the origins list is not in the source store") from None
            yield self._candidate_type(label, size, origin)

    def open(self, label: str, *, max_bytes: int | None = None) -> bytes:
        sha, _origin = self._entries[label]
        try:
            with self._store.open(sha) as stream:
                data = stream.read()
        except KeyError:
            raise StoredTreeError("a listed object is not in the source store", code="raw.object.missing") from None
        if hashlib.sha256(data).hexdigest() != sha:
            raise StoredTreeError("a stored object does not hash to its address", code="raw.digest.mismatch")
        if max_bytes is not None and len(data) > max_bytes:
            raise IngestError("ingest.size.file", "a stored object exceeds the limit", limit=max_bytes)
        return data

    def read(self, batch: Sequence[Any]) -> Iterator[tuple[Any, bytes | IngestError]]:
        for candidate in batch:
            try:
                yield candidate, self.open(candidate.label)
            except IngestError as exc:
                yield candidate, exc

    def snapshot_origin(self) -> dict[str, Any] | None:
        """The snapshot origin recorded in the source manifest (never a new local path)."""
        origin = self._snapshot.get("origin") if self._snapshot else None
        return dict(origin) if isinstance(origin, Mapping) else None

    # -------------------------------------------------------------------------------------- carried register rows
    def unreproducible(self, entries: Sequence[RegisterEntry]) -> list[RegisterEntry]:
        """The register rows a re-map cannot reproduce: path subjects of this snapshot whose file (or container, for a
        member path ``<container>!/<member>``) is not a stored input label (excludes, files the pin did not vouch for),
        and path subjects of a snapshot the manifest does not record. In a corpus with several snapshots each snapshot's
        tree answers for its own rows (D-202); the caller takes the union."""
        labels = set(self._entries)
        others = set(snapshot_ids(self.manifest)) - {self.snapshot_id}
        out: list[RegisterEntry] = []
        for entry in entries:
            subject = entry.subject
            if set(subject) != {"snapshot_id", "path"}:
                continue
            if self.snapshot_id is not None and subject["snapshot_id"] != self.snapshot_id:
                if subject["snapshot_id"] not in others:  # another recorded snapshot's tree decides about its own rows
                    out.append(entry)
                continue
            if subject["path"].split(MEMBER_SEPARATOR, 1)[0] not in labels:
                out.append(entry)
        return out


def check_reader(reader: CorpusReader) -> None:
    """Fail early when the source has no raw store (a re-map needs one)."""
    try:
        reader.raw_store()
    except (CorpusReadError, AgentProvError) as exc:
        raise StoredTreeError(f"the source corpus has no readable raw store ({exc.code})") from None
