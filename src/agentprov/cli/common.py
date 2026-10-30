"""Shared CLI machinery (docs/architecture MN M.1.2, N.1.1 to N.1.4, N.1.12, N.1.13).

* the parser class (``allow_abbrev`` off, errors raised instead of ``sys.exit``), the global options of N.1.2 as a
  parent parser with ``default=argparse.SUPPRESS`` so that ``agentprov -v import ...`` equals ``agentprov import ... -v``;
* display hygiene: :func:`safe_text` puts every data-derived string through ``escape_untrusted`` (N.1.13), keeps it on
  one line and applies the ``<home>``/``<host>``/credential redaction of N.1.12(6, 7);
* logging (:func:`configure_logging`; N.1.12): library loggers only, one stderr handler, an optional DEBUG file handler,
  text or JSON-lines (RFC 8785) format;
* the exception to exit-code mapping (N.1.3) and the typed refusals;
* the summary document ``agentprov-cli-summary/0.1`` (N.1.4).

Display of untrusted text goes through ``agentprov.ingest.quote`` only. Nothing here prints on its own: the callers
write to the streams of their :class:`Context`.
"""

from __future__ import annotations

import argparse
import logging
import os
import platform
import re
import signal
import sys
import threading
import traceback
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import IO, Any, Final, NoReturn, TextIO

from agentprov.envinfo import interpreter_advisory
from agentprov.errors import AgentProvError, ProfileError
from agentprov.ingest.quote import escape_untrusted
from agentprov.io.canonical import jcs_bytes
from agentprov.progress import NULL_PROGRESS, Progress
from agentprov.versions import VERSIONS, __version__

__all__ = [
    "EXIT_CODES",
    "SUMMARY_FORMAT",
    "CliArgumentParser",
    "CliUsageError",
    "CommandResult",
    "Context",
    "Failure",
    "LoggingHandle",
    "ParserExit",
    "Refusal",
    "UnsupportedCapability",
    "add_global_options",
    "apply_global_defaults",
    "build_summary",
    "configure_logging",
    "exit_code_for",
    "format_exception_safe",
    "install_signal_handlers",
    "normalised_options",
    "outcome_for",
    "redact_personal",
    "register_secret",
    "render_refusal",
    "safe_text",
    "startup_self_check",
    "version_text",
    "write_stdout_bytes",
]

SUMMARY_FORMAT: Final = "agentprov-cli-summary/0.1"
LOGGER_NAME: Final = "agentprov"

#: N.1.3: exit code to outcome name.
EXIT_CODES: Final[Mapping[int, str]] = {
    0: "ok",
    1: "failures",
    2: "usage",
    3: "environment",
    4: "refused",
    5: "unsupported",
    70: "internal",
    130: "interrupted",
}

# --------------------------------------------------------------------------------------------------------------
# Display hygiene (N.1.12(6, 7); N.1.13)
# --------------------------------------------------------------------------------------------------------------

_REDACTED: Final = "«redacted»"
_secrets: set[str] = set()
_secrets_lock = threading.Lock()


def register_secret(value: str) -> None:
    """Register a loaded credential value: from now on :func:`safe_text` and the log formatters replace it with
    ``«redacted»`` (N.1.12(6); defence in depth, the value is never printed in the first place). Values under four
    characters are ignored (a redaction of "ab" would mangle ordinary text).
    """
    if len(value) >= 4:
        with _secrets_lock:
            _secrets.add(value)


def _redact_secrets(text: str) -> str:
    if not _secrets:
        return text
    with _secrets_lock:
        values = sorted(_secrets, key=len, reverse=True)
    for value in values:
        text = text.replace(value, _REDACTED)
    return text


@lru_cache(maxsize=8)
def _personal_patterns(home: str, node: str) -> tuple[tuple[re.Pattern[str], str], ...]:
    patterns: list[tuple[re.Pattern[str], str]] = []
    if len(home) > 1 and home not in (os.sep, "//"):
        patterns.append((re.compile(re.escape(home.rstrip("/\\")) + r"(?=$|[/\\\s\"'),:;])"), "<home>"))
    host = node.strip()
    if len(host) >= 3 and host.lower() != "localhost":
        names = {host}
        short = host.split(".")[0]
        if len(short) >= 4:
            names.add(short)
        alternation = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
        patterns.append((re.compile(rf"(?<![\w.-])(?:{alternation})(?![\w-])", re.IGNORECASE), "<host>"))
    return tuple(patterns)


def redact_personal(text: str) -> str:
    """Write the home directory as ``<home>`` and the host name as ``<host>`` (N.1.12(7); R-51)."""
    try:
        home = str(Path.home())
    except (RuntimeError, KeyError, OSError):
        home = ""
    for pattern, replacement in _personal_patterns(home, platform.node()):
        text = pattern.sub(replacement, text)
    return text


def safe_text(value: object, max_chars: int | None = 500, *, redact: bool = True) -> str:
    """One line of display text for a data-derived value (N.1.13).

    The text goes through ``escape_untrusted`` (control, format, bidi and tag characters become ``<U+XXXX>``; truncated at
    ``max_chars``; ``None`` keeps the whole text), line breaks and tabs are written as escapes too so the result is a single line, registered
    credential values become ``«redacted»``, and, unless ``redact=False``, the home directory and host name become
    ``<home>`` and ``<host>``.
    """
    raw = _redact_secrets(value if isinstance(value, str) else str(value))  # before the cut: no partial key (CC-31)
    if redact:
        raw = redact_personal(raw)
    text = escape_untrusted(raw, max_chars=max_chars)
    text = text.replace("\n", "<U+000A>").replace("\t", "<U+0009>")
    text = _redact_secrets(text)
    return redact_personal(text) if redact else text


def format_exception_safe(exc: BaseException, *, frames: bool) -> str:
    """An exception for stderr or a log: type and escaped message, with traceback frames only when ``frames``.

    Every exception argument is passed through ``escape_untrusted`` (R-42): the arguments may carry source text.
    Frame lines show the file, line number and function name; source lines are omitted.
    """
    lines: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        message = ", ".join(safe_text(a, 500) for a in current.args) if current.args else ""
        head = f"{type(current).__name__}: {message}" if message else type(current).__name__
        if frames and current.__traceback__ is not None:
            for frame in traceback.extract_tb(current.__traceback__):
                lines.append(f"  at {safe_text(frame.filename, 300)}:{frame.lineno} in {safe_text(frame.name, 80)}")
        lines.append(head)
        current = current.__cause__ or (None if current.__suppress_context__ else current.__context__)
    return "\n".join(lines)


# --------------------------------------------------------------------------------------------------------------
# Errors and refusals (N.1.3, N.3.2)
# --------------------------------------------------------------------------------------------------------------


class CliUsageError(AgentProvError):
    """An argparse error, invalid combination or wrong-type path. Exit 2."""

    code = "cli.usage"
    exit_code = 2


class ParserExit(Exception):  # noqa: N818 - control flow, not an error
    """Raised in place of ``sys.exit`` by :class:`CliArgumentParser` (``main`` never calls ``sys.exit``; N.1.1(2))."""

    def __init__(self, status: int) -> None:
        super().__init__(status)
        self.status = status


@dataclass(frozen=True, slots=True)
class Refusal:
    """A typed refusal (N.3.2). ``lines`` are the reason lines (each already safe text)."""

    id: str
    mode: str
    status: str
    lines: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {"id": self.id, "mode": self.mode, "status": self.status, "lines": list(self.lines)}


def render_refusal(refusal: Refusal, *, details: str | None) -> list[str]:
    """The refusal template of N.3.2 as stderr lines."""
    head = f"agentprov: cannot {refusal.mode} '{safe_text(refusal.id, 80)}': {refusal.status}."
    out = [head, *(f"  {line}" for line in refusal.lines)]
    if details:
        out.append(f"  Details: {details}")
    return out


class UnsupportedCapability(AgentProvError):
    """A typed unsupported-capability refusal. Exit 5 (``unsupported``; N.1.3, N.3).

    Raised where the requested source, mode or capability does not exist in this build; it carries the
    :class:`Refusal` that goes to stderr and, with ``--json``, to ``summary.refusal``. Nothing pretends to work.
    """

    code = "cli.unsupported"
    exit_code = 5

    def __init__(self, message: str, *, refusal: Refusal | None = None, code: str | None = None) -> None:
        super().__init__(message, code=code)
        self.refusal = refusal


def outcome_for(exit_code: int) -> str:
    return EXIT_CODES.get(exit_code, "internal")


def exit_code_for(exc: BaseException) -> int:
    """Map an exception to its N.1.3 exit code: interruption to 130, a typed error to its ``exit_code`` when that is
    one of the table's codes, anything else (an unexpected exception, an unknown code) to 70.
    """
    if isinstance(exc, KeyboardInterrupt):
        return 130
    if isinstance(exc, ParserExit):
        return exc.status
    if isinstance(exc, AgentProvError):
        return exc.exit_code if exc.exit_code in EXIT_CODES and exc.exit_code != 0 else 70
    return 70


# --------------------------------------------------------------------------------------------------------------
# Parser (N.1.1)
# --------------------------------------------------------------------------------------------------------------


class CliArgumentParser(argparse.ArgumentParser):
    """``argparse`` with ``allow_abbrev`` off, no colour, and errors raised instead of ``sys.exit``."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("allow_abbrev", False)
        kwargs.setdefault("color", False)
        kwargs.setdefault("suggest_on_error", True)
        super().__init__(*args, **kwargs)

    def exit(self, status: int = 0, message: str | None = None) -> NoReturn:
        if message:
            sys.stderr.write(safe_text_block(message))
        raise ParserExit(status)

    def error(self, message: str) -> NoReturn:
        raise CliUsageError(f"{self.prog}: {safe_text(message, 1000)}\n  try '{self.prog} --help'")


def safe_text_block(text: str) -> str:
    return "\n".join(safe_text(line, 1000) for line in text.splitlines()) + "\n"


def version_text() -> str:
    """``--version`` (N.1.2): software version, the format and spec versions emitted, interpreter and its advisory."""
    emitted = " ".join(VERSIONS[k] for k in ("aer", "sem", "capture", "prov_spec", "ontology", "corpus_format"))
    advisory = interpreter_advisory()
    status = (
        "interpreter_advisory: none"
        if advisory is None
        else f"interpreter_advisory: below {advisory.floor} (missing {', '.join(advisory.missing)})"
    )
    return f"agentprov {__version__}\nformats: {emitted}\npython {platform.python_version()} ({status})"


class _VersionAction(argparse.Action):
    def __init__(self, option_strings: Sequence[str], dest: str, **kwargs: Any) -> None:
        super().__init__(option_strings, dest, nargs=0, default=argparse.SUPPRESS, help="show versions and exit")

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Any,
        option_string: str | None = None,
    ) -> None:
        sys.stdout.write(version_text() + "\n")
        parser.exit(0)


#: The largest integer an option may take: every option value enters the JCS summary and the start log line, and
#: RFC 8785 numbers are IEEE doubles, exact only up to 2^53 - 1 (CC-15; a larger one was an internal error, exit 70).
MAX_OPTION_INT: Final = 2**53 - 1


def bounded_int(text: str) -> int:
    """An integer option value within +/- :data:`MAX_OPTION_INT`; ``ArgumentTypeError`` (exit 2) otherwise."""
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError("must be an integer") from None
    if abs(value) > MAX_OPTION_INT:
        raise argparse.ArgumentTypeError(f"must be at most {MAX_OPTION_INT} in magnitude")
    return value


def _progress_interval(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError("must be a number of seconds") from None
    if not 1.0 <= value <= 3600.0:
        raise argparse.ArgumentTypeError("must be between 1 and 3600 seconds")
    return value


def _progress_max_bytes(text: str) -> int:
    value = bounded_int(text)
    if value < 64 * 1024:
        raise argparse.ArgumentTypeError("must be at least 65536 (64 KiB)")
    return value


def _content_chars(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError("must be an integer") from None
    if not 1 <= value <= 2000:
        raise argparse.ArgumentTypeError("must be between 1 and 2000")
    return value


def _non_negative_int(text: str) -> int:
    value = bounded_int(text)
    if value < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return value


#: Defaults applied after parsing (the options use ``default=SUPPRESS`` so a value given before or after the command
#: is never overridden by the other parser's default; N.1.1(3)).
GLOBAL_DEFAULTS: Final[Mapping[str, Any]] = {
    "verbose": 0,
    "quiet": False,
    "log_format": "text",
    "log_file": None,
    "log_content": False,
    "progress": None,
    "progress_format": None,
    "progress_file": None,
    "progress_interval": 2.0,
    "progress_max_bytes": 8 * 1024 * 1024,
    "control_file": None,
    "show_content": False,
    "content_chars": None,
    "json": False,
    "summary_json": None,
    "max_listed": 100,
    "no_colour": False,
    "break_stale_lock": False,
}

#: Output-control options: they never enter the summary's ``options`` (the summary is byte-identical at every
#: feedback level and format, F1; N.1.4(3)).
OUTPUT_CONTROL_OPTIONS: Final = frozenset(
    {
        "verbose",
        "quiet",
        "log_format",
        "log_file",
        "log_content",
        "progress",
        "progress_format",
        "progress_file",
        "progress_interval",
        "progress_max_bytes",
        "control_file",
        "show_content",
        "content_chars",
        "json",
        "summary_json",
        "no_colour",
    }
)


def add_global_options(parser: argparse.ArgumentParser) -> None:
    """Add the N.1.2 options (except ``-h``) to ``parser``, all with ``default=SUPPRESS``."""
    s = argparse.SUPPRESS
    g = parser.add_argument_group("global options")
    g.add_argument("--version", action=_VersionAction)
    g.add_argument("-v", "--verbose", action="count", default=s, help="log DEBUG (repeatable)")
    g.add_argument("-q", "--quiet", action="store_true", default=s, help="log WARNING and above; implies --progress off")
    g.add_argument("--log-format", choices=["text", "json"], default=s, help="stderr log format (default text)")
    g.add_argument("--log-file", metavar="PATH", default=s, help="also log to PATH (DEBUG, JSON lines)")
    g.add_argument("--log-content", action="store_true", default=s, help="permit escaped content excerpts in DEBUG logs")
    g.add_argument(
        "--progress",
        choices=["off", "summary", "status", "steps", "trace"],
        default=s,
        help="live feedback level on stderr (default: status on a terminal, else summary; env AGENTPROV_PROGRESS)",
    )
    g.add_argument(
        "--progress-format",
        choices=["auto", "tty", "plain", "jsonl"],
        default=s,
        help="feedback rendering (default auto: tty on an interactive terminal, else plain)",
    )
    g.add_argument("--progress-file", metavar="PATH", default=s,
                   help="also append feedback events as agentprov-progress/0.2 JSON lines to PATH (never below status)")
    g.add_argument("--progress-interval", type=_progress_interval, metavar="SECONDS", default=s,
                   help="heartbeat interval of --progress-file (default 2, minimum 1)")
    g.add_argument("--progress-max-bytes", type=_progress_max_bytes, metavar="N", default=s,
                   help="rotate --progress-file to PATH.1 past N bytes (default 8 MiB, minimum 64 KiB)")
    g.add_argument("--control-file", metavar="PATH", default=s,
                   help="writers: poll PATH for an agentprov-control/0.1 request (drain or stop; D-394)")
    g.add_argument("--show-content", action="store_true", default=s, help="add escaped content excerpts at steps and trace")
    g.add_argument(
        "--content-chars", type=_content_chars, metavar="N", default=s, help="excerpt length for --show-content (default 200, max 2000)"
    )
    g.add_argument("--json", action="store_true", default=s, help="summary document to stdout")
    g.add_argument("--summary-json", metavar="PATH", default=s, help="write the summary document to PATH (atomic)")
    g.add_argument(
        "--max-listed", type=_non_negative_int, metavar="N", default=s, help="cap on failures[] entries in the summary (default 100)"
    )
    g.add_argument("--no-colour", "--no-color", dest="no_colour", action="store_true", default=s, help="no ANSI colour")
    g.add_argument("--break-stale-lock", action="store_true", default=s, help="writers only: remove a lock whose pid is dead")


def apply_global_defaults(args: argparse.Namespace) -> None:
    """Fill the global options the user did not give, and check the combinations."""
    for name, default in GLOBAL_DEFAULTS.items():
        if not hasattr(args, name):
            setattr(args, name, default)
    if args.verbose and args.quiet:
        raise CliUsageError("agentprov: -v/--verbose and -q/--quiet cannot be combined")


# --------------------------------------------------------------------------------------------------------------
# Logging (N.1.12)
# --------------------------------------------------------------------------------------------------------------

_CONTEXT_KEYS: Final = ("ex", "cell", "source_key", "stage", "code")
_LOG_CAP: Final = 4000
_CONTENT_CAP: Final = 200


class _TextFormatter(logging.Formatter):
    """``LEVEL logger: message [key=value ...]`` (N.1.12(2))."""

    def __init__(self, *, log_content: bool, frames: bool) -> None:
        super().__init__()
        self._log_content = log_content
        self._frames = frames

    def format(self, record: logging.LogRecord) -> str:
        text = f"{record.levelname} {record.name}: {safe_text(record.getMessage(), _LOG_CAP)}"
        context = " ".join(f"{k}={safe_text(getattr(record, k), 200)}" for k in _CONTEXT_KEYS if hasattr(record, k))
        if context:
            text += f" [{context}]"
        content = getattr(record, "content", None)
        if self._log_content and content is not None and record.levelno <= logging.DEBUG:
            text += f" content={safe_text(content, _CONTENT_CAP)}"
        if record.exc_info and record.exc_info[1] is not None:
            text += "\n" + format_exception_safe(record.exc_info[1], frames=self._frames)
        return text


class _JsonFormatter(logging.Formatter):
    """One RFC 8785 object per line: ``{"ts", "level", "logger", "msg", ...context}`` (N.1.12(3))."""

    def __init__(self, *, log_content: bool, frames: bool, utc_now: Callable[[], str] | None = None) -> None:
        super().__init__()
        self._log_content = log_content
        self._frames = frames
        self._utc_now = utc_now

    def format(self, record: logging.LogRecord) -> str:
        from datetime import UTC, datetime

        ts = (
            self._utc_now()
            if self._utc_now
            else datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        )
        obj: dict[str, Any] = {
            "ts": ts,
            "level": record.levelname,
            "logger": record.name,
            "msg": safe_text(record.getMessage(), _LOG_CAP),
        }
        for key in _CONTEXT_KEYS:
            if hasattr(record, key):
                obj[key] = safe_text(getattr(record, key), 200)
        content = getattr(record, "content", None)
        if self._log_content and content is not None and record.levelno <= logging.DEBUG:
            obj["content"] = safe_text(content, _CONTENT_CAP)
        if record.exc_info and record.exc_info[1] is not None:
            obj["exc"] = format_exception_safe(record.exc_info[1], frames=self._frames)
        return jcs_bytes(obj).decode("utf-8")


class LoggingHandle:
    """What :func:`configure_logging` installed; :meth:`close` removes it and restores the logger."""

    def __init__(self, logger: logging.Logger, handlers: list[logging.Handler], level: int, propagate: bool) -> None:
        self._logger = logger
        self._handlers = handlers
        self._level = level
        self._propagate = propagate

    def close(self) -> None:
        for handler in self._handlers:
            self._logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:  # noqa: BLE001, S110
                pass
        self._handlers = []
        self._logger.setLevel(self._level)
        self._logger.propagate = self._propagate


def configure_logging(
    level: int | str,
    fmt: str = "text",
    file: str | os.PathLike[str] | None = None,
    *,
    log_content: bool = False,
    stream: TextIO | None = None,
) -> LoggingHandle:
    """Install the one stderr handler (and the optional DEBUG JSON-lines file handler) on the ``agentprov`` logger.

    Library modules log through ``logging.getLogger(__name__)`` and never configure handlers (N.1.12(1)). ``level`` is
    the stderr level. At DEBUG the exception formatter includes traceback frames. Personal paths, host names and
    registered credential values are redacted, control characters escaped, and content extras shown only with
    ``log_content`` at DEBUG (N.1.12(5-7)). The returned handle undoes everything.
    """
    logger = logging.getLogger(LOGGER_NAME)
    previous = LoggingHandle(logger, [], logger.level, logger.propagate)
    numeric = logging.getLevelName(level) if isinstance(level, str) else level
    if not isinstance(numeric, int):
        raise ValueError(f"unknown log level {level!r}")
    frames = numeric <= logging.DEBUG
    handlers: list[logging.Handler] = []
    stderr_handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
    stderr_handler.setLevel(numeric)
    stderr_handler.setFormatter(
        _JsonFormatter(log_content=log_content, frames=frames)
        if fmt == "json"
        else _TextFormatter(log_content=log_content, frames=frames)
    )
    handlers.append(stderr_handler)
    lowest = numeric
    if file is not None:
        file_handler = logging.FileHandler(os.fspath(file), mode="a", encoding="utf-8")
        file_handler.terminator = "\n"
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(_JsonFormatter(log_content=log_content, frames=True))
        handlers.append(file_handler)
        lowest = logging.DEBUG
    for handler in handlers:
        logger.addHandler(handler)
    logger.setLevel(lowest)
    logger.propagate = False
    return LoggingHandle(logger, handlers, previous._level, previous._propagate)


# --------------------------------------------------------------------------------------------------------------
# Signals (N.1.10(2, 3))
# --------------------------------------------------------------------------------------------------------------


def _kill_backend_workers() -> None:
    """Before the second signal's ``os._exit``: kill the live T2 worker trees (CC-27). Only if a worker was ever
    started, i.e. the module is loaded; nothing is imported on this path."""
    worker = sys.modules.get("agentprov.cli.live.worker")
    if worker is not None:
        try:
            worker.kill_all_workers()
        except Exception:  # noqa: BLE001, S110 - the process exits next whatever happens here
            pass


#: The signals whose first delivery takes the clean interruption path (N.1.10(2)).
INTERRUPT_SIGNALS: Final = ("SIGINT", "SIGTERM", "SIGHUP")


class Interrupted(KeyboardInterrupt):
    """The first interrupting signal (N.1.10(2)); ``signal_name`` names it for the summary notice."""

    def __init__(self, signum: int) -> None:
        super().__init__()
        try:
            self.signal_name = signal.Signals(signum).name
        except ValueError:
            self.signal_name = f"signal {signum}"


@contextmanager
def install_signal_handlers() -> Iterator[None]:
    """First SIGINT, SIGTERM or SIGHUP raises :class:`Interrupted` (a :class:`KeyboardInterrupt`) in the main thread
    (the command seals what it can, releases its lock and ``main`` exits 130); a second one aborts immediately with
    ``os._exit(130)``. Only in the main thread; the previous handlers are restored on exit. A signal the host does not
    provide is skipped (D-7: no platform branch).

    SIGHUP (the controlling terminal closed) takes the same clean path: by default it would kill the process with no
    flush, leaving a stale lock and, for ``import``, losing the unflushed index rows. A SIGHUP that the process inherited
    as ignored (``nohup``) stays ignored.
    """
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    count = 0

    def handler(signum: int, frame: object) -> None:
        nonlocal count
        count += 1
        if count > 1:
            _kill_backend_workers()
            os._exit(130)
        raise Interrupted(signum)

    saved: list[tuple[int, Any]] = []
    for name in INTERRUPT_SIGNALS:
        signum = getattr(signal, name, None)
        if signum is None:
            continue
        try:
            if name == "SIGHUP" and signal.getsignal(signum) == signal.SIG_IGN:
                continue  # nohup: the caller asked for a hang-up to be ignored
            saved.append((signum, signal.signal(signum, handler)))
        except (ValueError, OSError):
            continue
    try:
        yield
    finally:
        for signum, previous in saved:
            try:
                signal.signal(signum, previous)
            except (ValueError, OSError, TypeError):
                pass


# --------------------------------------------------------------------------------------------------------------
# Startup self-check (M.5.2(8))
# --------------------------------------------------------------------------------------------------------------


def startup_self_check() -> None:
    """Every command validates the packaged data it depends on; a defect is a defect of the installed package, so it
    exits 70 (M.5.2(8); N.1.3). Today that is the shipped ``aer`` rule catalogue. The source registry and the profiles
    join the check when ``agentprov.adapters`` exists.
    """
    from agentprov.aer.rules import load_catalogue

    try:
        load_catalogue("aer", 1)
    except Exception as exc:
        raise ProfileError(f"packaged data is broken: {type(exc).__name__}", code="adapter.profile") from None


# --------------------------------------------------------------------------------------------------------------
# Command results and the summary document (N.1.4)
# --------------------------------------------------------------------------------------------------------------

Failure = dict[str, Any]


@dataclass
class CommandResult:
    """What a command hands back to ``main``.

    ``messages`` are human lines for stderr, already safe text. ``info`` lines are suppressed when feedback is off
    (``-q``); ``error`` and ``output`` lines (errors, and what the user asked the command to print) are always shown.
    ``payload`` is the stdout payload of ``info`` (machine output).
    """

    exit_code: int = 0
    counters: dict[str, int] = field(default_factory=dict)
    issues_by_code: dict[str, int] = field(default_factory=dict)
    failures: list[Failure] = field(default_factory=list)
    refusal: Refusal | None = None
    notices: list[str] = field(default_factory=list)
    dry_run: bool = False
    corpus: dict[str, Any] | None = None
    messages: list[tuple[str, str]] = field(default_factory=list)
    payload: bytes | None = None

    def info(self, text: str) -> None:
        self.messages.append(("info", text))

    def error(self, text: str) -> None:
        self.messages.append(("error", text))

    def output(self, text: str) -> None:
        self.messages.append(("output", text))


@dataclass
class Context:
    """The per-invocation context handed to a command."""

    args: argparse.Namespace
    progress: Progress = NULL_PROGRESS
    stdout: IO[Any] = field(default_factory=lambda: sys.stdout)
    stderr: IO[Any] = field(default_factory=lambda: sys.stderr)
    env: Mapping[str, str] = field(default_factory=lambda: os.environ)
    log: logging.Logger = field(default_factory=lambda: logging.getLogger(LOGGER_NAME))


def normalised_options(args: argparse.Namespace) -> dict[str, Any]:
    """The command's options as the summary records them (N.1.4): the ones that were given (not ``None``), no
    output-control options, no internals, ``$HOME`` written ``<home>``, never a credential value (no option carries
    one; ``--env-file`` is a path).
    """
    out: dict[str, Any] = {}
    for key, value in sorted(vars(args).items()):
        if key.startswith("_") or key in OUTPUT_CONTROL_OPTIONS or key in ("command", "handler", "feedback"):
            continue
        if value is None:
            continue  # an option the user did not give is not recorded
        out[key] = _normalise(value)
    return out


def _normalise(value: Any) -> Any:
    if isinstance(value, str):
        return safe_text(value, 2000)  # option values are user-given, often paths: escaped and home-redacted
    if isinstance(value, bool | int | float) or value is None:
        return value
    if isinstance(value, list | tuple):
        return [_normalise(v) for v in value]
    return safe_text(value, 2000)


def _subject_key(failure: Failure) -> bytes:
    return jcs_bytes([failure.get("subject"), failure.get("stage"), failure.get("code")])


def build_summary(
    *,
    command: str,
    exit_code: int,
    result: CommandResult,
    options: Mapping[str, Any],
    max_listed: int,
    extra_notices: Sequence[str] = (),
) -> dict[str, Any]:
    """The ``agentprov-cli-summary/0.1`` document (N.1.4). No wall-clock times or durations: two runs on the same
    input serialise to the same bytes. ``failures`` are sorted by subject and capped at ``max_listed``.
    """
    failures = sorted(result.failures, key=_subject_key)
    return {
        "format": SUMMARY_FORMAT,
        "command": command,
        "agentprov_version": __version__,
        "exit_code": exit_code,
        "outcome": outcome_for(exit_code),
        "dry_run": result.dry_run,
        "corpus": result.corpus,
        "counters": dict(sorted(result.counters.items())),
        "issues_by_code": dict(sorted(result.issues_by_code.items())),
        "failures": failures[:max_listed],
        "failures_truncated": len(failures) > max_listed,
        "refusal": None if result.refusal is None else result.refusal.to_json(),
        "notices": [*result.notices, *extra_notices],
        "options": dict(options),
    }


def write_stdout_bytes(stream: IO[Any], data: bytes) -> None:
    """Write bytes to ``stream`` without newline translation (binary buffer when it has one; byte-stable output)."""
    buffer = getattr(stream, "buffer", None)
    if buffer is not None:
        stream.flush()
        buffer.write(data)
        buffer.flush()
    else:
        stream.write(data.decode("utf-8"))
        stream.flush()
