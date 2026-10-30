"""Reader of the MCPHunt dialect ``mcphunt.traces`` (docs/architecture D.21.1, D.21.2; D.2.3; layer L4).

**Files.** ``<split>/<name>.json``: ``{schema_version, pipeline_git_commit, task_taxonomy_version,
labeling_rules_version, traces: [...]}`` (variant ``v2.0.0`` = the ``schema_version``). The documents are large (up to
111 MB), so they are read only by :func:`agentprov.ingest.jsonstream.open_json_stream` with the declared array
``/traces`` (D-242): the strict loader's rules apply to every element and to the envelope, and nothing is yielded unless
the whole document is valid. One located item per trace: key locator ``{"p": "/traces/<i>"}`` with the element's byte
range ``bytes = (offset, end)`` in the stored object (D-323; ``bytes`` never enters the source key when ``p`` is present,
C.4.1), so the mapper carves a large string by that range alone (RB-3, D-218); the item's value is
``{"envelope": <the document without traces>, "trace": <the element>}`` (the reader's view, both parts verbatim).

The reader declares ``multi_execution`` (R-10k-1, D-320) and streams (D-323, RB-1): the runner maps every trace as its
own execution from :meth:`McpHuntReader.parse_stream` over a seekable handle (``JobContext.open_input``; never
``read_input``, RI-4). :meth:`McpHuntReader.parse` is a thin wrapper over it, so the two paths cannot drift.

Standard library and ``agentprov.{ingest,errors,adapters}`` only.
"""

from __future__ import annotations

import fnmatch
import io
import re
from collections.abc import Iterator, Mapping, Sequence
from typing import IO, Any, Final

from agentprov.adapters.mcphunt import DIALECT_ID, STREAMED_ARRAYS, VARIANT
from agentprov.adapters.profiles import SourceProfile
from agentprov.adapters.protocols import SourceTree
from agentprov.adapters.types import ArtefactRef, CandidateArtefact, LocatedItem, Locator, SniffResult
from agentprov.errors import IngestError, MalformedArtefact
from agentprov.ingest.jsonstream import JsonStream, JsonStreamItem, open_json_stream
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

__all__ = ["ENVELOPE_KEYS", "SPLITS", "McpHuntReader", "split_of"]

ENVELOPE_KEYS: Final = frozenset({"schema_version", "pipeline_git_commit", "task_taxonomy_version",
                                  "labeling_rules_version", "traces"})
#: The first line of a Git LFS pointer file (https://git-lfs.com/spec/v1): 15 of the 20 trace documents are LFS objects,
#: so a checkout of the pinned tree holds their pointers, which are registered, never mapped (mcphunt.lfs_pointer@1).
LFS_HEADER: Final = b"version https://git-lfs.github.com/spec/v1\n"
#: The register detail of a pointer (the reader's no-match reason).
LFS_POINTER: Final = "mcphunt.lfs_pointer"
#: The dataset's top-level directories that hold traces.
SPLITS: Final = ("main", "mitigation", "live_guard_defense", "browser_replication")
_STRAYS: Final = (".DS_Store",)


def split_of(label: str) -> str | None:
    """The split a trace document's label names (its directory), or ``None``."""
    parts = [p for p in label.replace("\\", "/").split("/") if p]
    return parts[-2] if len(parts) >= 2 and parts[-2] in SPLITS else None


def _span(element: JsonStreamItem) -> tuple[int, int]:
    """The element's byte range ``[offset, end)`` in the stored object (D-323): the carving locator of RB-3."""
    if element.end is None:  # the stream reports ``end`` for every element of a declared array
        raise MalformedArtefact("the trace's byte range is unknown")
    return element.offset, element.end


def _member_spans(handle: IO[bytes], end: int, envelope: Mapping[str, Any],
                  limits: IngestLimits) -> dict[str, list[int]]:
    """The byte spans ``[start, end)`` of the envelope's string members in the document before the first trace (regen
    item 149): a C.9.1 byte-range locator ``{"a": ..., "bytes": [start, end]}`` then cites the member by its own slice, so
    no locator of a trace's AER needs the whole document parsed (a document over ``max_json_bytes`` would not resolve).

    The member's key token followed by ``:`` and a string must occur exactly once in the prefix, and the slice must
    parse (strict loader) to the envelope's own value; otherwise the member has no span and keeps a pointer locator.
    The handle's position is restored (the stream reads on from it)."""
    position = handle.tell()
    handle.seek(0)
    head = handle.read(end)
    handle.seek(position)
    out: dict[str, list[int]] = {}
    for name, value in envelope.items():
        if not isinstance(value, str) or not name.isascii() or not name.isidentifier():
            continue
        hits = list(re.finditer(rb'"' + name.encode("ascii") + rb'"[ \t\r\n]*:[ \t\r\n]*"', head))
        if len(hits) != 1:
            continue
        start = stop = hits[0].end() - 1
        i = start + 1
        while i < len(head):  # the closing quote: the next unescaped '"'
            if head[i] == 0x5C:
                i += 2
                continue
            if head[i] == 0x22:
                stop = i + 1
                break
            i += 1
        if stop == start:
            continue
        try:
            if strict_json_loads(head[start:stop], limits) == value:
                out[name] = [start, stop]
        except IngestError:
            continue
    return out


def _match(label: str, glob: str) -> bool:
    if fnmatch.fnmatchcase(label, glob):
        return True
    return "**/" in glob and fnmatch.fnmatchcase(label, glob.replace("**/", "", 1))


class McpHuntReader:
    """``Reader`` for ``mcphunt.traces`` (D.2.3, D.21.2)."""

    dialect_id: Final = DIALECT_ID
    version: Final = "0.1.0"
    multi_execution: Final = True
    variants: Final = frozenset({VARIANT})
    media_types: Final = frozenset({"application/json"})

    def iter_artefacts(self, tree: SourceTree, profile: SourceProfile) -> Iterator[CandidateArtefact]:
        """Primary candidates: the trace documents the profile includes and does not exclude, in label order."""
        imp = profile.data.get("import", {})
        include = tuple(imp.get("include", ())) or tuple(f"{s}/*.json" for s in SPLITS)
        exclude = tuple(e["glob"] for e in imp.get("exclude", ()) if isinstance(e, Mapping) and "glob" in e)
        chosen = [c for c in tree.walk()
                  if c.label.rsplit("/", 1)[-1] not in _STRAYS and not c.label.rsplit("/", 1)[-1].startswith("._")
                  and any(_match(c.label, g) for g in include) and not any(_match(c.label, g) for g in exclude)]
        yield from sorted(chosen, key=lambda c: c.label)

    # ---------------------------------------------------------------------------------------------- sniff and parse
    @staticmethod
    def _open(source: bytes | IO[bytes], limits: IngestLimits) -> JsonStream:
        return open_json_stream(source, limits, arrays=STREAMED_ARRAYS)

    @staticmethod
    def _classify(envelope: object) -> SniffResult:
        if not isinstance(envelope, dict) or set(envelope) != ENVELOPE_KEYS:
            return SniffResult(False, reasons=("mcphunt.sniff.envelope_keys",))
        if envelope.get("schema_version") != VARIANT.removeprefix("v"):
            return SniffResult(False, reasons=("mcphunt.sniff.schema_version",))
        return SniffResult(True, DIALECT_ID, VARIANT, frozenset(), ("mcphunt.sniff.envelope",))

    def sniff(self, data: bytes, *, label: str, limits: IngestLimits) -> SniffResult:
        """Total classification (never raises for foreign input); validates the whole document (two-pass stream)."""
        return self.sniff_stream(io.BytesIO(data), limits=limits)

    def sniff_stream(self, handle: IO[bytes], *, limits: IngestLimits) -> SniffResult:
        start = handle.tell()
        head = handle.read(len(LFS_HEADER))
        handle.seek(start)
        if head == LFS_HEADER:  # a Git LFS pointer: valid input of another kind; its pinned object is the document
            return SniffResult(False, reasons=(LFS_POINTER,))
        try:
            stream = self._open(handle, limits)
        except IngestError as exc:
            return SniffResult(False, reasons=(exc.code,))
        except ValueError:
            return SniffResult(False, reasons=("mcphunt.sniff.not_streamable",))
        return self._classify(stream.envelope)

    @staticmethod
    def register_detail(reasons: Sequence[str]) -> str | None:
        """The register detail of a valid non-execution input: ``mcphunt.lfs_pointer``; ``None`` lets the runner use its
        default detail."""
        return LFS_POINTER if LFS_POINTER in reasons else None

    def parse(self, data: bytes, artefact: ArtefactRef, *, limits: IngestLimits) -> Iterator[LocatedItem]:
        """One item per trace (see :meth:`parse_stream`)."""
        yield from self.parse_stream(io.BytesIO(data), artefact, limits=limits)

    def parse_stream(self, handle: IO[bytes], artefact: ArtefactRef, *, limits: IngestLimits) -> Iterator[LocatedItem]:
        """One item per element of ``/traces`` (key locator ``{"p": "/traces/<i>"}`` with the element's byte range),
        streamed from a seekable handle opened at the start of the stored object."""
        stream = self._open(handle, limits)
        sniff = self._classify(stream.envelope)
        if not sniff.match or sniff.variant is None:
            raise MalformedArtefact(f"not an MCPHunt trace document ({', '.join(sniff.reasons)})")
        envelope: dict[str, Any] = {k: v for k, v in stream.envelope.items() if k != "traces"}
        spans: dict[str, list[int]] | None = None
        for element in stream:
            if spans is None:  # the envelope members precede the first trace in every pinned document
                spans = _member_spans(handle, element.offset, envelope, limits)
            yield LocatedItem(
                artefact=artefact,
                locator=Locator(a=artefact.id, p=f"/traces/{element.index}", bytes=_span(element)),
                dialect=DIALECT_ID,
                variant=sniff.variant,
                flags=sniff.flags,
                value={"envelope": envelope, "envelope_spans": spans, "trace": element.value},
            )
