"""Migration gates (docs/architecture J.3). This module holds the common gate contract and gates **G0** (J.3.1), **A** (J.3.2),
**B** (J.3.3), **D** (J.3.5; :mod:`agentprov.migration.gate_d`) and **E** (J.3.6).

The release gates run in the order ``G0 -> A (A1, A2) -> B -> D -> E`` (AD-07). Gate D (``migrate gate-d``, D-49) re-derives
and validates the stored AERs of the migration corpora; a full-scope gate E refuses to start until a passing full-scope D report
exists.
Gate E (the v2.3 -> ``agentprov-prov/0.1`` semantic diff, :mod:`agentprov.migration.semdiff`) runs the same pipeline with
B1 and a hook that classifies every compat edge, joins nodes and attributes with ``semdiff-map.toml`` and derives the AER;
it returns the gate report plus one ``SemDiffReport`` per tree, which :func:`write_semdiff` stores as
``$AGENTPROV_HOME/migration/semdiff/semdiff-<tree>.{json,md}``. Gate A (v1 -> AER -> v1 view, JCS and bytes) and gate B (compat graph bytes, from the view and from the source)
share the pipeline of :mod:`agentprov.migration.pipeline`: mapping runs in T1 workers, the parent seals, renders and compares.
Both run on the golden set (``scope="golden"``, CI) or on the two baseline trees (``scope="full"``, local only). Every gate returns a :class:`GateReport` of the
shape ``agentprov-migration-gate/0.1`` (J.3.0), which :func:`write_report` stores as
``$AGENTPROV_HOME/migration/reports/<gate>/<UTC date>-<short commit>.json`` (paths relative, never absolute user paths).
Nothing is written into the repository by default: a report meant to be committed is written there on purpose with
``--reports-dir migration/reports`` (or copied). The repository's ``migration/reports`` is still read when the gate order
is checked, so reports committed there keep counting.

**G0 is read-only on the old repository.** It runs ``git`` with ``--no-optional-locks`` (so even ``git status`` does not
refresh the index), reads blobs with ``cat-file`` and walks the gitignored corpus trees without writing a byte. Pass iff
(J.3.1): the old repo's ``HEAD`` equals the lock commit, or the tag resolves to it (the tracked files are then checked
against that commit's tree); the tag is an annotated tag object equal to ``framework.tag.object`` whose target is the lock
commit; ``git status --porcelain`` is empty; the five tree listings of J.1.4 match (counts and digests); and
``migration/baseline-requirements.txt`` and the baseline wheel match their recorded hashes (J.1.6).

Beyond the J.3.1 list, G0 also checks the 13 tracked-file digests (J.1.5) against the commit's blobs and that the existing
tags ``corpus-v2.2`` and ``corpus-v2.3`` have not moved (J.1.7).

The two J.1.6 hashes are not recorded in the lock yet (the hash-locked requirements export and the baseline wheel are built
with the differential gates). Unrecorded, each is a ``skipped`` check, which never counts as a pass (D8); with
``strict`` (release mode, ``agentprov migrate --release``) it is a failure.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import time
import tomllib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Literal

from agentprov.envinfo import interpreter_advisory
from agentprov.errors import AgentProvError
from agentprov.io.atomic import atomic_write_text
from agentprov.progress import NULL_PROGRESS, Progress
from agentprov.migration.lock import (
    PREDICATES,
    REPO_ROOT,
    BaselineLock,
    LockError,
    TreeListing,
    load_lock,
    lock_sha256,
    tree_listing,
)
from agentprov.migration.pipeline import (
    PairInput,
    TraceRow,
    TreeSummary,
    accounting_summary,
    full_inputs,
    golden_inputs,
    run_pipeline,
    tree_counts,
)
from agentprov.versions import VERSIONS, __version__

REPORT_FORMAT: Final = "agentprov-migration-gate/0.1"
DEFAULT_SEED: Final = 20261007  # J.3.0 example value; G0 draws no random numbers
#: The repository's report directory: never written by default, still searched for predecessor reports (J.3.0).
REPO_REPORTS_DIR: Final = REPO_ROOT / "migration" / "reports"
DEFAULT_REQUIREMENTS_PATH: Final = REPO_ROOT / "migration" / "baseline-requirements.txt"
DEFAULT_WHEEL_PATH: Final = REPO_ROOT / ".baseline" / "wheel" / "agentdojo_prov-1.0.0-py3-none-any.whl"
PORT_MANIFEST_PATH: Final = REPO_ROOT / "src" / "agentprov" / "prov" / "compat" / "adprov_v2_3" / "PORT_MANIFEST.json"

#: The J.2.6 variables (plus ``AGENTPROV_BASELINE_WHEEL``, the wheel of J.1.6, which J does not name).
ENV_BASELINE_CORPUS: Final = "AGENTPROV_BASELINE_CORPUS"
ENV_UPSTREAM_CACHE: Final = "AGENTPROV_UPSTREAM_CACHE"
ENV_BASELINE_PYTHON: Final = "AGENTPROV_BASELINE_PYTHON"
ENV_MIGRATION_WORK: Final = "AGENTPROV_MIGRATION_WORK"
ENV_BASELINE_WHEEL: Final = "AGENTPROV_BASELINE_WHEEL"
ENV_GOLDEN_DIR: Final = "AGENTPROV_GOLDEN_DIR"  # K.3.2: the golden fixture directory (golden scope)
ENV_NAMES: Final = (ENV_BASELINE_CORPUS, ENV_UPSTREAM_CACHE, ENV_BASELINE_PYTHON, ENV_MIGRATION_WORK, ENV_BASELINE_WHEEL)



def _home() -> Path:
    raw = os.environ.get("AGENTPROV_HOME")
    return Path(raw) if raw else Path.home() / ".agentprov"


def default_reports_dir() -> Path:
    """``$AGENTPROV_HOME/migration/reports`` (default ``~/.agentprov``): migrate never writes into the repository unasked."""
    return _home() / "migration" / "reports"


def default_semdiff_dir() -> Path:
    """``$AGENTPROV_HOME/migration/semdiff``: where gate E writes its semantic diff by default."""
    return _home() / "migration" / "semdiff"


PASS: Final = "pass"
FAIL: Final = "fail"
SKIPPED: Final = "skipped"


class BaselineUnavailableError(AgentProvError):
    """No usable baseline repository (J.3.0: environment error, CLI exit 3)."""

    code = "migration.baseline.unavailable"
    exit_code = 3


@dataclass(frozen=True, slots=True)
class MigrationConfig:
    """Paths and parameters of a migration run (J.2.6). Built by :meth:`from_env`; every field can be set directly."""

    baseline_corpus: Path | None = None  # the old repo root (AGENTPROV_BASELINE_CORPUS)
    upstream_cache: Path | None = None
    baseline_python: Path | None = None
    work: Path | None = None
    baseline_wheel: Path | None = None
    lock_path: Path = field(default_factory=lambda: REPO_ROOT / "migration" / "baseline.lock.json")
    requirements_path: Path = DEFAULT_REQUIREMENTS_PATH
    reports_dir: Path = field(default_factory=lambda: default_reports_dir())
    workers: int = 8
    strict: bool = False  # release mode: unrecorded or skipped checks fail
    golden_dir: Path | None = None  # golden scope: $AGENTPROV_GOLDEN_DIR, default tests/fixtures/agentdojo_prov_v1/golden
    in_process: bool = False  # debugging only (refused with strict): run the map job in this process

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        config_file: Path | None = None,
        **overrides: Any,
    ) -> MigrationConfig:
        """Read the J.2.6 variables. The environment wins over ``[env]`` of ``config_file`` (``migration/local.toml``)."""
        env = dict(os.environ if environ is None else environ)
        values: dict[str, str] = {}
        file_workers: int | None = None
        if config_file is not None and Path(config_file).is_file():
            try:
                document = tomllib.loads(Path(config_file).read_text(encoding="utf-8"))
            except (tomllib.TOMLDecodeError, UnicodeDecodeError):
                raise BaselineUnavailableError("migration/local.toml is not valid TOML") from None
            table = document.get("env", {})
            values.update({k: v for k, v in table.items() if k in ENV_NAMES and isinstance(v, str)})
            run = document.get("run", {})
            if isinstance(run, dict) and isinstance(run.get("workers"), int) and not isinstance(run["workers"], bool):
                file_workers = run["workers"]
        values.update({k: env[k] for k in ENV_NAMES if env.get(k)})

        def path(name: str) -> Path | None:
            return Path(values[name]).expanduser() if values.get(name) else None

        kwargs: dict[str, Any] = {
            "baseline_corpus": path(ENV_BASELINE_CORPUS),
            "upstream_cache": path(ENV_UPSTREAM_CACHE),
            "baseline_python": path(ENV_BASELINE_PYTHON),
            "work": path(ENV_MIGRATION_WORK),
            "baseline_wheel": path(ENV_BASELINE_WHEEL),
        }
        if file_workers is not None:
            kwargs["workers"] = file_workers
        golden = env.get(ENV_GOLDEN_DIR, "").strip()
        if golden:
            kwargs["golden_dir"] = Path(golden).expanduser()
        kwargs.update(overrides)
        return cls(**kwargs)


@dataclass(frozen=True, slots=True)
class Check:
    """One evaluated condition of a gate. ``detail`` never carries payload text."""

    check: str
    status: str  # pass | fail | skipped
    detail: str = ""


@dataclass(frozen=True, slots=True)
class GateReport:
    """``agentprov-migration-gate/0.1`` (J.3.0). :meth:`to_json` gives the committed form; ``checks`` is additive."""

    gate: str
    scope: str
    role: str
    agentprov: Mapping[str, Any]
    baseline_lock_sha256: str
    specs: Mapping[str, Any]
    environment: Mapping[str, Any]
    inputs: tuple[Mapping[str, Any], ...]
    params: Mapping[str, Any]
    checks: tuple[Check, ...]
    outputs: tuple[Mapping[str, Any], ...]
    started_at: str
    ended_at: str
    wall_s: float
    notes: tuple[str, ...] = ()
    #: Gates A and B count traces, not checks: when set, these replace the counts and failures derived from ``checks``.
    trace_counts: Mapping[str, int] | None = None
    trace_failures: tuple[Mapping[str, str], ...] = ()
    details: Mapping[str, Any] = field(default_factory=dict)  # additive, numbers and relative labels only

    @property
    def counts(self) -> dict[str, int]:
        if self.trace_counts is not None:
            return dict(self.trace_counts)
        statuses = [c.status for c in self.checks]
        return {
            "expected": len(statuses),
            "checked": statuses.count(PASS) + statuses.count(FAIL),
            "passed": statuses.count(PASS),
            "failed": statuses.count(FAIL),
            "skipped": statuses.count(SKIPPED),
        }

    @property
    def failures(self) -> list[dict[str, str]]:
        listed = [dict(f) for f in self.trace_failures]
        listed += [{"item": c.check, "check": c.check, "detail": c.detail} for c in self.checks if c.status == FAIL]
        return listed[:100]

    @property
    def verdict(self) -> str:
        failed = self.counts["failed"] > 0 or any(c.status == FAIL for c in self.checks)
        return FAIL if failed else PASS

    @property
    def report_id(self) -> str:
        """``<UTC date>-<short commit>``: the file stem, and what later reports record as the G0 report id."""
        return _report_id(self.started_at, self.agentprov.get("commit"))

    def to_json(self) -> dict[str, Any]:
        return {
            "report": REPORT_FORMAT,
            "gate": self.gate,
            "scope": self.scope,
            "role": self.role,
            "agentprov": dict(self.agentprov),
            "baseline_lock_sha256": self.baseline_lock_sha256,
            "specs": dict(self.specs),
            "environment": dict(self.environment),
            "inputs": [dict(i) for i in self.inputs],
            "params": dict(self.params),
            "counts": self.counts,
            "failures": self.failures,
            "checks": [{"check": c.check, "status": c.status, "detail": c.detail} for c in self.checks],
            "outputs": [dict(o) for o in self.outputs],
            "notes": list(self.notes),
            "details": dict(self.details),
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "wall_s": self.wall_s,
            "verdict": self.verdict,
        }


def _redacted(text: str) -> str:
    """Replace the user's home directory with ``<home>``: committed reports carry no absolute home paths."""
    home = str(Path.home())
    return text.replace(home, "<home>") if len(home) > 1 else text


def report_text(report: GateReport) -> str:
    return _redacted(json.dumps(report.to_json(), indent=2, ensure_ascii=False)) + "\n"


def _report_id(started_at: str, commit: object) -> str:
    return f"{started_at[:10]}-{commit[:7] if isinstance(commit, str) else 'nocommit'}"


class ReportExistsError(AgentProvError):
    """The default report path holds a report of another scope or mode (J.3.0). Exit 4 (refused)."""

    code = "migration.report.exists"
    exit_code = 4


def refuse_replacing_other_run(target: Path, *, scope: str, strict: bool) -> None:
    """Refuse (:class:`ReportExistsError`) to replace the report at the default path ``target`` when its ``scope`` or
    ``params.strict`` differs. The stem names only the date and commit, so a golden, sample or release-mode run on the day
    and commit of a full-scope run reaches the same file, and the replaced report may be the passing full-scope evidence
    that AD-07 and the release precondition look up. A rerun of the same scope and mode replaces it; ``--report`` is not
    checked (the user chose the file)."""
    try:
        document = json.loads(target.read_bytes())
    except (OSError, ValueError):
        return  # no report there (or none readable): nothing to keep
    if not isinstance(document, dict) or document.get("report") != REPORT_FORMAT:
        return
    params = document.get("params")
    stored_strict = isinstance(params, dict) and params.get("strict") is True
    if document.get("scope") != scope or stored_strict != strict:
        stored = f"{document.get('scope')!s:.20}, {'release' if stored_strict else 'dev'} mode"
        raise ReportExistsError(
            f"{target.parent.name}/{target.name} already holds a gate report of another run ({stored}); this {scope} run in "
            f"{'release' if strict else 'dev'} mode would replace it: pass --report PATH to write it elsewhere"
        )


def refuse_default_target(directory: Path, gate: str, *, scope: str, strict: bool) -> None:
    """:func:`refuse_replacing_other_run` before a gate runs, for the default path of a run started now at this commit."""
    report_id = _report_id(datetime.now(UTC).strftime("%Y-%m-%d"), _agentprov_identity().get("commit"))
    refuse_replacing_other_run(directory / gate / f"{report_id}.json", scope=scope, strict=strict)


def default_report_path(report: GateReport, directory: Path | None = None) -> Path:
    """``<directory>/<gate>/<report_id>.json`` (default directory ``$AGENTPROV_HOME/migration/reports``, D-522), checked
    by :func:`refuse_replacing_other_run`."""
    target = (directory if directory is not None else default_reports_dir()) / report.gate / f"{report.report_id}.json"
    refuse_replacing_other_run(target, scope=report.scope, strict=report.params.get("strict") is True)
    return target


def write_report(report: GateReport, directory: Path | None = None, *, path: Path | None = None) -> Path:
    """Write the report atomically: to ``path`` when given, else to :func:`default_report_path` (which refuses to replace
    a report of another scope or mode)."""
    target = Path(path) if path is not None else default_report_path(report, directory)
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(target, report_text(report))
    return target


# ------------------------------------------------------------------------------------------------ read-only git


def _git(repo: Path, *args: str, check: bool = False) -> subprocess.CompletedProcess[bytes]:
    """Run ``git`` on ``repo`` without writing to it (no optional locks, no fsmonitor, no pager, no prompts)."""
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0", "GIT_PAGER": "cat", "LC_ALL": "C"}
    return subprocess.run(
        ["git", "--no-pager", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(repo), *args],
        capture_output=True,
        env=env,
        check=check,
        timeout=300,
    )


def _git_text(repo: Path, *args: str) -> str | None:
    done = _git(repo, *args)
    return done.stdout.decode("utf-8", "replace").strip() if done.returncode == 0 else None


def _agentprov_identity() -> dict[str, Any]:
    commit = _git_text(REPO_ROOT, "rev-parse", "HEAD")
    if commit is None or len(commit) != 40:
        return {"version": __version__, "commit": None, "dirty": None}
    status = _git(REPO_ROOT, "status", "--porcelain")
    return {"version": __version__, "commit": commit, "dirty": bool(status.stdout.strip()) if status.returncode == 0 else None}


def _sha256_of(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _package_versions() -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for name in ("prov", "rdflib", "pyshacl", "rfc8785", "pyyaml"):
        try:
            out[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            out[name] = None
    return out


def _specs() -> dict[str, Any]:
    return {
        "aer": VERSIONS["aer"],
        "sem": VERSIONS["sem"],
        "agentprov-prov": VERSIONS["prov_spec"],
        "adprov-v2.3-compat": _sha256_of(PORT_MANIFEST_PATH),
    }


def _environment(advisory: Any, *, baseline_python: str | None = None) -> dict[str, Any]:
    return {
        "python": platform.python_version(),
        "interpreter_advisory": advisory.to_json() if advisory is not None else None,
        "baseline_python": baseline_python,  # G0, A and B do not execute the old package
        "platform": platform.platform(),
        "packages": _package_versions(),
        "uv_lock_sha256": _sha256_of(REPO_ROOT / "uv.lock"),
    }


# ------------------------------------------------------------------------------------------------ gate G0


def _check_head(repo: Path, lock: BaselineLock) -> tuple[Check, bool]:
    """``(check, head_matches)``: HEAD equals the lock commit, or the tag resolves to it."""
    pinned = lock.framework.commit
    head = _git_text(repo, "rev-parse", "HEAD")
    if head == pinned:
        return Check("git.head", PASS, "HEAD equals the lock commit"), True
    tagged = _git_text(repo, "rev-parse", f"{lock.framework.tag.name}^{{commit}}")
    if tagged == pinned:
        return Check("git.head", PASS, "HEAD differs from the lock commit; the tag resolves to it (tracked files are read from its tree)"), False
    return Check("git.head", FAIL, f"HEAD is {head!r}; neither HEAD nor the tag resolves to the lock commit"), False


def _check_tag(repo: Path, lock: BaselineLock) -> Check:
    pin = lock.framework.tag
    kind = _git_text(repo, "cat-file", "-t", pin.name)
    if kind != "tag":
        return Check("git.tag_object", FAIL, f"{pin.name} is {kind!r}, not an annotated tag object")
    obj = _git_text(repo, "rev-parse", pin.name)
    if obj != pin.object:
        return Check("git.tag_object", FAIL, f"tag object is {obj!r}, the lock records {pin.object}")
    target = _git_text(repo, "rev-parse", f"{pin.name}^{{commit}}")
    if target != lock.framework.commit:
        return Check("git.tag_object", FAIL, f"tag target is {target!r}, the lock commit is {lock.framework.commit}")
    return Check("git.tag_object", PASS, f"annotated tag object {pin.object} targets the lock commit")


def _check_existing_tags(repo: Path, lock: BaselineLock) -> Check:
    # J.1.1 records the commits the annotated tags point to, so the tags are peeled
    moved = [
        f"{name}={_git_text(repo, 'rev-parse', f'{name}^{{commit}}')!r}"
        for name, oid in lock.framework.existing_tags.items()
        if _git_text(repo, "rev-parse", f"{name}^{{commit}}") != oid
    ]
    if moved:
        return Check("git.existing_tags", FAIL, "moved or missing: " + ", ".join(moved))
    return Check("git.existing_tags", PASS, f"{len(lock.framework.existing_tags)} published tags unchanged")


def _check_status(repo: Path) -> Check:
    done = _git(repo, "status", "--porcelain")
    if done.returncode != 0:
        return Check("git.status_clean", FAIL, "git status failed")
    lines = done.stdout.splitlines()
    return Check("git.status_clean", FAIL if lines else PASS, f"{len(lines)} changed or untracked path(s)" if lines else "working tree clean")


def _check_tracked_files(repo: Path, lock: BaselineLock) -> Check:
    bad: list[str] = []
    for path, digest in lock.framework.tracked_files.items():
        done = _git(repo, "cat-file", "blob", f"{lock.framework.commit}:{path}")
        if done.returncode != 0 or hashlib.sha256(done.stdout).hexdigest() != digest:
            bad.append(path)
    if bad:
        return Check("git.tracked_files", FAIL, f"{len(bad)} of {len(lock.framework.tracked_files)} differ: " + ", ".join(bad))
    return Check("git.tracked_files", PASS, f"{len(lock.framework.tracked_files)} tracked files match the lock commit's blobs")


def _check_tree(
    repo: Path, name: str, lock: BaselineLock, workers: int
) -> tuple[Check, TreeListing | None]:
    pin = lock.trees[name]
    root = repo / pin.root
    try:
        listing = tree_listing(root, PREDICATES[pin.predicate], workers=workers)
    except FileNotFoundError:
        return Check(f"tree.{name}", FAIL, f"{pin.root} is not a directory"), None
    if listing.files != pin.files:
        return Check(f"tree.{name}", FAIL, f"{listing.files} files, the lock records {pin.files}"), listing
    if listing.listing_sha256 != pin.listing_sha256:
        return Check(f"tree.{name}", FAIL, f"listing sha256 {listing.listing_sha256}, the lock records {pin.listing_sha256}"), listing
    return Check(f"tree.{name}", PASS, f"{listing.files} files, listing {listing.listing_sha256[:16]}"), listing


def default_wheel_path(baseline_python: Path | None) -> Path:
    """Where the J.1.6 wheel is found without ``AGENTPROV_BASELINE_WHEEL``: ``tools/migration/build_baseline_env.py``
    keeps it in ``<venv>/wheel/`` beside the interpreter ``<venv>/bin/python``; else the repository's ``.baseline/``."""
    if baseline_python is not None:
        return baseline_python.parent.parent / "wheel" / DEFAULT_WHEEL_PATH.name
    return DEFAULT_WHEEL_PATH


def _check_recorded_hash(code: str, recorded: str | None, path: Path | None, strict: bool) -> Check:
    if recorded is None:
        return Check(code, FAIL if strict else SKIPPED, "the lock does not record this hash yet (J.1.6)")
    if path is None or not path.is_file():
        return Check(code, FAIL if strict else SKIPPED, "the file is missing")
    actual = _sha256_of(path)
    if actual != recorded:
        return Check(code, FAIL, f"sha256 {actual}, the lock records {recorded}")
    return Check(code, PASS, "matches the lock")


def verify_baseline(cfg: MigrationConfig, *, clock: Callable[[], datetime] | None = None) -> GateReport:
    """Gate G0 (J.3.1): verify the old repository, its corpora and the baseline environment against the lock.

    Raises :class:`BaselineUnavailableError` (exit 3) when ``cfg.baseline_corpus`` is unset or is not a git work tree, and
    :class:`~agentprov.migration.lock.LockError` when the lock is invalid. Never writes to the old repository.
    """
    now = clock or (lambda: datetime.now(UTC))
    started = now()
    t0 = time.perf_counter()
    lock = load_lock(cfg.lock_path)
    repo = cfg.baseline_corpus
    if repo is None:
        raise BaselineUnavailableError(f"{ENV_BASELINE_CORPUS} is not set")
    if not repo.is_dir() or _git_text(repo, "rev-parse", "--is-inside-work-tree") != "true":
        raise BaselineUnavailableError("the baseline path is not a git work tree")

    checks: list[Check] = []
    head_check, _ = _check_head(repo, lock)
    checks += [
        head_check,
        _check_tag(repo, lock),
        _check_existing_tags(repo, lock),
        _check_status(repo),
        _check_tracked_files(repo, lock),
    ]
    inputs: list[dict[str, Any]] = []
    for name in lock.trees:
        check, listing = _check_tree(repo, name, lock, cfg.workers)
        checks.append(check)
        if listing is not None:
            inputs.append({"name": name, "files": listing.files, "listing_sha256": listing.listing_sha256})
    checks.append(
        _check_recorded_hash(
            "environment.requirements_lock", lock.environment.requirements_lock_sha256, cfg.requirements_path, cfg.strict
        )
    )
    wheel = cfg.baseline_wheel if cfg.baseline_wheel is not None else default_wheel_path(cfg.baseline_python)
    checks.append(
        _check_recorded_hash("environment.baseline_wheel", lock.environment.baseline_wheel_sha256, wheel, cfg.strict)
    )

    advisory = interpreter_advisory()
    ended = now()
    notes = tuple(
        f"{c.check}: {c.detail}" for c in checks if c.status == SKIPPED
    )
    return GateReport(
        gate="G0",
        scope="full",
        role="release",
        agentprov=_agentprov_identity(),
        baseline_lock_sha256=lock_sha256(cfg.lock_path),
        specs=_specs(),
        environment=_environment(advisory),
        inputs=tuple(inputs),
        params={"workers": cfg.workers, "seed": DEFAULT_SEED, "strict": cfg.strict},
        checks=tuple(checks),
        outputs=(),
        started_at=started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        ended_at=ended.strftime("%Y-%m-%dT%H:%M:%SZ"),
        wall_s=round(time.perf_counter() - t0, 3),
        notes=notes,
    )


# ------------------------------------------------------------------------------------------------ gates A and B

def _compat_notice() -> str:
    from agentprov.prov.compat.adprov_v2_3 import NOTICE  # noqa: PLC0415 - the module is cheap; no oracle code loads

    return str(NOTICE)


Scope = Literal["golden", "full"]
GATE_ORDER: Final = ("G0", "A", "B", "D", "E")  # AD-07: the release gates in order
DEFAULT_GOLDEN_DIR: Final = REPO_ROOT / "tests" / "fixtures" / "agentdojo_prov_v1" / "golden"
#: Printed whenever compat output is produced (R-55; Q.30): gate B builds compat graphs and compares them.
COMPAT_NOTICE: Final = _compat_notice()
LISTED_FAILURES: Final = 100


class GateOrderError(AgentProvError):
    """A gate was started before its predecessors passed for this commit and lock (J.3.0, AD-07). Exit 4 (refused)."""

    code = "migration.gate.order"
    exit_code = 4


def _scope_inputs(cfg: MigrationConfig, scope: Scope) -> tuple[list[PairInput], dict[str, TreeSummary]]:
    if scope == "golden":
        env = os.environ.get(ENV_GOLDEN_DIR, "").strip()
        return golden_inputs(cfg.golden_dir or (Path(env).expanduser() if env else DEFAULT_GOLDEN_DIR))
    if cfg.baseline_corpus is None:
        raise BaselineUnavailableError(f"{ENV_BASELINE_CORPUS} is not set (the full scope reads the old repository's trees)")
    if not cfg.baseline_corpus.is_dir():
        raise BaselineUnavailableError("the baseline path is not a directory")
    return full_inputs(cfg.baseline_corpus)


def _passing_report_exists(directories: Sequence[Path], *, gate: str, scope: str, commit: str | None, lock_digest: str, strict: bool) -> bool:
    for directory in directories:
        if not directory.is_dir():
            continue
        for candidate in sorted([*directory.glob("*.json"), *directory.glob("*/*.json")]):
            try:
                document = json.loads(candidate.read_bytes())
            except (OSError, ValueError):
                continue
            if not isinstance(document, dict) or document.get("report") != REPORT_FORMAT:
                continue
            identity = document.get("agentprov")
            params = document.get("params")
            if (
                document.get("gate") == gate
                and document.get("scope") == scope
                and document.get("verdict") == PASS
                and document.get("baseline_lock_sha256") == lock_digest
                and isinstance(identity, dict)
                and identity.get("commit") == commit
                and (not strict or (isinstance(params, dict) and params.get("strict") is True))
            ):
                return True
    return False


def require_predecessors(cfg: MigrationConfig, gate: str, scope: Scope, *, extra_dirs: Sequence[Path] = ()) -> None:
    """Refuse (:class:`GateOrderError`) unless every predecessor of ``gate`` has a passing full-scope report for this
    commit and lock under ``cfg.reports_dir`` or ``extra_dirs`` (J.3.0). Only the full scope is chained: the golden scope
    runs in CI, where no baseline repository exists, so G0 cannot precede it."""
    if scope != "full":
        return
    commit = _agentprov_identity().get("commit")
    lock_digest = lock_sha256(cfg.lock_path)
    directories = list(dict.fromkeys([cfg.reports_dir, *extra_dirs, REPO_REPORTS_DIR]))  # committed reports count
    for predecessor in GATE_ORDER[: GATE_ORDER.index(gate)]:
        if not _passing_report_exists(directories, gate=predecessor, scope="full", commit=commit, lock_digest=lock_digest, strict=cfg.strict):
            raise GateOrderError(
                f"gate {gate} needs a passing full-scope gate {predecessor} report for this commit and lock "
                f"(AD-07: {' -> '.join(GATE_ORDER)}); run gate {predecessor} at full scope first"
            )


def _tree_check(code: str, ok: bool, detail: str) -> Check:
    return Check(code, PASS if ok else FAIL, detail)


def _pins_for(lock: BaselineLock, tree: str, *, graphs: bool) -> tuple[str, Any]:
    name = f"{tree}_{'graphs' if graphs else 'transcripts'}"
    return name, lock.trees[name]


def _input_checks(
    trees: Mapping[str, TreeSummary], scope: Scope, lock: BaselineLock, *, graphs: bool
) -> tuple[list[dict[str, Any]], list[Check]]:
    """The ``inputs`` of a report and its input checks: transcript/graph pairing, and at full scope the J.1.4 lock pins."""
    inputs: list[dict[str, Any]] = []
    checks: list[Check] = []
    for tree, summary in trees.items():
        inputs.append({"name": f"{tree}_transcripts", "files": summary.transcripts, "listing_sha256": summary.transcript_listing_sha256})
        if graphs:
            inputs.append({"name": f"{tree}_graphs", "files": summary.graphs, "listing_sha256": summary.graph_listing_sha256})
            paired = not summary.unpaired_transcripts and not summary.unpaired_graphs
            checks.append(
                _tree_check(
                    f"inputs.{tree}.pairing", paired,
                    f"{summary.transcripts} transcripts, {summary.graphs} graphs, {len(summary.unpaired_transcripts)} transcripts "
                    f"without a graph, {len(summary.unpaired_graphs)} graphs without a transcript",
                )
            )
        if scope == "full":
            for is_graph in (False, True) if graphs else (False,):
                name, pin = _pins_for(lock, tree, graphs=is_graph)
                files = summary.graphs if is_graph else summary.transcripts
                digest = summary.graph_listing_sha256 if is_graph else summary.transcript_listing_sha256
                ok = files == pin.files and digest == pin.listing_sha256
                checks.append(_tree_check(f"inputs.{name}.lock", ok, "matches the lock pin (J.1.4)" if ok else f"{files} files, listing {digest}; the lock records {pin.files}, {pin.listing_sha256}"))
    return inputs, checks


def _gate_ab(
    gate: str,
    want: frozenset[str],
    cfg: MigrationConfig,
    scope: Scope,
    *,
    progress: Progress,
    hook: Any,
    clock: Callable[[], datetime] | None,
) -> GateReport:
    now = clock or (lambda: datetime.now(UTC))
    started = now()
    t0 = time.perf_counter()
    lock = load_lock(cfg.lock_path)
    pairs, trees = _scope_inputs(cfg, scope)
    if not pairs:
        raise BaselineUnavailableError("no transcripts found for this scope")
    work = cfg.work
    run = run_pipeline(
        pairs, trees, want, work=work, workers=cfg.workers, release=cfg.strict, in_process=cfg.in_process,
        progress=progress, hook=hook,
    )
    checks_list = sorted(want)
    checks: list[Check] = []
    notes: list[str] = []
    graphs = bool(want & {"B1", "B2"})

    if scope == "golden":
        again = run_pipeline(pairs, trees, want, work=work, workers=cfg.workers, release=cfg.strict, in_process=cfg.in_process)
        same = run.aer_listing_sha256 == again.aer_listing_sha256 and [r.execution_digest for r in run.rows] == [
            r.execution_digest for r in again.rows
        ]
        checks.append(_tree_check("determinism.aer_listing", same, "two runs give identical AER digest listings" if same else "the two runs differ"))
    else:
        notes.append("full scope: the AER digest listing is recorded in outputs so that two runs can be compared (J.3.0)")

    inputs, input_checks = _input_checks(run.trees, scope, lock, graphs=graphs)
    checks += input_checks

    counts = tree_counts(run.rows, checks_list)
    for tree, c in counts.items():
        for name in checks_list:
            checks.append(_tree_check(f"{name}.{tree}", c[name] == c["traces"], f"{c[name]}/{c['traces']} traces"))
        valid = sum(1 for r in run.rows if r.tree == tree and r.aer_valid is True and not r.degenerate)
        checks.append(_tree_check(f"aer.validator.{tree}", valid == c["traces"], f"{valid}/{c['traces']} AERs valid in release mode, none degenerate"))

    failed_rows = [r for r in run.rows if not r.passed]
    failures = tuple(
        {"item": r.item, "check": r.codes[0], "detail": "; ".join(r.codes)[:300] + f" (transcript sha256 {r.sha256[:16]})"}
        for r in failed_rows[:LISTED_FAILURES]
    )
    trace_counts = {
        "expected": len(pairs), "checked": len(run.rows), "passed": len(run.rows) - len(failed_rows),
        "failed": len(failed_rows), "skipped": 0,
    }
    outputs: list[dict[str, Any]] = [
        {"name": "aer_digest_listing", "tree": t, "files": counts.get(t, {}).get("traces", 0), "sha256": d}
        for t, d in run.aer_listing_sha256.items()
    ]
    outputs += [
        {"name": "compat_graph_digest_listing", "tree": t, "files": counts.get(t, {}).get("traces", 0), "sha256": d}
        for t, d in run.graph_listing_sha256.items()
    ]
    if work is not None:
        _write_rows(work, gate, scope, run.rows, failed_rows)
    if graphs:
        notes.append(COMPAT_NOTICE)
    iso = run.isolation
    details = {
        "checks": counts,
        "accounting": accounting_summary(run.rows),
        "mapping": {"adapter": "adprov.transcript_v1", "profile": "adprov-v1", "origin": "AgentDojo-PROV 2.3 at 579a908"},
        "isolation": {"mode": iso.get("mode"), "grade": iso.get("grade")},
    }
    ended = now()
    return GateReport(
        gate=gate,
        scope=scope,
        role="release",
        agentprov=_agentprov_identity(),
        baseline_lock_sha256=lock_sha256(cfg.lock_path),
        specs=_specs(),
        environment=_environment(interpreter_advisory()),
        inputs=tuple(inputs),
        params={"workers": cfg.workers, "seed": DEFAULT_SEED, "strict": cfg.strict, "checks": checks_list},
        checks=tuple(checks),
        outputs=tuple(outputs),
        started_at=started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        ended_at=ended.strftime("%Y-%m-%dT%H:%M:%SZ"),
        wall_s=round(time.perf_counter() - t0, 3),
        notes=tuple(notes),
        trace_counts=trace_counts,
        trace_failures=failures,
        details=details,
    )


def _write_rows(work: Path, gate: str, scope: str, rows: Sequence[TraceRow], failed: Sequence[TraceRow]) -> None:
    """``<work>/reports/<gate>-<scope>/traces.jsonl`` (every trace) and ``failures.jsonl`` (J.3.0): digests and codes only."""
    directory = Path(work) / "reports" / f"{gate}-{scope}"
    directory.mkdir(parents=True, exist_ok=True)
    atomic_write_text(directory / "traces.jsonl", "".join(json.dumps(r.to_json(), sort_keys=True) + "\n" for r in rows))
    atomic_write_text(directory / "failures.jsonl", "".join(json.dumps(r.to_json(), sort_keys=True) + "\n" for r in failed))


def gate_a_v1_identity(
    cfg: MigrationConfig,
    *,
    scope: Scope,
    progress: Progress = NULL_PROGRESS,
    trace_hook: Any = None,
    clock: Callable[[], datetime] | None = None,
) -> GateReport:
    """Gate A (J.3.2): v1 -> AER -> v1 view. A1 compares JCS bytes (value identity), A2 compares bytes, from the AER alone.

    Also requires each AER to pass the release-mode validator with locators resolved, and records every trace's seal
    accounting verdicts (``details.accounting``). ``scope="golden"`` runs the golden set and runs the producer twice
    (determinism); ``scope="full"`` needs ``cfg.baseline_corpus`` and runs both baseline trees.
    """
    return _gate_ab("A", frozenset({"A1", "A2"}), cfg, scope, progress=progress, hook=trace_hook, clock=clock)


def gate_b_compat_bytes(
    cfg: MigrationConfig,
    *,
    scope: Scope,
    progress: Progress = NULL_PROGRESS,
    trace_hook: Any = None,
    clock: Callable[[], datetime] | None = None,
) -> GateReport:
    """Gate B (J.3.3): the ``adprov-v2.3-compat`` oracle reproduces the stored graph bytes. B1 builds from the v1 view of the
    mapped AER, B2 from the stored transcript (isolating port faults from view faults). Compat output is a regression
    oracle (R-55): the report notes it, and the CLI prints the notice."""
    return _gate_ab("B", frozenset({"B1", "B2"}), cfg, scope, progress=progress, hook=trace_hook, clock=clock)


# ------------------------------------------------------------------------------------------------ gate D


def gate_d_validate(
    cfg: MigrationConfig,
    *,
    scope: Scope,
    corpora: Sequence[Path] = (),
    limit: int | None = None,
    accept_gaps: Sequence[str] = (),
    progress: Progress = NULL_PROGRESS,
    rows_sink: list[dict[str, Any]] | None = None,
) -> GateReport:
    """Gate D (J.3.5): SEM and ``agentprov-prov/0.1`` re-derived from sealed AERs and validated in every D8 tier, release mode.

    ``scope="golden"`` runs the golden AERs of ``tests/golden/test_gate_d.py`` (twice, with the committed pins);
    ``scope="full"`` reads the stored AERs of ``corpora`` read-only (one corpus per tree: the v1 imports of the release and
    converted trees and the native June-2024 import); ``limit`` takes an evenly spaced subset and reports scope ``sample``.
    Per-execution rows (digests, wall time, statement counts) are appended to ``rows_sink`` when given. Implemented in
    :mod:`agentprov.migration.gate_d`.
    """
    from agentprov.migration import gate_d  # noqa: PLC0415 - the engines load only when gate D runs

    result = gate_d.gate_d_validate(
        cfg, scope=scope, corpora=corpora, limit=limit, accept_gaps=accept_gaps, progress=progress
    )
    if rows_sink is not None:
        rows_sink.extend(result.rows)
    return result.report


# ------------------------------------------------------------------------------------------------ gate E



def _read_graph(path: Path) -> Any:
    from agentprov.ingest.loaders import strict_json_loads  # noqa: PLC0415

    with open(path, "rb") as stream:
        return strict_json_loads(stream.read())


def _semdiff_run(
    pairs: Sequence[PairInput],
    trees: dict[str, TreeSummary],
    cfg: MigrationConfig,
    semdiff_map: Any,
    progress: Progress,
) -> tuple[Any, list[Any]]:
    """Map, seal and render every pair (with B1), then classify its compat graph and derive its AER (the hook)."""
    from agentprov.migration import semdiff  # noqa: PLC0415
    from agentprov.views.transcript_v1 import render  # noqa: PLC0415

    found: dict[str, semdiff.ExecutionDiff] = {}

    def hook(pair: PairInput, document: Any, _info: Any) -> None:
        diff = semdiff.ExecutionDiff(pair.item, pair.tree)
        found[pair.item] = diff
        try:
            if pair.graph is None:
                diff.codes.append("compat.graph_missing")
            else:
                semdiff.classify_graph(diff, render(document), _read_graph(pair.graph), semdiff_map)
            semdiff.aer_measures(diff, document)
            semdiff.derivation_measures(diff, document)
        except Exception as exc:  # noqa: BLE001 - a fault fails the execution, with the exception type only (MP-6)
            diff.codes.append(f"semdiff.error:{type(exc).__name__}")

    run = run_pipeline(
        pairs, trees, frozenset({"B1"}), work=cfg.work, workers=cfg.workers, release=cfg.strict,
        in_process=cfg.in_process, progress=progress, hook=hook,
    )
    diffs = []
    for row in run.rows:
        diff = found.get(row.item) or semdiff.ExecutionDiff(row.item, row.tree, codes=["semdiff.not_evaluated"])
        diff.b1 = row.b1
        diff.codes.extend(row.codes)
        semdiff.finish_codes(diff, semdiff_map)
        diffs.append(diff)
    return run, diffs


def _semdiff_reports(scope: Scope, run: Any, diffs: Sequence[Any], semdiff_map: Any) -> dict[str, Any]:
    from agentprov.migration import semdiff  # noqa: PLC0415
    from agentprov.prov.specs import load_spec  # noqa: PLC0415

    spec = load_spec()
    versions = {**_specs(), "catalogue": {"aprov": {"version": spec.catalogue_version, "sha256": spec.catalogue_sha256}}}
    reports: dict[str, Any] = {}
    for tree, summary in run.trees.items():
        inputs = {
            "transcripts": summary.transcripts,
            "transcript_listing_sha256": summary.transcript_listing_sha256,
            "graphs": summary.graphs,
            "graph_listing_sha256": summary.graph_listing_sha256,
            "aer_listing_sha256": run.aer_listing_sha256.get(tree),
        }
        reports[tree] = semdiff.build_report(
            tree, scope, [d for d in diffs if d.tree == tree], semdiff_map, spec_versions=versions, inputs=inputs
        )
    return reports


def _semdiff_checks(tree: str, report: Any, diffs: Sequence[Any], semdiff_map: Any, scope: Scope) -> list[Check]:
    doc = report.document
    mine = [d for d in diffs if d.tree == tree]
    n = len(mine)
    edges, nodes, i6 = doc["edges"], doc["nodes"], doc["inference6"]
    r6_only = doc["values"]["used_r6_only"]
    omitted = doc["defence_omitted"]
    derivation_codes = sorted({c for d in mine for c in d.codes if c.startswith("derivation.")})
    checks = [
        _tree_check(f"semdiff.{tree}.compat_bytes", all(d.b1 is True for d in mine),
                    f"{sum(1 for d in mine if d.b1 is True)}/{n} compat graphs regenerated from the AER equal the stored bytes"),
        _tree_check(f"semdiff.{tree}.edges", edges["unclassified"] == 0 and edges["missing"] == 0,
                    f"{edges['classified']}/{edges['total']} edges classified; {edges['unclassified']} unclassified, "
                    f"{edges['missing']} predicted but absent (the classified union equals the edge set)"),
        _tree_check(f"semdiff.{tree}.nodes", nodes["missing"] == 0, f"{nodes['missing']} predicted nodes absent"),
        _tree_check(f"semdiff.{tree}.unmapped", doc["unmapped"] == 0, f"unmapped = {doc['unmapped']}"),
        _tree_check(f"semdiff.{tree}.inference6",
                    i6.get("entailed_not_asserted") == r6_only and i6.get("asserted_not_entailed", 0) == 0,
                    f"entailed-not-asserted {i6.get('entailed_not_asserted')} = R6-only used {r6_only}; "
                    f"asserted-not-entailed {i6.get('asserted_not_entailed')}"),
        _tree_check(f"semdiff.{tree}.defence_omitted",
                    omitted["compat_entities"] == omitted["aer_redact_decisions_overwritten"] == omitted["derived_overwritten_entities"],
                    f"{omitted['compat_entities']} defence_omitted entities, {omitted['aer_redact_decisions_overwritten']} redact "
                    f"decisions with /original overwritten, {omitted['derived_overwritten_entities']} apv:Overwritten entities (R-08)"),
        _tree_check(f"semdiff.{tree}.unexecuted", not any("unexecuted.listed_mismatch" in d.codes for d in mine),
                    f"{doc['aer'].get('unexecuted_requests', 0)} requests without execution, each listed under unexecuted_tool_call"),
        _tree_check(f"semdiff.{tree}.derivation",
                    not derivation_codes and not doc["derivation"]["rules_not_targeted"]
                    and not any(c.startswith("semdiff.error") for d in mine for c in d.codes),
                    f"{doc['derivation']['statements']} statements; every fired rule is a map target in an allowed bundle and "
                    f"class" if not derivation_codes else "; ".join(derivation_codes)[:300]),
    ]
    if scope == "full":
        for entry in doc["rows"]:
            if entry["frozen"] is not None:
                ok = entry["count"] == entry["frozen"]
                checks.append(_tree_check(f"frozen.{entry['id']}.{tree}", ok, f"{entry['count']} measured, {entry['frozen']} frozen"))
            for name, extra in (entry.get("extra") or {}).items():
                if extra["frozen"] is not None:
                    ok = extra["count"] == extra["frozen"]
                    checks.append(_tree_check(f"frozen.{entry['id']}.{name}.{tree}", ok, f"{extra['count']} measured, {extra['frozen']} frozen"))
    return checks


def gate_e_semdiff(
    cfg: MigrationConfig,
    *,
    scope: Scope,
    progress: Progress = NULL_PROGRESS,
    clock: Callable[[], datetime] | None = None,
) -> tuple[GateReport, dict[str, Any]]:
    """Gate E (J.3.6): the semantic diff of every compat graph in scope against ``agentprov-prov/0.1``.

    Returns the gate report and one :class:`~agentprov.migration.semdiff.SemDiffReport` per tree (``release``,
    ``converted``; J.3.6 writes one file per tree and O never pools them). For every pair, the AER is mapped and sealed
    as in gates A/B, the compat graph regenerated from its view must equal the stored bytes (B1), every edge of the stored
    graph is classified by the recomputed builder predicates, nodes and attributes are joined with the map, and the AER is
    derived once to count the counterpart statements. An execution passes iff its edges and nodes reconcile exactly,
    nothing is unmapped, the Inference-6 reading equals the R6-only edges, ``defence_omitted`` equals the Overwritten
    pre-decision entities (R-08), the unexecuted requests are the listed ones, and every derived statement's rule, bundle
    and class is allowed by the map. ``scope="golden"`` runs twice and requires identical report bytes;
    ``scope="full"`` (phase 13) reconciles every frozen count of the map (J.1.3) and the J.1.4 input pins.
    """
    from agentprov.migration.semdiff import MAP_RELPATH, load_map  # noqa: PLC0415
    from agentprov.prov.specs import load_spec  # noqa: PLC0415

    now = clock or (lambda: datetime.now(UTC))
    started = now()
    t0 = time.perf_counter()
    lock = load_lock(cfg.lock_path)
    semdiff_map = load_map()
    pairs, trees = _scope_inputs(cfg, scope)
    if not pairs:
        raise BaselineUnavailableError("no transcripts found for this scope")
    run, diffs = _semdiff_run(pairs, trees, cfg, semdiff_map, progress)
    reports = _semdiff_reports(scope, run, diffs, semdiff_map)
    checks: list[Check] = []
    notes: list[str] = [COMPAT_NOTICE]
    if scope == "golden":
        again_run, again_diffs = _semdiff_run(pairs, trees, cfg, semdiff_map, NULL_PROGRESS)
        again = _semdiff_reports(scope, again_run, again_diffs, semdiff_map)
        for tree, report in reports.items():
            same = tree in again and again[tree].json_bytes() == report.json_bytes()
            checks.append(_tree_check(f"determinism.semdiff.{tree}", same, "two runs give identical report bytes" if same else "the two runs differ"))
    else:
        notes.append("full scope: the semdiff report digests are recorded in outputs so that two runs can be compared (J.3.0)")
    inputs, input_checks = _input_checks(run.trees, scope, lock, graphs=True)
    checks += input_checks
    for tree, report in reports.items():
        checks += _semdiff_checks(tree, report, diffs, semdiff_map, scope)
    pending = sorted(semdiff_map.targets() - set(load_spec().rules))
    if pending:
        notes.append(f"map targets not in the shipped engine catalogue (no statements yet): {', '.join(pending)}")
    failed = [d for d in diffs if not d.passed]
    failures = tuple(
        {"item": d.item, "check": d.codes[0], "detail": "; ".join(d.codes)[:300]} for d in failed[:LISTED_FAILURES]
    )
    outputs: list[dict[str, Any]] = [
        {"name": "semdiff_report", "tree": t, "files": r.document["executions"], "sha256": r.sha256} for t, r in reports.items()
    ]
    outputs += [
        {"name": "aer_digest_listing", "tree": t, "files": run.trees[t].transcripts, "sha256": d}
        for t, d in run.aer_listing_sha256.items()
    ]
    details = {
        "semdiff": {
            t: {
                "unmapped": r.unmapped,
                "overlaps": r.document["overlaps"],
                "edges": {k: v for k, v in r.document["edges"].items() if k != "by_relation"},
                "values": r.document["values"],
            }
            for t, r in reports.items()
        },
        "map": {"path": MAP_RELPATH, "version": semdiff_map.version, "sha256": semdiff_map.sha256, "unresolved_targets": pending},
        "isolation": {"mode": run.isolation.get("mode"), "grade": run.isolation.get("grade")},
    }
    ended = now()
    report = GateReport(
        gate="E",
        scope=scope,
        role="release",
        agentprov=_agentprov_identity(),
        baseline_lock_sha256=lock_sha256(cfg.lock_path),
        specs=_specs(),
        environment=_environment(interpreter_advisory()),
        inputs=tuple(inputs),
        params={"workers": cfg.workers, "seed": DEFAULT_SEED, "strict": cfg.strict},
        checks=tuple(checks),
        outputs=tuple(outputs),
        started_at=started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        ended_at=ended.strftime("%Y-%m-%dT%H:%M:%SZ"),
        wall_s=round(time.perf_counter() - t0, 3),
        notes=tuple(notes),
        trace_counts={"expected": len(pairs), "checked": len(diffs), "passed": len(diffs) - len(failed), "failed": len(failed), "skipped": 0},
        trace_failures=failures,
        details=details,
    )
    return report, reports


def write_semdiff(reports: Mapping[str, Any], directory: Path | None = None, *, scope: Scope) -> list[Path]:
    """Write ``semdiff-<tree>.json`` and ``.md`` per tree (J.3.6; default ``$AGENTPROV_HOME/migration/semdiff``). The
    golden scope writes ``semdiff-<tree>.golden.{json,md}`` so that it never overwrites the full-scope reports a release
    cites."""
    target = Path(directory) if directory is not None else default_semdiff_dir()
    target.mkdir(parents=True, exist_ok=True)
    suffix = "" if scope == "full" else f".{scope}"
    written: list[Path] = []
    for tree, report in reports.items():
        stem = target / f"semdiff-{tree}{suffix}"
        atomic_write_text(stem.with_name(stem.name + ".json"), report.json_text())
        atomic_write_text(stem.with_name(stem.name + ".md"), report.markdown())
        written += [stem.with_name(stem.name + ".json"), stem.with_name(stem.name + ".md")]
    return written


__all__ = [
    "COMPAT_NOTICE",
    "GATE_ORDER",
    "BaselineUnavailableError",
    "Check",
    "GateOrderError",
    "GateReport",
    "LockError",
    "MigrationConfig",
    "Scope",
    "gate_a_v1_identity",
    "gate_b_compat_bytes",
    "gate_d_validate",
    "gate_e_semdiff",
    "report_text",
    "require_predecessors",
    "verify_baseline",
    "write_report",
    "write_semdiff",
]
