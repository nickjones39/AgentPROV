"""Reader of the AutoGen guard-placement run files, dialect ``autogen.runs`` (docs/architecture D.19.1, D.19.2; D.2.3).

**Files.** ``runs.jsonl`` of one phase directory: one JSON object per line, read with
:func:`agentprov.ingest.loaders.scan_jsonl` (strict profile, LF framing, per-line findings; any rejected line rejects the
file). A **run row** holds AutoGen ``TaskResult.messages`` (key ``messages``) and the run's settings; the variant is its
key set (:data:`VARIANT_KEYS`). Two other row kinds are valid inputs that are not runs (D-300):

* a guardrail-rail row (``probe_id, response, backend, history_id, outcome, events, wall_s``; phase 7): the bench's rail
  on a probe, no agent -> reason ``autogen.rail_probe_no_agent`` (``select.not_execution_artefact``);
* a framework row (``probe_id, framework, result, returncode, stderr_tail, wall_s``; phases 8 and 9): the team rebuilt
  in LangGraph or CrewAI, tool calls without results -> reason ``autogen.partial_trajectory`` (``select.out_of_scope``).

:meth:`AutoGenRunsReader.parse` yields **one located item per run row** (locator ``{"a": "a0", "line": n}``, 0-based).
The reader declares ``multi_execution`` (R-10k-1, D-320), so the runner maps every run row as its own execution with
source key ``sha256:<file>#{"line": n}`` (D-301). :meth:`AutoGenRunsReader.rejected` reports the rows of a run file
that are not runs, one register row each (D-321); a file without any run row is excluded as a whole by the profile (D-300).

**Label grammar** (D.19.1)::

    <root>/results/phase<N>[/<arm>]/runs.jsonl

``<root>`` is ``autogen-guard-placement`` in the pinned zip; the segments from ``results`` on are matched, so a prefix is
tolerated. The label is a label, never a path to open.

**Per-unit inputs** (runner items R1 and R2 of D.16.14): :meth:`AutoGenRunsReader.auxiliary_for` names the phase
directory's ``events.jsonl`` and ``guard_raw.jsonl`` and the deposit's probe sets, InjecAgent cases and tool schemas,
``config.json`` and the phase-0 capture, when the tree holds them.

Standard library and ``agentprov.{ingest,errors,adapters}`` only.
"""

from __future__ import annotations

import fnmatch
import io
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Protocol

from agentprov.adapters.autogen import DIALECT_ID, VARIANTS
from agentprov.adapters.profiles import SourceProfile
from agentprov.adapters.protocols import SourceTree
from agentprov.adapters.types import ArtefactRef, CandidateArtefact, LocatedItem, Locator, Rejected, SniffResult
from agentprov.errors import IngestError, MalformedArtefact
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import NO_VALUE, scan_jsonl

__all__ = [
    "AUXILIARY_FILES",
    "COMMON_KEYS",
    "VARIANT_KEYS",
    "AutoGenRunsReader",
    "LabelFacets",
    "ParsedRows",
    "parse_label",
    "parse_rows",
    "row_reason",
    "row_variant",
]

#: Keys every run row has (D-302).
COMMON_KEYS: Final = frozenset({"run_id", "phase", "entry", "error", "messages", "tool_calls", "wall_s"})
#: Variant -> (required extra keys, optional extra keys).
VARIANT_KEYS: Final[Mapping[str, tuple[frozenset[str], frozenset[str]]]] = {
    "team": (frozenset({"probe_id", "modes", "block_guard"}), frozenset({"stop_reason"})),
    "injecagent": (frozenset({"case_id", "modes", "block_guard", "block_at", "stop_reason"}), frozenset()),
    "condition": (frozenset({"probe_id", "modes", "condition", "stop_reason"}),
                  frozenset({"carrier_id", "termination", "keyword"})),
    "defense": (frozenset({"probe_id", "defense", "stop_reason"}), frozenset()),
}
RAIL_KEYS: Final = frozenset({"probe_id", "response", "backend", "history_id", "outcome", "events", "wall_s"})
FRAMEWORK_KEYS: Final = frozenset({"probe_id", "framework", "result", "returncode", "stderr_tail", "wall_s"})
#: Per-unit input roles and the label each names, relative to the phase directory (``./``) or the deposit root (``/``).
AUXILIARY_FILES: Final[Mapping[str, str]] = {
    "events": "./events.jsonl",
    "guard_raw": "./guard_raw.jsonl",
    "probes": "/data/probes/probes.jsonl",
    "keyword_probes": "/data/probes/keyword_probes.jsonl",
    "injecagent_cases": "/data/thirdparty/injecagent_dh.jsonl",
    "config": "/config.json",
    "capture": "/results/phase0/capture.json",
}
_PHASE: Final = re.compile(r"phase(?P<n>[0-9]{1,2})")
_ARM: Final = re.compile(r"[a-z][a-z0-9_]*")
_STRAYS: Final = (".DS_Store",)


class Listing(Protocol):
    """What the runner tells a reader about the walked trees (runner items R1/R2): directory siblings and existence."""

    def siblings(self, label: str) -> Sequence[str]: ...

    def exists(self, ref: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class LabelFacets:
    """The facets of a run file's label (D.19.1). ``prefix`` is everything before ``results/`` (the deposit root)."""

    prefix: str
    phase: int
    arm: str | None

    @property
    def directory(self) -> str:
        """The phase directory's label, from the deposit root."""
        tail = f"results/phase{self.phase}" + (f"/{self.arm}" if self.arm else "")
        return self.prefix + tail

    def to_json(self) -> dict[str, Any]:
        return {"phase": self.phase, "arm": self.arm}


def parse_label(label: str) -> LabelFacets | None:
    """The facets of a ``runs.jsonl`` label, or ``None`` outside the grammar."""
    parts = [p for p in label.replace("\\", "/").split("/") if p]
    if not parts or parts[-1] != "runs.jsonl" or "results" not in parts:
        return None
    i = len(parts) - 1 - parts[::-1].index("results")
    tail = parts[i + 1:-1]
    if len(tail) not in (1, 2):
        return None
    m = _PHASE.fullmatch(tail[0])
    if m is None or (len(tail) == 2 and _ARM.fullmatch(tail[1]) is None):
        return None
    prefix = "/".join(parts[:i]) + ("/" if i else "")
    return LabelFacets(prefix, int(m["n"]), tail[1] if len(tail) == 2 else None)


def row_variant(row: Mapping[str, Any]) -> str | None:
    """The variant of a run row by its key set, or ``None`` when the row is not a run row of a known shape."""
    keys = set(row)
    if not COMMON_KEYS <= keys:
        return None
    extra = keys - COMMON_KEYS
    hits = [v for v, (req, opt) in VARIANT_KEYS.items() if req <= extra and extra <= req | opt]
    return hits[0] if len(hits) == 1 else None


def row_reason(row: object) -> str | None:
    """``None`` for a run row; otherwise the register detail of a row that is not a run (D-300)."""
    if not isinstance(row, dict):
        return "autogen.sniff.not_object"
    if row_variant(row) is not None:
        return None
    keys = set(row)
    if keys == RAIL_KEYS:
        return "autogen.rail_probe_no_agent"
    if keys == FRAMEWORK_KEYS:
        return "autogen.partial_trajectory"
    return "autogen.sniff.keys"


@dataclass(frozen=True, slots=True)
class ParsedRows:
    """The rows of one ``runs.jsonl``: ``(line, value)`` in line order, every line a parsed JSON value."""

    rows: tuple[tuple[int, Any], ...]

    def runs(self) -> list[tuple[int, dict[str, Any], str]]:
        """``(line, row, variant)`` of the run rows."""
        out = []
        for line, value in self.rows:
            if isinstance(value, dict):
                variant = row_variant(value)
                if variant is not None:
                    out.append((line, value, variant))
        return out


def parse_rows(data: bytes, limits: IngestLimits) -> ParsedRows:
    """Every line of a JSONL file through the strict scanner. ``IngestError`` for a rejected or blank line."""
    rows: list[tuple[int, Any]] = []
    for line, _offset, value, findings in scan_jsonl(io.BytesIO(data), limits):
        bad = next((f for f in findings if f.severity == "error"), None)
        if bad is not None:
            raise IngestError(bad.code, f"line {line}: rejected")
        if value is NO_VALUE:
            raise MalformedArtefact(f"line {line}: a blank line in a run file")
        rows.append((line, value))
    return ParsedRows(tuple(rows))


def _match(label: str, glob: str) -> bool:
    """``fnmatch`` over a POSIX label, ``**/`` also matching zero directories (the runner's matcher)."""
    if fnmatch.fnmatchcase(label, glob):
        return True
    return "**/" in glob and fnmatch.fnmatchcase(label, glob.replace("**/", "", 1))


def auxiliary_labels(facets: LabelFacets) -> dict[str, str]:
    """Role -> label of every per-unit input of a run file (``AUXILIARY_FILES`` resolved against its directory)."""
    out = {}
    for role, rel in AUXILIARY_FILES.items():
        out[role] = facets.directory + rel[1:] if rel.startswith("./") else facets.prefix + rel[1:]
    return out


class AutoGenRunsReader:
    """``Reader`` for ``autogen.runs`` (D.2.3, D.19.2)."""

    @staticmethod
    def sample_stratum(label: str) -> str | None:
        """D-529 ``--sample-mode spread``: the phase and arm of the label grammar (``results/phase<N>[/<arm>]``)."""
        facets = parse_label(label)
        return None if facets is None else f"phase{facets.phase}" + (f"/{facets.arm}" if facets.arm else "")

    dialect_id: Final = DIALECT_ID
    version: Final = "0.1.0"
    variants: Final = VARIANTS
    #: One execution per located item (one run row; R-10k-1, D-320; D-301): the runner maps each line as its own unit.
    multi_execution: Final = True
    media_types: Final = frozenset({"application/jsonl", "application/x-ndjson"})

    def __init__(self) -> None:
        self._last: tuple[bytes, ParsedRows] | None = None  # the runner sniffs, then parses the same bytes

    # ---------------------------------------------------------------------------------------------- discovery
    def iter_artefacts(self, tree: SourceTree, profile: SourceProfile) -> Iterator[CandidateArtefact]:
        """Primary candidates: the run files the profile includes and does not exclude, in label order."""
        imp = profile.data.get("import", {})
        include = tuple(imp.get("include", ())) or ("**/runs.jsonl",)
        exclude = tuple(e["glob"] for e in imp.get("exclude", ()) if isinstance(e, Mapping) and "glob" in e)
        chosen: list[CandidateArtefact] = []
        for candidate in tree.walk():
            name = candidate.label.rsplit("/", 1)[-1]
            if name in _STRAYS or name.startswith("._"):
                continue
            if any(_match(candidate.label, g) for g in include) and not any(_match(candidate.label, g) for g in exclude):
                chosen.append(candidate)
        yield from sorted(chosen, key=lambda c: c.label)

    def auxiliary_for(self, label: str, listing: Listing) -> dict[str, str]:
        """The per-unit inputs of ``label`` that the tree holds (role -> label)."""
        facets = parse_label(label)
        if facets is None:
            return {}
        return {role: ref for role, ref in auxiliary_labels(facets).items() if listing.exists(ref)}

    # ---------------------------------------------------------------------------------------------- sniff and parse
    def _load(self, data: bytes, limits: IngestLimits) -> ParsedRows:
        if self._last is not None and self._last[0] is data:
            return self._last[1]
        parsed = parse_rows(data, limits)
        self._last = (data, parsed)
        return parsed

    def sniff(self, data: bytes, *, label: str, limits: IngestLimits) -> SniffResult:
        """Total classification (never raises for foreign input). A file without a run row is not of the dialect; its
        reason is the rows' common register detail (``autogen.rail_probe_no_agent``, ``autogen.partial_trajectory``)."""
        try:
            parsed = self._load(data, limits)
        except IngestError as exc:
            return SniffResult(False, reasons=(exc.code,))
        except MalformedArtefact:
            return SniffResult(False, reasons=("autogen.sniff.blank_line",))
        if not parsed.rows:
            return SniffResult(False, reasons=("autogen.sniff.empty",))
        if parsed.runs():
            return SniffResult(True, DIALECT_ID, parsed.runs()[0][2], frozenset(), ("autogen.sniff.run_rows",))
        reasons = sorted({row_reason(v) or "autogen.sniff.keys" for _line, v in parsed.rows})
        return SniffResult(False, reasons=tuple(reasons))

    @staticmethod
    def register_detail(reasons: Sequence[str]) -> str | None:
        """The register detail of a valid file without runs; ``None`` for the default."""
        return next((r for r in reasons if r.startswith("autogen.") and not r.startswith("autogen.sniff.")), None)

    def rejected(self, data: bytes, artefact: ArtefactRef, *, limits: IngestLimits) -> Iterator[Rejected]:
        """The rows of a run file that are not runs (D-321; D-300): a guardrail-rail row is
        ``select.not_execution_artefact``, a framework row (tool calls without results) ``select.out_of_scope``, a row of
        another shape ``select.not_execution_artefact``; each with its line locator. In the pinned deposit the 190 non-run
        rows fill three files of their own (phases 7-9), which have no run row, so the runner asks for their rows too."""
        parsed = self._load(data, limits)
        for line, value in parsed.rows:
            reason = row_reason(value)
            if reason is None:
                continue
            code = "select.out_of_scope" if reason == "autogen.partial_trajectory" else "select.not_execution_artefact"
            yield Rejected(Locator(a=artefact.id, line=line), code, reason)

    def parse(self, data: bytes, artefact: ArtefactRef, *, limits: IngestLimits) -> Iterator[LocatedItem]:
        """One located item per run row (locator ``{"a": <artefact>, "line": n}``); other rows yield nothing here and are
        registered by the row-unit capability (D-301)."""
        sniff = self.sniff(data, label="", limits=limits)
        if not sniff.match:
            raise MalformedArtefact(f"not an AutoGen guard-placement run file ({', '.join(sniff.reasons)})")
        parsed = self._load(data, limits)
        self._last = None
        for line, value, variant in parsed.runs():
            yield LocatedItem(
                artefact=artefact,
                locator=Locator(a=artefact.id, line=line),
                dialect=DIALECT_ID,
                variant=variant,
                flags=frozenset(),
                value=value,
            )
