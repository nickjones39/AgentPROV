"""Reader of the wire-log dialect ``wirelog.request_response`` (docs/architecture D.20.1, D.20.2; D.2.3; layer L4).

**Files.** The primary artefact of a unit is a run directory's response log ``response_raw.json``: a JSON array of the
decoded responses the harness received, in order (variants in :mod:`~agentprov.adapters.wirelog.wire`). It is the
provider's own output and differs between trials, whereas a request log repeats byte for byte across trials whose
requests were the same (1,263 distinct request logs in 1,334 runs of the first source; D-281 addendum), so the response
log is the content-addressed identity of a run. The request log ``request.json`` is the per-unit auxiliary ``request``.
The reader parses with :func:`agentprov.ingest.loaders.strict_json_loads` under the ingest limits, detects the variant
and interprets nothing else: one located item per file (key locator ``{"p": ""}``). Valid JSON of another shape returns
no match with reason ``wirelog.sniff.*``.

**Run-directory layout** (D.20.1; the harness's ``save()`` of the first source)::

    <root>/<runs_dir>/<model>__<arm>__<NNNN>/response_raw.json   primary
    <root>/<runs_dir>/<model>__<arm>__<NNNN>/<sibling files>     per-unit auxiliaries (:data:`SIBLINGS`)
    <root>/results.csv, <root>/attacks.json                      the deposit's tables (:data:`ROOT_FILES`)

The label is a label, never a path to open; the last three segments are matched, so a prefix is tolerated (a ``local``
origin carries the whole local path).

Standard library and ``agentprov.{ingest,errors,adapters}`` only.
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final, Protocol

from agentprov.adapters.profiles import SourceProfile
from agentprov.adapters.protocols import SourceTree
from agentprov.adapters.types import ArtefactRef, CandidateArtefact, LocatedItem, Locator, SniffResult
from agentprov.adapters.wirelog import DIALECT_ID, VARIANTS
from agentprov.adapters.wirelog.wire import detect_response_variant
from agentprov.errors import IngestError, MalformedArtefact
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

__all__ = ["PRIMARY_NAME", "ROOT_FILES", "SIBLINGS", "LabelFacets", "WireLogReader", "parse_label"]

PRIMARY_NAME: Final = "response_raw.json"
#: Auxiliary role -> file name in the run directory (the harness's ``save()``).
SIBLINGS: Final[Mapping[str, str]] = MappingProxyType({
    "request": "request.json",
    "meta": "meta.json",
    "dispatch": "tools_called.txt",
    "outcome": "outcome.txt",
    "outcome_v2": "outcome_v2.txt",
    "final_message": "final_message.txt",
    "final_user_text": "final_user_text.txt",
    "final_reasoning": "final_reasoning.txt",
})
#: Auxiliary role -> file name at the deposit root (the parent of the runs directory).
ROOT_FILES: Final[Mapping[str, str]] = MappingProxyType({"results": "results.csv", "attacks": "attacks.json"})
_DIR: Final = re.compile(r"(?P<model>[A-Za-z0-9][A-Za-z0-9._:-]*)__(?P<arm>[a-z0-9_]+)__(?P<number>[0-9]{4,})")
_STRAYS: Final = (".DS_Store",)


class Listing(Protocol):
    """What the runner tells a reader about the walked trees (runner items R1/R2): directory siblings and existence."""

    def siblings(self, label: str) -> Sequence[str]: ...

    def exists(self, ref: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class LabelFacets:
    """The facets of a response log's label (D.20.1). ``root`` is the prefix before the runs directory ("" in the zip)."""

    root: str
    runs_dir: str
    run_dir: str
    model: str
    arm: str
    number: int

    @property
    def directory(self) -> str:
        return "/".join(p for p in (self.root, self.runs_dir, self.run_dir) if p)

    def root_ref(self, name: str) -> str:
        return f"{self.root}/{name}" if self.root else name

    def to_json(self) -> dict[str, Any]:
        return {"runs_dir": self.runs_dir, "run_dir": self.run_dir, "model": self.model, "arm": self.arm,
                "number": self.number}


def parse_label(label: str) -> LabelFacets | None:
    """The facets of a response-log label, or ``None`` when its last three segments are outside the layout."""
    parts = [p for p in label.replace("\\", "/").split("/") if p]
    if len(parts) < 3 or parts[-1] != PRIMARY_NAME:
        return None
    m = _DIR.fullmatch(parts[-2])
    if m is None:
        return None
    return LabelFacets("/".join(parts[:-3]), parts[-3], parts[-2], m["model"], m["arm"], int(m["number"]))


def _match(label: str, glob: str) -> bool:
    """``fnmatch`` over a POSIX label, ``**/`` also matching zero directories (the runner's matcher)."""
    if fnmatch.fnmatchcase(label, glob):
        return True
    return "**/" in glob and fnmatch.fnmatchcase(label, glob.replace("**/", "", 1))


class WireLogReader:
    """``Reader`` for ``wirelog.request_response`` (D.2.3, D.20.2)."""

    dialect_id: Final = DIALECT_ID
    version: Final = "0.1.0"
    variants: Final = VARIANTS
    media_types: Final = frozenset({"application/json"})

    def __init__(self) -> None:
        self._last: tuple[bytes, Any] | None = None  # (data, parsed value): the runner sniffs, then parses the same bytes

    # ---------------------------------------------------------------------------------------------- discovery
    def iter_artefacts(self, tree: SourceTree, profile: SourceProfile) -> Iterator[CandidateArtefact]:
        """Primary candidates: the response logs the profile includes and does not exclude, in label order. The run's other
        files and the deposit's tables are walked too, but only as auxiliaries (:meth:`auxiliary_for`)."""
        imp = profile.data.get("import", {})
        include = tuple(imp.get("include", ())) or ("**/" + PRIMARY_NAME,)
        exclude = tuple(e["glob"] for e in imp.get("exclude", ()) if isinstance(e, Mapping) and "glob" in e)
        chosen: list[CandidateArtefact] = []
        for candidate in tree.walk():
            name = candidate.label.rsplit("/", 1)[-1]
            if name in _STRAYS or name.startswith("._") or name != PRIMARY_NAME:
                continue
            if any(_match(candidate.label, g) for g in include) and not any(_match(candidate.label, g) for g in exclude):
                chosen.append(candidate)
        yield from sorted(chosen, key=lambda c: c.label)

    def auxiliary_for(self, label: str, listing: Listing) -> dict[str, str]:
        """The per-unit inputs of primary ``label``: the run directory's sibling files and the deposit's tables, by role,
        when present."""
        facets = parse_label(label)
        if facets is None:
            return {}
        out: dict[str, str] = {}
        for role, name in SIBLINGS.items():
            ref = f"{facets.directory}/{name}"
            if listing.exists(ref):
                out[role] = ref
        for role, name in ROOT_FILES.items():
            ref = facets.root_ref(name)
            if listing.exists(ref):
                out[role] = ref
        return out

    # ---------------------------------------------------------------------------------------------- sniff and parse
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
        if not isinstance(value, list):
            return SniffResult(False, reasons=("wirelog.sniff.not_array",))
        variant = detect_response_variant(value)
        if variant is None:
            return SniffResult(False, reasons=("wirelog.sniff.response_bodies",))
        return SniffResult(True, DIALECT_ID, variant, frozenset(), (f"wirelog.sniff.{variant}",))

    @staticmethod
    def register_detail(reasons: Sequence[str]) -> str | None:
        """No valid non-execution input of this dialect has its own register detail."""
        return None

    def parse(self, data: bytes, artefact: ArtefactRef, *, limits: IngestLimits) -> Iterator[LocatedItem]:
        """One item for the whole response log (key locator ``{"p": ""}``)."""
        sniff = self.sniff(data, label="", limits=limits)
        if not sniff.match or sniff.variant is None:
            raise MalformedArtefact(f"not a wire response log ({', '.join(sniff.reasons)})")
        value = self._load(data, limits)
        self._last = None
        yield LocatedItem(
            artefact=artefact,
            locator=Locator(a=artefact.id, p=""),
            dialect=DIALECT_ID,
            variant=sniff.variant,
            flags=sniff.flags,
            value=value,
        )
