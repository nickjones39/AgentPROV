"""``agentprov devrun``: a quick end-to-end check before a full import (D-705; GUI design §19; D-544, D-529).

    agentprov devrun plan [--format text|json]          # the parts, sample counts and steps (writes nothing)
    agentprov devrun start [--confirm-r2] [--format]    # create the run folder and start its batch
    agentprov devrun list [--format text|json]          # the runs, newest first, with a summary per part
    agentprov devrun prune [--keep N] [--yes]           # delete old run folders (never one in use)

The settings are ``agentprov settings`` ``devrun.*`` keys (:mod:`agentprov.devrun.plan`). Per part, three steps of
one batch (D-704, continue on failure), each through the machine-wide job queue when this checkout has it:
``import SOURCE --snapshot PART --fetch --sample N|--limit N --corpus <run>/<part>``, ``validate --corpus …`` and
``recompute --corpus … --dry-run``. Never ``--release``, ``package`` or a stored corpus. The import reads the fetch
cache (``--fetch``, R2), so ``start`` needs ``--confirm-r2`` (exit 4 without). With ``devrun.prov_conformance`` off
the import skips tier 4 and validate runs ``aer,sem,linkage`` only (§8.3a). After a start, all but the newest
``devrun.keep`` run folders are deleted, sparing every folder a running job or an unfinished batch uses (GR-25).
"""

from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path
from typing import Any

from agentprov.cli.common import CliUsageError, CommandResult, Context, safe_text

LIST_FORMAT = "agentprov-devrun-list/0.1"


def register(sub: Any, shared: argparse.ArgumentParser) -> None:
    p = sub.add_parser("devrun", parents=[shared], help="dev runs: a few samples of every part, imported and checked",
                       description=__doc__.splitlines()[0], allow_abbrev=False)
    p.set_defaults(command="devrun", handler=run_devrun, feedback=False)
    actions = p.add_subparsers(dest="devrun_action", metavar="ACTION", required=True)
    pl = actions.add_parser("plan", parents=[shared], help="the parts and steps a start would run", allow_abbrev=False)
    pl.add_argument("--format", choices=["text", "json"], default="text")
    st = actions.add_parser("start", parents=[shared], help="create a run folder and start its batch",
                            allow_abbrev=False)
    st.add_argument("--confirm-r2", action="store_true", help="confirm the imports' fetch-cache reads (R2)")
    st.add_argument("--format", choices=["text", "json"], default="text")
    ls = actions.add_parser("list", parents=[shared], help="the runs, newest first", allow_abbrev=False)
    ls.add_argument("--format", choices=["text", "json"], default="text")
    pr = actions.add_parser("prune", parents=[shared], help="delete old run folders (lists them without --yes)",
                            allow_abbrev=False)
    pr.add_argument("--keep", type=int, metavar="N", help="keep the newest N (default devrun.keep)")
    pr.add_argument("--yes", action="store_true", help="delete them")


def _payload(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"


def _settings(home: Path) -> Any:
    from agentprov import settings
    from agentprov.devrun.plan import DevSettings

    try:
        return DevSettings.from_settings(settings.items("devrun.", home=home))
    except settings.SettingsError as exc:
        raise CliUsageError(f"agentprov devrun: {exc}") from None


def new_run_dir(home: Path, now: float | None = None) -> Path:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now))
    path = home / "dev-runs" / stamp
    n = 1
    while path.exists():  # two runs in the same second
        path = home / "dev-runs" / f"{stamp}-{n}"
        n += 1
    return path


def run_steps(part: Any, run_dir: Path, s: Any, *, queue: bool) -> list[Any]:
    """The three batch steps of one part (D-544; D-529: ``--seed`` only with ``--sample-mode random``)."""
    from agentprov.jobs.batch import BatchStep
    from agentprov.jobs.manager import JobRequest

    skip = not s.prov_conformance
    corpus = str(run_dir / part.folder)
    sampling = ("--sample", str(part.samples), "--sample-mode", s.mode,
                *(("--seed", str(s.seed)) if s.mode == "random" else ()))
    extra = {"devrun": run_dir.name, "part": part.key}
    cpu = s.queue_cpu if queue else None
    imp = ("import", "--corpus", corpus, "--snapshot", part.part, "--fetch", *sampling,
           *(("--skip-prov-conformance",) if skip else ()), part.source)
    requests = [
        JobRequest(imp, f"dev run · import {part.key}", writes=(corpus,), queue_cpu=cpu, extra=extra,
                   conformance_skipped=skip),
        JobRequest(("validate", "--corpus", corpus, *(("--tiers", "aer,sem,linkage") if skip else ())),
                   f"dev run · validate {part.key}" + (" (PROV tier not run)" if skip else ""), reads=(corpus,),
                   queue_cpu=cpu, extra=extra, conformance_skipped=skip),
        JobRequest(("recompute", "--corpus", corpus, "--dry-run"), f"dev run · recompute {part.key}",
                   reads=(corpus,), queue_cpu=cpu, extra=extra),
    ]
    steps = [BatchStep(r) for r in requests]
    for step in steps:
        step.recorded_tier = step.request.tier
    return steps


def busy_runs(home: Path) -> set[Path]:
    """GR-25: the run folders a running job or an unfinished batch's step writes, reads or names as its ``devrun``."""
    from agentprov.jobs.batch import Batch
    from agentprov.jobs.record import list_jobs

    root = (home / "dev-runs").resolve()
    busy: set[Path] = set()

    def mark(paths: list[object]) -> None:
        for p in paths:
            try:
                rel = Path(str(p)).expanduser().resolve().relative_to(root)
            except (OSError, RuntimeError, ValueError):
                continue
            if rel.parts:
                busy.add(root / rel.parts[0])

    for job in list_jobs(home):
        if job.state == "running":
            run = job.meta.get("devrun")
            mark([*job.writes, *(job.record.get("reads") or []), *((root / run,) if isinstance(run, str) and run
                                                                     else ())])
    for batch in Batch.load_all(home):
        for step in batch.steps:
            if step.state in ("pending", "held", "running"):
                run = step.request.extra.get("devrun")
                mark([*step.request.writes, *step.request.reads,
                      *((root / run,) if isinstance(run, str) and run else ())])
    return busy


def prune(home: Path, keep: int, *, spare: set[Path] | None = None, delete: bool) -> list[Path]:
    """All but the newest ``keep`` run folders, sparing busy ones (deleted only with ``delete``)."""
    from agentprov.devrun.plan import run_dirs

    busy = {p.resolve() for p in (*busy_runs(home), *(spare or set()))}
    runs = run_dirs(home)
    old = [p for p in runs[: max(0, len(runs) - max(1, keep))] if p.resolve() not in busy]
    if delete:
        for p in old:
            shutil.rmtree(p)
    return old


def run_devrun(ctx: Context) -> CommandResult:
    from agentprov.cli.live.envs import agentprov_home
    from agentprov.devrun.plan import plan

    args = ctx.args
    home = agentprov_home(ctx.env)
    result = CommandResult()
    s = _settings(home)
    action = args.devrun_action
    if action in ("plan", "start"):
        from agentprov.jobs.manager import checkout_root, queue_available

        parts = plan(s)
        if not parts:
            raise CliUsageError("agentprov devrun: no corpus part is selected (devrun.include / devrun.exclude)")
        root = checkout_root()
        queue = queue_available(root)
        run_dir = new_run_dir(home)
        steps = [st for p in parts for st in run_steps(p, run_dir, s, queue=queue)]
        doc: dict[str, Any] = {"settings": s.to_json(), "parts": [p.to_json() for p in parts],
                               "steps": [st.to_json() for st in steps], "queue": queue}
        if action == "plan":
            if args.format == "json":
                result.payload = _payload({"format": "agentprov-devrun-plan/0.1", **doc})
            else:
                result.output(f"{len(parts)} part(s), {len(steps)} step(s) "
                              f"({'through the job queue' if queue else 'no job queue in this checkout'})")
                for p in parts:
                    result.output(safe_text(f"  {p.key}: {p.samples} sample(s) ({s.mode})", 200))
            return result
        from agentprov.cli.batch import _start, checkout_pin
        from agentprov.jobs.batch import Batch
        from agentprov.jobs.manager import atomic_write_json

        if not args.confirm_r2:
            from agentprov.jobs.manager import SpawnRefused

            raise SpawnRefused("agentprov devrun start: the imports read the fetch cache (--fetch, R2); give "
                               "--confirm-r2", "devrun.r2_unconfirmed")
        run_dir.mkdir(parents=True, exist_ok=False)
        batch = Batch.new(home, f"dev run {run_dir.name}", steps, continue_on_failure=True, pin=checkout_pin())
        atomic_write_json(run_dir / "devrun.json", {
            "format": "agentprov-devrun/0.1", "settings": s.to_json(), "parts": [p.key for p in parts],
            "samples": {p.key: p.samples for p in parts}, "batch_id": batch.batch_id, "pin": batch.pin,
            "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})  # fmt: skip
        driver = _start(ctx, batch, True, result)
        pruned = prune(home, s.keep, spare={run_dir}, delete=True)
        out = {"run_dir": str(run_dir), "batch_id": batch.batch_id, "driver_job_id": driver.job_id,
               "parts": len(parts), "steps": len(steps), "pruned": [p.name for p in pruned]}
        if args.format == "json":
            result.payload = _payload(out)
        else:
            result.output(f"dev run {run_dir.name}: {len(parts)} part(s), batch {batch.batch_id}, driver "
                          f"{driver.job_id}; pruned {len(pruned)}")
        result.counters = {"parts": len(parts), "steps": len(steps), "pruned": len(pruned)}
    elif action == "list":
        from agentprov.devrun.plan import run_dirs, summarise
        from agentprov.jobs.record import list_jobs, read_json

        jobs = list_jobs(home)
        rows: list[dict[str, Any]] = []
        for run in reversed(run_dirs(home)):
            manifest = read_json(run / "devrun.json") or {}
            mine = [j for j in jobs if j.meta.get("devrun") == run.name]
            rows.append({"run": run.name, "batch_id": manifest.get("batch_id"), "created": manifest.get("created"),
                         "parts": [r.to_json() for r in summarise(mine)]})
        if args.format == "json":
            result.payload = _payload({"format": LIST_FORMAT, "runs": rows})
        else:
            for r in rows:
                result.output(safe_text(f"{r['run']}  batch {r['batch_id']}  {len(r['parts'])} part(s)", 200))
    elif action == "prune":
        keep = s.keep if args.keep is None else args.keep
        if keep < 1:
            raise CliUsageError("agentprov devrun prune: --keep >= 1")
        old = prune(home, keep, delete=args.yes)
        for folder in old:
            result.output(folder.name)
        result.counters = {"deleted" if args.yes else "to_delete": len(old)}
    return result
