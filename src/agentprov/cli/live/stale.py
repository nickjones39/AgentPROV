"""Stale backend environments and their rebuild: ``agentprov backends rebuild-stale`` (MN N.2.10; D-1130).

After an update (a version bump, a re-lock of ``backends/<b>/uv.lock``, a new guarded module), an environment built
for the old checkout is no longer accepted: ``run`` and ``run --catalogue`` refuse it as ``backend.unavailable`` ("not
built", when the checkout names a new ``<backend>-<commit8>``) or ``adapter.identity_mismatch`` (the same name, other
content). This module finds those environments without building anything and rebuilds each in turn.

**The backends** are the registry's (``adapters.registry.BACKENDS``), in registry order, never a fixed list.

**Detection** (:func:`detect`) is the check ``run --catalogue`` and ``backends build --offline-check`` make before the
worker starts, without the worker: the marker (complete), the T0 identity against the marker and the checkout's lock
(``envs.compute_identity``, ``envs.check_against_marker``), the NLTK zip, an Inspect environment's dataset and the
provisioned defence assets. It reads files only; nothing is spawned or written. A backend this host cannot build
(D-1064, ``platforms.unavailable("backend_build")``) is ``unsupported``: it is reported, never rebuilt, and is not a
failure.

**Missing inputs** (:func:`missing_inputs`): what a build reads offline besides the uv cache is checked first, so a
missing one is named with the step that supplies it instead of failing inside the build. Blocking: ``uv`` itself, and
an Inspect environment's pinned dataset in the fetch cache (``<cache>/hf/<repo>/<revision>/``; a download that needs
the user's consent, which no build makes). Not blocking: AutoDojo's NLTK ``punkt_tab`` when it is not cached and the
network is not allowed (the environment is built without it, as ``backends build`` does, with a notice).

**Rebuild** (:func:`rebuild_stale`): each stale backend is built (``builder``) and then verified as
``--offline-check`` does (``checker``); a failure is recorded with its code, its reason and the command to run, and the
next backend follows. A backend whose environment a running live job uses is skipped (``busy``, :func:`busy`). A stale
environment that holds defence assets (``backends build --defence-assets``; its marker's ``defence_assets``) is never
rebuilt here (D-1130 review): a rebuild without them would uninstall the defences group's packages from the very
directory that holds them, so it is ``blocked`` with the command that rebuilds it with its assets. Only the
environment the checkout names is written, exactly as ``backends build`` writes it;
every other directory under ``$AGENTPROV_HOME/envs`` is left as it is. Progress: one ``start`` with the number of
backends, then one unit per backend (status ``current``, ``rebuilt``, ``failed``, ``blocked``, ``busy``, ``unsupported`` or, in a
dry run, ``stale``); a build's own stages arrive as ``step`` events of that unit.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from agentprov.errors import AgentProvError, BackendUnavailable, IdentityMismatch
from agentprov.progress import NULL_PROGRESS, Progress, ProgressEvent

__all__ = [
    "REPORT_FORMAT",
    "EnvState",
    "MissingInput",
    "Outcome",
    "detect",
    "live_backend_ids",
    "missing_inputs",
    "rebuild_stale",
]

REPORT_FORMAT: Final = "agentprov-backends-rebuild/0.1"
#: The error code of a backend whose build is blocked by a missing offline input.
INPUT_MISSING: Final = "backend.input_missing"
#: The error code of a stale environment that holds defence assets (rebuilt only with them, by hand).
DEFENCE_ASSETS: Final = "backend.defence_assets_kept"

CURRENT: Final = "current"
STALE: Final = "stale"
UNSUPPORTED: Final = "unsupported"
UNAVAILABLE: Final = "unavailable"


def live_backend_ids() -> tuple[str, ...]:
    """The registry's backends (``adapters.registry.BACKENDS``), in registry order."""
    from agentprov.adapters.registry import BACKENDS

    return tuple(BACKENDS)


@dataclass(frozen=True)
class EnvState:
    """What :func:`detect` found for one backend."""

    backend: str
    env_name: str | None
    status: str  # current | stale | unsupported | unavailable
    code: str  # current | not_built | incomplete | identity_mismatch | unverifiable | platform_unsupported | project_missing
    reason: str
    others: tuple[str, ...] = ()  # the backend's other environments under envs/ (never touched)
    files_verified: int = 0

    def to_json(self) -> dict[str, Any]:
        return {"backend": self.backend, "env_name": self.env_name, "status": self.status, "code": self.code,
                "reason": self.reason, "other_environments": list(self.others), "files_verified": self.files_verified}


@dataclass(frozen=True)
class MissingInput:
    """An offline input a build reads that is not there. ``blocking``: the build is not started."""

    backend: str
    kind: str  # uv | dataset | nltk
    blocking: bool
    what: str
    step: str

    def to_json(self) -> dict[str, Any]:
        return {"kind": self.kind, "blocking": self.blocking, "what": self.what, "step": self.step}


@dataclass
class Outcome:
    """One backend's line of the report."""

    state: EnvState
    status: str  # current | rebuilt | failed | blocked | busy | unsupported | stale (dry run) | unavailable
    missing: list[MissingInput] = field(default_factory=list)
    stage: str | None = None  # busy | inputs | build | offline_check (where a failure happened)
    code: str | None = None
    reason: str | None = None
    commands: list[str] = field(default_factory=list)  # what to run by hand
    lines: list[str] = field(default_factory=list)  # the build's and the check's own output lines
    notices: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status not in ("failed", "blocked", "busy", UNAVAILABLE)

    def to_json(self) -> dict[str, Any]:
        return {**self.state.to_json(), "outcome": self.status, "stage": self.stage, "error_code": self.code,
                "error": self.reason, "commands": list(self.commands),
                "missing_inputs": [m.to_json() for m in self.missing], "notices": list(self.notices)}


# ------------------------------------------------------------------------------------------------ detection
def _others(home: Path, backend: str, env_name: str | None) -> tuple[str, ...]:
    """The backend's other environment directories (``<backend>-<8 hex>``), in name order; read-only."""
    root = home / "envs"
    try:
        names = sorted(p.name for p in root.iterdir() if p.is_dir() and not p.is_symlink())
    except OSError:
        return ()
    prefix = f"{backend}-"
    return tuple(n for n in names if n.startswith(prefix) and n != env_name
                 and len(n) == len(prefix) + 8 and all(c in "0123456789abcdef" for c in n[len(prefix):]))


def detect(backend: str, root: Path, home: Path) -> EnvState:
    """Whether ``backend``'s environment for the checkout at ``root`` exists and passes the identity check (files only;
    nothing is spawned or written)."""
    from agentprov.cli.common import safe_text
    from agentprov.cli.live import envs
    from agentprov.platforms import unavailable

    hit = unavailable("backend_build", subject=backend)
    if hit is not None:
        return EnvState(backend, None, UNSUPPORTED, "platform_unsupported", hit.message())
    try:
        project = envs.backend_project(backend, root)
    except BackendUnavailable as exc:
        return EnvState(backend, None, UNAVAILABLE, "project_missing", safe_text(str(exc), 300))
    env = envs.env_dir(project, home)
    others = _others(home, backend, project.env_name)

    def stale(code: str, reason: str) -> EnvState:
        return EnvState(backend, project.env_name, STALE, code, safe_text(reason, 600), others)

    try:
        marker = envs.read_marker(env)
        if marker is None:
            return stale("not_built", f"the environment {project.env_name} for this checkout is not built"
                         + (f" (other {backend} environments: {', '.join(others)})" if others else ""))
        if marker.get("status") != "complete":
            return stale("incomplete", f"the build of {project.env_name} did not complete")
        identity = envs.compute_identity(env, project)
        envs.check_against_marker(identity, marker, project)
        envs.check_nltk(env, marker)
        envs.check_dataset(env, project, marker)
        from agentprov.cli.backends import check_defence_assets

        check_defence_assets(env, marker, project)
    except IdentityMismatch as exc:
        return stale("identity_mismatch", str(exc))
    except (AgentProvError, OSError) as exc:
        return stale("unverifiable", f"{type(exc).__name__}: {exc}")
    verified = sum(d.files_verified for d in identity.distributions.values())
    return EnvState(backend, project.env_name, CURRENT, CURRENT, "marker, lock, RECORD and guarded files verified",
                    others, verified)


# ------------------------------------------------------------------------------------------------ missing inputs
def missing_inputs(backend: str, root: Path, home: Path, environ: Mapping[str, str], *, allow_network: bool,
                   uv_found: bool) -> list[MissingInput]:
    """The offline inputs a build of ``backend`` reads that are not there (see the module docstring)."""
    from agentprov.cli.common import redact_personal
    from agentprov.cli.live import envs
    from agentprov.raw.fetch import resolve_cache_dir

    out: list[MissingInput] = []
    if not uv_found:
        out.append(MissingInput(backend, "uv", True, "uv is not on PATH",
                                "install uv (https://docs.astral.sh/uv/), then run 'agentprov backends rebuild-stale' "
                                "again"))
    project = envs.backend_project(backend, root)
    try:
        cache = resolve_cache_dir(None, environ)
    except AgentProvError as exc:
        if project.dataset is not None or project.nltk is not None:
            out.append(MissingInput(backend, "cache", True, f"the fetch cache is unusable: {exc}",
                                    "set AGENTPROV_UPSTREAM_CACHE (or AGENTPROV_HOME) to a folder outside every git "
                                    "repository"))
        return out
    recipe = envs.dataset_recipe(project)
    if recipe is not None:
        folder = cache / "hf" / recipe["repo"] / recipe["revision"]
        absent = [f for f in recipe["files"] if not _cached(cache, recipe, f)]
        if absent:
            total = sum(int(f["bytes"]) for f in recipe["files"])
            copy = _verified_copy(home, backend, recipe)
            out.append(MissingInput(
                backend, "dataset", True,
                f"the pinned dataset {recipe['repo']}@{recipe['revision'][:12]} lacks {len(absent)} of "
                f"{len(recipe['files'])} files in the fetch cache ({redact_personal(str(folder))}); the build copies "
                "it from there and never downloads it",
                f"the dataset is a download from Hugging Face (https://huggingface.co/datasets/{recipe['repo']} at "
                f"revision {recipe['revision']}, {len(recipe['files'])} files, {total:,} bytes) and needs your "
                "consent: put the pinned files into that folder (each is accepted only with its pinned size and "
                "sha256"
                + (f"; the earlier environment {copy} holds a verified copy under "
                   f"share/agentprov/datasets/{recipe['benchmark']}/{recipe['revision']}/" if copy else "")
                + "), then run 'agentprov backends rebuild-stale' again"))
    nltk = envs.nltk_recipe(project) if project.nltk is not None else None
    if project.nltk is not None and nltk is None:
        out.append(MissingInput(backend, "nltk", False, "NLTK punkt_tab is not pinned in [tool.agentprov.nltk]",
                                "the environment is built without it (nltk_sha256 null): a filter-defence run on it is "
                                "refused"))
    elif nltk is not None and not allow_network and not nltk.cache_path(cache).is_file():
        out.append(MissingInput(backend, "nltk", False, "NLTK punkt_tab is not in the fetch cache",
                                "the environment is built without it (nltk_sha256 null), so a filter-defence run on it "
                                "is refused; rerun with --allow-network to fetch the pinned file (sha256 "
                                f"{nltk.sha256[:16]}...)"))
    return out


def _cached(cache: Path, recipe: Mapping[str, Any], f: Mapping[str, Any]) -> bool:
    from agentprov.cli.live.envs import _read_no_follow

    data = _read_no_follow(cache, "/".join(("hf", recipe["repo"], recipe["revision"], f["path"])), int(f["bytes"]))
    return data is not None and hashlib.sha256(data).hexdigest() == f["sha256"]


def _verified_copy(home: Path, backend: str, recipe: Mapping[str, Any]) -> str | None:
    """An earlier environment of ``backend`` whose provisioned dataset has every pinned file (read-only)."""
    from agentprov.cli.live.envs import dataset_dir

    for name in reversed(_others(home, backend, None)):
        root = dataset_dir(home / "envs" / name, recipe)
        if root.is_dir() and all(_has(root, f) for f in recipe["files"]):
            return name
    return None


def _has(root: Path, f: Mapping[str, Any]) -> bool:
    from agentprov.cli.live.envs import _read_no_follow

    data = _read_no_follow(root, f["path"], int(f["bytes"]))
    return data is not None and hashlib.sha256(data).hexdigest() == f["sha256"]


# ------------------------------------------------------------------------------------------------ busy
def _sources_of(backend: str) -> frozenset[str]:
    """The registry sources whose live capability runs on ``backend`` (``run SOURCE``)."""
    from agentprov.adapters.registry import REGISTRY

    return frozenset(r.source_id for r in REGISTRY for cap in r.capabilities
                     if cap.live_status is not None and cap.backend == backend)


def busy(backend: str, root: Path, home: Path, *, prune: bool = True) -> list[str]:
    """Why ``backend``'s environment must not be rebuilt now (D-1130: never under a running live job): a live ``run``
    registered as a user of the environment (G6a), a running job whose argv names a path inside the environment or the
    checkout's ``backends/<project>``, and a running ``run`` job of a source on this backend (its argv need not name the
    environment: the worker starts the environment's interpreter later). Reads only (dead same-host registrations are
    removed, as every lock check does, unless ``prune`` is false: a dry run writes nothing). A running ``batch run``
    driver whose batch has a live run of this backend still to start counts too. The path rule is the update's
    (:func:`agentprov.update.busy.jobs_using`)."""
    from agentprov.cli.common import safe_text
    from agentprov.cli.live import envs
    from agentprov.io.locks import backend_use
    from agentprov.jobs.record import list_jobs
    from agentprov.update.busy import jobs_using

    project = envs.backend_project(backend, root)
    env = envs.env_dir(project, home)
    reasons = [f"a run (pid {u.pid}, {safe_text(u.command, 60)}) uses {project.env_name}"
               for u in backend_use(home, project.env_name).live_users(prune=prune)]
    jobs = list_jobs(home)
    named: dict[str, str] = {j["job_id"]: str(j.get("command") or "") for j in jobs_using(home, [env, project.project],
                                                                                         jobs=lambda _home: jobs)}
    sources = _sources_of(backend)
    for job in jobs:
        if job.state != "running" or job.job_id in named:
            continue
        argv = job.subcommand_argv
        if _runs_on(argv, sources):  # the source anywhere: the GUI puts its positionals after the options
            named[job.job_id] = f"run {next(a for a in argv[1:] if a in sources)}"
        elif argv[:2] == ["batch", "run"] and len(argv) > 2 and _batch_runs_on(home, argv[2], sources):
            named[job.job_id] = f"batch {argv[2]}, whose pending steps run on {backend}"
    reasons += [f"the running job {safe_text(job_id, 64)} ({safe_text(what, 80)})" for job_id, what in named.items()]
    return reasons


def _runs_on(argv: Sequence[str], sources: frozenset[str]) -> bool:
    """Whether ``argv`` (a job's subcommand argv) is ``run`` of one of ``sources``, wherever its positional is."""
    return argv[:1] == ["run"] and any(a in sources for a in argv[1:])


def _batch_runs_on(home: Path, batch_id: str, sources: frozenset[str]) -> bool:
    """Whether the batch a running driver advances has a step not yet ended that is a live run of ``sources``: the
    driver starts it as soon as its slot frees, so a rebuild between two steps would change the environment under the
    campaign. An unreadable batch counts as one that does (never rebuilt on a guess)."""
    import re

    from agentprov.jobs.batch import Batch
    from agentprov.jobs.record import batches_dir

    if re.fullmatch(r"[0-9A-Za-z-]{1,64}", batch_id) is None:
        return True
    batch = Batch.load(batches_dir(home) / f"{batch_id}.json")
    if batch is None:
        return True
    return any(step.state in ("pending", "held", "running") and _runs_on(list(step.request.argv), sources)
               for step in batch.steps)


def defence_assets(backend: str, root: Path, home: Path) -> list[str]:
    """The defence assets the environment the checkout names records (its marker's ``defence_assets``), read only."""
    from agentprov.cli.live import envs

    marker = envs.read_marker(envs.env_dir(envs.backend_project(backend, root), home))
    recorded = marker.get("defence_assets") if isinstance(marker, Mapping) else None
    return sorted(str(k) for k in recorded) if isinstance(recorded, Mapping) else []


# ------------------------------------------------------------------------------------------------ rebuild
#: ``builder(backend, progress)`` builds one environment and returns its output lines and notices; it raises
#: :class:`~agentprov.errors.AgentProvError` on failure. ``checker`` verifies it as ``--offline-check`` does.
Builder = Callable[[str, Progress], tuple[list[str], list[str]]]


class _UnitProgress:
    """A build's events as steps of one backend's unit: its ``unit_done`` events become ``step`` events and its stage
    names are prefixed with the backend, so the job's done of total counts backends."""

    __slots__ = ("backend", "parent")

    def __init__(self, parent: Progress, backend: str) -> None:
        self.parent, self.backend = parent, backend

    def emit(self, event: ProgressEvent) -> None:
        try:
            if event.kind == "unit_done":
                self.parent.emit(ProgressEvent("step", unit=self.backend, stage=event.unit, status=event.status,
                                               duration_s=event.duration_s))
            elif event.kind == "stage":
                self.parent.emit(ProgressEvent("stage", stage=f"{self.backend}/{event.stage}",
                                               duration_s=event.duration_s, fields=event.fields))
            elif event.kind not in ("unit_start", "start"):
                self.parent.emit(event)
        except Exception:  # noqa: BLE001 - a sink never raises into the caller (progress contract)
            return


def _error_text(exc: BaseException) -> tuple[str, str]:
    from agentprov.cli.common import safe_text

    code = exc.code if isinstance(exc, AgentProvError) else "backend.build_error"
    return code, safe_text(f"{exc}" if isinstance(exc, AgentProvError) else f"{type(exc).__name__}: {exc}", 600)


def rebuild_stale(backends: Sequence[str], *, root: Path, home: Path, environ: Mapping[str, str],
                  allow_network: bool, dry_run: bool, builder: Builder, checker: Builder, uv_found: bool,
                  progress: Progress = NULL_PROGRESS) -> list[Outcome]:
    """Detect each backend's state, then (not ``dry_run``) build and check each stale one in turn."""
    network = " --allow-network" if allow_network else ""
    progress.emit(ProgressEvent("start", total=len(backends), fields={
        "command": "backends rebuild-stale", "plan": "dry run" if dry_run else "rebuild", "backends": len(backends)}))
    outcomes: list[Outcome] = []
    for backend in backends:
        started = time.monotonic()
        progress.emit(ProgressEvent("unit_start", unit=backend))
        outcome = _one(backend, root=root, home=home, environ=environ, allow_network=allow_network, dry_run=dry_run,
                       builder=builder, checker=checker, uv_found=uv_found, network=network, progress=progress)
        outcomes.append(outcome)
        progress.emit(ProgressEvent("unit_done", unit=backend, status=outcome.status,
                                    duration_s=time.monotonic() - started,
                                    codes=(outcome.code,) if outcome.code else ()))
    return outcomes


def _one(backend: str, *, root: Path, home: Path, environ: Mapping[str, str], allow_network: bool, dry_run: bool,
         builder: Builder, checker: Builder, uv_found: bool, network: str, progress: Progress) -> Outcome:
    try:
        state = detect(backend, root, home)
    except Exception as exc:  # noqa: BLE001 - one backend's surprise never stops the others
        code, reason = _error_text(exc)
        return Outcome(EnvState(backend, None, UNAVAILABLE, "unverifiable", reason), UNAVAILABLE, stage="detect",
                       code=code, reason=reason)
    if state.status == UNSUPPORTED:
        return Outcome(state, UNSUPPORTED)
    if state.status == UNAVAILABLE:
        return Outcome(state, UNAVAILABLE, stage="detect", code="adapter.backend_unavailable", reason=state.reason)
    if state.status == CURRENT:
        return Outcome(state, CURRENT)
    build = f"agentprov backends build {backend}{network}"
    check = f"agentprov backends build {backend} --offline-check"
    try:
        users = busy(backend, root, home, prune=not dry_run)
    except Exception as exc:  # noqa: BLE001
        code, reason = _error_text(exc)
        return Outcome(state, "failed", stage="busy", code=code, reason=reason, commands=[build, check])
    if users:
        return Outcome(state, "busy", stage="busy", code="io.resource_busy",
                       reason="in use, not rebuilt: " + "; ".join(users),
                       commands=["wait for it to end, then run 'agentprov backends rebuild-stale' again"])
    try:
        assets = defence_assets(backend, root, home)
    except Exception as exc:  # noqa: BLE001 - an unreadable marker: never rebuilt on a guess
        code, reason = _error_text(exc)
        return Outcome(state, "blocked", stage="defences", code=code, reason=reason, commands=[build, check])
    if assets:
        ids = ",".join(assets)
        return Outcome(state, "blocked", stage="defences", code=DEFENCE_ASSETS,
                       reason=f"{state.env_name} holds the defence assets {ids}; a rebuild here would remove them, so "
                              "it is left as it is",
                       commands=[f"agentprov backends build {backend} --defence-assets {ids}{network}", check])
    try:
        missing = missing_inputs(backend, root, home, environ, allow_network=allow_network, uv_found=uv_found)
    except Exception as exc:  # noqa: BLE001
        code, reason = _error_text(exc)
        return Outcome(state, "failed", stage="inputs", code=code, reason=reason, commands=[build, check])
    outcome = Outcome(state, STALE, missing=missing)
    outcome.notices += [f"{m.what}: {m.step}" for m in missing if not m.blocking]
    blocking = [m for m in missing if m.blocking]
    if blocking:
        outcome.status, outcome.stage, outcome.code = "blocked", "inputs", INPUT_MISSING
        outcome.reason = "; ".join(m.what for m in blocking)
        outcome.commands = [m.step for m in blocking]
        return outcome
    if dry_run:
        outcome.commands = [build, check]
        return outcome
    unit = _UnitProgress(progress, backend)
    try:
        lines, notices = builder(backend, unit)
        outcome.lines += lines
        outcome.notices += notices
    except Exception as exc:  # noqa: BLE001 - recorded; the next backend follows
        outcome.status, outcome.stage = "failed", "build"
        outcome.code, outcome.reason = _error_text(exc)
        if outcome.code == "io.resource_busy":  # a run registered between the busy check and the build's lock
            outcome.status, outcome.stage = "busy", "busy"
            outcome.commands = ["wait for it to end, then run 'agentprov backends rebuild-stale' again"]
            return outcome
        hint = " --allow-network" if not allow_network and "offline" in (outcome.reason or "") else network
        outcome.commands = [f"agentprov backends build {backend}{hint}", check]
        return outcome
    try:
        lines, notices = checker(backend, unit)
        outcome.lines += lines
        outcome.notices += notices
    except Exception as exc:  # noqa: BLE001
        outcome.status, outcome.stage = "failed", "offline_check"
        outcome.code, outcome.reason = _error_text(exc)
        outcome.commands = [check, build]
        return outcome
    outcome.status = "rebuilt"
    return outcome
