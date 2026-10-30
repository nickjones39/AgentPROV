"""Reader of the AgentOps-Bench run dialect ``agentops.trace`` (docs/architecture D.18.1, D.18.2; D.2.3; layer L4).

**Files.** One JSON object per run, ``{task_id, agent_id, condition, run_number, trace, scores}`` (variant ``v1``, all
7,202 run files of the pilot; the pydantic ``RunResult`` of the harness snapshot). The reader parses with
:func:`agentprov.ingest.loaders.strict_json_loads` under the ingest limits and interprets nothing: it yields one located
item per file (key locator ``{"p": ""}``). A per-model ``*_report.json`` (``{agent_id, results, aggregate_scores, ...}``)
is a valid input of another kind: the sniff returns no match with reason ``agentops.report`` (register detail of
``select.not_execution_artefact``). Bytes that fail the strict loader return the ``ingest.*`` reason.

**Label grammar** (D.18.1)::

    <root>/<agent_dir>/<provider_model>/<condition>/<domain>_<NNN>_run<k>.json

``<root>`` is ``pilot_v1_seeded`` in the pinned archive; the last five segments are matched, so a prefix is tolerated (a
``local`` origin carries the whole local path). The label is a label, never a path to open.

**Per-unit inputs** (runner items R1 and R2 of D.16.14): :meth:`AgentOpsTraceReader.auxiliary_for` names the run's task
definition in the ``tasks`` pin (``task``), found through the pinned table ``tables/task_files.toml`` (the file name's
slug is not derivable from a run).

Standard library and ``agentprov.{ingest,errors,adapters}`` only.
"""

from __future__ import annotations

import fnmatch
import re
import tomllib
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from importlib import resources
from types import MappingProxyType
from typing import Any, Final, Protocol

from agentprov.adapters.agentops import DIALECT_ID, VARIANT
from agentprov.adapters.profiles import SourceProfile
from agentprov.adapters.protocols import SourceTree
from agentprov.adapters.types import ArtefactRef, CandidateArtefact, LocatedItem, Locator, SniffResult
from agentprov.errors import IngestError, MalformedArtefact
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

__all__ = [
    "CONDITIONS",
    "RESULT_KEYS",
    "RUN_KEYS",
    "STEP_KEYS",
    "TASKS_ROLE",
    "TRACE_KEYS",
    "AgentOpsTraceReader",
    "LabelFacets",
    "TaskFile",
    "parse_label",
    "task_files",
]

CONDITIONS: Final = frozenset({"clean", "noisy", "adversarial"})
RUN_KEYS: Final = frozenset({"task_id", "agent_id", "condition", "run_number", "trace", "scores"})
TRACE_KEYS: Final = frozenset({"task_id", "agent_id", "condition", "steps", "total_input_tokens", "total_output_tokens",
                               "total_cost_usd", "wall_time_seconds", "completed", "final_output", "error"})
STEP_KEYS: Final = frozenset({"step_number", "llm_input_tokens", "llm_output_tokens", "tool_calls", "tool_results",
                              "reasoning"})
CALL_KEYS: Final = frozenset({"tool_name", "arguments", "timestamp"})
RESULT_KEYS: Final = frozenset({"tool_name", "result", "latency_ms", "injected_failure", "injected_payload"})
REPORT_KEYS: Final = frozenset({"agent_id", "results", "aggregate_scores"})
#: The ``tasks`` pin role of the profile: task definitions are named ``tasks:<member label>`` (runner item R2).
TASKS_ROLE: Final = "tasks"
_STRAYS: Final = (".DS_Store",)
_FILE: Final = re.compile(r"(?P<domain>[a-z][a-z_]*)_(?P<number>[0-9]{3})_run(?P<run>[1-9][0-9]*)\.json")


class Listing(Protocol):
    """What the runner tells a reader about the walked trees (runner items R1/R2): directory siblings and existence."""

    def siblings(self, label: str) -> Sequence[str]: ...

    def exists(self, ref: str) -> bool: ...


# ------------------------------------------------------------------------------------------------ label grammar
@dataclass(frozen=True, slots=True)
class LabelFacets:
    """The facets of a run's member label (D.18.1). ``relpath`` starts at the archive root segment."""

    relpath: str
    root: str
    agent_dir: str
    model_dir: str
    condition: str
    domain: str
    number: str  # three digits, as written
    run: int
    file: str

    @property
    def task_id(self) -> str:
        """The task id the label names: ``<domain>/<NNN>`` (the form of the in-record ``task_id``)."""
        return f"{self.domain}/{self.number}"

    def to_json(self) -> dict[str, Any]:
        return {"root": self.root, "agent_dir": self.agent_dir, "model_dir": self.model_dir,
                "condition": self.condition, "domain": self.domain, "number": self.number, "run": self.run,
                "file": self.file}  # fmt: skip


def parse_label(label: str) -> LabelFacets | None:
    """The facets of a run label, or ``None`` when its last five segments are outside the grammar."""
    parts = [p for p in label.replace("\\", "/").split("/") if p]
    if len(parts) < 5:
        return None
    root, agent_dir, model_dir, condition, name = parts[-5:]
    m = _FILE.fullmatch(name)
    if condition not in CONDITIONS or m is None:
        return None
    return LabelFacets("/".join(parts[-5:]), root, agent_dir, model_dir, condition, m["domain"], m["number"],
                       int(m["run"]), name)


# ------------------------------------------------------------------------------------------------ task table
@dataclass(frozen=True, slots=True)
class TaskFile:
    """One row of ``tables/task_files.toml``: the member of the ``tasks`` pin that defines a task."""

    id: str
    label: str
    sha256: str
    bytes: int


@cache
def task_files() -> Mapping[str, TaskFile]:
    """The pinned task table by task id (package data; D-194)."""
    raw = resources.files("agentprov.adapters.agentops").joinpath("tables", "task_files.toml").read_bytes()
    doc = tomllib.loads(raw.decode("utf-8"))
    out: dict[str, TaskFile] = {}
    for row in doc.get("task", []):
        entry = TaskFile(str(row["id"]), str(row["label"]), str(row["sha256"]), int(row["bytes"]))
        if entry.id in out:
            raise MalformedArtefact(f"task table: task {entry.id!r} is listed twice")
        out[entry.id] = entry
    return MappingProxyType(out)


def _match(label: str, glob: str) -> bool:
    """``fnmatch`` over a POSIX label, ``**/`` also matching zero directories (the runner's matcher)."""
    if fnmatch.fnmatchcase(label, glob):
        return True
    return "**/" in glob and fnmatch.fnmatchcase(label, glob.replace("**/", "", 1))


class AgentOpsTraceReader:
    """``Reader`` for ``agentops.trace`` (D.2.3, D.18.2)."""

    dialect_id: Final = DIALECT_ID
    version: Final = "0.1.0"
    variants: Final = frozenset({VARIANT})
    media_types: Final = frozenset({"application/json"})

    def __init__(self) -> None:
        self._last: tuple[bytes, Any] | None = None  # (data, parsed value): the runner sniffs, then parses the same bytes

    # ---------------------------------------------------------------------------------------------- discovery
    def iter_artefacts(self, tree: SourceTree, profile: SourceProfile) -> Iterator[CandidateArtefact]:
        """Primary candidates: the run files the profile includes and does not exclude, in label order."""
        imp = profile.data.get("import", {})
        include = tuple(imp.get("include", ())) or ("**/*.json",)
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
        """The per-unit inputs of primary ``label``: its task definition (``task``), when the pin holds it."""
        facets = parse_label(label)
        if facets is None:
            return {}
        row = task_files().get(facets.task_id)
        if row is None:
            return {}
        ref = f"{TASKS_ROLE}:{row.label}"
        return {"task": ref} if listing.exists(ref) else {}

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
        if not isinstance(value, dict):
            return SniffResult(False, reasons=("agentops.sniff.not_object",))
        keys = set(value)
        if keys == RUN_KEYS:
            trace = value.get("trace")
            if isinstance(trace, dict) and set(trace) == TRACE_KEYS:
                return SniffResult(True, DIALECT_ID, VARIANT, frozenset(), ("agentops.sniff.run_keys",))
            return SniffResult(False, reasons=("agentops.sniff.trace_keys",))
        if REPORT_KEYS <= keys:
            return SniffResult(False, reasons=("agentops.report",))
        return SniffResult(False, reasons=("agentops.sniff.keys",))

    @staticmethod
    def register_detail(reasons: Sequence[str]) -> str | None:
        """The register detail of a valid non-execution input (``agentops.report``); ``None`` for the default."""
        return next((r for r in reasons if r.startswith("agentops.") and not r.startswith("agentops.sniff.")), None)

    def parse(self, data: bytes, artefact: ArtefactRef, *, limits: IngestLimits) -> Iterator[LocatedItem]:
        """One item for the whole file (key locator ``{"p": ""}``)."""
        sniff = self.sniff(data, label="", limits=limits)
        if not sniff.match:
            raise MalformedArtefact(f"not an AgentOps-Bench run file ({', '.join(sniff.reasons)})")
        value = self._load(data, limits)
        self._last = None
        yield LocatedItem(
            artefact=artefact,
            locator=Locator(a=artefact.id, p=""),
            dialect=DIALECT_ID,
            variant=VARIANT,
            flags=sniff.flags,
            value=value,
        )
