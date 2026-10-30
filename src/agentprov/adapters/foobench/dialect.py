"""Reader of the FooBench JSONL dialect (docs/architecture D.12.1; D.2.3; layer L4).

Dialect ``foobench.jsonl``, variant ``v1``. A FooBench trace is a JSONL file: line 0 is a header object carrying the
declared ``schema`` key (``"foobench/1"``); every later line is one event object with a string ``type``. A hand-off
writes the sub-agent's events into a **second file** with the same framing; its header has a ``parent`` object (flag
``role:sub``) and the profile lists such files under ``[import] auxiliary`` so they join the parent's execution unit.

Parsing goes through :func:`agentprov.ingest.loaders.iter_jsonl` only (A-1, invariant 3), which fails closed on a blank
line, CRLF, a missing final newline, a BOM or an over-long line (``IngestError``). The reader interprets nothing: it
produces one located item for the whole primary file (the key locator is ``{}``) whose value lists the events with their
0-based line numbers; the mapper cites an event as the locator ``{"line": n}``.

Standard library and ``agentprov.{ingest,errors,adapters}`` only.
"""

from __future__ import annotations

import fnmatch
import io
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any, Final

from agentprov.adapters.foobench import ADAPTER_ID
from agentprov.adapters.profiles import SourceProfile
from agentprov.adapters.protocols import SourceTree
from agentprov.adapters.types import ArtefactRef, CandidateArtefact, LocatedItem, Locator, SniffResult
from agentprov.errors import IngestError, MalformedArtefact
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import iter_jsonl, strict_json_loads

__all__ = ["DIALECT_ID", "FLAG_SUB", "SCHEMA_ID", "VARIANT", "FooJsonlReader", "ParsedFile", "parse_events"]

DIALECT_ID: Final = ADAPTER_ID
VARIANT: Final = "v1"
SCHEMA_ID: Final = "foobench/1"
FLAG_SUB: Final = "role:sub"
_STRAYS: Final = (".DS_Store",)


@dataclass(frozen=True, slots=True)
class ParsedFile:
    """A parsed FooBench file: the header object and ``(line, event)`` pairs in file order."""

    header: Mapping[str, Any]
    events: tuple[tuple[int, Mapping[str, Any]], ...]


def _header_problem(value: object) -> str | None:
    """``None`` when ``value`` is a FooBench header, else the reason code."""
    if not isinstance(value, dict):
        return "not_object"
    if value.get("schema") != SCHEMA_ID:
        return "schema_id"
    return None


def _file_problem(header: Mapping[str, Any]) -> str | None:
    """A header that declares the schema but cannot head a parseable file (``MalformedArtefact`` in :func:`parse_events`)."""
    if "parent" in header:  # a sub-agent file: the task belongs to its parent's header
        return None if isinstance(header["parent"], dict) else "parent_not_object"
    task = header.get("task")
    return None if isinstance(task, str) and task else "task_missing"


def parse_events(data: bytes, limits: IngestLimits) -> ParsedFile:
    """Parse a whole FooBench file (primary or sub-agent). ``IngestError`` (limits, framing) or ``MalformedArtefact``."""
    if len(data) > limits.max_artefact_bytes:
        raise IngestError("ingest.size.file", "artefact exceeds the size limit", limit=limits.max_artefact_bytes)
    header: Mapping[str, Any] | None = None
    events: list[tuple[int, Mapping[str, Any]]] = []
    for line_no, _offset, value in iter_jsonl(io.BytesIO(data), limits):
        if line_no == 0:
            reason = _header_problem(value) or _file_problem(value)
            if reason is not None:
                raise MalformedArtefact(f"line 0 is not a FooBench header ({reason})")
            header = value
            continue
        if not isinstance(value, dict) or not isinstance(value.get("type"), str):
            raise MalformedArtefact(f"line {line_no} is not an event object with a string type")
        events.append((line_no, value))
    if header is None:
        raise MalformedArtefact("the file has no header line")
    return ParsedFile(header, tuple(events))


def flags_of(header: Mapping[str, Any]) -> frozenset[str]:
    """``role:sub`` for a sub-agent file (a ``parent`` object in the header)."""
    return frozenset({FLAG_SUB}) if "parent" in header else frozenset()


class FooJsonlReader:
    """``Reader`` for ``foobench.jsonl`` (D.2.3)."""

    dialect_id: Final = DIALECT_ID
    version: Final = "0.1.0"
    variants: Final = frozenset({VARIANT})
    media_types: Final = frozenset({"application/x-ndjson"})

    def iter_artefacts(self, tree: SourceTree, profile: SourceProfile) -> Iterator[CandidateArtefact]:
        """Primary candidates: ``[import] include`` globs, minus strays, excludes and the auxiliary patterns."""
        imp = profile.data.get("import", {})
        include = tuple(imp.get("include", ())) or ("**/*.jsonl",)
        exclude = tuple(e["glob"] for e in imp.get("exclude", ()) if isinstance(e, Mapping) and "glob" in e)
        auxiliary = tuple(imp.get("auxiliary", ()))
        for candidate in sorted(tree.walk(), key=lambda c: c.label):
            name = candidate.label.rsplit("/", 1)[-1]
            if name in _STRAYS or name.startswith("._"):
                continue
            if not any(_match(candidate.label, g) for g in include):
                continue
            if any(_match(candidate.label, g) for g in (*exclude, *auxiliary)):
                continue
            yield candidate

    def sniff(self, data: bytes, *, label: str, limits: IngestLimits) -> SniffResult:
        """Total classification from the first line: never raises for foreign input."""
        end = data.find(b"\n")
        first = data if end < 0 else data[:end]
        try:
            value = strict_json_loads(first, limits, record=True)
        except IngestError as exc:
            return SniffResult(False, reasons=(exc.code,))
        reason = _header_problem(value)
        if reason is not None:
            return SniffResult(False, reasons=(f"foobench.sniff.{reason}",))
        return SniffResult(True, DIALECT_ID, VARIANT, flags_of(value), ("foobench.sniff.schema_id",))

    def parse(self, data: bytes, artefact: ArtefactRef, *, limits: IngestLimits) -> Iterator[LocatedItem]:
        """One item for the whole file (key locator ``{}``); events carry their own ``{"line": n}`` locators."""
        parsed = parse_events(data, limits)
        yield LocatedItem(
            artefact=artefact,
            locator=Locator(a=artefact.id),
            dialect=DIALECT_ID,
            variant=VARIANT,
            flags=flags_of(parsed.header),
            value={"header": parsed.header, "events": [{"line": n, "event": e} for n, e in parsed.events]},
        )


def _match(label: str, glob: str) -> bool:
    """``fnmatch`` over a POSIX label, with ``**/`` also matching zero directories."""
    if fnmatch.fnmatchcase(label, glob):
        return True
    return glob.startswith("**/") and fnmatch.fnmatchcase(label, glob[3:])
