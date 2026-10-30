"""Reader of the gemini-cli stream dialect ``geminicli.stream_json`` (docs/architecture D.23.1, D.23.2; D.2.3; layer L4).

**Files.** A rollout of the gemini_cli cells writes the CLI's ``--output-format stream-json`` output to
``gemini_stream.jsonl``: one JSON object per LF-terminated line, the first an ``init`` event. The reader parses it with
:func:`agentprov.ingest.loaders.iter_jsonl` under the ingest limits (fail closed: a blank line, CRLF, a missing final
newline or an over-long line raises) and interprets nothing: it yields one located item for the whole file (key locator
``{"a": <id>}``) whose value lists the events with their 0-based line numbers; the mapper cites an event as
``{"line": n}``. Variant ``v1`` is the event vocabulary of the 2,182 census streams.

**Primaries** (D-331). Per rollout directory the reader chooses ``gemini_stream.jsonl``; a directory without one offers its
``verdict.json`` instead, so the rollout is registered rather than skipped: its sniff returns no match with the reason
``geminicli.no_stream``. An empty stream returns ``geminicli.empty_stream``. Both are register details of
``select.not_execution_artefact``; their sibling files are then registered as the auxiliary artefacts of a file that is
not an execution. The other scaffolds' verdicts are excluded by the profile (``select.out_of_scope``).

**Label grammar** (D.23.1)::

    <root>/cells/<scaffold>__<model>/<SK-SKELETON>__m<NN>/<file>

``<root>`` is ``RESULTS_build`` in the pinned archive; the last four segments are matched, so a prefix is tolerated (a
``local`` origin carries the whole local path). The label is a label, never a path to open.

**Per-unit inputs** (runner items R1 and R2 of D.16.14): :meth:`GeminiStreamReader.auxiliary_for` names the rollout's
sibling members by role (:data:`SIBLING_ROLES`) and the deposit's ``manifest.csv`` (``manifest``), when the expanded
archive holds them (the profile's ``include`` selects them, so the ``expand`` stage stores them).

Standard library and ``agentprov.{ingest,errors,adapters}`` only.
"""

from __future__ import annotations

import fnmatch
import io
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final, Protocol

from agentprov.adapters.geminicli import DIALECT_ID, VARIANT
from agentprov.adapters.profiles import SourceProfile
from agentprov.adapters.protocols import SourceTree
from agentprov.adapters.types import ArtefactRef, CandidateArtefact, LocatedItem, Locator, SniffResult
from agentprov.errors import IngestError, MalformedArtefact
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import iter_jsonl, strict_json_loads

__all__ = [
    "EVENT_TYPES",
    "MANIFEST",
    "SIBLING_ROLES",
    "STREAM",
    "VERDICT",
    "VERDICT_KEYS",
    "GeminiStreamReader",
    "LabelFacets",
    "parse_events",
    "parse_label",
]

STREAM: Final = "gemini_stream.jsonl"
VERDICT: Final = "verdict.json"
#: The deposit's run table, beside ``cells/`` under the root (the D-337 cross-check).
MANIFEST: Final = "manifest.csv"
#: The event vocabulary of variant ``v1`` (the census's 2,182 streams).
EVENT_TYPES: Final = frozenset({"init", "message", "tool_use", "tool_result", "error", "result"})
#: Sibling file name -> auxiliary role (D-330). The stream is the primary; ``verdict.json`` is a primary only where the
#: directory holds no stream.
SIBLING_ROLES: Final[Mapping[str, str]] = MappingProxyType({
    VERDICT: "verdict",
    "gemini_meta.json": "meta",
    "fs_before.json": "fs_before",
    "fs_after.json": "fs_after",
    "final_diff.patch": "diff",
    "events.jsonl": "harness_events",
    "gemini_stderr.log": "cli_stderr",
    "runner_stdout.log": "runner_stdout",
    "runner_stderr.log": "runner_stderr",
    "atoms.flat": "atoms",
})  # fmt: skip
#: The keys every census ``verdict.json`` holds: a verdict offered as a primary is a rollout without a stream (D-331).
VERDICT_KEYS: Final = frozenset({"mutation_id", "agent", "model", "n", "n_misaligned", "elicited", "elapsed_sec",
                                 "exit_code", "timed_out", "sut_id"})
_STRAYS: Final = (".DS_Store",)
_CELL: Final = re.compile(r"(?P<scaffold>[a-z][a-z_]*)__(?P<model>[A-Za-z0-9][A-Za-z0-9._-]*)")
_MUTATION: Final = re.compile(r"(?P<skeleton>SK-[A-Z0-9]+)__(?P<variant>m[0-9]{2})")


class Listing(Protocol):
    """What the runner tells a reader about the walked trees (runner items R1/R2): directory siblings and existence."""

    def siblings(self, label: str) -> Sequence[str]: ...

    def exists(self, ref: str) -> bool: ...


# ------------------------------------------------------------------------------------------------ label grammar
@dataclass(frozen=True, slots=True)
class LabelFacets:
    """The facets of a rollout member's label (D.23.1). ``root`` is everything before ``cells/``."""

    root: str
    cell: str
    scaffold: str
    model: str
    mutation: str
    skeleton: str
    variant: str
    file: str

    @property
    def directory(self) -> str:
        """The rollout directory's label (``<root>/cells/<cell>/<mutation>``)."""
        return f"{self.root}/cells/{self.cell}/{self.mutation}" if self.root else f"cells/{self.cell}/{self.mutation}"

    @property
    def manifest(self) -> str:
        return f"{self.root}/{MANIFEST}" if self.root else MANIFEST

    def to_json(self) -> dict[str, Any]:
        return {"cell": self.cell, "scaffold": self.scaffold, "model": self.model, "mutation": self.mutation,
                "skeleton": self.skeleton, "variant": self.variant, "file": self.file}  # fmt: skip


def parse_label(label: str) -> LabelFacets | None:
    """The facets of a rollout member label, or ``None`` when its last four segments are outside the grammar."""
    parts = [p for p in label.replace("\\", "/").split("/") if p]
    if len(parts) < 4 or parts[-4] != "cells":
        return None
    cell, mutation, name = parts[-3:]
    c, m = _CELL.fullmatch(cell), _MUTATION.fullmatch(mutation)
    if c is None or m is None:
        return None
    return LabelFacets("/".join(parts[:-4]), cell, c["scaffold"], c["model"], mutation, m["skeleton"], m["variant"], name)


def _match(label: str, glob: str) -> bool:
    """``fnmatch`` over a POSIX label, ``**/`` also matching zero directories (the runner's matcher)."""
    if fnmatch.fnmatchcase(label, glob):
        return True
    return "**/" in glob and fnmatch.fnmatchcase(label, glob.replace("**/", "", 1))


# ------------------------------------------------------------------------------------------------ parsing
def parse_events(data: bytes, limits: IngestLimits) -> list[tuple[int, Mapping[str, Any]]]:
    """``(line, event)`` pairs of a whole stream, in file order. ``IngestError`` (limits, framing) or
    ``MalformedArtefact`` (a line that is not an object with a string ``type``)."""
    if len(data) > limits.max_artefact_bytes:
        raise IngestError("ingest.size.file", "artefact exceeds the size limit", limit=limits.max_artefact_bytes)
    events: list[tuple[int, Mapping[str, Any]]] = []
    for line_no, _offset, value in iter_jsonl(io.BytesIO(data), limits):
        if not isinstance(value, dict) or not isinstance(value.get("type"), str):
            raise MalformedArtefact(f"line {line_no} is not an event object with a string type")
        events.append((line_no, value))
    if not events or events[0][1].get("type") != "init":
        raise MalformedArtefact("the stream does not start with an init event")
    return events


def _verdict_document(data: bytes, limits: IngestLimits) -> bool:
    """Whether ``data`` is one JSON object with the verdict keys (the sniff is called without the label)."""
    try:
        value = strict_json_loads(data, limits)
    except IngestError:
        return False
    return isinstance(value, dict) and VERDICT_KEYS <= set(value)


class GeminiStreamReader:
    """``Reader`` for ``geminicli.stream_json`` (D.2.3, D.23.2)."""

    dialect_id: Final = DIALECT_ID
    version: Final = "0.1.0"
    variants: Final = frozenset({VARIANT})
    media_types: Final = frozenset({"application/x-ndjson"})

    # ---------------------------------------------------------------------------------------------- discovery
    def iter_artefacts(self, tree: SourceTree, profile: SourceProfile) -> Iterator[CandidateArtefact]:
        """Primary candidates: per rollout directory the stream, else its verdict (D-331), among the files the profile
        includes and does not exclude, in label order. Other included files are siblings, never primaries."""
        imp = profile.data.get("import", {})
        include = tuple(imp.get("include", ())) or (f"**/cells/*/*/{STREAM}",)
        exclude = tuple(e["glob"] for e in imp.get("exclude", ()) if isinstance(e, Mapping) and "glob" in e)
        by_dir: dict[str, dict[str, CandidateArtefact]] = {}
        for candidate in tree.walk():
            name = candidate.label.rsplit("/", 1)[-1]
            if name in _STRAYS or name.startswith("._") or name not in (STREAM, VERDICT):
                continue
            if not any(_match(candidate.label, g) for g in include) or any(_match(candidate.label, g) for g in exclude):
                continue
            if parse_label(candidate.label) is None:
                continue
            by_dir.setdefault(candidate.label.rpartition("/")[0], {})[name] = candidate
        chosen = [files.get(STREAM) or files[VERDICT] for files in by_dir.values()]
        yield from sorted(chosen, key=lambda c: c.label)

    def auxiliary_for(self, label: str, listing: Listing) -> dict[str, str]:
        """The per-unit inputs of primary ``label``: its siblings by role and the deposit's manifest, where present."""
        facets = parse_label(label)
        if facets is None:
            return {}
        plan: dict[str, str] = {}
        for sibling in listing.siblings(label):
            role = SIBLING_ROLES.get(sibling.rsplit("/", 1)[-1])
            if role is not None and sibling != label:
                plan[role] = sibling
        if listing.exists(facets.manifest):
            plan["manifest"] = facets.manifest
        return plan

    # ---------------------------------------------------------------------------------------------- sniff and parse
    def sniff(self, data: bytes, *, label: str, limits: IngestLimits) -> SniffResult:
        """Total classification from the first line (never raises for foreign input)."""
        if not data:
            return SniffResult(False, reasons=("geminicli.empty_stream",))
        end = data.find(b"\n")
        first = data if end < 0 else data[:end]
        try:
            value = strict_json_loads(first, limits, record=True)
        except IngestError as exc:
            whole = _verdict_document(data, limits)
            return SniffResult(False, reasons=("geminicli.no_stream",) if whole else (exc.code,))
        if isinstance(value, dict) and VERDICT_KEYS <= set(value) and "type" not in value:
            return SniffResult(False, reasons=("geminicli.no_stream",))
        if not isinstance(value, dict):
            return SniffResult(False, reasons=("geminicli.sniff.not_object",))
        if value.get("type") != "init":
            return SniffResult(False, reasons=("geminicli.sniff.first_event",))
        return SniffResult(True, DIALECT_ID, VARIANT, frozenset(), ("geminicli.sniff.init_event",))

    @staticmethod
    def register_detail(reasons: Sequence[str]) -> str | None:
        """The register detail of a valid non-execution input (``geminicli.no_stream``, ``geminicli.empty_stream``)."""
        return next((r for r in reasons if r.startswith("geminicli.") and not r.startswith("geminicli.sniff.")), None)

    def parse(self, data: bytes, artefact: ArtefactRef, *, limits: IngestLimits) -> Iterator[LocatedItem]:
        """One item for the whole file (key locator ``{"a": <id>}``); events carry their own ``{"line": n}`` locators."""
        sniff = self.sniff(data, label="", limits=limits)
        if not sniff.match:
            raise MalformedArtefact(f"not a gemini-cli stream ({', '.join(sniff.reasons)})")
        events = parse_events(data, limits)
        yield LocatedItem(
            artefact=artefact,
            locator=Locator(a=artefact.id),
            dialect=DIALECT_ID,
            variant=VARIANT,
            flags=sniff.flags,
            value={"events": [{"line": n, "event": e} for n, e in events]},
        )
