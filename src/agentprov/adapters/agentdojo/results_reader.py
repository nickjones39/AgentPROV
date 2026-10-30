"""Reader of the results-container dialect ``agentdojo.results_container`` (docs/architecture D.6.20; DECISIONS D-470; phase
10q; layer L4).

memo-ozdincer/agentdojo's evaluation scripts write one JSON document per evaluation call (``results/**/*.json``): the
call's settings at top level and its runs in a ``results`` list. The settings hold for every row (D-470,
``rescont.container_fields_apply_to_rows@1``):

=====================  ===================================================================================================
container key          meaning
=====================  ===================================================================================================
``label``              the output label (file stem)
``model``              the served-model name the client sent: a checkpoint path, a LoRA adapter name or a provider id
``n_results``          the number of rows (checked against the list)
``results``            the rows
``aggregate``          the script's summary of the rows (not read)
``suite``              the AgentDojo suite (absent in smoke containers; then each row has ``suite``)
``adapter``            a label the script stores for its cross-suite report
``defense``            the AgentDojo-style defence of the pipeline, or null
``attack``             the attack's registry name (absent for some writer versions)
``mode``               ``attack``, ``benign`` or ``smoke``
``base_url``, ``port`` the model server
``elapsed_seconds``    the wall time of the whole call
=====================  ===================================================================================================

Variants are chosen per row by its key set: ``rc.k7`` (``run_eval`` rows) and ``rc.k12`` (``eval_benign_utility`` rows,
with ``classification`` in attack mode and ``suite`` in smoke rows). A row with any other key set is ``rc.unknown``: the
mapper raises :class:`~agentprov.errors.UnsupportedVariant` for it, so that row is sealed as a degenerate AER and never
dropped.

The reader declares ``multi_execution = True`` (D-320): one located item per row, key locator ``{"p": "/results/<i>"}``,
whose value is the whole parsed container (the mapper reads its row by the locator). A container whose ``n_results``
differs from the list length flags every item ``rc:n_results_mismatch`` (the mapper reports it); a container with no
rows yields no item, which the runner registers as ``select.not_execution_artefact`` (D-320). Parsing goes through
:func:`agentprov.ingest.loaders.strict_json_loads` only (invariant 3). Nothing here interprets message content.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Iterator, Mapping, Sequence
from typing import Any, Final

from agentprov.adapters.profiles import SourceProfile
from agentprov.adapters.protocols import SourceTree
from agentprov.adapters.types import ArtefactRef, CandidateArtefact, LocatedItem, Locator, SniffResult
from agentprov.errors import IngestError, MalformedArtefact
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

__all__ = ["CONTAINER_KEYS", "CONTAINER_REQUIRED", "DIALECT_ID", "FLAG_N_MISMATCH", "MAPPED_VARIANTS", "ROW_K12", "ROW_K7",
           "VARIANTS", "ResultsContainerReader", "row_variant"]

DIALECT_ID: Final = "agentdojo.results_container"
CONTAINER_REQUIRED: Final = frozenset({"label", "model", "n_results", "results"})
CONTAINER_KEYS: Final = CONTAINER_REQUIRED | {"aggregate", "suite", "adapter", "defense", "attack", "mode", "base_url", "port",
                                              "elapsed_seconds"}
ROW_K7: Final = frozenset({"user_task_id", "injection_task_id", "utility", "security", "duration", "classification", "messages"})
ROW_K12: Final = frozenset({"user_task_id", "injection_task_id", "utility", "security", "duration", "mode", "failure_mode",
                            "n_assistant_turns", "n_total_tool_calls", "any_garbled", "turns", "messages"})
_K12_OPTIONAL: Final = frozenset({"classification", "suite"})
VARIANTS: Final = frozenset({"rc.k7", "rc.k12", "rc.unknown"})
MAPPED_VARIANTS: Final = frozenset({"rc.k7", "rc.k12"})
FLAG_N_MISMATCH: Final = "rc:n_results_mismatch"
_STRAYS: Final = (".DS_Store",)


def row_variant(row: object) -> str:
    """``rc.k7``, ``rc.k12`` or ``rc.unknown`` by the row's key set (total: never raises)."""
    if not isinstance(row, dict):
        return "rc.unknown"
    keys = frozenset(row)
    if keys == ROW_K7:
        return "rc.k7"
    if ROW_K12 <= keys <= ROW_K12 | _K12_OPTIONAL:
        return "rc.k12"
    return "rc.unknown"


def _match(label: str, glob: str) -> bool:
    if fnmatch.fnmatchcase(label, glob):
        return True
    return glob.startswith("**/") and fnmatch.fnmatchcase(label, glob[3:])


class ResultsContainerReader:
    """``Reader`` for ``agentdojo.results_container`` (D.2.3, D.6.20)."""

    dialect_id: Final = DIALECT_ID
    version: Final = "0.1.0"
    variants: Final = VARIANTS
    media_types: Final = frozenset({"application/json"})
    #: one execution per row (R-10k-1, D-320)
    multi_execution: Final = True

    def __init__(self) -> None:
        self._last: tuple[bytes, Any] | None = None  # (data, parsed value): the runner sniffs, then parses the same bytes

    def iter_artefacts(self, tree: SourceTree, profile: SourceProfile) -> Iterator[CandidateArtefact]:
        """Candidates matching the profile's ``[import] include`` globs, minus strays and excludes, in label order."""
        imp = profile.data.get("import", {})
        include = tuple(imp.get("include", ())) or ("**/*.json",)
        exclude = tuple(e["glob"] for e in imp.get("exclude", ()) if isinstance(e, Mapping) and "glob" in e)
        for candidate in sorted(tree.walk(), key=lambda c: c.label):
            name = candidate.label.rsplit("/", 1)[-1]
            if name in _STRAYS or name.startswith("._"):
                continue
            if any(_match(candidate.label, g) for g in include) and not any(_match(candidate.label, g) for g in exclude):
                yield candidate

    def _load(self, data: bytes, limits: IngestLimits) -> Any:
        if self._last is not None and self._last[0] is data:
            return self._last[1]
        value = strict_json_loads(data, limits)
        self._last = (data, value)
        return value

    @staticmethod
    def _classify(value: Any) -> SniffResult:
        if not isinstance(value, dict):
            return SniffResult(False, reasons=("rescont.not_a_container",))
        keys = set(value)
        if not (CONTAINER_REQUIRED <= keys <= CONTAINER_KEYS) or not isinstance(value.get("results"), list):
            return SniffResult(False, reasons=("rescont.not_a_container",))
        n = value.get("n_results")
        if isinstance(n, bool) or not isinstance(n, int):
            return SniffResult(False, reasons=("rescont.not_a_container",))
        rows: Sequence[Any] = value["results"]
        variants = {row_variant(r) for r in rows}
        variant = next(iter(variants)) if len(variants) == 1 else ("rc.unknown" if variants else "rc.k7")
        flags = {FLAG_N_MISMATCH} if n != len(rows) else set()
        return SniffResult(True, DIALECT_ID, variant, frozenset(flags), ("rescont.sniff.container_keys",))

    def sniff(self, data: bytes, *, label: str, limits: IngestLimits) -> SniffResult:
        """Total classification: never raises for foreign input."""
        try:
            value = self._load(data, limits)
        except IngestError as exc:
            return SniffResult(False, reasons=(exc.code,))
        return self._classify(value)

    @staticmethod
    def register_detail(reasons: Sequence[str]) -> str | None:
        """The register detail of valid JSON that is not a results container."""
        return next((r for r in reasons if r == "rescont.not_a_container"), None)

    def parse(self, data: bytes, artefact: ArtefactRef, *, limits: IngestLimits) -> Iterator[LocatedItem]:
        """One item per row (key locator ``{"p": "/results/<i>"}``); the item's value is the whole parsed container."""
        value = self._load(data, limits)
        self._last = None
        sniff = self._classify(value)
        if not sniff.match:
            raise MalformedArtefact(f"not a results container ({', '.join(sniff.reasons)})")
        for index, row in enumerate(value["results"]):
            yield LocatedItem(
                artefact=artefact,
                locator=Locator(a=artefact.id, p=f"/results/{index}"),
                dialect=DIALECT_ID,
                variant=row_variant(row),
                flags=sniff.flags,
                value=value,
            )
