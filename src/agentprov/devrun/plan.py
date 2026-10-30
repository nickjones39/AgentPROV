"""Dev runs, the pure part (D-705; GUI design §19; D-544, D-529; moved from the GUI): the settings, the part plan
and the per-part summary. Read-only: no write, spawn or network, so the GUI may import it (D-391 allowlist) to
preview a plan; ``agentprov devrun`` (``cli/devrun.py``) does everything that writes.

**Settings** are ``agentprov settings`` keys (D-703): ``devrun.samples``, ``devrun.override.<source>[.<part>]``,
``devrun.include``/``exclude``, ``devrun.sample_mode``, ``devrun.seed``, ``devrun.keep``, ``devrun.queue_cpu``,
``devrun.prov_conformance`` and the live ones ``devrun.live.*``. An unset key is the shipped default
(:data:`DEFAULTS`).

**The plan** is every registry part whose import status is ``supported`` or ``partial`` (role ``source``), less the
excluded ones, restricted to the included ones when any are given, each with its sample count (an override of 0 skips
it).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Final

__all__ = ["DEFAULTS", "DEVRUN_FORMAT", "DevPart", "DevSettings", "PartSummary", "importable_parts", "plan",
           "summarise"]

IMPORTABLE: Final = ("supported", "partial")
DEVRUN_FORMAT: Final = "agentprov-devrun/0.1"
RUN_DIR_RE: Final = re.compile(r"(\d{8}T\d{6}Z)(?:-(\d+))?")  # fullmatch: <stamp> or <stamp>-N
_SAFE: Final = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True, slots=True)
class DevSettings:
    samples: int = 5
    overrides: Mapping[str, int] = field(default_factory=dict)  # "source/part" or "source" -> N (0 skips)
    include: tuple[str, ...] = ()  # empty: every importable part
    exclude: tuple[str, ...] = ()
    mode: str = "first"  # first | spread | random
    seed: int = 0
    keep: int = 5
    queue_cpu: int = 2
    prov_conformance: bool = True  # §8.3a: on by default
    live_transport: str = "scripted"
    live_tasks_per_suite: int = 3
    live_attacks_per_task: int = 1
    live_suites: tuple[str, ...] = ()
    live_call_cap: int = 5
    live_cost_cap: float | None = None

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["overrides"] = dict(self.overrides)
        d["include"], d["exclude"], d["live_suites"] = list(self.include), list(self.exclude), list(self.live_suites)
        return d

    @classmethod
    def from_settings(cls, values: Mapping[str, Any]) -> DevSettings:
        """From ``agentprov settings`` values (already checked by its schema); an absent key is the default."""
        d = DEFAULTS

        def get(key: str, default: Any) -> Any:
            return values.get(f"devrun.{key}", default)

        overrides: dict[str, int] = {}
        for key, value in values.items():
            if key.startswith("devrun.override.") and isinstance(value, int) and not isinstance(value, bool):
                name = key[len("devrun.override."):]
                source, _, part = name.partition(".")
                overrides[f"{source}/{part}" if part else source] = value
        cost = get("live.cost_cap", None)
        return cls(
            samples=int(get("samples", d.samples)), overrides=overrides,
            include=tuple(get("include", [])), exclude=tuple(get("exclude", [])),
            mode=str(get("sample_mode", d.mode)), seed=int(get("seed", d.seed)), keep=int(get("keep", d.keep)),
            queue_cpu=int(get("queue_cpu", d.queue_cpu)),
            prov_conformance=get("prov_conformance", True) is not False,
            live_transport=str(get("live.transport", d.live_transport)),
            live_tasks_per_suite=int(get("live.tasks_per_suite", d.live_tasks_per_suite)),
            live_attacks_per_task=int(get("live.attacks_per_task", d.live_attacks_per_task)),
            live_suites=tuple(get("live.suites", [])), live_call_cap=int(get("live.call_cap", d.live_call_cap)),
            live_cost_cap=float(cost) if isinstance(cost, int | float) and not isinstance(cost, bool) else None,
        )  # fmt: skip

    def to_settings(self) -> dict[str, Any]:
        """The ``agentprov settings`` keys that differ from :data:`DEFAULTS` (what ``settings set`` stores)."""
        out: dict[str, Any] = {}
        pairs = (("samples", self.samples, DEFAULTS.samples), ("sample_mode", self.mode, DEFAULTS.mode),
                 ("seed", self.seed, DEFAULTS.seed), ("keep", self.keep, DEFAULTS.keep),
                 ("queue_cpu", self.queue_cpu, DEFAULTS.queue_cpu),
                 ("prov_conformance", self.prov_conformance, DEFAULTS.prov_conformance),
                 ("live.transport", self.live_transport, DEFAULTS.live_transport),
                 ("live.tasks_per_suite", self.live_tasks_per_suite, DEFAULTS.live_tasks_per_suite),
                 ("live.attacks_per_task", self.live_attacks_per_task, DEFAULTS.live_attacks_per_task),
                 ("live.call_cap", self.live_call_cap, DEFAULTS.live_call_cap))
        for key, value, default in pairs:
            if value != default:
                out[f"devrun.{key}"] = value
        lists: tuple[tuple[str, tuple[str, ...]], ...] = (("include", self.include), ("exclude", self.exclude),
                                                          ("live.suites", self.live_suites))
        for name, items in lists:
            if items:
                out[f"devrun.{name}"] = list(items)
        if self.live_cost_cap is not None:
            out["devrun.live.cost_cap"] = self.live_cost_cap
        for name, n in self.overrides.items():
            source, _, part = name.partition("/")
            out[f"devrun.override.{source}" + (f".{part}" if part else "")] = n
        return out


DEFAULTS: Final = DevSettings()


@dataclass(frozen=True, slots=True)
class DevPart:
    source: str
    part: str
    samples: int
    status: str
    profile: str | None

    @property
    def key(self) -> str:
        return f"{self.source}/{self.part}"

    @property
    def folder(self) -> str:
        return _SAFE.sub("_", f"{self.source}-{self.part}")

    def to_json(self) -> dict[str, Any]:
        return {"source": self.source, "part": self.part, "samples": self.samples, "status": self.status,
                "profile": self.profile, "folder": self.folder}


def importable_parts() -> list[tuple[str, str, str, str | None]]:
    """``(source, part, import status, profile)`` of every registry part a dev run can import."""
    from agentprov.adapters.registry import REGISTRY

    out = []
    for source in REGISTRY:
        for cap in source.capabilities:
            if cap.import_status in IMPORTABLE and cap.role == "source":
                out.append((source.source_id, cap.part, str(cap.import_status), cap.profile))
    return sorted(out)


def plan(settings: DevSettings, parts: Iterable[tuple[str, str, str, str | None]] | None = None) -> list[DevPart]:
    chosen: list[DevPart] = []
    for source, part, status, profile in (importable_parts() if parts is None else parts):
        key = f"{source}/{part}"
        if settings.include and key not in settings.include and source not in settings.include:
            continue
        if key in settings.exclude or source in settings.exclude:
            continue
        n = settings.overrides.get(key, settings.overrides.get(source, settings.samples))
        if n > 0:
            chosen.append(DevPart(source, part, n, status, profile))
    return chosen


@dataclass(slots=True)
class PartSummary:
    part: str
    import_outcome: str | None = None
    counters: dict[str, int] = field(default_factory=dict)
    issues_top: list[tuple[str, int]] = field(default_factory=list)
    validate_outcome: str | None = None
    recompute_outcome: str | None = None
    recompute_counters: dict[str, int] = field(default_factory=dict)
    seconds: dict[str, float] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {**asdict(self), "issues_top": [list(i) for i in self.issues_top]}


def _ints(value: Any) -> dict[str, int]:
    return {str(k): v for k, v in value.items() if isinstance(v, int) and not isinstance(v, bool)} \
        if isinstance(value, dict) else {}


def summarise(jobs: Iterable[Any]) -> list[PartSummary]:
    """One row per part from dev-run jobs (:class:`agentprov.jobs.record.Job`, or anything with ``record``,
    ``command``, ``outcome`` and ``file``): their ``summary.json`` and ``job.json``. A job's part is its ``part``
    fact (``--meta`` / a batch step's ``extra``)."""
    from agentprov.jobs.record import read_json

    rows: dict[str, PartSummary] = {}
    for job in jobs:
        extra = job.record.get("extra") if isinstance(job.record.get("extra"), dict) else {}
        part = job.record.get("part", extra.get("part"))
        if not isinstance(part, str):
            continue
        row = rows.setdefault(part, PartSummary(part))
        summary = read_json(job.file("summary.json")) or {}
        outcome = job.outcome or (str(summary.get("outcome")) if summary.get("outcome") else None)
        try:
            spent = job.file("ended.json").stat().st_mtime - job.file("job.json").stat().st_ctime
        except OSError:
            spent = None
        if spent is not None and spent >= 0:
            row.seconds[job.command] = round(spent, 1)
        if job.command == "import":
            row.import_outcome = outcome
            row.counters = _ints(summary.get("counters"))
            issues = _ints(summary.get("issues_by_code"))
            row.issues_top = sorted(issues.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
        elif job.command == "validate":
            row.validate_outcome = outcome
        elif job.command == "recompute":
            row.recompute_outcome = outcome
            row.recompute_counters = _ints(summary.get("counters"))
    return [rows[k] for k in sorted(rows)]


def run_dirs(home: Path) -> list[Path]:
    """The ``dev-runs/<stamp>[-N]`` folders with a regular ``devrun.json`` of :data:`DEVRUN_FORMAT`, oldest first
    (GR-26: anything else is neither listed nor pruned; a linked ``dev-runs`` folder is refused)."""
    from agentprov.jobs.record import read_json

    root = Path(home) / "dev-runs"
    if root.is_symlink() or not root.is_dir():
        return []
    runs: list[tuple[tuple[str, int], Path]] = []
    for p in root.iterdir():
        m = RUN_DIR_RE.fullmatch(p.name)
        manifest = p / "devrun.json"
        if m is None or p.is_symlink() or not p.is_dir() or manifest.is_symlink() or not manifest.is_file():
            continue
        if (read_json(manifest) or {}).get("format") != DEVRUN_FORMAT:
            continue
        runs.append(((m[1], int(m[2] or 0)), p))
    return [p for _, p in sorted(runs, key=lambda r: r[0])]
