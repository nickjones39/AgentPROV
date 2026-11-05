"""``agentprov batch``: ordered job lists that run as one job (D-704; GUI design §4.4; user decision 2026-10-22).

    agentprov batch create (SPEC.json | --stdin) [--label L] [--concurrency N] [--[no-]continue-on-failure] [--format]
    agentprov batch start ID [--confirm-r2] [--format]       # starts the driver job `batch run ID`
    agentprov batch run ID [--confirm-r2] [--interval S]       # the driver loop (normally inside its job)
    agentprov batch resume ID [--confirm-r2] [--format]      # a new driver for a stopped batch
    agentprov batch stop ID [--steps] [--wait S] [--format]  # stop the driver (with --steps: the whole batch)
    agentprov batch list [--format] | show ID [--format]

``SPEC.json`` (or stdin with ``--stdin``) is ``{"steps": [{"argv": [...], "label", "writes", "reads", "slot", "queue_cpu",
"progress_level", "with_control_file", "extra"}, ...]}``, read strictly. Each step's argv must parse as an
``agentprov`` command, and may not start jobs or batches or be destructive (exit 2). A step with an R2 flag (network or
paid) runs only under a driver started with ``--confirm-r2``; without it, ``start`` refuses (exit 4). The batch pins
the checkout (path, commit, digest of the uncommitted diff): a change blocks the remaining steps.

``stop`` marks the batch stopped, so no driver starts another step of it, and stops its driver (one SIGTERM, or the
control file's ``stop``); the steps already started keep running. With ``--steps`` it also stops every running or
queued step job of the batch the same way (``agentprov jobs stop``), then waits up to ``--wait`` seconds for them to end
and records how they ended. Exit 1 when a running step job could not be signalled. ``resume`` starts the batch again
from its pending steps.
"""

from __future__ import annotations

import argparse
import os
import hashlib
import json
import signal
import sys
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from agentprov.cli.common import CliUsageError, CommandResult, Context, safe_text

LIST_FORMAT = "agentprov-batches-list/0.1"
STOP_FORMAT = "agentprov-batch-stop/0.1"
MAX_SPEC_BYTES = 4 * 1024 * 1024


def register(sub: Any, shared: argparse.ArgumentParser) -> None:
    p = sub.add_parser("batch", parents=[shared], help="ordered job lists that run as one job",
                       description=__doc__.splitlines()[0], allow_abbrev=False)
    p.set_defaults(command="batch", handler=run_batch, feedback=False)
    actions = p.add_subparsers(dest="batch_action", metavar="ACTION", required=True)
    c = actions.add_parser("create", parents=[shared], help="create a batch from a step list (not started)",
                           allow_abbrev=False)
    c.add_argument("spec", nargs="?", metavar="SPEC.json", help="the step list (a file)")
    c.add_argument("--stdin", action="store_true", help="read the step list from stdin instead")
    c.add_argument("--label", default="", metavar="TEXT")
    c.add_argument("--concurrency", type=int, default=1, metavar="N", help="steps at a time (1 to 16)")
    c.add_argument("--continue-on-failure", action=argparse.BooleanOptionalAction, default=None,
                   help="go on after a step ends with exit 4 or 70 (default: the setting jobs.continue_on_failure)")
    c.add_argument("--format", choices=["text", "json"], default="text")
    for name, help_text in (("start", "start the batch's driver job"),
                            ("resume", "start a new driver for a batch whose driver ended"),
                            ("run", "advance the batch in the foreground until it is done (the driver)")):
        a = actions.add_parser(name, parents=[shared], help=help_text, allow_abbrev=False)
        a.add_argument("batch_id", metavar="ID")
        a.add_argument("--confirm-r2", action="store_true",
                       help="confirm the batch's R2 steps (network, downloads, paid calls) for this driver")
        if name == "run":
            a.add_argument("--interval", type=float, default=2.0, metavar="S", help="seconds between ticks")
        else:
            a.add_argument("--format", choices=["text", "json"], default="text")
    st = actions.add_parser("stop", parents=[shared],
                            help="stop the driver (the steps it started keep running unless --steps)",
                            allow_abbrev=False)
    st.add_argument("batch_id", metavar="ID")
    st.add_argument("--steps", action="store_true",
                    help="stop the whole batch: also every running or queued step job (a graceful stop each, as "
                         "'agentprov jobs stop')")
    st.add_argument("--wait", type=float, default=10.0, metavar="S",
                    help="seconds to wait for the stopped jobs to end before recording how they ended (0: do not "
                         "wait; default 10)")
    st.add_argument("--format", choices=["text", "json"], default="text")
    ls = actions.add_parser("list", parents=[shared], help="the batches, newest first", allow_abbrev=False)
    ls.add_argument("--format", choices=["text", "json"], default="text")
    sh = actions.add_parser("show", parents=[shared], help="one batch and its steps", allow_abbrev=False)
    sh.add_argument("batch_id", metavar="ID")
    sh.add_argument("--format", choices=["text", "json"], default="text")


def _payload(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"


def _home(ctx: Context) -> Path:
    from agentprov.cli.live.envs import agentprov_home

    return agentprov_home(ctx.env)


def validate_argv(argv: Sequence[str]) -> str | None:
    """Why ``argv`` is not a runnable ``agentprov`` command line (the CLI's own parser), or ``None``."""
    from agentprov.cli.common import CliUsageError as Usage
    from agentprov.cli.common import ParserExit
    from agentprov.cli.main import build_parser

    try:
        args = build_parser().parse_args(list(argv))
    except Usage as exc:
        return safe_text(str(exc).splitlines()[0], 200)
    except ParserExit:
        return "not a runnable command (help or version)"
    if getattr(args, "handler", None) is None:
        return "not a command"
    return None


def checkout_pin() -> dict[str, str] | None:
    """GR-70: the checkout's path, commit and the sha256 of ``git diff HEAD``; ``None`` without a checkout."""
    from agentprov.cli.package import _git
    from agentprov.jobs.manager import checkout_root

    root = checkout_root()
    if root is None:
        return None
    head = (_git(root, "rev-parse", "HEAD") or "").strip()
    diff = _git(root, "diff", "HEAD") or ""
    return {"checkout": str(root), "commit": head or "unknown",
            "diff": hashlib.sha256(diff.encode("utf-8", "surrogateescape")).hexdigest()}


@contextmanager
def _locked(path: Path, wait_s: float = 10.0) -> Iterator[None]:
    """The batch file's lock: the driver and ``start``/``resume``/``stop`` change the file one at a time."""
    from agentprov.io.locks import ResourceBusyError, ResourceLock

    deadline = time.monotonic() + wait_s
    while True:
        try:
            with ResourceLock(path.with_name(path.name + ".lock"), what="the batch file", command="batch"):
                yield
                return
        except ResourceBusyError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.05)


def _load(ctx: Context, batch_id: str) -> Any:
    from agentprov.jobs.batch import Batch
    from agentprov.jobs.record import batches_dir

    if not batch_id.replace("-", "").isalnum() or len(batch_id) > 64:
        raise CliUsageError("agentprov batch: not a batch id")
    batches = Batch.load_all(_home(ctx))
    hits = [b for b in batches if b.batch_id == batch_id] or [
        b for b in batches if len(batch_id) >= 8 and b.batch_id.startswith(batch_id)]
    if len(hits) != 1:
        raise CliUsageError(f"agentprov batch: no batch {safe_text(batch_id, 40)!r} (or the prefix is not unique)")
    assert hits[0].path is not None and hits[0].path.parent == batches_dir(_home(ctx))
    return hits[0]


def _driver_running(ctx: Context, batch: Any) -> bool:
    from agentprov.jobs.manager import find

    if batch.driver_job_id is None:
        return False
    job = find(_home(ctx), batch.driver_job_id)
    return job is not None and job.state == "running"


def _read_spec(spec: str | None, from_stdin: bool) -> dict[str, Any]:
    from agentprov.errors import IngestError
    from agentprov.ingest.limits import IngestLimits
    from agentprov.ingest.loaders import strict_json_loads

    if (spec is None) == (not from_stdin):
        raise CliUsageError("agentprov batch create: give SPEC.json or --stdin (one of them)")
    try:
        if from_stdin:
            data = sys.stdin.buffer.read(MAX_SPEC_BYTES + 1)
        else:
            with open(str(spec), "rb") as fh:
                data = fh.read(MAX_SPEC_BYTES + 1)
    except OSError as exc:
        raise CliUsageError(f"agentprov batch create: the step list cannot be read ({type(exc).__name__})") from None
    if len(data) > MAX_SPEC_BYTES:
        raise CliUsageError("agentprov batch create: the step list is larger than 4 MiB")
    try:
        doc = strict_json_loads(data.strip(), IngestLimits().replace(max_json_bytes=MAX_SPEC_BYTES, max_json_depth=8))
    except IngestError as exc:
        raise CliUsageError(f"agentprov batch create: the step list is not strict JSON ({exc.code})") from None
    if not isinstance(doc, dict) or not isinstance(doc.get("steps"), list) or not doc["steps"]:
        raise CliUsageError('agentprov batch create: the step list is {"steps": [...]} with at least one step')
    return doc


def _start(ctx: Context, batch: Any, confirm: bool, result: CommandResult) -> Any:
    from agentprov.jobs.manager import JobManager, JobRequest, new_job_id

    r2 = [i + 1 for i, s in enumerate(batch.steps) if s.state in ("pending", "held") and s.request.tier == "R2"]
    if r2 and not confirm:
        from agentprov.jobs.manager import SpawnRefused

        raise SpawnRefused(f"agentprov batch: step(s) {', '.join(map(str, r2[:20]))} reach the network or cost money "
                           "(R2): give --confirm-r2 to run them", "batch.r2_unconfirmed")
    if _driver_running(ctx, batch):
        raise CliUsageError("agentprov batch: its driver is already running")
    driver_id = new_job_id()
    assert batch.path is not None
    with _locked(batch.path):
        from agentprov.jobs.batch import Batch

        fresh = Batch.load(batch.path) or batch
        fresh.driver_job_id = driver_id
        fresh.r2_confirmed_by = driver_id if confirm else None
        fresh.stopped = None  # a stopped batch goes on from its pending steps
        for step in fresh.steps:
            if step.state == "held":
                step.state, step.note = "pending", ""
        fresh.save()
    job = JobManager(_home(ctx), environ=ctx.env).spawn(
        JobRequest(("batch", "run", fresh.batch_id), label=f"batch {fresh.label}"[:200]), job_id=driver_id)
    result.counters = {"drivers_started": 1}
    return job


def run_batch(ctx: Context) -> CommandResult:
    from agentprov.jobs.batch import Batch, BatchStep, check_step

    args = ctx.args
    result = CommandResult()
    action = args.batch_action
    home = _home(ctx)
    if action == "create":
        if not 1 <= args.concurrency <= 16:
            raise CliUsageError("agentprov batch create: --concurrency is 1 to 16")
        doc = _read_spec(args.spec, args.stdin)
        steps = []
        problems = []
        from agentprov.cli.jobs import _absolute, absolute_argv

        cwd = os.getcwd()
        for i, raw in enumerate(doc["steps"], 1):
            if isinstance(raw, dict) and raw.get("tool") is None:  # F-14: as jobs start, against this cwd
                raw = {**raw, **{k: [_absolute(v, "path", cwd) if isinstance(v, str) else v for v in raw[k]]
                                 for k in ("writes", "reads") if isinstance(raw.get(k), list)}}
                if isinstance(raw.get("argv"), list) and all(isinstance(a, str) for a in raw["argv"]):
                    raw["argv"] = absolute_argv(raw["argv"], cwd)
            try:
                step = BatchStep.from_json(raw if isinstance(raw, dict) else {})
            except ValueError as exc:
                problems.append(f"step {i}: {exc}")
                continue
            step.state, step.job_id, step.exit_code, step.note = "pending", None, None, ""
            step.recorded_tier = step.request.tier
            reason = check_step(step, validate_argv)
            if reason is not None:
                problems.append(f"step {i}: {reason}")
            steps.append(step)
        if problems:
            raise CliUsageError("agentprov batch create: refused:\n" + "\n".join(f"  {safe_text(p, 300)}"
                                                                                for p in problems[:50]))
        if any(step.request.queue_cpu is not None for step in steps):
            from agentprov.jobs.manager import check_queue_platform

            check_queue_platform()  # D-1064: refused at create, not step by step under the driver
        go_on = args.continue_on_failure
        if go_on is None:
            from agentprov import settings

            try:
                go_on = settings.items("jobs.", home=home).get("jobs.continue_on_failure") is True
            except settings.SettingsError as exc:
                raise CliUsageError(f"agentprov batch create: {exc}") from None
        batch = Batch.new(home, args.label[:200], steps, concurrency=args.concurrency, continue_on_failure=go_on,
                          pin=checkout_pin())
        if args.format == "json":
            result.payload = _payload(batch.to_json())
        else:
            result.output(f"created {batch.batch_id}: {len(steps)} step(s) (start it with 'agentprov batch start')")
        result.counters = {"steps": len(steps)}
    elif action in ("start", "resume"):
        batch = _load(ctx, args.batch_id)
        if batch.finished:
            raise CliUsageError("agentprov batch: every step has ended")
        job = _start(ctx, batch, args.confirm_r2, result)
        if args.format == "json":
            result.payload = _payload({"batch_id": batch.batch_id, "driver_job_id": job.job_id})
        else:
            result.output(f"batch {batch.batch_id}: driver job {job.job_id}")
    elif action == "run":
        _run_driver(ctx, args, result)
    elif action == "stop":
        _stop(ctx, args, result)
    elif action == "list":
        batches = Batch.load_all(home)
        rows = [{"batch_id": b.batch_id, "label": b.label, "created": b.created, "counts": b.counts(),
                 "finished": b.finished, "driver_job_id": b.driver_job_id, "stopped": b.stopped} for b in batches]
        if args.format == "json":
            result.payload = _payload({"format": LIST_FORMAT, "batches": rows})
        else:
            for r in rows:
                result.output(safe_text(f"{r['batch_id']}  {r['label']}  {r['counts']}", 300))
    elif action == "show":
        batch = _load(ctx, args.batch_id)
        if args.format == "json":
            result.payload = _payload({**batch.to_json(), "driver_running": _driver_running(ctx, batch)})
        else:
            result.output(safe_text(f"{batch.batch_id}  {batch.label}  {batch.counts()}", 300))
            for i, s in enumerate(batch.steps, 1):
                result.output(safe_text(f"  {i:>3}. {s.state:<8} {' '.join(s.request.argv)[:120]}  {s.note}", 400))
    return result


def _stop(ctx: Context, args: argparse.Namespace, result: CommandResult) -> None:
    """``batch stop``: under the batch file's lock (so no driver tick is half done), mark the batch stopped, stop its
    driver and, with ``--steps``, every running step job of the batch; then wait for them and record how they ended."""
    from agentprov.jobs.batch import STOPPED_NOTE, Batch, advance
    from agentprov.jobs.manager import JobManager, find
    from agentprov.jobs.record import list_jobs

    if not 0 <= args.wait <= 600:
        raise CliUsageError("agentprov batch stop: --wait is 0 to 600 seconds")
    home = _home(ctx)
    batch = _load(ctx, args.batch_id)
    assert batch.path is not None
    manager = JobManager(home, environ=ctx.env)
    signalled: list[str] = []
    unsignalled: list[str] = []
    with _locked(batch.path):
        fresh = Batch.load(batch.path) or batch
        fresh.stopped = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        driver = find(home, fresh.driver_job_id) if fresh.driver_job_id else None
        driver_running = driver is not None and driver.state == "running"
        driver_stopped = bool(driver is not None and driver_running and manager.stop(driver))
        if args.steps:
            listed = {s.job_id: s for s in fresh.steps if s.state == "running" and s.job_id}
            # a step job the file does not list yet (a driver killed between its spawn and its save) is found by the
            # batch id every step job records
            jobs = [j for j in list_jobs(home) if j.state == "running" and j.job_id != fresh.driver_job_id and (
                j.job_id in listed or j.record.get("batch_id") == fresh.batch_id)]
            for job in jobs:
                if manager.stop(job):
                    signalled.append(job.job_id)
                    if job.job_id in listed:
                        listed[job.job_id].note = STOPPED_NOTE
                else:
                    unsignalled.append(job.job_id)
        fresh.save()
    waiting = [*signalled, *([driver.job_id] if driver is not None and driver_stopped else [])]
    deadline = time.monotonic() + args.wait
    while waiting and time.monotonic() < deadline:
        time.sleep(0.1)
        waiting = [jid for jid in waiting if (seen := find(home, jid)) is not None and seen.state == "running"]
    if args.steps:
        with _locked(batch.path):  # record the steps that ended (a stopped batch starts nothing)
            loaded = Batch.load(batch.path)
            if loaded is not None and loaded.stopped is not None:
                advance(loaded, manager, validate=validate_argv, pin_now=checkout_pin, driver_job_id=None)
    driver_text = "stopped" if driver_stopped else "not signalled" if driver_running else "not running"
    for jid in unsignalled:
        result.failures.append({"subject": {"job": jid}, "stage": "stop", "code": "batch.stop.unsignalled",
                                "detail": "the process identity did not match, or this platform has no graceful stop"})
        result.error(f"batch {fresh.batch_id}: step job {jid} could not be signalled; stop it with "
                     "'agentprov jobs stop' or 'agentprov jobs kill'")
    if unsignalled:
        result.exit_code = 1
    result.counters = {"steps_stopped": len(signalled), "steps_unsignalled": len(unsignalled),
                       "still_running": len(waiting)}
    if args.format == "json":
        result.payload = _payload({"format": STOP_FORMAT, "batch_id": fresh.batch_id,
                                   "driver_job_id": fresh.driver_job_id, "driver": driver_text,
                                   "steps_stopped": signalled, "steps_unsignalled": unsignalled,
                                   "still_running": waiting, "stopped": fresh.stopped})
    else:
        result.info(f"batch {fresh.batch_id}: driver {driver_text}; {len(signalled)} step(s) stopped"
                    + (f"; {len(waiting)} job(s) still ending" if waiting else "")
                    + ("" if args.steps else " (the steps it started keep running; --steps stops them too)"))


def _run_driver(ctx: Context, args: argparse.Namespace, result: CommandResult) -> None:
    """The driver loop: tick (lock, load, advance, save) until every step has ended or a SIGTERM arrives."""
    import os

    from agentprov.jobs.batch import Batch, advance
    from agentprov.jobs.manager import JobManager

    batch = _load(ctx, args.batch_id)
    assert batch.path is not None
    me = os.environ.get("AGENTPROV_JOB_ID") or None
    if me is None:  # a foreground driver: started by hand, so a stopped batch goes on (as after resume)
        with _locked(batch.path):
            fresh = Batch.load(batch.path) or batch
            fresh.stopped = None
            if args.confirm_r2:  # confirmed by its own option
                me = f"foreground-{os.getpid()}"
                fresh.driver_job_id, fresh.r2_confirmed_by = None, me
            fresh.save()
    stop = {"now": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.__setitem__("now", True))
    manager = JobManager(_home(ctx), environ=ctx.env)
    interval = min(60.0, max(0.2, args.interval))
    ticks = started = 0
    current: Batch = batch
    while not stop["now"]:
        with _locked(batch.path):
            loaded = Batch.load(batch.path)
            if loaded is None:
                raise CliUsageError("agentprov batch run: the batch file is no longer readable")
            current = loaded
            if stop["now"] or current.stopped is not None:  # `batch stop` holds this lock while it signals
                stop["now"] = True
                break
            started += len(advance(current, manager, validate=validate_argv, pin_now=checkout_pin, driver_job_id=me))
        ticks += 1
        if current.finished:
            break
        waiting = [s for s in current.steps if s.state in ("pending", "held")]
        if waiting and waiting[0].state == "held" and not any(s.state == "running" for s in current.steps):
            result.notices.append("batch: held at an R2 step; resume with 'agentprov batch resume ID --confirm-r2'")
            break  # nothing runs and nothing can start under this driver
        time.sleep(interval)
    result.counters = {"ticks": ticks, "steps_started": started, **current.counts()}
    if stop["now"]:
        result.info(f"batch {current.batch_id}: the driver stopped; "
                    + ("'agentprov batch resume' goes on from its pending steps" if current.stopped is not None
                       else "its running steps continue"))
        result.exit_code = 130
    else:
        result.info(f"batch {current.batch_id}: every step has ended {current.counts()}")
