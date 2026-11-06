"""The desktop bundle's own ``agentprov`` (D-1130): the bundle's one executable is also the command-line program.

A frozen bundle (``gui/packaging/entry.py``) has no ``python`` to run, yet the core starts processes as
``sys.executable -I -m MODULE``: a job's supervisor and its CLI (``agentprov.jobs.manager``), the T1 worker pool
(``agentprov.io.workers``), the keychain helper (``agentprov.keys``) and the Windows update helper
(``agentprov.update.install``). In the bundle ``sys.executable`` is the app's executable, so it answers those argv
itself, before Qt is imported:

* ``AgentPROV --cli ARGS``: ``agentprov ARGS`` (:func:`agentprov.cli.main.main`), the form the desktop app runs;
* ``AgentPROV [-I] [-B] [-E] [-s] [-S] [-u] -m MODULE ARGS`` for exactly the modules in :data:`MODULES` (their own
  ``main``); any other module, a script path or ``-c CODE`` is refused (exit 2, one line on stderr): the bundle is not a
  general Python interpreter. ``agentprov.host``'s ``RLIMIT_AS`` probe (``-c``) is therefore "not decided" in the
  bundle, and the worker pool falls back as on any host where the probe cannot run;
* ``AgentPROV --keychain-helper``: the keychain helper (``agentprov.keys.helper_argv`` already starts it so).

Anything else (no argument, ``--smoke``, ``--preview-helper``, a file to open) is not a CLI call: :func:`dispatch`
returns ``None`` and the bundle starts the desktop app. Nothing here reads the environment or the network.

**Windows.** The bundle is a GUI-subsystem executable (``console=False``), so started from ``cmd`` or PowerShell it has
no standard streams of its own and Python sets ``sys.stdout``/``sys.stderr`` to ``None``. For ``--cli``,
:func:`attach_console` then attaches to the parent's console (``AttachConsole(ATTACH_PARENT_PROCESS)``) and reopens
the missing streams on ``CONOUT$``/``CONIN$``; streams that exist (a pipe from the desktop app or a job's supervisor)
are never replaced. Without a parent console nothing changes. Untested on Windows by this project's tests (D-1130).

**Code digests (D-1130 review).** A corpus records the digest of the code that wrote it
(:func:`agentprov.stage_definitions.code_sha256` hashes the package's source files on disk) and the versions of the
libraries it used (``importlib.metadata``). A PyInstaller bundle keeps its modules as bytecode, so the spec ships the
core's ``.py`` files and the metadata of :data:`RECORDED_DISTRIBUTIONS` beside them, and the build checks that they equal
the build environment's. Should a bundle lack them anyway, :func:`sources_problem` says what is missing and every command
outside :data:`SAFE_WITHOUT_SOURCES` is refused (exit 3) rather than record a false digest or an ``absent`` version.

What the bundled program cannot do, because it has no checkout (``backends/``, ``tools/``, a ``.venv``): live runs
(``run``, ``backends``, ``migrate`` find the backend projects from a checkout), the job queue (``--queue-cpu``,
``tools/suite_queue.py``), the checkout's tools (``jobs start --tool``) and the Zenodo uploader (``agentprov-zenodo``,
the checkout's environment); ``render`` needs Graphviz and the ``render`` extra, which the bundle does not carry. Those
commands refuse with their own reasons, and the desktop app says so before it starts them.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from importlib import import_module
from typing import Final

__all__ = ["CLI_FLAG", "KEYCHAIN_FLAG", "MODULES", "PYTHON_FLAGS", "RECORDED_DISTRIBUTIONS", "SAFE_WITHOUT_SOURCES",
           "attach_console", "dispatch", "is_cli_call", "sources_problem"]

CLI_FLAG: Final = "--cli"
KEYCHAIN_FLAG: Final = "--keychain-helper"
#: the ``-m`` modules the core starts with ``sys.executable`` and the function that is each one's ``__main__``
MODULES: Final = {
    "agentprov": ("agentprov.cli.main", "main"),
    "agentprov.jobs.supervisor": ("agentprov.jobs.supervisor", "main"),
    "agentprov.worker": ("agentprov.worker", "main"),
    "agentprov.keys.helper": ("agentprov.keys.helper", "main"),
    "agentprov.update.apply": ("agentprov.update.apply", "main"),
}
#: interpreter options the core passes (``-I``, ``-B``) and the harmless others; they change nothing in a frozen app
PYTHON_FLAGS: Final = frozenset({"-I", "-B", "-E", "-s", "-S", "-u"})
_NO_ARGV: Final = frozenset({"agentprov.keys.helper"})  # its main() reads stdin only
#: the distributions whose versions a corpus records (stage definitions, key_distributions, the engine); the bundle's
#: spec copies their metadata (``gui/packaging/agentprov-gui.spec``, the same tuple; a test pins the two)
RECORDED_DISTRIBUTIONS: Final = ("agentprov", "agentprov-capture", "prov", "rdflib", "rfc8785", "PyYAML")
#: the commands that record or compare no code digest: they run even in a bundle without its sources. Any other command
#: (import, run, derive, recompute, validate, package, verify, purge, migrate, fetch, devrun, …) is refused there
SAFE_WITHOUT_SOURCES: Final = frozenset({"info", "sources", "settings", "keys", "prices", "estimate", "models", "jobs",
                                         "batch", "assist", "update", "launcher", "inspect", "stats", "priors"})


def is_cli_call(argv: Sequence[str]) -> bool:
    """Whether ``argv`` (without the program name) is one of the forms :func:`dispatch` answers."""
    if not argv:
        return False
    first = argv[0]
    return first in (CLI_FLAG, KEYCHAIN_FLAG) or first in PYTHON_FLAGS or first in ("-m", "-c")


def _open_console(name: str, mode: str) -> object:
    """A console stream in UTF-8 that never raises on a character the console cannot show (the CLI prints →, ›, …;
    the locale's code page would raise ``UnicodeEncodeError`` mid-output)."""
    return open(name, mode, encoding="utf-8", errors="replace")  # noqa: SIM115 - it becomes sys.stdout


def attach_console(*, platform: str | None = None, attach: Callable[[], bool] | None = None,
                   reopen: Callable[[str, str], object] = _open_console) -> list[str]:
    """Windows only: give ``--cli`` the parent console's streams where Python has none (see the module docstring);
    the names of the streams it set. ``attach`` and ``reopen`` are seams for the tests."""
    if (sys.platform if platform is None else platform) != "win32":
        return []
    missing = [name for name in ("stdout", "stderr", "stdin") if getattr(sys, name) is None]
    if not missing:
        return []
    if attach is None:
        import ctypes

        def attach() -> bool:
            return bool(ctypes.windll.kernel32.AttachConsole(-1))  # type: ignore[attr-defined]  # ATTACH_PARENT_PROCESS
    if not attach():
        return []
    done = []
    for name in missing:
        try:
            setattr(sys, name, reopen("CONIN$" if name == "stdin" else "CONOUT$", "r" if name == "stdin" else "w"))
            done.append(name)
        except OSError:
            continue
    return done


def sources_problem(*, root: object = None, version: Callable[[str], str] | None = None) -> str | None:
    """What this bundle lacks to record true code digests and library versions, or ``None`` (it has both). ``root``
    (the ``agentprov`` package folder) and ``version`` are seams for the tests."""
    from pathlib import Path

    if version is None:
        from importlib import metadata

        def version(name: str) -> str:
            return metadata.version(name)
    package = Path(str(root)) if root is not None else Path(__file__).resolve().parents[1]
    if not (package / "stage_definitions.py").is_file() or not (package / "cli" / "frozen.py").is_file():
        return "the core's source files"
    missing = []
    for name in RECORDED_DISTRIBUTIONS:
        try:
            version(name)
        except Exception:  # noqa: BLE001 - PackageNotFoundError, or unreadable metadata
            missing.append(name)
    return f"the package metadata of {', '.join(missing)}" if missing else None


def _subcommand(args: list[str]) -> str | None:
    """The subcommand ``args`` name (the CLI's own parser), or ``None`` when they do not parse (the CLI reports it)."""
    from agentprov.cli.main import build_parser

    try:
        ns, _rest = build_parser().parse_known_args(args)
    except (SystemExit, Exception):  # noqa: BLE001 - a usage error: the CLI itself prints it
        return None
    command = getattr(ns, "command", None)
    return command if isinstance(command, str) else None


def _cli(args: list[str], *, load: Callable[[str], object], err: Callable[[str], object],
         problem: Callable[[], str | None]) -> int:
    """``agentprov ARGS``, unless the bundle lacks its sources and the command would record a code digest."""
    missing = problem() if getattr(sys, "frozen", False) else None
    if missing is not None:
        command = _subcommand(args)
        if command is not None and command not in SAFE_WITHOUT_SOURCES:
            err(f"agentprov (bundled): this copy of the app lacks {missing}, so {command} would record false code "
                "digests or library versions in a corpus: refused. Use a checkout or a pip, uv tool or pipx install of "
                "agentprov (Settings › General), or download the app again\n")
            return 3
    return _call("agentprov", args, load=load)


def _refuse(message: str, err: Callable[[str], object]) -> int:
    err(f"agentprov (bundled): {message}\n")
    return 2


def _call(module: str, args: list[str], *, load: Callable[[str], object]) -> int:
    name, func = MODULES[module]
    entry = getattr(load(name), func)
    if module in _NO_ARGV:
        sys.argv = [module]
        return int(entry() or 0)
    sys.argv = [module, *args]
    return int(entry(args) or 0)


def dispatch(argv: Sequence[str], *, load: Callable[[str], object] = import_module,
             err: Callable[[str], object] | None = None,
             problem: Callable[[], str | None] = sources_problem) -> int | None:
    """The exit code of a CLI call of the bundle, or ``None`` when ``argv`` is not one (the desktop app starts).
    ``load`` imports a module (a seam for the tests); ``err`` writes a refusal (default ``sys.stderr.write``);
    ``problem`` is :func:`sources_problem` (a seam)."""
    args = list(argv)
    if not is_cli_call(args):
        return None
    if args[0] == CLI_FLAG:
        attach_console()
    write = err if err is not None else (lambda text: sys.stderr.write(text))
    if args[0] == CLI_FLAG:
        return _cli(args[1:], load=load, err=write, problem=problem)
    if args[0] == KEYCHAIN_FLAG:
        if len(args) != 1:
            return _refuse("--keychain-helper takes no argument", write)
        return _call("agentprov.keys.helper", [], load=load)
    i = 0
    while i < len(args) and args[i] in PYTHON_FLAGS:
        i += 1
    if i >= len(args):
        return _refuse("an interpreter option without -m MODULE", write)
    if args[i] == "-c":
        return _refuse("-c is not supported: the bundle runs agentprov's own modules only", write)
    if args[i] != "-m" or i + 1 >= len(args):
        return _refuse("only -m MODULE is supported (the bundle cannot run a script: the checkout's tools need a "
                       "checkout, Settings › General)", write)
    module = args[i + 1]
    if module not in MODULES:
        return _refuse(f"-m {module[:80]!r} is not one of the bundle's modules ({', '.join(sorted(MODULES))})", write)
    if module == "agentprov":
        return _cli(args[i + 2:], load=load, err=write, problem=problem)
    return _call(module, args[i + 2:], load=load)
