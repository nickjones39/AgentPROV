"""L5 corpus layer: layout, register, index, source keys, the working-corpus writer (docs/architecture H) and, from
phase 11, the corpus model: facets (:mod:`~agentprov.corpus.facets`), checksums and digests
(:mod:`~agentprov.corpus.integrity`) and the read-only :class:`~agentprov.corpus.reader.CorpusReader`.

Sealing (phase 11, U3): the corpus spec (:mod:`~agentprov.corpus.spec`), the full manifest, its validator and published
schema (:mod:`~agentprov.corpus.manifest`), the datasheet (:mod:`~agentprov.corpus.datasheet`) and ``seal()``
(:mod:`~agentprov.corpus.package`). ``verify`` levels beyond ``checksums`` and ``derive`` / ``recompute`` arrive with the
other phase-11 units. Submodules are imported explicitly;
this package re-exports only the phase-3 names below. ``CorpusWriter`` is re-exported lazily (GR-34), so that a
reader of a corpus (the GUI) does not load the writer, the worker pool or the host probes.
"""

from typing import TYPE_CHECKING, Any

from agentprov.corpus.index import ExecutionEntry, IndexLog, IndexRow, RawRef
from agentprov.corpus.layout import CorpusLayout, SealedCorpusError, assert_writable
from agentprov.corpus.register import RegisterEntry, RegisterLog

if TYPE_CHECKING:
    from agentprov.corpus.writer import CorpusWriter

__all__ = [
    "CorpusLayout",
    "CorpusWriter",
    "ExecutionEntry",
    "IndexLog",
    "IndexRow",
    "RawRef",
    "RegisterEntry",
    "RegisterLog",
    "SealedCorpusError",
    "assert_writable",
]


def __getattr__(name: str) -> Any:
    if name == "CorpusWriter":  # GR-34: loaded on first use only
        from agentprov.corpus.writer import CorpusWriter

        return CorpusWriter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

