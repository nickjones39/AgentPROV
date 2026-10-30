"""Reader of the DTap-Bench trajectory dialect ``dtap.trajectory`` (docs/architecture D.16.1, D.16.2; D.2.3; layer L4).

**Files.** One JSON object per run, ``{task_info, traj_info, trajectory[]}`` plus an optional ``debug`` block (variant
``v1``, all four harnesses). The reader parses with :func:`agentprov.ingest.loaders.strict_json_loads` under the ingest
limits and interprets nothing: it yields one located item per file (key locator ``{"p": ""}``). A task directory's
``judge_result.json`` is an auxiliary artefact of the trajectories of its directory; it is the primary artefact (flag
:data:`FLAG_JUDGE_ONLY`) only where the directory holds no trajectory-bearing file (D.16.8).

**Sniff outcomes** (D.16.2 table). A Git LFS pointer standing in for JSON, a ``synthetic: true`` trajectory and a
red-teaming log are *valid* inputs of another kind: the sniff returns no match with a ``dtap.*`` reason, which
:meth:`DtapTrajectoryReader.register_detail` hands the runner as the register detail of ``select.not_execution_artefact``.
Bytes that fail the strict loader return the ``ingest.*`` reason (the runner seals a degenerate AER, D.2.8 case 3).

**Path grammar** (D.16.1)::

    <framework>/<model>/<domain>/benign/[<subcategory>/]<task_dir>/<file>
    <framework>/<model>/<domain>/malicious/<threat>/<risk_category>/<task_dir>/<file>

The path is the logical identity of a run; it is read from the artefact's origin (``path``), never from
``task_info.task_id`` or ``trace_id``. A file stem is the generating machine's local time and is never a time (D.16.4).

**Per-unit inputs** (runner items R1 and R2 of D.16.14): :meth:`DtapTrajectoryReader.auxiliary_for` names, for one
primary label, the directory's judge file (``judge``), a byte-identical judge copy (``copy:judge``, stored and registered
``dedup.collapsed`` by the runner), the other trajectory-bearing files of the directory (``attempt:<n>``, for the re-run
group and the judge-to-attempt link of D.16.8) and the joined configuration of the ``tasks`` pin (``config``, the path
rule of D.16.5).

Standard library and ``agentprov.{ingest,errors,adapters}`` only.
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Protocol

from agentprov.adapters.dtap import DIALECT_ID, VARIANT
from agentprov.adapters.profiles import SourceProfile
from agentprov.adapters.protocols import SourceTree
from agentprov.adapters.types import ArtefactRef, CandidateArtefact, LocatedItem, Locator, SniffResult
from agentprov.errors import IngestError, MalformedArtefact
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

__all__ = [
    "FLAG_DEBUG",
    "FLAG_JUDGE_ONLY",
    "FRAMEWORKS",
    "LFS_HEADER",
    "SPLITS",
    "THREATS",
    "DtapTrajectoryReader",
    "PathFacets",
    "config_path",
    "file_class",
    "parse_path",
    "state_form",
]

FRAMEWORKS: Final = frozenset({"openaisdk", "claudesdk", "googleadk", "openclaw"})
SPLITS: Final = frozenset({"benign", "malicious"})
THREATS: Final = frozenset({"direct", "indirect", "direct_prompt", "direct_no_attack"})
#: The first line of a Git LFS pointer file (https://git-lfs.com/spec/v1).
LFS_HEADER: Final = b"version https://git-lfs.github.com/spec/v1\n"
FLAG_DEBUG: Final = "dtap:debug"
FLAG_JUDGE_ONLY: Final = "dtap:judge_only"
TRAJECTORY_KEYS: Final = frozenset({"task_info", "traj_info", "trajectory"})
JUDGE_KEYS: Final = frozenset({"task_success", "task_message", "task_metadata", "attack_success", "attack_message",
                               "attack_metadata", "error", "audit_correction"})
JUDGE_NAME: Final = "judge_result.json"
JUDGE_COPY_NAME: Final = "judge_result(1).json"
#: The ``tasks`` pin role of the profile: configurations are named ``tasks:<path>`` (runner item R2).
TASKS_ROLE: Final = "tasks"
CONFIG_NAME: Final = "config.yaml"
_TS: Final = re.compile(r"[0-9]{8}_[0-9]{6}")
_STRAYS: Final = (".DS_Store",)


class Listing(Protocol):
    """What the runner tells a reader about the walked trees (runner item R1/R2): directory siblings and existence."""

    def siblings(self, label: str) -> Sequence[str]: ...

    def exists(self, ref: str) -> bool: ...


# ------------------------------------------------------------------------------------------------ path grammar
@dataclass(frozen=True, slots=True)
class PathFacets:
    """The path facets of a run (D.16.1). ``relpath`` is the path relative to the dataset root."""

    relpath: str
    framework: str
    model: str
    domain: str
    split: str  # "benign" | "malicious"
    threat: str | None  # malicious only
    risk_category: str | None  # malicious only
    subcategory: str | None  # benign only
    task_dir: str
    file: str

    @property
    def directory(self) -> str:
        return self.relpath.rsplit("/", 1)[0]

    @property
    def file_stem(self) -> str:
        return self.file.removesuffix(".json")

    @property
    def task_path(self) -> str:
        """The path from the split segment to the task directory (``task.task_id``, D.16.1)."""
        if self.split == "benign":
            return "/".join(p for p in ("benign", self.subcategory, self.task_dir) if p is not None)
        return "/".join(("malicious", str(self.threat), str(self.risk_category), self.task_dir))

    @property
    def split_label(self) -> str:
        """``benign`` or the threat segment."""
        return "benign" if self.split == "benign" else str(self.threat)

    def to_json(self) -> dict[str, Any]:
        return {
            "framework": self.framework, "model": self.model, "domain": self.domain, "split": self.split,
            "threat": self.threat, "risk_category": self.risk_category, "subcategory": self.subcategory,
            "task_dir": self.task_dir, "file": self.file,
        }  # fmt: skip


def parse_path(path: str) -> PathFacets | None:
    """The facets of a dataset path, or ``None`` when it is outside the grammar.

    A leading prefix is tolerated (a ``local`` origin carries the whole local path): the grammar is matched at the
    first segment that names a framework and is followed by a well-formed remainder.
    """
    parts = [p for p in path.replace("\\", "/").split("/") if p]
    for i, segment in enumerate(parts):
        if segment not in FRAMEWORKS:
            continue
        found = _facets(parts[i:])
        if found is not None:
            return found
    return None


def _facets(parts: list[str]) -> PathFacets | None:
    if len(parts) < 6 or parts[3] not in SPLITS:
        return None
    fw, model, domain, split = parts[:4]
    rel = "/".join(parts)
    if split == "benign":
        if len(parts) == 6:
            return PathFacets(rel, fw, model, domain, split, None, None, None, parts[4], parts[5])
        if len(parts) == 7:
            return PathFacets(rel, fw, model, domain, split, None, None, parts[4], parts[5], parts[6])
        return None
    if len(parts) == 8 and parts[4] in THREATS:
        return PathFacets(rel, fw, model, domain, split, parts[4], parts[5], None, parts[6], parts[7])
    return None


def config_path(facets: PathFacets) -> str:
    """``dtap.config_path_join@1``: the configuration path of a run in the ``tasks`` dataset (D.16.5)."""
    if facets.split == "benign":
        tail = "/".join(p for p in ("benign", facets.subcategory, facets.task_dir) if p is not None)
    else:
        threat = "direct" if facets.threat in ("direct_prompt", "direct_no_attack") else str(facets.threat)
        tail = "/".join(("malicious", threat, str(facets.risk_category), facets.task_dir))
    return f"{facets.domain}/{tail}/{CONFIG_NAME}"


def file_class(name: str) -> str:
    """The D.16.2 class of a file name: ``timestamp``, ``rerun``, ``copy``, ``trajectory``, ``partial``, ``judge``,
    ``judge_copy``, ``red_teaming``, ``other_json`` or ``other``."""
    if not name.endswith(".json"):
        return "other"
    stem = name[:-5]
    if _TS.fullmatch(stem):
        return "timestamp"
    if stem.endswith("(1)") and _TS.fullmatch(stem[:-3]):
        return "copy"
    head, sep, tail = stem.rpartition("_")
    if sep and _TS.fullmatch(head) and tail.isdigit() and tail.isascii():
        return "rerun"
    if name == "trajectory.json":
        return "trajectory"
    if name == "partial_trajectory.json":
        return "partial"
    if name == JUDGE_NAME:
        return "judge"
    if name == JUDGE_COPY_NAME:
        return "judge_copy"
    if name.startswith("red_teaming_agent_"):
        return "red_teaming"
    return "other_json"


#: File classes that carry a trajectory (D.16.2); ``other_json`` is offered to the sniff too (unknown names are never
#: dropped silently).
TRAJECTORY_CLASSES: Final = frozenset({"timestamp", "rerun", "copy", "trajectory", "partial", "other_json"})


def state_form(value: object) -> str:
    """The D.16.2 classification of a tool ``state``, without interpreting it: ``object``, ``array``, ``text``,
    ``python_repr`` (starts with ``{'`` or ``[{'`` and is not JSON), ``brace_text`` (another ``{``/``[`` string that is
    not JSON), ``integer``, ``number``, ``boolean`` or ``null``. Nothing is evaluated."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        stripped = value.lstrip()
        if stripped.startswith(("{", "[")):
            try:
                strict_json_loads(stripped.encode("utf-8"))
            except (IngestError, UnicodeEncodeError):
                return "python_repr" if stripped.startswith(("{'", "[{'")) else "brace_text"
            return "json_text"
        return "text"
    return "other"


def _sort_key(label: str) -> tuple[str, str]:
    """Directory order; inside a directory a ``(1)`` copy follows its plain file (so the plain file is the primary)."""
    head, _, name = label.rpartition("/")
    return head, name.replace("(1).json", ".json\x7f")


def _match(label: str, glob: str) -> bool:
    """``fnmatch`` over a POSIX label, ``**/`` also matching zero directories (the runner's matcher)."""
    if fnmatch.fnmatchcase(label, glob):
        return True
    return "**/" in glob and fnmatch.fnmatchcase(label, glob.replace("**/", "", 1))


class DtapTrajectoryReader:
    """``Reader`` for ``dtap.trajectory`` (D.2.3, D.16.2)."""

    dialect_id: Final = DIALECT_ID
    version: Final = "0.1.0"
    variants: Final = frozenset({VARIANT})
    media_types: Final = frozenset({"application/json"})

    def __init__(self) -> None:
        self._last: tuple[bytes, Any] | None = None  # (data, parsed value): the runner sniffs, then parses the same bytes

    # ---------------------------------------------------------------------------------------------- discovery
    def iter_artefacts(self, tree: SourceTree, profile: SourceProfile) -> Iterator[CandidateArtefact]:
        """Primary candidates: trajectory-bearing files, and a judge file only where its directory holds none."""
        imp = profile.data.get("import", {})
        include = tuple(imp.get("include", ())) or ("**/*.json",)
        exclude = tuple(e["glob"] for e in imp.get("exclude", ()) if isinstance(e, Mapping) and "glob" in e)
        by_dir: dict[str, list[CandidateArtefact]] = {}
        for candidate in tree.walk():
            name = candidate.label.rsplit("/", 1)[-1]
            if name in _STRAYS or name.startswith("._"):
                continue
            if not any(_match(candidate.label, g) for g in include) or any(_match(candidate.label, g) for g in exclude):
                continue
            by_dir.setdefault(candidate.label.rpartition("/")[0], []).append(candidate)
        chosen: list[CandidateArtefact] = []
        for items in by_dir.values():
            classes = {c.label: file_class(c.label.rsplit("/", 1)[-1]) for c in items}
            trajectories = [c for c in items if classes[c.label] in TRAJECTORY_CLASSES]
            if trajectories:
                chosen += trajectories
            else:
                chosen += [c for c in items if classes[c.label] == "judge"]
        yield from sorted(chosen, key=lambda c: _sort_key(c.label))

    def auxiliary_for(self, label: str, listing: Listing) -> dict[str, str]:
        """The per-unit inputs of primary ``label`` (runner items R1 and R2; module docstring)."""
        out: dict[str, str] = {}
        directory, _, name = label.rpartition("/")
        own = file_class(name)
        prefix = f"{directory}/" if directory else ""
        if own == "judge":
            if listing.exists(prefix + JUDGE_COPY_NAME):
                out["copy:judge"] = prefix + JUDGE_COPY_NAME
            return out
        if listing.exists(prefix + JUDGE_NAME):
            out["judge"] = prefix + JUDGE_NAME
            if listing.exists(prefix + JUDGE_COPY_NAME):
                out["copy:judge"] = prefix + JUDGE_COPY_NAME
        others = [s for s in listing.siblings(label) if s != label
                  and file_class(s.rsplit("/", 1)[-1]) in TRAJECTORY_CLASSES]
        for n, sibling in enumerate(sorted(others, key=_sort_key)):
            out[f"attempt:{n}"] = sibling
        facets = parse_path(label)
        if facets is not None:
            ref = f"{TASKS_ROLE}:{config_path(facets)}"
            if listing.exists(ref):
                out["config"] = ref
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
        if data.startswith(LFS_HEADER):
            return SniffResult(False, reasons=("dtap.lfs_pointer",))
        try:
            value = self._load(data, limits)
        except IngestError as exc:
            return SniffResult(False, reasons=(exc.code,))
        if not isinstance(value, dict):
            return SniffResult(False, reasons=("dtap.sniff.not_object",))
        keys = set(value)
        if TRAJECTORY_KEYS <= keys and keys <= TRAJECTORY_KEYS | {"debug"}:
            task_info, traj_info = value.get("task_info"), value.get("traj_info")
            metadata = traj_info.get("metadata") if isinstance(traj_info, dict) else None
            if (isinstance(task_info, dict) and task_info.get("synthetic") is True) or (
                    isinstance(metadata, dict) and metadata.get("synthetic") is True):
                return SniffResult(False, reasons=("dtap.synthetic",))
            flags = frozenset({FLAG_DEBUG}) if "debug" in keys else frozenset()
            return SniffResult(True, DIALECT_ID, VARIANT, flags, ("dtap.sniff.trajectory_keys",))
        if {"task_success", "attack_success"} <= keys and keys <= JUDGE_KEYS:
            return SniffResult(True, DIALECT_ID, VARIANT, frozenset({FLAG_JUDGE_ONLY}), ("dtap.sniff.judge_keys",))
        if {"task_info", "attack_trajectory"} <= keys:
            return SniffResult(False, reasons=("dtap.red_teaming_log",))
        return SniffResult(False, reasons=("dtap.sniff.keys",))

    @staticmethod
    def register_detail(reasons: Sequence[str]) -> str | None:
        """The register detail of a valid non-execution input (D.16.2: ``dtap.synthetic``, ``dtap.lfs_pointer``,
        ``dtap.red_teaming_log``); ``None`` lets the runner use its default detail."""
        return next((r for r in reasons if r.startswith("dtap.") and not r.startswith("dtap.sniff.")), None)

    def parse(self, data: bytes, artefact: ArtefactRef, *, limits: IngestLimits) -> Iterator[LocatedItem]:
        """One item for the whole file (key locator ``{"p": ""}``)."""
        sniff = self.sniff(data, label="", limits=limits)
        if not sniff.match:
            raise MalformedArtefact(f"not a DTap trajectory or judge file ({', '.join(sniff.reasons)})")
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
