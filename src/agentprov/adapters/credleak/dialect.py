"""Reader of the credential-leak cell dialect ``credleak.cell`` (docs/architecture D.19.1, D.19.2; D.2.3; layer L4).

**Files.** One JSON object per cell, ``{config, defence, model, runId, runs, scenario, summary, technique, timestamp}``
plus an optional ``__note`` (variant ``v1``; 643 cells in v3 of the deposit). The reader parses with
:func:`agentprov.ingest.loaders.strict_json_loads` under the ingest limits and interprets nothing: it yields **one
located item per run**, with key locator ``{"p": "/runs/<i>"}`` (HL H.7.1, element of a JSON array) and the whole parsed
cell as the item's value, so the mapper reads the cell-level fields (model, technique, scenario, config) of the run's
own cell. A cell with no run yields no item (the mapper is never asked for an execution the file does not hold).

**Sniff outcomes.** A JSON object with exactly the cell keys (``__note`` optional) and an array ``runs`` is a cell. Other
valid JSON of the deposit (the T-EMIT audit files, the independent-scanner outputs) returns no match with the register
detail ``credleak.not_a_cell``; bytes that fail the strict loader return the ``ingest.*`` reason (the collector log of
v3 has a duplicate key; the profile does not select it).

**Path grammar** (D.19.1), read from the right of the artefact's origin label or path::

    .../<section>/<channel>/<model>/<file>.json
    .../<section>/<channel>/excluded-models/<model>/<file>.json
    .../<section>/<channel>/_<dir>/<file>.json          (no model directory: the not-scorable probe, a replication wave)

``section`` is ``01-injection-map``, ``03-egress-axis`` or ``04-hygiene``. The path names the layout class of a cell
(roster, excluded model, an underscore directory such as the not-scorable probe) and the file-name prefix its batch
(``run``, ``archive-…``, ``addendum-…``, ``extcanary``). It is a facet, never the run's identity, which is the cell's
digest plus the run's locator.

Standard library and ``agentprov.{ingest,errors,adapters}`` only.
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from agentprov.adapters.credleak import DIALECT_ID, VARIANT
from agentprov.adapters.profiles import SourceProfile
from agentprov.adapters.protocols import SourceTree
from agentprov.adapters.types import ArtefactRef, CandidateArtefact, LocatedItem, Locator, SniffResult
from agentprov.errors import IngestError, MalformedArtefact
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

__all__ = [
    "CELL_KEYS",
    "SECTIONS",
    "CredleakCellReader",
    "PathFacets",
    "parse_path",
]

CELL_KEYS: Final = frozenset({"config", "defence", "model", "runId", "runs", "scenario", "summary", "technique",
                              "timestamp"})
CELL_OPTIONAL: Final = frozenset({"__note"})
SECTIONS: Final = frozenset({"01-injection-map", "03-egress-axis", "04-hygiene"})
EXCLUDED_DIR: Final = "excluded-models"
_PREFIX: Final = re.compile(r"(?P<prefix>run|extcanary|archive-[A-Za-z0-9.-]+?|addendum-[0-9]{4}-[0-9]{2}-[0-9]{2})__")
_STRAYS: Final = (".DS_Store",)


# ------------------------------------------------------------------------------------------------ path grammar
@dataclass(frozen=True, slots=True)
class PathFacets:
    """The layout facets of a cell's path (D.19.1). Every value is a label taken verbatim from the path."""

    section: str
    channel: str
    model_dir: str | None  # None under an underscore directory, which holds the cells directly
    file: str
    excluded_models: bool
    underscore_dir: str | None
    prefix: str  # run | extcanary | archive-… | addendum-YYYY-MM-DD | other

    @property
    def layout_class(self) -> str:
        """``roster``, ``excluded-models`` or ``underscore`` (a ``_<dir>/`` the deposit keeps apart)."""
        if self.excluded_models:
            return "excluded-models"
        return "underscore" if self.underscore_dir is not None else "roster"

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "section": self.section,
            "channel": self.channel,
            "file": self.file,
            "layout_class": self.layout_class,
            "prefix": self.prefix,
        }
        if self.model_dir is not None:
            out["model_dir"] = self.model_dir
        if self.underscore_dir is not None:
            out["underscore_dir"] = self.underscore_dir
        return out


def parse_path(path: str) -> PathFacets | None:
    """The facets of a POSIX label or path, read from the right; ``None`` outside the grammar."""
    parts = [p for p in path.split("/") if p]
    if len(parts) < 4 or not parts[-1].endswith(".json"):
        return None
    file, parent = parts[-1], parts[-2]
    model_dir: str | None = parent
    excluded, underscore = False, None
    if parent.startswith("_"):
        model_dir, underscore, rest = None, parent, parts[:-2]
    elif parts[-3] == EXCLUDED_DIR:
        excluded, rest = True, parts[:-3]
    else:
        rest = parts[:-2]
    if len(rest) < 2 or rest[-2] not in SECTIONS:
        return None
    match = _PREFIX.match(file)
    prefix = match.group("prefix") if match else "other"
    return PathFacets(rest[-2], rest[-1], model_dir, file, excluded, underscore, prefix)


def _match(label: str, glob: str) -> bool:
    """``fnmatch`` over a POSIX label, ``**/`` also matching zero directories (the runner's matcher)."""
    if fnmatch.fnmatchcase(label, glob):
        return True
    return "**/" in glob and fnmatch.fnmatchcase(label, glob.replace("**/", "", 1))


# ------------------------------------------------------------------------------------------------ the reader
class CredleakCellReader:
    """``Reader`` for ``credleak.cell`` (D.2.3, D.19.2)."""

    @staticmethod
    def sample_stratum(label: str) -> str | None:
        """D-529 ``--sample-mode spread``: the section and channel of the path grammar (D.19.1)."""
        facets = parse_path(label)
        return None if facets is None else f"{facets.section}/{facets.channel}"

    dialect_id: Final = DIALECT_ID
    version: Final = "0.1.0"
    variants: Final = frozenset({VARIANT})
    media_types: Final = frozenset({"application/json"})
    #: one execution per located item (R-10k-1, D-320): the runner maps every run of a cell as its own unit
    multi_execution: Final = True

    def __init__(self) -> None:
        self._last: tuple[bytes, Any] | None = None  # (data, parsed value): the runner sniffs, then parses the same bytes

    def iter_artefacts(self, tree: SourceTree, profile: SourceProfile) -> Iterator[CandidateArtefact]:
        """Primary candidates: the profile's include globs minus its excludes, sorted by label."""
        imp = profile.data.get("import", {})
        include = tuple(imp.get("include", ())) or ("**/*.json",)
        exclude = tuple(e["glob"] for e in imp.get("exclude", ()) if isinstance(e, Mapping) and "glob" in e)
        chosen = []
        for candidate in tree.walk():
            name = candidate.label.rsplit("/", 1)[-1]
            if name in _STRAYS or name.startswith("._"):
                continue
            if any(_match(candidate.label, g) for g in include) and not any(_match(candidate.label, g) for g in exclude):
                chosen.append(candidate)
        yield from sorted(chosen, key=lambda c: c.label)

    def _load(self, data: bytes, limits: IngestLimits) -> Any:
        if self._last is not None and self._last[0] is data:
            return self._last[1]
        value = strict_json_loads(data, limits)
        self._last = (data, value)
        return value

    def sniff(self, data: bytes, *, label: str, limits: IngestLimits) -> SniffResult:
        """Total classification (never raises for foreign input)."""
        try:
            value = self._load(data, limits)
        except IngestError as exc:
            return SniffResult(False, reasons=(exc.code,))
        if not isinstance(value, dict):
            return SniffResult(False, reasons=("credleak.not_a_cell",))
        keys = set(value)
        if CELL_KEYS <= keys <= CELL_KEYS | CELL_OPTIONAL and isinstance(value.get("runs"), list):
            return SniffResult(True, DIALECT_ID, VARIANT, frozenset(), ("credleak.sniff.cell_keys",))
        return SniffResult(False, reasons=("credleak.not_a_cell",))

    @staticmethod
    def register_detail(reasons: Sequence[str]) -> str | None:
        """The register detail of valid JSON that is not a cell (``credleak.not_a_cell``)."""
        return next((r for r in reasons if r == "credleak.not_a_cell"), None)

    def parse(self, data: bytes, artefact: ArtefactRef, *, limits: IngestLimits) -> Iterator[LocatedItem]:
        """One item per run (key locator ``{"p": "/runs/<i>"}``); the item's value is the whole parsed cell."""
        sniff = self.sniff(data, label="", limits=limits)
        if not sniff.match:
            raise MalformedArtefact(f"not a credential-leak cell ({', '.join(sniff.reasons)})")
        value = self._load(data, limits)
        self._last = None
        for index in range(len(value["runs"])):
            yield LocatedItem(
                artefact=artefact,
                locator=Locator(a=artefact.id, p=f"/runs/{index}"),
                dialect=DIALECT_ID,
                variant=VARIANT,
                flags=sniff.flags,
                value=value,
            )
