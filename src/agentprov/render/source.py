"""Reading a corpus for ``agentprov render``: strict and read-only (MN N.2.13; G.8.6 common rules; HL consumers).

``render`` is a consumer: it opens files below the corpus root through ``agentprov.ingest.paths`` (no-follow, regular
files only, size-limited), parses them with the strict loaders under ``IngestLimits`` and never writes. The files are
AgentPROV-format files, but a downloaded corpus is untrusted, so nothing here trusts a recorded path: a path from an
index row is recomputed from the layout and compared before it is opened.

* ``executions.jsonl`` is decoded by :func:`agentprov.corpus.index.decode_index` (strict JSONL, sorted, canonical);
* ``corpus.json`` gives the corpus id and whether it is sealed; it is optional for a bare working tree;
* an execution's PROV-JSON is ``prov/<spec_dir>/<ss>/<ex>.prov.json``; its AER header (line 0) is read for ``--select``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from agentprov.corpus.index import IndexRow, decode_index
from agentprov.corpus.layout import PARTIAL_SUFFIX, CorpusLayout
from agentprov.errors import AgentProvError, IngestError
from agentprov.ingest.limits import IngestLimits, prov_document_limits
from agentprov.ingest.loaders import strict_json_loads
from agentprov.ingest.paths import open_evidence
from agentprov.render.errors import RenderCorpusError

__all__ = ["SPEC_ID", "CorpusSource", "locate_corpus", "open_corpus", "prov_label", "read_aer_header", "read_prov_document"]

SPEC_ID: Final = "agentprov-prov/0.1"
_LIMITS: Final = IngestLimits()


@dataclass(frozen=True, slots=True)
class CorpusSource:
    """An opened corpus: its root, identity and execution index (read once)."""

    root: Path
    corpus_id: str | None
    state: str  # sealed | working
    rows: tuple[IndexRow, ...]
    used_partial: bool  # the given path did not exist but ``<path>.partial`` did

    def layout(self, depth: int) -> CorpusLayout:
        return CorpusLayout(self.root, shard_depth=depth)


def _read(root: Path, label: str, limits: IngestLimits = _LIMITS) -> bytes:
    try:
        with open_evidence(root, label, limits) as stream:
            return stream.read()
    except IngestError as exc:
        raise RenderCorpusError(f"{label}: cannot be read ({exc.code})", code="render.corpus_unreadable") from None
    except OSError as exc:
        raise RenderCorpusError(f"{label}: cannot be read ({type(exc).__name__})", code="render.corpus_unreadable") from None


def locate_corpus(path: str | os.PathLike[str]) -> tuple[Path, bool]:
    """The directory of the corpus at ``path`` and whether it is the working tree: ``<path>`` itself, or ``<path>.partial``
    when only that exists (an import in progress or not yet sealed). Raises :class:`RenderCorpusError` (exit 2: a usage error) otherwise."""
    given = Path(os.fspath(path))
    if given.is_dir():
        return given, False
    partial = given.with_name(given.name + PARTIAL_SUFFIX)
    if partial.is_dir():
        return partial, True
    raise RenderCorpusError("the corpus directory does not exist", code="render.corpus_missing", exit_code=2)


def open_corpus(path: str | os.PathLike[str]) -> CorpusSource:
    """Open the corpus at ``path`` (see :func:`locate_corpus`), reading ``executions.jsonl`` and, when present,
    ``corpus.json``. Raises :class:`RenderCorpusError` (exit 1) when the index is missing or malformed."""
    root, used_partial = locate_corpus(path)
    resolved = Path(os.path.realpath(root))
    try:
        index = decode_index(_read(resolved, "executions.jsonl"))
    except AgentProvError as exc:
        if isinstance(exc, RenderCorpusError):
            raise
        raise RenderCorpusError(f"executions.jsonl is not a valid index ({exc.code})", code="render.index_invalid") from None
    corpus_id: str | None = None
    state = "working"
    manifest_path = resolved / "corpus.json"
    if manifest_path.is_file():
        try:
            manifest = strict_json_loads(_read(resolved, "corpus.json"), _LIMITS)
        except IngestError as exc:
            raise RenderCorpusError(f"corpus.json is not strict JSON ({exc.code})", code="render.manifest_invalid") from None
        if isinstance(manifest, dict):
            value = manifest.get("corpus_id")
            corpus_id = value if isinstance(value, str) else None
            state = "sealed" if manifest.get("sealed") is True else "working"
    return CorpusSource(resolved, corpus_id, state, tuple(index), used_partial)


def prov_label(source: CorpusSource, row: IndexRow, spec: str = SPEC_ID) -> str | None:
    """The corpus-relative path of ``row``'s PROV-JSON for ``spec``, recomputed from the layout and checked against the
    recorded path; ``None`` when the row has no PROV output for ``spec`` or the recorded path is not the layout's."""
    recorded = (row.prov_paths or {}).get(spec)
    if recorded is None:
        return None
    for depth in (1, 2):
        expected = source.layout(depth).prov_relpath(spec, row.ex)
        if recorded == expected:
            return expected
    return None


def read_prov_document(source: CorpusSource, label: str) -> Any:
    """The decoded PROV-JSON at ``label`` (strict loader, the PROV-document limits of D-935)."""
    data = _read(source.root, label, prov_document_limits(_LIMITS))
    try:
        return strict_json_loads(data, prov_document_limits(_LIMITS))
    except IngestError as exc:
        raise RenderCorpusError(f"{label}: not strict JSON ({exc.code})", code="render.prov_unreadable") from None


def read_aer_header(source: CorpusSource, row: IndexRow) -> dict[str, Any] | None:
    """Line 0 of the execution's AER (the ``execution`` record) for ``--select``; ``None`` if it cannot be read."""
    expected = {source.layout(depth).aer_relpath(row.ex) for depth in (1, 2)}
    if row.aer_path not in expected:
        return None
    try:
        with open_evidence(source.root, row.aer_path, _LIMITS) as stream:
            line = stream.readline(_LIMITS.max_jsonl_line_bytes + 2)
        record = strict_json_loads(line.rstrip(b"\n"), _LIMITS, record=True)
    except (IngestError, OSError):
        return None
    return record if isinstance(record, dict) and record.get("k") == "execution" else None
