"""Reader of the OpenHands event-stream dialect ``openhands.events`` (docs/architecture D.17.1, D.17.2; D.2.3; layer L4).

**Files.** One JSON array of serialised events per run. An event is an object with ``id``, ``timestamp`` and ``source``
and exactly one of ``action`` and ``observation``. The reader parses with
:func:`agentprov.ingest.loaders.strict_json_loads` under the ingest limits and interprets nothing: it yields one located
item per file (key locator ``{"p": ""}``).

**Variants** (D-170), chosen from the event vocabulary, never from a path:

* ``oh-1.5``: the first event is a ``system`` action whose ``args`` carry ``openhands_version`` (every RedCode run of
  Zenodo 23168099: ``1.5.0``);
* ``oas-0.28``: no ``system`` action anywhere (every OpenAgentSafety run: the 0.28.1 fork with Sotopia NPC ``chat``).

A ``system`` action elsewhere, or one without ``openhands_version``, is a vocabulary this reader does not know: the sniff
says no with ``openhands.sniff.variant``. An empty array is not a run (``openhands.sniff.empty``).

**Path grammars** (D.17.1). The path is the run's logical identity; it is read from the artefact's origin (``path`` of a
git origin, ``label`` of a member or local origin), with any leading prefix tolerated::

    evaluation/<model_dir>/traj_<task>.json                                                     (OpenAgentSafety)
    results/OH/<model>/<S1|S2|S3>/<python|bash>/trajectory/oh_<sc>_<payload>[_py|_sh]_<S>-<hash>.json   (RedCode)

**Per-unit inputs** (runner items R1/R2 of D.16.14): :meth:`OpenHandsEventsReader.auxiliary_for` names, for one primary,
the OpenAgentSafety evaluation file (``eval``), state file (``state``), the model directory's LLM-judge summary
(``llm_judge``) and the task directory's ``task.md``, ``checkpoints.md``, ``scenarios.json`` and ``utils/evaluator.py``
(``task_md``, ``checkpoints``, ``scenarios``, ``evaluator``; never executed); for RedCode the score record
(``score``), the generated prompt (``prompt``, S2/S3) and the dataset code (``dataset``, S1) of the deposit.

Standard library and ``agentprov.{ingest,errors,adapters}`` only.
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Protocol

from agentprov.adapters.openhands import DIALECT_ID, VARIANT_OAS, VARIANT_OH15, VARIANTS
from agentprov.adapters.profiles import SourceProfile
from agentprov.adapters.protocols import SourceTree
from agentprov.adapters.types import ArtefactRef, CandidateArtefact, LocatedItem, Locator, SniffResult
from agentprov.errors import IngestError, MalformedArtefact
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

__all__ = ["OAS", "REDCODE", "OpenHandsEventsReader", "PathFacets", "event_kind", "parse_path"]

OAS: Final = "oas"
REDCODE: Final = "redcode"
_OAS_PATH: Final = re.compile(r"(?:^|.*/)(?P<rel>evaluation/(?P<model>[^/]+)/traj_(?P<task>[^/]+)\.json)$")
_RC_PATH: Final = re.compile(
    r"(?:^|.*/)(?P<rel>results/OH/(?P<model>[^/]+)/(?P<target>S[123])/(?P<lang>python|bash)/trajectory/"
    r"oh_(?P<scenario>[0-9]{1,4})_(?P<payload>[0-9]{1,4})(?:_(?P<ltag>py|sh))?_(?P<target2>S[123])-(?P<hash>[0-9a-f]{1,64})\.json)$"
)
_EVENT_KEYS: Final = frozenset({"id", "timestamp", "source"})
_STRAYS: Final = (".DS_Store",)
_DATASET_DIR: Final = {"python": "py2text_dataset_json", "bash": "bash2text_dataset_json"}
#: D-932 (D-530): RedCode's score records, prompts and dataset code are members of the supplementary zip, the ``supp``
#: context pin; a context listing answers existence only, so the dataset file is named exactly (qwencode's names).
SUPP_ROLE: Final = "supp"
_DATASET_FILE: Final = {"python": "index{sc}_30_codes_full.json", "bash": "index{sc}_30_codes_full_upd.json"}


class Listing(Protocol):
    """What the runner tells a reader about the walked trees (runner items R1/R2): directory siblings and existence."""

    def siblings(self, label: str) -> Sequence[str]: ...

    def exists(self, ref: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class PathFacets:
    """The path facets of a run (D.17.1). ``prefix`` is whatever precedes the grammar's first segment."""

    source: str  # "oas" | "redcode"
    prefix: str
    relpath: str
    model: str
    task: str | None = None  # OAS
    target: str | None = None  # RedCode S1-S3
    language: str | None = None
    scenario: int | None = None
    payload: int | None = None
    case_hash: str | None = None

    @property
    def case_key(self) -> str | None:
        """RedCode ``"<scenario>_<payload>"`` (the ``index`` of the deposit's score records)."""
        return None if self.scenario is None else f"{self.scenario}_{self.payload}"

    def to_json(self) -> dict[str, Any]:
        if self.source == OAS:
            return {"source": OAS, "model_dir": self.model, "task": self.task}
        return {"source": REDCODE, "model_dir": self.model, "target": self.target, "language": self.language,
                "scenario": self.scenario, "payload": self.payload, "case_hash": self.case_hash}


def parse_path(path: str) -> PathFacets | None:
    """The facets of a run path, or ``None`` outside both grammars (a mismatched target pair is outside too)."""
    text = path.replace("\\", "/")
    m = _OAS_PATH.match(text)
    if m is not None:
        return PathFacets(OAS, text[: m.start("rel")], m["rel"], m["model"], task=m["task"])
    m = _RC_PATH.match(text)
    if m is None or m["target"] != m["target2"]:
        return None
    return PathFacets(REDCODE, text[: m.start("rel")], m["rel"], m["model"], target=m["target"], language=m["lang"],
                      scenario=int(m["scenario"]), payload=int(m["payload"]), case_hash=m["hash"])


def event_kind(event: Mapping[str, Any]) -> tuple[str, str]:
    """``("action", name)``, ``("observation", name)`` or ``("other", "?")``."""
    if "action" in event and "observation" not in event:
        return "action", str(event.get("action"))
    if "observation" in event and "action" not in event:
        return "observation", str(event.get("observation"))
    return "other", "?"


def _match(label: str, glob: str) -> bool:
    if fnmatch.fnmatchcase(label, glob):
        return True
    return "**/" in glob and fnmatch.fnmatchcase(label, glob.replace("**/", "", 1))


class OpenHandsEventsReader:
    """``Reader`` for ``openhands.events`` (D.2.3, D.17.2)."""

    dialect_id: Final = DIALECT_ID
    version: Final = "0.1.0"
    variants: Final = frozenset(VARIANTS)
    media_types: Final = frozenset({"application/json"})

    def __init__(self) -> None:
        self._last: tuple[bytes, Any] | None = None  # (data, parsed value): the runner sniffs, then parses the same bytes

    # ---------------------------------------------------------------------------------------------- discovery
    def iter_artefacts(self, tree: SourceTree, profile: SourceProfile) -> Iterator[CandidateArtefact]:
        """Primary candidates: files of the profile's include globs (minus excludes) inside a path grammar."""
        imp = profile.data.get("import", {})
        include = tuple(imp.get("include", ())) or ("**/*.json",)
        exclude = tuple(e["glob"] for e in imp.get("exclude", ()) if isinstance(e, Mapping) and "glob" in e)
        chosen = []
        for candidate in tree.walk():
            name = candidate.label.rsplit("/", 1)[-1]
            if name in _STRAYS or name.startswith("._"):
                continue
            if not any(_match(candidate.label, g) for g in include) or any(_match(candidate.label, g) for g in exclude):
                continue
            chosen.append(candidate)
        yield from sorted(chosen, key=lambda c: c.label)

    def auxiliary_for(self, label: str, listing: Listing) -> dict[str, str]:
        """The per-unit inputs of primary ``label`` (module docstring); only files the listing has are named."""
        facets = parse_path(label)
        if facets is None:
            return {}
        out: dict[str, str] = {}
        pre = facets.prefix
        if facets.source == OAS:
            base = f"{pre}evaluation/{facets.model}/"
            for role, name in (("eval", f"eval_{facets.task}.json"), ("state", f"state_{facets.task}.json")):
                if listing.exists(base + name):
                    out[role] = base + name
            summaries = sorted(s for s in listing.siblings(label)
                               if s.startswith(base) and s.endswith("_safety_eval_results.json") and "/" not in s[len(base):])
            if len(summaries) == 1:
                out["llm_judge"] = summaries[0]
            task_dir = f"{pre}workspaces/tasks/{facets.task}/"
            for role, name in (("task_md", "task.md"), ("checkpoints", "checkpoints.md"), ("scenarios", "scenarios.json"),
                               ("evaluator", "utils/evaluator.py")):
                if listing.exists(task_dir + name):
                    out[role] = task_dir + name
            return out
        lang, target, sc = str(facets.language), str(facets.target), facets.scenario

        def ref(rel: str) -> str | None:  # the supp context tree first (D-530), else the primary tree (one tree holds both)
            return next((r for r in (f"{SUPP_ROLE}:{rel}", f"{pre}{rel}") if listing.exists(r)), None)

        score = ref(f"results/OH/{facets.model}/{target}/{lang}/conversation_log/index{sc}.json")
        if score is not None:
            out["score"] = score
        if target == "S1":
            rel = f"dataset/RedCode-Exec/{_DATASET_DIR[lang]}/"
            named = f"{SUPP_ROLE}:{rel}{_DATASET_FILE[lang].format(sc=sc)}"
            if listing.exists(named):
                out["dataset"] = named
            else:
                folder = f"{pre}{rel}"
                hits = sorted(s for s in listing.siblings(folder + "x.json")
                              if s.startswith(f"{folder}index{sc}_") and s.endswith(".json") and "/" not in s[len(folder):])
                if len(hits) == 1:
                    out["dataset"] = hits[0]
        else:
            prompt = ref(f"prompt_generator/output/{lang}/{target}/index{sc}.json")
            if prompt is not None:
                out["prompt"] = prompt
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
            return SniffResult(False, reasons=("openhands.sniff.not_array",))
        if not value:
            return SniffResult(False, reasons=("openhands.sniff.empty",))
        for event in value:
            if not isinstance(event, dict) or not _EVENT_KEYS <= set(event) or event_kind(event)[0] == "other":
                return SniffResult(False, reasons=("openhands.sniff.event_shape",))
        systems = [i for i, e in enumerate(value) if e.get("action") == "system"]
        if not systems:
            return SniffResult(True, DIALECT_ID, VARIANT_OAS, frozenset(), ("openhands.sniff.no_system_action",))
        args = value[0].get("args")
        if systems == [0] and isinstance(args, dict) and isinstance(args.get("openhands_version"), str):
            return SniffResult(True, DIALECT_ID, VARIANT_OH15, frozenset(), ("openhands.sniff.system_first",))
        return SniffResult(False, reasons=("openhands.sniff.variant",))

    @staticmethod
    def register_detail(reasons: Sequence[str]) -> str | None:
        """The register detail of a valid non-execution input: ``openhands.sniff.empty`` (an empty event list)."""
        return "openhands.empty_event_list" if "openhands.sniff.empty" in reasons else None

    def parse(self, data: bytes, artefact: ArtefactRef, *, limits: IngestLimits) -> Iterator[LocatedItem]:
        """One item for the whole file (key locator ``{"p": ""}``)."""
        sniff = self.sniff(data, label="", limits=limits)
        if not sniff.match or sniff.variant is None:
            raise MalformedArtefact(f"not an OpenHands event list ({', '.join(sniff.reasons)})")
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
