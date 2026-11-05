"""Local estimate priors from the user's sealed corpora: which corpora, and reading them (D-1062).

The pure part (the rows, the document, the labels) is :mod:`agentprov.estimate.localpriors`; this module reads the
corpora, which sit above the estimate's layer, for ``agentprov priors build``.

**Which corpora.** :func:`discover` takes every **sealed** corpus under ``$AGENTPROV_HOME/corpora``, the highest
``corpus_version`` of each corpus id; a working ``.partial`` tree, a symbolic link and anything that is not a sealed
corpus are skipped and named in ``built_from.skipped``, and a ``.withheld`` sidecar is never opened. :func:`check_given`
takes the ``--corpus`` directories instead: each must be sealed, and no corpus id may come twice. A discovered corpus
that turns out unreadable as a whole while it is read (a damaged index or ``WITHHELD.json``) adds nothing and is named
in ``built_from.skipped``; a ``--corpus`` one refuses the build, naming its number.

**Reading.** Every corpus is read through :class:`agentprov.corpus.reader.CorpusReader`, which never writes: the index
is streamed, and each execution's AER is read and verified against its index row (the D9 chain), in worker processes
when ``jobs`` > 1, with at most four tasks per worker in flight. A sealed corpus has already removed its withheld
executions from the index; an execution that ``WITHHELD.json`` names is skipped all the same. An execution read in an
earlier corpus (the same ``ex`` id: a corpus derived from another, or a copy) counts once; one whose AER could not be
read there is not "seen", so a readable copy later still counts. Only counts leave a worker;
an execution whose labels are not plain is counted as ``unlabelled`` and left out. The executions are counted in index
order and every quantile is order-free, so ``jobs`` never changes the bytes.

Outside every stage closure (class 0): nothing here writes to a corpus or feeds AER, SEM, PROV or a corpus.
"""

from __future__ import annotations

import hashlib
from collections import deque
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from concurrent.futures import Future, ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

from agentprov.errors import AgentProvError
from agentprov.estimate.localpriors import PriorsBuildError, label, local_document, plain_labels
from agentprov.estimate.usage import ExecutionUsage, usage_from_records

__all__ = ["build_local", "check_given", "discover"]

#: executions per worker task
CHUNK: Final = 32


def _version_key(version: str | None) -> tuple[int, ...]:
    parts = (version or "").split(".")
    return tuple(int(p) for p in parts) if all(p.isdigit() for p in parts) else ()


@dataclass(frozen=True, slots=True)
class _Corpus:
    path: Path
    corpus_id: str | None
    version: str | None


def _open_sealed(path: Path) -> tuple[_Corpus | None, str]:
    """``(corpus, "")`` for a sealed corpus, else ``(None, reason)``."""
    from agentprov.corpus.reader import CorpusNotFoundError, CorpusReader

    try:
        reader = CorpusReader.open(path)
    except CorpusNotFoundError:
        return None, "not a corpus"
    except AgentProvError as exc:
        return None, f"unreadable ({exc.code})"
    if not reader.sealed:
        return None, "working (not sealed)"
    manifest = reader.manifest() or {}
    return _Corpus(reader.root, label(manifest.get("corpus_id")), label(manifest.get("corpus_version"))), ""


def _rank(corpus: _Corpus) -> tuple[tuple[int, ...], bool, str]:
    """The higher version first; of two copies of one version, not a ``.pre-`` copy, then the later name."""
    return _version_key(corpus.version), ".pre-" not in corpus.path.name, corpus.path.name


def discover(corpora_root: Path) -> tuple[list[Path], list[dict[str, Any]]]:
    """The sealed corpora under ``corpora_root`` (one per corpus id: the highest version) and the directories skipped,
    each ``{"name", "reason"}`` (a name that is not a plain label is recorded as ``null``)."""
    try:
        children = sorted(p for p in Path(corpora_root).iterdir() if p.is_dir())
    except OSError:
        return [], []
    found: list[_Corpus] = []
    skipped: list[dict[str, Any]] = []
    for child in children:
        if child.name.endswith(".withheld"):  # a sealed corpus's private sidecar: never read
            continue
        if child.is_symlink():  # name it with --corpus to read it
            skipped.append({"name": label(child.name), "reason": "a symbolic link"})
            continue
        if child.name.endswith(".partial"):
            skipped.append({"name": label(child.name), "reason": "working (not sealed)"})
            continue
        corpus, why = _open_sealed(child)
        if corpus is None:
            skipped.append({"name": label(child.name), "reason": why})
        else:
            found.append(corpus)
    best: dict[str, _Corpus] = {}
    for corpus in found:
        key = corpus.corpus_id or f"\0{corpus.path.name}"  # without a usable id, each directory stands alone
        held = best.get(key)
        if held is None or _rank(corpus) > _rank(held):
            if held is not None:
                skipped.append({"name": label(held.path.name), "reason": "an older version of a corpus read"})
            best[key] = corpus
        else:
            skipped.append({"name": label(corpus.path.name), "reason": "an older version of a corpus read"})
    skipped.sort(key=lambda s: (s["name"] or "", s["reason"]))
    return sorted(c.path for c in best.values()), skipped


def check_given(paths: Sequence[Path]) -> list[Path]:
    """The corpora named on the command line: each must be sealed, and no corpus id may come twice (its executions
    would count twice). :class:`PriorsBuildError` otherwise."""
    out: list[Path] = []
    ids: dict[str, int] = {}
    for n, path in enumerate(paths, 1):
        corpus, why = _open_sealed(Path(path))
        if corpus is None:
            raise PriorsBuildError(f"--corpus number {n} is not a sealed corpus: {why}")
        if corpus.corpus_id is not None:
            if corpus.corpus_id in ids:
                raise PriorsBuildError(f"--corpus numbers {ids[corpus.corpus_id]} and {n} are one corpus "
                                       f"({corpus.corpus_id}): its executions would count twice")
            ids[corpus.corpus_id] = n
        out.append(corpus.path)
    return out


# ------------------------------------------------------------------------------------------------ reading
@dataclass(frozen=True, slots=True)
class _RowRef:
    """What :meth:`CorpusReader.read_aer` reads of an index row (a worker gets these, not the whole row)."""

    ex: str
    aer_path: str
    aer_digest: str


def _read_chunk(task: tuple[str, tuple[_RowRef, ...]]) -> list[tuple[str, ExecutionUsage | None]]:
    """A worker's task: the counts of a few executions of one sealed corpus, each beside its ``ex`` id (``None``:
    unreadable, never repaired)."""
    from agentprov.corpus.index import IndexRow
    from agentprov.corpus.reader import SEALED, CorpusReader

    root, refs = task
    reader = CorpusReader(root, state=SEALED)
    out: list[tuple[str, ExecutionUsage | None]] = []
    for ref in refs:
        try:
            document = reader.read_aer(cast(IndexRow, ref))
        except AgentProvError:
            out.append((ref.ex, None))
            continue
        out.append((ref.ex, usage_from_records(document.records)))
    return out


def _ordered_map[T, R](fn: Callable[[T], R], items: Iterable[T], jobs: int) -> Iterator[R]:
    """``map(fn, items)`` in order, over ``jobs`` processes with at most ``4 * jobs`` tasks in flight (bounded memory)."""
    if jobs <= 1:
        yield from map(fn, items)
        return
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        window: deque[Future[R]] = deque()
        for item in items:
            window.append(pool.submit(fn, item))
            if len(window) >= 4 * jobs:
                yield window.popleft().result()
        while window:
            yield window.popleft().result()


def _read_corpus(path: Path, jobs: int, seen: set[str], usages: list[ExecutionUsage]) -> dict[str, Any]:
    """Append the counts of one sealed corpus's executions to ``usages`` and their ``ex`` ids to ``seen``; returns its
    ``built_from`` entry. Both are extended only when the whole corpus was read (a corpus that fails part way adds
    nothing), and an ``ex`` is marked seen only once its AER was read, so an unreadable copy never hides a readable one
    in a later corpus (AU-NC-103)."""
    from agentprov.corpus.layout import MANIFEST, WITHHELD
    from agentprov.corpus.reader import CorpusReader
    from agentprov.corpus.withheld import decode_withheld

    reader = CorpusReader.open(path)
    if not reader.sealed:  # checked when chosen; a corpus unsealed since then is refused, never read as working
        raise PriorsBuildError("a corpus is no longer sealed")
    manifest = reader.manifest() or {}
    withheld = {e.ex for e in decode_withheld(reader.read_bytes(WITHHELD), reader.limits).executions} \
        if reader.exists(WITHHELD) else set()
    # withheld: the executions WITHHELD.json lists (sealing removed them from the index; one still indexed is skipped)
    counts = {"executions_indexed": 0, "withheld": len(withheld), "duplicates": 0}

    def refs() -> Iterator[_RowRef]:
        for row in reader.iter_index():
            counts["executions_indexed"] += 1
            if row.ex in withheld:
                continue
            if row.ex in seen:
                counts["duplicates"] += 1
            else:
                yield _RowRef(row.ex, row.aer_path, row.aer_digest)

    def chunks() -> Iterator[tuple[str, tuple[_RowRef, ...]]]:
        batch: list[_RowRef] = []
        for ref in refs():
            batch.append(ref)
            if len(batch) == CHUNK:
                yield str(reader.root), tuple(batch)
                batch = []
        if batch:
            yield str(reader.root), tuple(batch)

    read = unreadable = unlabelled = 0
    got: list[ExecutionUsage] = []
    got_ex: set[str] = set()
    for results in _ordered_map(_read_chunk, chunks(), jobs):
        for ex, u in results:
            if u is None:
                unreadable += 1
                continue
            got_ex.add(ex)  # read: a later copy of it is a duplicate
            if not plain_labels(u):
                unlabelled += 1
            else:
                got.append(u)
                read += 1
    entry = {"name": label(reader.root.name), "corpus_id": label(manifest.get("corpus_id")),
             "corpus_version": label(manifest.get("corpus_version")),
             "manifest_sha256": hashlib.sha256(reader.read_bytes(MANIFEST)).hexdigest(), **counts,
             "executions_read": read, "unreadable": unreadable, "unlabelled": unlabelled}
    seen.update(got_ex)
    usages.extend(got)
    return entry


def build_local(paths: Sequence[Path], *, jobs: int = 1, min_executions: int = 5,
                skipped: Sequence[Mapping[str, Any]] = (), given: bool = False) -> tuple[bytes, dict[str, Any]]:
    """The local priors document of the sealed corpora ``paths`` (in this order) and its ``built_from``.

    A corpus that cannot be read as a whole (a damaged index or ``WITHHELD.json``, or no longer sealed) is skipped and
    named in ``built_from.skipped`` (``unreadable (<code>)``) when the corpora were discovered (AU-NC-102: like any
    other directory :func:`discover` cannot use); when they were ``given`` (``--corpus``), the build is refused naming
    its ``--corpus`` number, as :func:`check_given` refuses a corpus that is not sealed."""
    usages: list[ExecutionUsage] = []
    seen: set[str] = set()
    corpora: list[dict[str, Any]] = []
    dropped = list(skipped)
    for n, p in enumerate(paths, 1):
        try:
            corpora.append(_read_corpus(Path(p), max(1, jobs), seen, usages))
        except AgentProvError as exc:
            name = label(Path(p).name)
            why = "working (not sealed)" if isinstance(exc, PriorsBuildError) else f"unreadable ({exc.code})"
            if given:
                raise PriorsBuildError(f"--corpus number {n}{f' ({name})' if name else ''} is not readable as a "
                                       f"sealed corpus: {why}") from exc
            dropped.append({"name": name, "reason": why})
    if len(dropped) != len(skipped):
        dropped.sort(key=lambda s: (s["name"] or "", s["reason"]))
    return local_document(usages, corpora, dropped, min_executions)
