"""Local CI: the jobs of ``.github/workflows/ci.yml``, run on this machine (D-462; updates D-431).

Usage::

    uv run python tools/ci_local.py                       # every job that needs no network and no dispatch
    uv run python tools/ci_local.py --only core,secrets   # a selection (ids as in ci.yml, plus the local gates)
    uv run python tools/ci_local.py --skip core
    uv run python tools/ci_local.py --with-dispatch-jobs --allow-network   # also old-vs-new, backend-autodojo, ...
    uv run python tools/ci_local.py --list
    uv run python tools/ci_local.py --strict              # a skipped or unavailable job also fails (releases, K.19.1)

**Why.** GitHub CI is optional (D-431 and its update: repository variables ``CI_ON_PUSH`` and ``CI_RUNNER``), so the
same checks must be runnable here, and the release checklist (K.19.1) and the merge train can call one command.

**Jobs.** :data:`JOBS` lists one entry per ``ci.yml`` job (same id) plus the local gates (``generated``, ``pins``,
``readme-sources``, ``ids``). ``tests/unit/workflow/test_ci_local.py`` keeps them in step with ``ci.yml``: the same job ids, the
same dispatch-only jobs, the same lockfiles. The local commands differ where a runner differs:

* ``core`` runs the merge gate itself, the full suite through ``tools/suite_queue.py -- pytest -n N ...`` (the queue
  serialises heavy work across sessions), plus mypy, which ``ci.yml`` does not run. ``N`` is
  ``$AGENTPROV_SUITE_WORKERS``, else :func:`suite_workers` (10 on the 12-core M2 Max, 24 on the 36-core Mac Studio). It runs on this machine's OS only;
  the OS matrix stays a GitHub job.
* Environment syncs use ``--offline`` unless ``--allow-network`` is given; a sync that needs a download reports
  ``needs network`` instead of failing.
* Backend environments that ``ci.yml`` keeps in ``$RUNNER_TEMP`` go under ``$AGENTPROV_HOME/ci-local/`` (outside the
  checkout); the in-project ``backends/*/.venv`` layouts are the same as in ``ci.yml`` (git-ignored).

**Network.** ``live-run`` (backend build), ``dependencies`` (osv-scanner asks osv.dev), ``old-vs-new`` and
``backend-autodojo`` download. They are skipped unless ``--allow-network`` is given, and a session asks the user before
passing it. ``old-vs-new``, ``backend-autodojo`` and ``fuzz-thorough`` are dispatch-only in ``ci.yml`` too and need
``--with-dispatch-jobs``.

**Report.** One line per job (pass, fail, skipped, unavailable) and the log directory
``$AGENTPROV_HOME/ci-local/<run-id>/``. Exit 0 only if every selected job that ran passed; with ``--strict``, also none
was skipped or unavailable.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _workflow import agentprov_home, git_ok, safe_text, utc_now, write_json_atomic  # noqa: E402

#: The projects whose ``uv.lock`` must be current (``ci.yml`` core, "Every lockfile is current").
LOCK_PROJECTS = (".", "capture", "backends/shared", "backends/agentdojo", "backends/autodojo", "backends/agentdyn",
                 "backends/inspect/envs/agentharm", "gui")
#: The lockfiles osv-scanner reads (``ci.yml`` dependencies).
OSV_LOCKFILES = ("uv.lock", "backends/shared/uv.lock", "backends/agentdojo/uv.lock", "backends/autodojo/uv.lock",
                 "backends/agentdyn/uv.lock", "backends/inspect/envs/agentharm/uv.lock", "gui/uv.lock")
CORE_MARKERS = "not network and not backend_agentdojo and not backend_autodojo and not full_corpus"
SUITE_OPTIONS = ("--dist", "loadgroup", "-p", "no:randomly", "-p", "no:cacheprovider")


def suite_workers(environ: Mapping[str, str] = os.environ, cpus: int | None = None) -> int:
    """The merge gate's xdist workers: ``$AGENTPROV_SUITE_WORKERS``, else 10 (the user's decision of 2026-10-14, on the
    12-core M2 Max) or, on a larger host, two thirds of its CPUs (24 on the 36-core Mac Studio; Mac Studio tuning)."""
    raw = environ.get("AGENTPROV_SUITE_WORKERS")
    if raw:
        if not raw.isdigit() or int(raw) < 1:
            raise SystemExit(f"ci-local: $AGENTPROV_SUITE_WORKERS must be an integer of at least 1, not {raw[:20]!r}")
        return int(raw)
    return max(10, 2 * (cpus or os.cpu_count() or 1) // 3)


def suite_argv(environ: Mapping[str, str] = os.environ, cpus: int | None = None) -> tuple[str, ...]:
    """The full-suite command the ``core`` job queues."""
    return ("pytest", "-n", str(suite_workers(environ, cpus)), *SUITE_OPTIONS)


UV_RUN = ("uv", "run")
OFFLINE_HINTS = ("offline", "network connectivity is disabled", "failed to fetch", "not found in the cache")


@dataclass(frozen=True)
class Step:
    name: str
    argv: tuple[str, ...]
    cwd: str = "."
    env: tuple[tuple[str, str], ...] = ()
    sync: bool = False  # an environment sync: --offline is added unless the network is allowed


@dataclass(frozen=True)
class Job:
    id: str
    ci_job: str | None  # the ci.yml job it mirrors; None for a local gate
    steps: Callable[[Context], list[Step]]
    network: bool = False
    dispatch_only: bool = False
    requires: tuple[str, ...] = ()  # executables that must be on PATH
    note: str = ""


@dataclass
class Context:
    root: Path
    rundir: Path
    label: str
    allow_network: bool

    @property
    def work(self) -> Path:
        return self.rundir / "work"


def _lock_steps(ctx: Context) -> list[Step]:
    flag = () if ctx.allow_network else ("--offline",)
    return [Step(f"uv lock --check ({p})", ("uv", "lock", "--check", *flag), cwd=p) for p in LOCK_PROJECTS]


def _core(ctx: Context) -> list[Step]:
    py = (*UV_RUN, "python", "-c")
    return [
        *_lock_steps(ctx),
        Step("sync (locked)", ("uv", "sync", "--locked"), sync=True),
        Step("interpreter floor 3.14.8", (*py, "import sys; print(sys.version); assert sys.version_info >= (3, 14, 8)")),
        Step("no backend packages in the core environment", (*py, (
            "import importlib.util as u, sys; bad = [m for m in ('agentdojo', 'agentprov_backend', 'openai', 'httpx', "
            "'inspect_ai') if u.find_spec(m)]; print('present:', bad); sys.exit(bool(bad))"))),
        Step("host profile", (*py, "import json; from agentprov.host import detect_host; "
                                   "print(json.dumps(detect_host().to_record(), indent=1))")),
        Step("unicode", (*UV_RUN, "python", "tools/check_unicode.py")),
        Step("ruff", (*UV_RUN, "ruff", "check", ".")),
        Step("mypy", (*UV_RUN, "mypy")),
        Step("full suite (through the queue)", (*UV_RUN, "python", "tools/suite_queue.py", "--label", ctx.label,
                                                "--", *suite_argv())),
    ]


def _capture(ctx: Context) -> list[Step]:
    return [Step("capture tests (3.14)", (*UV_RUN, "python", "tools/suite_queue.py", "--targeted", "--", "pytest",
                                          "-q", "-p", "no:cacheprovider", "capture/tests"))]


def _backend_shared(ctx: Context) -> list[Step]:
    env = (("UV_PROJECT_ENVIRONMENT", str(agentprov_home() / "ci-local" / "envs" / "shared")),)
    return [Step("sync (locked, 3.12)", ("uv", "sync", "--locked", "--python", "3.12", "--project", "backends/shared"),
                 env=env, sync=True),
            Step("backend-shared and capture tests (3.12)", ("uv", "run", "--no-sync", "--project", "backends/shared",
                                                             "pytest", "backends/shared/tests", "capture/tests"),
                 env=env)]


def _backend_agentdojo(ctx: Context) -> list[Step]:
    proj = ("--project", "backends/agentdojo")
    unset = (("UV_PROJECT_ENVIRONMENT", ""),)  # the in-project layout, as in ci.yml
    return [Step("sync (locked, 3.12)", ("uv", "sync", "--locked", "--python", "3.12", *proj), env=unset, sync=True),
            Step("agentdojo is 0.1.35", ("uv", "run", "--no-sync", *proj, "python", "-c", "import importlib.metadata "
                                         "as m; assert m.version('agentdojo') == '0.1.35'"), env=unset),
            Step("tests", ("uv", "run", "--no-sync", *proj, "pytest", "backends/agentdojo/tests", "-m",
                           "backend_agentdojo and not old_package"), env=unset)]


def _live_run(ctx: Context) -> list[Step]:
    home = ctx.work / "agentprov-home"
    env = (("AGENTPROV_HOME", str(home)),)
    run = (*UV_RUN, "agentprov")
    return [
        Step("sync (locked, core)", ("uv", "sync", "--locked"), sync=True),
        Step("build the AgentDojo backend", (*run, "backends", "build", "agentdojo", "--allow-network"), env=env),
        Step("verify the build offline", (*run, "backends", "build", "agentdojo", "--offline-check"), env=env),
        Step("scripted live run", (*run, "run", "agentdojo", "--corpus", str(ctx.work / "live-corpus"), "--campaign",
                                   "ci", "--suite", "banking", "--user-tasks", "user_task_1", "--attack",
                                   "important_instructions", "--injection-tasks", "injection_task_0",
                                   "--model-display-name", "Scripted Model", "--llm-script",
                                   "tests/fixtures/capture/benign_banking_single_pass/script.json", "--keep-staging",
                                   "--progress", "steps", "--progress-format", "plain"), env=env),
        Step("core mapping of the produced sessions", (*UV_RUN, "pytest", "tests/integration/test_live_mapping.py",
                                                       "tests/differential"),
             env=(*env, ("AGENTPROV_LIVE_ARTEFACTS", str(home / "staging")))),
        Step("end-to-end and T0 tests", (*UV_RUN, "pytest", "tests/integration/test_run_live_agentdojo.py",
                                         "tests/integration/test_run_spawn.py", "tests/cli/test_backends_cmd.py"),
             env=(*env, ("AGENTPROV_TEST_BUILD_NETWORK", "1"))),
    ]


def _backend_autodojo(ctx: Context) -> list[Step]:
    home = (("AGENTPROV_HOME", str(ctx.work / "agentprov-home")),)
    run = (*UV_RUN, "agentprov")
    proj = ("--project", "backends/autodojo")
    unset = (("UV_PROJECT_ENVIRONMENT", ""),)
    return [
        Step("sync (locked, core)", ("uv", "sync", "--locked"), sync=True),
        Step("build the AutoDojo backend", (*run, "backends", "build", "autodojo", "--allow-network"), env=home),
        Step("verify the build offline", (*run, "backends", "build", "autodojo", "--offline-check"), env=home),
        Step("core build test", (*UV_RUN, "pytest", "tests/integration/test_backends_build_autodojo.py",
                                 "tests/cli/test_backends_cmd.py"), env=home),
        Step("end-to-end scripted runs", (*UV_RUN, "pytest", "tests/integration/test_run_live_autodojo.py"),
             env=(*home, ("AGENTPROV_TEST_BUILD_NETWORK", "1"))),
        Step("harness environment (3.12, in-project)", ("uv", "sync", "--locked", "--python", "3.12", *proj),
             env=unset, sync=True),
        Step("harness tests", ("uv", "run", "--no-sync", *proj, "pytest", "backends/autodojo/tests", "-m",
                               "backend_autodojo"), env=unset),
        Step("fixtures are current", ("uv", "run", "--no-sync", *proj, "python",
                                      "backends/autodojo/tools/make_capture_fixtures.py", "--check"), env=unset),
    ]


def _old_vs_new(ctx: Context) -> list[Step]:
    work = ctx.work
    env = (("AGENTPROV_HOME", str(work / "agentprov-home")), ("AGENTPROV_C6_WORK", str(work / "c6")),
           ("AGENTPROV_GATE_WORK", str(work / "gates")))
    baseline = work / "baseline-src"
    unset = (("UV_PROJECT_ENVIRONMENT", ""),)
    return [
        Step("baseline repository at 579a908 (read-only clone)",
             ("git", "clone", "--quiet", "https://github.com/nickjones39/agentdojo-prov", str(baseline))),
        Step("pin 579a908", ("git", "-C", str(baseline), "checkout", "--quiet",
                             "579a908354b93361efe0905ffb7623256aa96a06")),
        Step("baseline environment (J.1.6)", ("uv", "run", "--no-project", "--python", "3.12", "python",
                                              "tools/migration/build_baseline_env.py", "--baseline-repo",
                                              str(baseline)), env=env),
        Step("backend environment (3.12)", ("uv", "sync", "--locked", "--python", "3.12", "--project",
                                            "backends/agentdojo"), env=unset, sync=True),
        Step("C6 producer", ("uv", "run", "--no-sync", "--project", "backends/agentdojo", "pytest",
                             "backends/agentdojo/tests/test_c6_old_vs_new.py", "-m", "old_package"), env=env),
        Step("core environment (shacl)", ("uv", "sync", "--locked", "--extra", "shacl"), env=unset, sync=True),
        Step("C6 comparer", ("uv", "run", "--no-sync", "pytest", "tests/migration/test_c6_old_vs_new.py", "-m",
                             "old_package"), env=(*env, *unset)),
        Step("C2 (golden scope)", ("uv", "run", "--no-sync", "python", "tools/migration/gate_c2.py", "--scope", "golden",
                                   "--work", str(work / "gates" / "c2"), "--report", str(work / "gates" / "C2.json")),
             env=(*env, *unset)),
        Step("C5 (converter)", ("uv", "run", "--no-sync", "python", "tools/migration/gate_c5.py", "--work",
                                str(work / "gates" / "c5"), "--report", str(work / "gates" / "C5.json")),
             env=(*env, *unset)),
    ]


def _secrets(ctx: Context) -> list[Step]:
    return [Step("gitleaks over the full history", ("gitleaks", "git", "--redact", "--no-banner", "--config",
                                                    ".gitleaks.toml", "."))]


def _dependencies(ctx: Context) -> list[Step]:
    return [Step("osv-scanner over every lockfile", ("osv-scanner", "scan", *(f"--lockfile={f}" for f in
                                                                              OSV_LOCKFILES)))]


def _fuzz_thorough(ctx: Context) -> list[Step]:
    return [Step("fuzz suites, thorough budgets", (*UV_RUN, "python", "tools/suite_queue.py", "--label",
                                                   f"{ctx.label} fuzz-thorough", "--", "pytest", "tests/fuzz",
                                                   "tests/security/test_ingest_fuzz.py",
                                                   "tests/adapters/foobench/test_fuzz.py",
                                                   "tests/adapters/agentdojo/test_reader.py", "tests/property"),
                 env=(("AGENTPROV_FUZZ", "thorough"),))]


def _generated(ctx: Context) -> list[Step]:
    return [Step("generated docs", (*UV_RUN, "python", "tools/gen_docs.py", "--check")),
            Step("generated registry lists", (*UV_RUN, "python", "tools/gen_registry.py", "--check")),
            Step("every spec item citation resolves", (*UV_RUN, "python", "tools/spec_labels.py", "--check"))]


def _pins(ctx: Context) -> list[Step]:
    return [Step("every test pin is current (twice, in a scratch worktree)", (*UV_RUN, "python",
                                                                             "tools/regen_pins.py", "--check"))]


def _ids(ctx: Context) -> list[Step]:
    return [Step("numbers: no duplicate, and every new definition reserved",
                 (*UV_RUN, "python", "tools/reserve_id.py", "--scan-ref", "origin/main", "scan", "--strict",
                  "--require-reserved"))]


def _readme(ctx: Context) -> list[Step]:
    steps = [Step("README source tables", (*UV_RUN, "python", "tools/gen_readme_sources.py", "--check"))]
    if (ctx.root / "tools" / "gen_readme_corpora.py").is_file():
        steps.append(Step("user guide corpus listing", (*UV_RUN, "python", "tools/gen_readme_corpora.py", "--check")))
    if (ctx.root / "tools" / "gen_user_guide_cli.py").is_file():
        steps.append(Step("user guide CLI reference", (*UV_RUN, "python", "tools/gen_user_guide_cli.py", "--check")))
    return steps


JOBS: tuple[Job, ...] = (
    Job("core", "core", _core, note="this machine only; the OS matrix stays on GitHub"),
    Job("capture", "capture", _capture),
    Job("backend-shared", "backend-shared", _backend_shared),
    Job("backend-agentdojo", "backend-agentdojo", _backend_agentdojo),
    Job("old-vs-new", "old-vs-new", _old_vs_new, network=True, dispatch_only=True),
    Job("live-run", "live-run", _live_run, network=True),
    Job("backend-autodojo", "backend-autodojo", _backend_autodojo, network=True, dispatch_only=True),
    Job("secrets", "secrets", _secrets, requires=("gitleaks",)),
    Job("dependencies", "dependencies", _dependencies, network=True, requires=("osv-scanner",)),
    Job("fuzz-thorough", "fuzz-thorough", _fuzz_thorough, dispatch_only=True),
    Job("generated", None, _generated),
    Job("pins", None, _pins),
    Job("readme-sources", None, _readme),
    Job("ids", None, _ids, note="decision, regen-batch, spec-item and section-heading numbers (tools/reserve_id.py)"),
)


# --------------------------------------------------------------------------------------------------- running


@dataclass
class Result:
    job: str
    status: str  # pass | fail | skipped | unavailable
    reason: str = ""
    seconds: float = 0.0
    steps: list[dict[str, Any]] = field(default_factory=list)


def _which(name: str) -> bool:
    return any((Path(d) / name).is_file() and os.access(Path(d) / name, os.X_OK)
               for d in os.environ.get("PATH", "").split(os.pathsep) if d)


def select(only: Sequence[str] | None, skip: Sequence[str], with_dispatch: bool) -> list[Job]:
    ids = {j.id for j in JOBS}
    unknown = [x for x in [*(only or ()), *skip] if x not in ids]
    if unknown:
        raise ValueError(f"unknown job(s): {', '.join(unknown)}; see --list")
    chosen = [j for j in JOBS if (only is None or j.id in only) and j.id not in skip]
    if only is None:
        chosen = [j for j in chosen if with_dispatch or not j.dispatch_only]
    return chosen


def _report_line(result: Result) -> str:
    return f"ci-local: {result.job:<18} {result.status}{'  ' + result.reason if result.reason else ''}"


def run_job(job: Job, ctx: Context, log: Callable[[str], None]) -> Result:
    early = None
    missing = [r for r in job.requires if not _which(r)]
    if job.network and not ctx.allow_network:
        early = Result(job.id, "skipped", "needs the network: run with --allow-network after the user's yes")
    elif missing:
        early = Result(job.id, "unavailable", f"not installed: {', '.join(missing)}")
    if early is not None:
        log(_report_line(early))
        return early
    started = time.monotonic()
    result = Result(job.id, "pass")
    logfile = ctx.rundir / f"{job.id}.log"
    ctx.work.mkdir(parents=True, exist_ok=True)
    with logfile.open("w", encoding="utf-8") as fh:
        for step in job.steps(ctx):
            argv = list(step.argv) + (["--offline"] if step.sync and not ctx.allow_network else [])
            env = {k: v for k, v in os.environ.items()}
            for key, value in step.env:
                if value == "":
                    env.pop(key, None)
                else:
                    env[key] = value
            fh.write(f"\n=== {step.name}: {' '.join(argv)} (cwd {step.cwd})\n")
            fh.flush()
            t0 = time.monotonic()
            done = subprocess.run(argv, cwd=ctx.root / step.cwd, env=env, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True, errors="replace")
            fh.write(done.stdout)
            result.steps.append({"name": step.name, "exit": done.returncode,
                                 "seconds": round(time.monotonic() - t0, 1)})
            if done.returncode != 0:
                text = done.stdout.lower()
                offline = (step.sync or "--offline" in argv) and not ctx.allow_network and any(
                    h in text for h in OFFLINE_HINTS)
                result.status = "unavailable" if offline else "fail"
                result.reason = (f"{step.name}: needs the network (offline sync could not complete)" if offline
                                 else f"{step.name}: exit {done.returncode}")
                break
    result.seconds = round(time.monotonic() - started, 1)
    log(_report_line(result))
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(allow_abbrev=False, description=__doc__.split("\n\n")[0])
    p.add_argument("-C", dest="cwd", type=Path, default=Path.cwd())
    p.add_argument("--only", help="comma-separated job ids")
    p.add_argument("--skip", default="", help="comma-separated job ids")
    p.add_argument("--with-dispatch-jobs", action="store_true", help="also the jobs ci.yml runs only by dispatch")
    p.add_argument("--allow-network", action="store_true",
                   help="run the jobs that download (ask the user first) and sync environments online")
    p.add_argument("--strict", action="store_true", help="a skipped or unavailable job also fails the run")
    p.add_argument("--label", help="label for the queued suite (default: the branch)")
    p.add_argument("--list", action="store_true", help="list the jobs and exit")
    p.add_argument("--json", action="store_true", help="print the report as JSON")
    a = p.parse_args(argv)
    if a.list:
        for j in JOBS:
            flags = [f for f, on in (("network", j.network), ("dispatch-only", j.dispatch_only)) if on]
            mirror = f"ci.yml {j.ci_job}" if j.ci_job else "local gate"
            print(f"{j.id:<18} {mirror:<26} {', '.join(flags) or '-':<24} {j.note}")
        return 0
    top = git_ok(["rev-parse", "--show-toplevel"], a.cwd)
    if top is None:
        print(f"ci-local: {a.cwd} is not inside a git worktree", file=sys.stderr)
        return 2
    root = Path(top)
    try:
        jobs = select([x for x in a.only.split(",") if x] if a.only else None,
                      [x for x in a.skip.split(",") if x], a.with_dispatch_jobs)
    except ValueError as exc:
        print(f"ci-local: {exc}", file=sys.stderr)
        return 2
    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + secrets.token_hex(2)
    rundir = agentprov_home() / "ci-local" / run_id
    rundir.mkdir(parents=True, exist_ok=True)
    head = git_ok(["rev-parse", "HEAD"], root) or "?"
    dirty = bool(git_ok(["status", "--porcelain"], root))
    label = a.label or f"ci-local {git_ok(['symbolic-ref', '--quiet', '--short', 'HEAD'], root) or head[:10]}"
    ctx = Context(root=root, rundir=rundir, label=label, allow_network=a.allow_network)
    print(f"ci-local: {len(jobs)} job(s) on {head[:10]}{' (uncommitted changes!)' if dirty else ''}; logs in {rundir}")
    results = [run_job(j, ctx, print) for j in jobs]
    failed = [r for r in results if r.status == "fail"]
    soft = [r for r in results if r.status in ("skipped", "unavailable")]
    ok = not failed and not (a.strict and soft)
    report: dict[str, Any] = {"run_id": run_id, "head": head, "dirty": dirty, "started_at": utc_now(),
                              "allow_network": a.allow_network, "strict": a.strict, "passed": ok,
                              "jobs": [r.__dict__ for r in results]}
    write_json_atomic(rundir / "report.json", report)
    if a.json:
        print(json.dumps(report, indent=2, ensure_ascii=True))
    print(f"ci-local: {'PASS' if ok else 'FAIL'}: {sum(r.status == 'pass' for r in results)} passed, {len(failed)} "
          f"failed, {len(soft)} skipped or unavailable" + (" (counted as failures: --strict)" if a.strict and soft
                                                            else ""))
    for r in failed + (soft if a.strict else []):
        print(f"  {r.job}: {safe_text(r.reason, 200)} (log {rundir / (r.job + '.log')})")
    return 0 if ok else 1


def ci_jobs(workflow: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """The jobs of a parsed ``ci.yml`` (for the sync test)."""
    return dict(workflow.get("jobs", {}))


if __name__ == "__main__":
    raise SystemExit(main())
