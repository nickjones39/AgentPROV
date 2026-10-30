"""``agentprov`` command-line entry point (docs/architecture MN N.1; M.1.2).

``main(argv) -> int`` builds the parser, runs the startup self-check (M.5.2(8)), dispatches, and maps exceptions to
the exit codes of N.1.3. It never calls ``sys.exit``; the console script and ``python -m agentprov`` do that with the
returned code. stdout carries only machine output (the ``--json`` summary, or the payload of ``info``); progress,
notices and errors go to stderr (N.1.4).

Commands in this build: ``info`` (alias ``sources``), ``validate``, ``import`` (alias ``convert``), ``fetch``, ``run``,
``backends`` (``build``), ``models`` (D-691), ``migrate`` (gates G0, A, B, D, E), ``render``, ``inspect``, ``purge``, ``stats``, ``package``, ``derive``, ``recompute`` and ``verify``. The
other commands of N.2 arrive with the layers they drive and are not registered as stubs.
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

from agentprov.cli import backends, checks, derive, fetch, import_, info, migrate, models, run
from agentprov.cli import inspect as inspect_cmd
from agentprov.cli import package as package_cmd
from agentprov.cli import purge as purge_cmd
from agentprov.cli import render as render_cmd
from agentprov.cli import stats as stats_cmd
from agentprov.cli import estimate as estimate_cmd  # D-701
from agentprov.cli import batch as batch_cmd  # D-704
from agentprov.cli import devrun as devrun_cmd  # D-705
from agentprov.cli import jobs as jobs_cmd  # D-704
from agentprov.cli import keys as keys_cmd  # D-702
from agentprov.cli import prices as prices_cmd  # D-701
from agentprov.cli import settings_cmd  # D-703
from agentprov.cli import verify as verify_cmd
from agentprov.cli.common import (
    CliArgumentParser,
    CliUsageError,
    CommandResult,
    Context,
    Interrupted,
    ParserExit,
    Refusal,
    UnsupportedCapability,
    add_global_options,
    apply_global_defaults,
    build_summary,
    configure_logging,
    exit_code_for,
    format_exception_safe,
    install_signal_handlers,
    normalised_options,
    outcome_for,
    render_refusal,
    safe_text,
    startup_self_check,
    write_stdout_bytes,
)
from agentprov.errors import AgentProvError
from agentprov.io.atomic import atomic_write_bytes
from agentprov.io.canonical import jcs_bytes
from agentprov.progress import NULL_PROGRESS, ProgressEvent
from agentprov.versions import VERSIONS, __version__

__all__ = ["COMMANDS", "build_parser", "main"]

#: The commands registered in this build (a subset of the fifteen of MN N.2; the rest arrive with their layers).
COMMANDS = (
    "info", "validate", "import", "fetch", "run", "backends", "migrate", "render", "inspect", "purge", "stats", "package",
    "derive", "recompute", "verify", "models", "settings", "keys", "prices", "estimate", "jobs", "batch", "devrun",
)

_LOG = logging.getLogger("agentprov.cli")


def build_parser() -> CliArgumentParser:
    """The root parser: shared options on the root and on every subcommand (N.1.1(3))."""
    shared = CliArgumentParser(add_help=False)
    add_global_options(shared)
    parser = CliArgumentParser(
        prog="agentprov",
        description="AgentPROV: execution provenance for LLM-agent security research.",
        parents=[shared],
        allow_abbrev=False,
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND", parser_class=CliArgumentParser)
    info.register(sub, shared)
    checks.register(sub, shared)
    import_.register(sub, shared)
    fetch.register(sub, shared)
    run.register(sub, shared)
    models.register(sub, shared)
    backends.register(sub, shared)
    migrate.register(sub, shared)
    render_cmd.register(sub, shared)
    inspect_cmd.register(sub, shared)
    purge_cmd.register(sub, shared)
    stats_cmd.register(sub, shared)
    package_cmd.register(sub, shared)
    derive.register(sub, shared)
    verify_cmd.register(sub, shared)
    settings_cmd.register(sub, shared)
    keys_cmd.register(sub, shared)
    prices_cmd.register(sub, shared)
    estimate_cmd.register(sub, shared)
    jobs_cmd.register(sub, shared)
    batch_cmd.register(sub, shared)
    devrun_cmd.register(sub, shared)
    return parser


# --------------------------------------------------------------------------------------------------------------
# Result handling
# --------------------------------------------------------------------------------------------------------------


#: The reason lines a refusal keeps in ``summary.refusal`` (the last one names any overflow; re-check RC-18).
_REFUSAL_LINES: Final = 16


def _result_from_exception(exc: BaseException, args: Any) -> CommandResult:
    """Map an exception to a result: its exit code (N.1.3), its message, and a refusal when it carries one."""
    code = exit_code_for(exc)
    result = CommandResult(exit_code=code, dry_run=bool(getattr(args, "dry_run", False)))
    verbose = bool(getattr(args, "verbose", 0))
    if isinstance(exc, KeyboardInterrupt):
        result.error("agentprov: interrupted; in-flight work was sealed or rolled back")
        result.notices.append(f"interrupted ({exc.signal_name})" if isinstance(exc, Interrupted) else "interrupted")
    elif isinstance(exc, UnsupportedCapability):
        if exc.refusal is not None:
            result.refusal = exc.refusal
            details = "agentprov info" if exc.refusal.mode != "info" else None
            for line in render_refusal(exc.refusal, details=details):
                result.error(line)
        else:
            result.error(f"agentprov: unsupported: {safe_text(str(exc), 1000)}")
        result.notices.append(f"error {exc.code}: {safe_text(str(exc), 300)}")
    elif isinstance(exc, CliUsageError):
        for line in str(exc).splitlines():
            result.error(safe_text(line, 1000))
        result.notices.append(f"error {exc.code}: {safe_text(str(exc).splitlines()[0] if str(exc) else '', 300)}")
    elif isinstance(exc, AgentProvError) and code != 70:
        # re-check RC-18: a reason of several lines (the drift report) is printed line by line, never as escapes, and
        # the notice carries its first line whole
        lines = [line for line in str(exc).splitlines() if line] or [""]
        result.error(f"agentprov: error [{exc.code}]: {safe_text(lines[0], 1000)}")
        for line in lines[1:]:
            result.error(f"  {safe_text(line, 1000)}")
        result.notices.append(f"error {exc.code}: {safe_text(lines[0], 1000)}")
        if code == 4:  # P-3: a refused precondition (outcome "refused") names its code and reason in summary.refusal
            command = str(getattr(args, "command", "") or "agentprov")
            shown = [safe_text(line, 300) for line in lines[:_REFUSAL_LINES]]
            if len(lines) > _REFUSAL_LINES:  # RC-18: never drop reason lines silently
                shown[-1] = f"... and {len(lines) - _REFUSAL_LINES + 1} more line(s); see stderr"
            result.refusal = Refusal(id=command, mode=command, status=str(exc.code), lines=tuple(shown))
    else:
        what = type(exc).__name__
        result.error(f"agentprov: internal error: {what}: {safe_text(str(exc), 300)} (exit 70)")
        if verbose:
            for line in format_exception_safe(exc, frames=True).splitlines():
                result.error(f"  {line}")
        else:
            result.error("  rerun with -v for the traceback frames")
        result.notices.append(f"internal error: {what}")
    return result


def _print_messages(result: CommandResult, args: Any, show_info: bool) -> None:
    for kind, text in result.messages:
        if kind == "info" and not show_info:
            continue
        sys.stderr.write(text + "\n")
    sys.stderr.flush()


def _write_summary(args: Any, command: str, exit_code: int, result: CommandResult) -> None:
    if not (args.json or args.summary_json):
        return
    summary = build_summary(
        command=command,
        exit_code=exit_code,
        result=result,
        options=normalised_options(args),
        max_listed=args.max_listed,
    )
    data = jcs_bytes(summary) + b"\n"
    if args.summary_json:
        atomic_write_bytes(Path(args.summary_json), data)
    if args.json:
        write_stdout_bytes(sys.stdout, data)


def _preflight_outputs(args: Any) -> None:
    """Fail early (exit 2) when an output path cannot work: writing it later would lose the result. An output inside a
    sealed corpus is refused (exit 4, H.1.5(2)): it would be a stray file that fails ``verify`` (CC-22)."""
    from agentprov.corpus.layout import assert_writable

    for flag, value in (("--summary-json", args.summary_json), ("--log-file", args.log_file),
                        ("--progress-file", args.progress_file), ("--control-file", args.control_file)):
        if value is None:
            continue
        parent = Path(value).parent
        if not parent.is_dir():
            raise CliUsageError(f"agentprov: {flag}: the directory {safe_text(str(parent), 200)!r} does not exist")
        if flag == "--control-file":
            continue  # read, never written
        try:
            assert_writable(Path(value))
        except AgentProvError:
            args.summary_json = None  # the refusal's own summary must not land there either
            raise


def _run_header(command: str, args: Any) -> dict[str, Any]:
    """The ``run`` header fields of ``agentprov-progress/0.2`` (D-393) that the CLI knows before the command starts.
    Paths are escaped and home-redacted; nothing from the options that could carry a value is copied."""
    header: dict[str, Any] = {"command": command, "dry_run": bool(getattr(args, "dry_run", False)),
                              "mode": "release" if getattr(args, "release", False) else "dev"}
    jobs = getattr(args, "jobs", None)
    if isinstance(jobs, int) and not isinstance(jobs, bool):
        header["jobs"] = jobs
    corpus = getattr(args, "corpus", None)
    if isinstance(corpus, list):
        corpus = corpus[0] if len(corpus) == 1 else None
    if isinstance(corpus, str):
        header["corpus_root"] = safe_text(os.path.abspath(corpus), 400)
    if args.summary_json:
        header["summary"] = safe_text(os.path.abspath(args.summary_json), 400)
    return header


# --------------------------------------------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI; returns the exit code of N.1.3. Never calls ``sys.exit``."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    try:
        args = parser.parse_args(arguments)
        apply_global_defaults(args)
        if args.command is None:
            raise CliUsageError("agentprov: a command is required\n" + parser.format_usage().rstrip())
    except ParserExit as stop:
        return stop.status
    except CliUsageError as exc:
        for line in str(exc).splitlines():
            sys.stderr.write(safe_text(line, 1000) + "\n")
        return exc.exit_code

    from agentprov.cli.feedback import make_sink, resolve_feedback_config

    command: str = args.command
    result = CommandResult()
    exit_code = 0
    sink = None
    watcher = None
    log_handle = None
    show_info = True
    with install_signal_handlers():
        try:
            _preflight_outputs(args)
            try:
                log_handle = configure_logging(
                    logging.DEBUG if args.verbose else logging.WARNING if args.quiet else logging.INFO,
                    args.log_format,
                    args.log_file,
                    log_content=args.log_content,
                )
            except OSError:
                raise CliUsageError("agentprov: --log-file cannot be opened") from None
            config = resolve_feedback_config(
                progress=args.progress,
                progress_format=args.progress_format,
                progress_file=args.progress_file,
                show_content=args.show_content,
                content_chars=args.content_chars,
                quiet=args.quiet,
                env=os.environ,
                stream=sys.stderr,
                progress_interval=args.progress_interval,
                progress_max_bytes=args.progress_max_bytes,
                header=_run_header(command, args),
            )
            show_info = config.level != "off"
            startup_self_check()
            # a command without live feedback still honours --progress-file (start and end lines, and its own events)
            sink = make_sink(config, sys.stderr, stderr=bool(args.feedback))
            if sink is not None and not args.feedback:
                sink.emit(ProgressEvent("start", fields={"command": command}))
            ctx = Context(args=args, progress=sink if sink is not None else NULL_PROGRESS)
            if args.control_file:  # D-394: polled from here on; a stop takes the first-SIGTERM path
                from agentprov.cli.control import ControlWatcher

                watcher = ControlWatcher(args.control_file, command=command, progress=ctx.progress)
                watcher.start()
            _LOG.info(
                "start command=%s agentprov=%s formats=%s options=%s",
                command,
                __version__,
                ",".join(VERSIONS[k] for k in ("aer", "sem", "capture", "prov_spec")),
                jcs_bytes(normalised_options(args)).decode("utf-8"),
            )
            result = args.handler(ctx)
            exit_code = result.exit_code
        except (Exception, KeyboardInterrupt) as exc:
            result = _result_from_exception(exc, args)
            exit_code = result.exit_code
            _LOG.debug("command failed", exc_info=exc if not isinstance(exc, KeyboardInterrupt) else None)
        finally:
            outcome = None
            if watcher is not None:
                watcher.close()
                notice = watcher.notice()
                if notice is not None:
                    result.notices.append(notice)
                if watcher.effect == "drain" and exit_code == 0:
                    outcome = "drained"  # D-394: the command finished its in-flight units and stopped early
            if sink is not None:
                sink.close(exit_code, outcome=outcome)
        try:
            _print_messages(result, args, show_info)
            if result.payload is not None:
                write_stdout_bytes(sys.stdout, result.payload)
            _LOG.info(
                "end command=%s exit_code=%d outcome=%s counters=%s",
                command,
                exit_code,
                outcome_for(exit_code),
                jcs_bytes(result.counters).decode("utf-8"),
            )
            _write_summary(args, command, exit_code, result)
        except (OSError, AgentProvError) as exc:
            sys.stderr.write(f"agentprov: cannot write the summary: {safe_text(str(exc), 300)}\n")
            exit_code = exit_code or 70
        except KeyboardInterrupt:
            exit_code = 130
        finally:
            if log_handle is not None:
                log_handle.close()
    return exit_code
