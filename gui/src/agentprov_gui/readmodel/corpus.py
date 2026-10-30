"""Corpus discovery and summaries (design §6.1 "Corpora list"). No Qt here.

A configured root (by default ``~/.agentprov/corpora``) is listed one level deep. Each ``DIR`` or ``DIR.partial`` found is
resolved by the core's N.1.5 rule (:func:`agentprov.corpus.reader.resolve_corpus`) and its ``corpus.json`` is read
through :class:`~agentprov.corpus.reader.CorpusReader` (strict, format-checked, no link followed). Nothing is written and
no lock is taken: a writer's ``.agentprov.lock`` is only observed (``lstat``), never opened, so a CLI job is never blocked.

Every string kept here is data from the corpus and is escaped by the view before display.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from agentprov.corpus.layout import LOCK, MANIFEST, PARTIAL_SUFFIX
from agentprov.corpus.reader import SEALED, CorpusReader, resolve_corpus
from agentprov.errors import AgentProvError
from agentprov.ingest.limits import IngestLimits

__all__ = ["CorpusSummary", "discover", "summarise"]

UNREADABLE: Final = "unreadable"
#: corpus.json is one JSON document: a larger file is refused by its size before it is read (GR-35). The default
#: ``max_artefact_bytes`` (2 GiB) would let discovery read it whole on the UI thread before the JSON limit refused it.
_MANIFEST_LIMITS: Final = IngestLimits().replace(max_artefact_bytes=IngestLimits().max_json_bytes)


@dataclass(frozen=True, slots=True)
class CorpusSummary:
    """One corpus as the Corpora list shows it."""

    path: Path  # the final DIR (what ``--corpus`` names)
    root: Path | None  # the tree read (DIR or DIR.partial); None when unreadable
    state: str  # sealed | working | unreadable
    writing: bool  # a writer's lock is present in the working tree ("being written")
    corpus_id: str | None
    corpus_version: str | None
    executions: int | None
    content_digest: str | None
    mode: str | None  # import | live (the manifest's mode)
    release: bool | None
    error: str | None = None  # a closed error code from the core, never corpus text
    prov_conformance: str | None = None  # the manifest's validation.prov_conformance ("skipped" after G2c-5)

    @property
    def name(self) -> str:
        return self.path.name


def _lock_present(root: Path) -> bool:
    try:
        return stat.S_ISREG(os.lstat(root / LOCK).st_mode)
    except OSError:
        return False


def _str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def summarise(path: Path) -> CorpusSummary:
    """The summary of the corpus that ``path`` names (``DIR`` or ``DIR.partial``); never raises for a bad corpus."""
    final = path.with_name(path.name[: -len(PARTIAL_SUFFIX)]) if path.name.endswith(PARTIAL_SUFFIX) else path
    try:
        location = resolve_corpus(final, limits=_MANIFEST_LIMITS)
        reader = CorpusReader(location.root, state=location.state, used_partial=location.used_partial,
                              limits=_MANIFEST_LIMITS)
        manifest = reader.manifest() or {}
    except AgentProvError as exc:
        return CorpusSummary(final, None, UNREADABLE, False, None, None, None, None, None, None, exc.code)
    counts = manifest.get("counts")
    executions = _int(counts.get("executions")) if isinstance(counts, dict) else None
    release = manifest.get("release")
    return CorpusSummary(
        path=final,
        root=location.root,
        state=location.state,
        writing=location.state != SEALED and _lock_present(location.root),
        corpus_id=_str(manifest.get("corpus_id")),
        corpus_version=_str(manifest.get("corpus_version")),
        executions=executions,
        content_digest=_str(manifest.get("content_digest")),
        mode=_str(manifest.get("mode")),
        release=release if isinstance(release, bool) else None,
        prov_conformance=_str(validation.get("prov_conformance")) if isinstance(
            validation := manifest.get("validation"), dict) else None,
    )


def _candidates(root: Path) -> list[Path]:
    """Final ``DIR`` names below ``root``: every ``X.partial`` directory gives ``X``; a directory with ``corpus.json``
    gives itself. Links are not followed."""
    finals: set[str] = set()
    try:
        entries = list(os.scandir(root))
    except OSError:
        return []
    for entry in entries:
        try:
            if not entry.is_dir(follow_symlinks=False):
                continue
        except OSError:
            continue
        name = entry.name
        if name.startswith("."):
            continue
        if name.endswith(PARTIAL_SUFFIX) and len(name) > len(PARTIAL_SUFFIX):
            finals.add(name[: -len(PARTIAL_SUFFIX)])
            continue
        try:
            if stat.S_ISREG(os.lstat(Path(entry.path) / MANIFEST).st_mode):
                finals.add(name)
        except OSError:
            continue
    return [root / name for name in sorted(finals)]


def discover(roots: Iterable[Path]) -> list[CorpusSummary]:
    """Every corpus one level below each root, sorted by root then name."""
    out: list[CorpusSummary] = []
    for root in roots:
        out.extend(summarise(path) for path in _candidates(root))
    return out
