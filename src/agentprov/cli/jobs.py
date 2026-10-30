"""``agentprov jobs``: detached jobs that outlive the command that started them (D-704; GUI design §4; reverse CLI
parity D-700).

    agentprov jobs start [--label L] [--writes DIR]... [--reads DIR]... [--slot NAME] [--with-control-file]
                         [--queue-cpu N] [--progress-level status|steps] [--tool tools/X.py] [--format] -- ARGV...
    agentprov jobs list [--state running|ended|all] [--format text|json]
    agentprov jobs show ID [--format text|json]
    agentprov jobs follow ID [--timeout S] [--log]
    agentprov jobs stop ID | kill ID --yes | drain ID | resume ID
    agentprov jobs prune [--keep N] [--max-age-days D] [--yes]

A job is ``agentprov ARGV`` (or one ``tools/<name>.py`` of this checkout with ``--tool``) under a supervisor that
records its real exit code; its directory is ``$AGENTPROV_HOME/jobs/<id>/`` (:mod:`agentprov.jobs`). ``ID`` is a job
id or a unique prefix of at least 8 characters. ``start`` refuses a second writer of a corpus and a second job of a
slot (exit 4). Everything a job prints is escaped before it is shown here.
"""

from __future__ import annotations

import argparse
import functools
import json
import os
import time
from collections.abc import Sequence
from typing import Any, Final

from agentprov.cli.common import CliUsageError, CommandResult, Context, safe_text

LIST_FORMAT = "agentprov-jobs-list/0.1"


def register(sub: Any, shared: argparse.ArgumentParser) -> None:
    p = sub.add_parser("jobs", parents=[shared], help="start, list, follow, stop or prune detached jobs",
                       description=__doc__.splitlines()[0], allow_abbrev=False)
    p.set_defaults(command="jobs", handler=run_jobs, feedback=False)
    actions = p.add_subparsers(dest="jobs_action", metavar="ACTION", required=True)
    s = actions.add_parser("start", parents=[shared], help="start ARGV (after --) as a detached job",
                           allow_abbrev=False)
    s.add_argument("--label", default="", metavar="TEXT", help="a label shown in lists")
    s.add_argument("--writes", action="append", default=[], metavar="DIR", help="a corpus the job writes (one writer "
                   "per corpus; repeatable)")
    s.add_argument("--reads", action="append", default=[], metavar="DIR", help="a corpus the job reads (repeatable)")
    s.add_argument("--slot", choices=["network", "backends"], help="a global slot (one job at a time)")
    s.add_argument("--with-control-file", action="store_true", help="give the job a control file (drain, D-394)")
    s.add_argument("--queue-cpu", type=int, metavar="N", help="run through the machine-wide job queue reserving N CPUs")
    s.add_argument("--progress-level", choices=["status", "steps"], default="status")
    s.add_argument("--tool", metavar="tools/NAME.py", help="run one repository tool of this checkout instead of "
                   "agentprov (ARGV are its arguments)")
    s.add_argument("--note", action="append", default=[], metavar="TEXT", help="a note recorded with the job")
    s.add_argument("--meta", action="append", default=[], metavar="KEY=VALUE",
                   help="a fact recorded with the job (KEY [a-z_][a-z0-9_]*; VALUE a JSON scalar or text; repeatable)")
    s.add_argument("--format", choices=["text", "json"], default="text")
    s.add_argument("argv", nargs=argparse.REMAINDER, metavar="-- ARGV", help="the agentprov arguments of the job")
    ls = actions.add_parser("list", parents=[shared], help="the jobs, newest first", allow_abbrev=False)
    ls.add_argument("--state", choices=["running", "ended", "all"], default="all")
    ls.add_argument("--format", choices=["text", "json"], default="text")
    sh = actions.add_parser("show", parents=[shared], help="one job, with the tails of its output", allow_abbrev=False)
    sh.add_argument("job_id", metavar="ID")
    sh.add_argument("--format", choices=["text", "json"], default="text")
    f = actions.add_parser("follow", parents=[shared], help="print a job's progress (or log) lines until it ends",
                           allow_abbrev=False)
    f.add_argument("job_id", metavar="ID")
    f.add_argument("--timeout", type=float, default=0.0, metavar="S", help="stop following after S seconds (0: never)")
    f.add_argument("--log", action="store_true", help="the job's log records (log.jsonl) instead of its progress")
    for name, help_text in (("stop", "a graceful stop (SIGTERM to the job's CLI)"),
                            ("drain", "finish the units in flight, start no new ones (needs --with-control-file)"),
                            ("resume", "start the job's request again (the CLI's resume rules decide what is redone)")):
        a = actions.add_parser(name, parents=[shared], help=help_text, allow_abbrev=False)
        a.add_argument("job_id", metavar="ID")
        if name == "resume":
            a.add_argument("--format", choices=["text", "json"], default="text")
    k = actions.add_parser("kill", parents=[shared], help="force kill the job's whole process tree", allow_abbrev=False)
    k.add_argument("job_id", metavar="ID")
    k.add_argument("--yes", action="store_true", help="confirm (a forced kill can leave a stale lock)")
    pr = actions.add_parser("prune", parents=[shared], help="delete old ended jobs (lists them without --yes)",
                            allow_abbrev=False)
    pr.add_argument("--keep", type=int, metavar="N", help="keep the newest N ended jobs (default: the setting "
                    "jobs.retention, else 200)")
    pr.add_argument("--max-age-days", type=int, metavar="D", help="and none older than D days (default: the setting "
                    "jobs.retention_days, else 90)")
    pr.add_argument("--yes", action="store_true", help="delete them")
    pr.add_argument("--format", choices=["text", "json"], default="text")


def _meta(items: list[str]) -> dict[str, str | int | float | bool]:
    """``--meta KEY=VALUE`` pairs: a JSON scalar where VALUE parses as one, else the text (at most 200 characters)."""
    import re

    out: dict[str, str | int | float | bool] = {}
    for item in items:
        key, sep, raw = item.partition("=")
        if not sep or not re.fullmatch(r"[a-z_][a-z0-9_]{0,39}", key) or len(raw) > 200 or len(out) >= 32:
            raise CliUsageError("agentprov jobs start: --meta is KEY=VALUE (KEY [a-z_][a-z0-9_]*, at most 32)")
        try:
            value = json.loads(raw)
        except ValueError:
            value = raw
        out[key] = value if isinstance(value, str | int | float | bool) and value == value else raw
    return out


def _payload(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"


def _line(job: Any) -> str:
    code = "" if job.exit_code is None else f" exit {job.exit_code}"
    return safe_text(f"{job.job_id}  {job.state}{code}  {job.command}  {job.record.get('label') or ''}", 300)


def _job(ctx: Context, job_id: str) -> Any:
    from agentprov.jobs.manager import find

    job = find(_home(ctx), job_id)
    if job is None:
        raise CliUsageError(f"agentprov jobs: no job {safe_text(job_id, 40)!r} (or the prefix is not unique)")
    return job


def _home(ctx: Context) -> Any:
    from agentprov.cli.live.envs import agentprov_home

    return agentprov_home(ctx.env)


def _manager(ctx: Context) -> Any:
    from agentprov.jobs.manager import JobManager

    return JobManager(_home(ctx), environ=ctx.env)


#: option metavars that name a file or directory (D-704 amendment, F-14); ``ROLE=PATH`` style pairs carry one after '='
_PATH_METAVARS: Final = frozenset({"PATH", "DIR", "FILE", "TREE", "SRC", "NEW", "OUT", "SPEC.toml", "PLAN.toml",
                                   "SCRIPT.json", "SPEC.json", "CARD.md", "release.toml", "RESPONSE.json"})
_PAIR_METAVARS: Final = frozenset({"ROLE=PATH", "NAME=PATH"})
#: positionals that may name a path: ``inspect TARGET`` is an execution id, a file or a corpus root
_MAYBE_PATH_METAVARS: Final = frozenset({"TARGET"})
_NO_VALUE: Final = (argparse._StoreTrueAction, argparse._StoreFalseAction, argparse._CountAction,
                    argparse._StoreConstAction, argparse._AppendConstAction, argparse._HelpAction,
                    argparse._VersionAction, argparse.BooleanOptionalAction)


def _absolute(value: str, kind: str, cwd: str) -> str:
    if kind == "pair":
        name, sep, path = value.partition("=")
        return f"{name}={_absolute(path, 'path', cwd)}" if sep else value
    if not value or value == "-" or "://" in value:
        return value
    expanded = os.path.expanduser(value)
    return expanded if os.path.isabs(expanded) else os.path.normpath(os.path.join(cwd, expanded))


def _looks_like_path(value: str, cwd: str) -> bool:
    """A ``TARGET`` that is a path rather than an execution id: it exists under ``cwd``, has a separator, or starts
    with ``.`` or ``~`` (an execution id is ``ex_…`` and has none of these)."""
    return (os.sep in value or "/" in value or value.startswith((".", "~"))
            or os.path.lexists(os.path.join(cwd, value)))


@functools.cache
def _parser() -> argparse.ArgumentParser:
    from agentprov.cli.main import build_parser

    return build_parser()


def absolute_argv(argv: Sequence[str], cwd: str | None = None) -> list[str]:
    """``argv`` with every relative path option value made absolute against ``cwd`` (default: this process's), as a
    shell user means it (D-704 amendment, F-14): a job runs in its own folder, where a relative path names nothing.

    The options are those of the subcommand ``argv`` names whose metavar names a path (``--corpus DIR``,
    ``--out PATH``, ``--plan PLAN.toml``, ``--input-file ROLE=PATH``, …), as ``--opt VALUE[ VALUE…]`` or
    ``--opt=VALUE``; ``-`` (stdin) and URLs are kept. Positionals are rewritten too, from the parser's own metadata:
    a path metavar (``validate FILE…``) always, ``inspect TARGET`` when it is a path (:func:`_looks_like_path`), never
    an execution id."""
    cwd = os.getcwd() if cwd is None else cwd
    node: argparse.ArgumentParser = _parser()
    i = 0
    while True:
        subs = [a for a in node._actions if isinstance(a, argparse._SubParsersAction)]
        if not subs or i >= len(argv) or argv[i] not in subs[0].choices:
            break
        node = subs[0].choices[argv[i]]
        i += 1
    kinds: dict[str, tuple[str, Any]] = {}
    arity: dict[str, int | None] = {}  # option string -> values it takes (None: one or more)
    positionals: list[argparse.Action] = []
    for action in node._actions:
        if isinstance(action, argparse._SubParsersAction):
            continue
        if not action.option_strings:
            positionals.append(action)
            continue
        metavar = str(action.metavar) if action.metavar else ""
        kind = "path" if metavar in _PATH_METAVARS else "pair" if metavar in _PAIR_METAVARS else None
        if kind is not None:
            kinds.update({opt: (kind, action.nargs) for opt in action.option_strings})
        takes = 0 if isinstance(action, _NO_VALUE) or action.nargs == 0 else (
            None if action.nargs in ("+", "*") or (isinstance(action.nargs, int) and action.nargs > 1) else 1)
        arity.update(dict.fromkeys(action.option_strings, takes))
    out = list(argv)
    free: list[int] = []  # the positional tokens, in order
    j = i
    while j < len(out):
        token = out[j]
        if token == "--":
            free.extend(range(j + 1, len(out)))
            break
        if token.startswith("-") and token != "-":
            option, eq, _value = token.partition("=")
            takes = arity.get(option, 1)
            j += 1
            if not eq:
                while takes != 0 and j < len(out) and (not out[j].startswith("-") or out[j] == "-"):
                    j += 1
                    if takes == 1:
                        break
            continue
        free.append(j)
        j += 1
    for action in positionals:
        take = len(free) if action.nargs in ("*", "+", argparse.REMAINDER) else (0 if not free else 1)
        mine, free = free[:take], free[take:]
        metavar = str(action.metavar) if action.metavar else ""
        for k in mine:
            if metavar in _PATH_METAVARS or (metavar in _MAYBE_PATH_METAVARS and _looks_like_path(out[k], cwd)):
                out[k] = _absolute(out[k], "path", cwd)
    j = i
    while j < len(out):
        if out[j] == "--":
            break
        option, eq, value = out[j].partition("=")
        if option in kinds and option.startswith("-"):
            kind, nargs = kinds[option]
            if eq:
                out[j] = f"{option}={_absolute(value, kind, cwd)}"
            else:
                many = nargs in ("+", "*") or (isinstance(nargs, int) and nargs > 1)
                k = j + 1
                while k < len(out) and (not out[k].startswith("-") or out[k] == "-"):
                    out[k] = _absolute(out[k], kind, cwd)
                    k += 1
                    if not many:
                        break
                j = k
                continue
        j += 1
    return out


def run_jobs(ctx: Context) -> CommandResult:
    from agentprov.jobs.manager import JobRequest
    from agentprov.jobs.record import list_jobs, tail_bytes

    args = ctx.args
    result = CommandResult()
    action = args.jobs_action
    if action == "start":
        argv = list(args.argv[1:] if args.argv[:1] == ["--"] else args.argv)
        if args.queue_cpu is not None and not 1 <= args.queue_cpu <= 256:
            raise CliUsageError("agentprov jobs start: --queue-cpu is 1 to 256")
        cwd = os.getcwd()
        if args.tool is None:  # F-14: relative paths mean the caller's cwd, recorded absolute (a tool's are its own)
            argv = absolute_argv(argv, cwd)
        writes = tuple(_absolute(w, "path", cwd) for w in args.writes)
        reads = tuple(_absolute(r, "path", cwd) for r in args.reads)
        req = JobRequest(tuple(argv), args.label, writes, reads, args.slot, tuple(args.note),
                         args.with_control_file, args.queue_cpu, args.progress_level, args.tool,
                         extra=_meta(args.meta))
        job = _manager(ctx).spawn(req)
        doc = job.to_json()
        if args.format == "json":
            result.payload = _payload(doc)
        else:
            result.output(f"started {job.job_id} ({safe_text(job.command, 80)}, tier {req.tier}): {job.directory}")
        result.counters = {"jobs_started": 1}
    elif action == "list":
        jobs = [j for j in list_jobs(_home(ctx)) if args.state == "all" or j.state == args.state
                or (args.state == "ended" and j.state == "unobserved")]
        if args.format == "json":
            result.payload = _payload({"format": LIST_FORMAT, "jobs": [j.to_json() for j in jobs]})
        else:
            for job in jobs:
                result.output(_line(job))
        result.counters = {"jobs": len(jobs)}
    elif action == "show":
        job = _job(ctx, args.job_id)
        doc = {**job.to_json(), "stderr_tail": tail_bytes(job.file("stderr.txt"), 8192).decode("utf-8", "replace"),
               "stdout_tail": tail_bytes(job.file("stdout.txt"), 8192).decode("utf-8", "replace")}
        if args.format == "json":
            result.payload = _payload(doc)
        else:
            result.output(_line(job))
            for name in ("stderr_tail", "stdout_tail"):
                for text in doc[name].splitlines()[-20:]:
                    result.output(f"  {name[:6]}: {safe_text(text, 500)}")
    elif action == "follow":
        _follow(ctx, args, result)
    elif action in ("stop", "drain", "kill"):
        job = _job(ctx, args.job_id)
        if job.state != "running":
            raise CliUsageError(f"agentprov jobs {action}: the job is not running ({job.state})")
        manager = _manager(ctx)
        if action == "kill" and not args.yes:
            raise CliUsageError("agentprov jobs kill: give --yes (a forced kill can leave a stale lock)")
        done = (manager.stop(job) if action == "stop" else manager.kill(job) if action == "kill"
                else manager.request(job, "drain"))
        if not done:
            from agentprov.jobs.manager import SpawnRefused

            why = ("the job has no control file" if action == "drain" else
                   "the process identity did not match, or this platform has no graceful stop")
            raise SpawnRefused(f"agentprov jobs {action}: not done: {why}", "jobs.control.refused")
        result.info(f"jobs: {action} sent to {job.job_id}")
    elif action == "resume":
        job = _job(ctx, args.job_id)
        if job.state == "running":
            raise CliUsageError("agentprov jobs resume: the job is still running")
        new = _manager(ctx).resume(job)
        if args.format == "json":
            result.payload = _payload(new.to_json())
        else:
            result.output(f"started {new.job_id} (resume of {job.job_id})")
    elif action == "prune":
        from agentprov import settings

        manager = _manager(ctx)
        try:
            stored = settings.items("jobs.", home=manager.home)
        except settings.SettingsError as exc:
            raise CliUsageError(f"agentprov jobs prune: {exc}") from None
        retention, days = stored.get("jobs.retention", 200), stored.get("jobs.retention_days", 90)
        if args.keep is None:
            args.keep = retention if isinstance(retention, int) else 200  # the schema stores an int
        if args.max_age_days is None:
            args.max_age_days = days if isinstance(days, int) else 90
        if args.keep < 0 or args.max_age_days < 1:
            raise CliUsageError("agentprov jobs prune: --keep >= 0 and --max-age-days >= 1")
        candidates = manager.prune_candidates(args.keep, args.max_age_days)
        if args.format == "json":
            result.payload = _payload({"format": LIST_FORMAT, "jobs": [j.to_json() for j in candidates],
                                       "deleted": bool(args.yes)})
        else:
            for job in candidates:
                result.output(_line(job))
        if args.yes:
            result.counters = {"jobs_deleted": manager.delete(candidates)}
        else:
            result.counters = {"jobs_to_delete": len(candidates)}
            result.notices.append("prune: nothing deleted without --yes")
    return result


def _follow(ctx: Context, args: argparse.Namespace, result: CommandResult) -> None:
    from agentprov.jobs.follow import TailReader
    from agentprov.jobs.record import load_job

    job = _job(ctx, args.job_id)
    reader = TailReader(job.file("log.jsonl" if args.log else "progress.jsonl"))
    deadline = time.monotonic() + args.timeout if args.timeout > 0 else None
    while True:
        for obj in reader.read():
            ctx.stdout.write(json.dumps(obj, sort_keys=True, ensure_ascii=True) + "\n")
        ctx.stdout.flush()
        job = load_job(job.directory) or job
        if job.state != "running" or (deadline is not None and time.monotonic() > deadline):
            break
        time.sleep(0.5)
    for obj in reader.read():
        ctx.stdout.write(json.dumps(obj, sort_keys=True, ensure_ascii=True) + "\n")
    result.info(f"jobs: {job.job_id} is {job.state}" + ("" if job.exit_code is None else f" (exit {job.exit_code})"))
