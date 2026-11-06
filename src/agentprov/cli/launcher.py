"""``agentprov launcher``: the Terminal command of the desktop app (D-1130; the app's Install Command Line Tool…).

    agentprov launcher install [--dir DIR] [--app EXE] [--format text|json]
    agentprov launcher remove  [--dir DIR] [--format text|json]
    agentprov launcher status  [--dir DIR] [--app EXE] [--format text|json]

The desktop bundle carries its own ``agentprov`` (``AgentPROV --cli ARGS``, :mod:`agentprov.cli.frozen`). ``install``
writes a small launcher named ``agentprov`` (Windows: ``agentprov.cmd``) that runs it, so the bundled CLI also works in
a Terminal, as an editor's "install the command in PATH" does:

* the launcher names the app's executable by its absolute path and runs ``EXE --cli ARGS``; an app update replaces the
  app in place, so the Terminal command follows it. When the app has moved or been deleted, the launcher says so and
  exits 127 (it never looks for another copy);
* the default folder is ``~/.local/bin`` (Windows: ``%USERPROFILE%\\.local\\bin``), made when missing; no
  administrator rights. ``--dir`` names another folder, which must exist and be writable (``/usr/local/bin`` only when
  this account can write it): the command never uses ``sudo`` or elevation;
* the launcher's second line is the marker :data:`MARKER`. ``install`` replaces only a launcher with that marker, and
  ``remove`` deletes only such a launcher: an ``agentprov`` that pip, ``uv tool``, ``pipx`` or a checkout's ``.venv``
  put there (or any other file) is refused and named (exit 4);
* the reply says when the folder is not on ``PATH`` (with the line to add it) and when another ``agentprov`` comes
  first on ``PATH``.

``EXE`` is this program's own executable when it is the frozen bundle (``sys.executable``); from any other
``agentprov`` (pip, a checkout) ``install`` needs ``--app`` naming the app's executable (``AgentPROV``,
``AgentPROV.exe``). Nothing here starts a process or opens a connection. ``remove`` without ``--dir`` looks in the
default folder and (POSIX) ``/usr/local/bin``.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from agentprov.cli.common import CliUsageError, CommandResult, Context, Refusal, render_refusal, safe_text

__all__ = [
    "FORMAT",
    "MARKER",
    "SYSTEM_DIR",
    "app_name",
    "default_dir",
    "describe_other",
    "is_launcher",
    "launcher_app",
    "launcher_name",
    "register",
    "render",
    "run_launcher",
]

#: the launcher's second line (after ``#!/bin/sh`` or ``@echo off``), behind ``# `` or ``rem ``
MARKER: Final = "agentprov-launcher/1"
FORMAT: Final = "agentprov-launcher/0.1"
#: the shared folder offered besides the default (POSIX), only when this account can write it
SYSTEM_DIR: Final = "/usr/local/bin"
_HEAD_BYTES: Final = 4096
_MAX_LAUNCHER: Final = 64 * 1024
#: characters a launcher cannot carry safely in its quoted path: control characters, and on Windows ``%`` and ``"``
_WINDOWS_BAD: Final = frozenset('%"')
#: other names Windows would run for ``agentprov`` before ``agentprov.cmd`` (PATHEXT order)
_WINDOWS_SHADOWS: Final = ("agentprov.com", "agentprov.exe", "agentprov.bat")


def _windows(platform: str | None = None) -> bool:
    return (sys.platform if platform is None else platform) == "win32"


def app_name(platform: str | None = None) -> str:
    """The bundle's executable name (``gui/packaging/agentprov-gui.spec``)."""
    return "AgentPROV.exe" if _windows(platform) else "AgentPROV"


def launcher_name(platform: str | None = None) -> str:
    return "agentprov.cmd" if _windows(platform) else "agentprov"


def default_dir(home: Path | None = None) -> Path:
    """``~/.local/bin`` on every platform (on Windows the folder ``uv tool`` also uses)."""
    return (Path.home() if home is None else home) / ".local" / "bin"


def _sh_quote(text: str) -> str:
    return "'" + text.replace("'", "'\\''") + "'"


def render(app: str, platform: str | None = None) -> str:
    """The launcher's text for the app executable ``app`` (absolute, already checked by :func:`_check_app`)."""
    if _windows(platform):
        return "\r\n".join((
            "@echo off",
            f"rem {MARKER}",
            "rem The Terminal command of the AgentPROV desktop app: it runs the app's own agentprov, so an app update",
            "rem updates it too. Made by Install Command Line Tool (agentprov launcher install); remove it with",
            "rem Uninstall Command Line Tool (agentprov launcher remove). Edits are lost on the next install.",
            "setlocal",
            f'set "AGENTPROV_APP={app}"',
            'if not exist "%AGENTPROV_APP%" goto moved',
            '"%AGENTPROV_APP%" --cli %*',
            "exit /b %ERRORLEVEL%",
            ":moved",
            '>&2 echo agentprov: the AgentPROV app is no longer at "%AGENTPROV_APP%" (moved or deleted).',
            ">&2 echo Install the command again from the app (Help, Install Command Line Tool), or delete \"%~f0\".",
            "exit /b 127",
            "",
        ))
    return "\n".join((
        "#!/bin/sh",
        f"# {MARKER}",
        "# The Terminal command of the AgentPROV desktop app: it runs the app's own agentprov, so an app update updates",
        "# it too. Made by Install Command Line Tool (agentprov launcher install); remove it with Uninstall Command",
        "# Line Tool (agentprov launcher remove). Edits are lost on the next install.",
        f"app={_sh_quote(app)}",
        'if [ ! -x "$app" ]; then',
        "  printf '%s\\n' \"agentprov: the AgentPROV app is no longer at $app (moved or deleted).\" \\",
        "    \"Install the command again from the app (Install Command Line Tool), or delete $0.\" >&2",
        "  exit 127",
        "fi",
        'exec "$app" --cli "$@"',
        "",
    ))


def _head(path: Path) -> bytes | None:
    """The first bytes of a regular file (never through a symbolic link), or ``None``."""
    try:
        st = path.lstat()
        if not stat.S_ISREG(st.st_mode) or st.st_size > _MAX_LAUNCHER:
            return None
        with path.open("rb") as fh:
            return fh.read(_HEAD_BYTES)
    except OSError:
        return None


def is_launcher(path: Path) -> bool:
    """Whether ``path`` is a launcher :func:`render` wrote: a regular file (not a link) of at most 64 KiB whose second
    line is the marker. Anything else is someone else's ``agentprov``."""
    head = _head(path)
    if head is None:
        return False
    lines = head.decode("utf-8", "replace").splitlines()
    return len(lines) >= 2 and lines[1].strip() in (f"# {MARKER}", f"rem {MARKER}")


def launcher_app(path: Path) -> str | None:
    """The app executable a launcher names (``None`` when ``path`` is not a launcher or the line is unreadable)."""
    if not is_launcher(path):
        return None
    head = _head(path) or b""
    for line in head.decode("utf-8", "replace").splitlines():
        if line.startswith("app='") and line.endswith("'"):
            return line[5:-1].replace("'\\''", "'")
        if line.startswith('set "AGENTPROV_APP=') and line.endswith('"'):
            return line[len('set "AGENTPROV_APP='):-1]
    return None


def describe_other(path: Path) -> str:
    """What the ``agentprov`` at ``path`` is, in words, when it is not a launcher (pip, uv tool, pipx, a ``.venv``)."""
    try:
        if path.is_symlink():
            target = os.readlink(path)
            where = Path(os.path.realpath(path)).as_posix()
            kind = ("installed with uv tool" if "/uv/tools/" in where else
                    "installed with pipx" if "/pipx/" in where else
                    "in a virtual environment (a checkout's .venv or another)" if "/.venv/" in where or
                    "/venvs/" in where else "a symbolic link")
            return f"{kind}: a link to {safe_text(target, 200)}"
    except OSError:
        return "a file this account cannot read"
    if path.is_dir():
        return "a folder"
    head = _head(path)
    if head is None:
        return "a file this account cannot read"
    first = head.split(b"\n", 1)[0].decode("utf-8", "replace").strip()
    if path.suffix.lower() == ".exe" or head.startswith(b"MZ"):
        return "a program (pip, uv tool or pipx put agentprov.exe in a Scripts or bin folder)"
    if first.startswith("#!") and "python" in first.lower():
        interp = first[2:].strip()
        kind = ("in a virtual environment (a checkout's .venv or another)" if "/.venv/" in interp or "/venvs/" in interp
                else "installed with uv tool" if "/uv/tools/" in interp
                else "installed with pipx" if "/pipx/" in interp else "installed with pip")
        return f"{kind}: a Python script run by {safe_text(interp, 200)}"
    return "a file that is not this app's launcher"


@dataclass(frozen=True, slots=True)
class _Env:
    platform: str
    environ: Mapping[str, str]
    home: Path


def _env(ctx: Context) -> _Env:
    return _Env(sys.platform, ctx.env, Path.home())


def _norm(path: str | Path) -> str:
    return os.path.normcase(os.path.realpath(os.path.expanduser(str(path))))


def _path_dirs(environ: Mapping[str, str]) -> list[str]:
    return [d for d in environ.get("PATH", "").split(os.pathsep) if d]


def _on_path(folder: Path, environ: Mapping[str, str]) -> bool:
    want = _norm(folder)
    return any(_norm(d) == want for d in _path_dirs(environ))


def _first_on_path(environ: Mapping[str, str]) -> str | None:
    found = shutil.which("agentprov", path=environ.get("PATH", ""))
    return os.path.abspath(found) if found else None


def _path_hint(folder: Path, env: _Env) -> list[str]:
    """How to put ``folder`` on ``PATH`` (the user does it; nothing here edits a profile or the registry)."""
    if _windows(env.platform):
        return [f"Add {folder} to your PATH: Settings, search for \"Edit environment variables for your account\", "
                f"select Path, New, and paste the folder; or in PowerShell:",
                "[Environment]::SetEnvironmentVariable(\"Path\", [Environment]::GetEnvironmentVariable(\"Path\", "
                f"\"User\") + \";{folder}\", \"User\")",
                "Then open a new terminal window."]
    shown = "$HOME" + str(folder)[len(str(env.home)):] if str(folder).startswith(str(env.home) + os.sep) else str(folder)
    profile = "~/.zprofile" if env.platform == "darwin" else "~/.profile"
    return [f"{folder} is not on your PATH. Add it (zsh and bash) with:",
            f"echo 'export PATH=\"{shown}:$PATH\"' >> {profile}",
            "Then open a new Terminal window."]


def _bad_chars(text: str, platform: str) -> bool:
    return any(ord(c) < 32 or ord(c) == 127 for c in text) or (_windows(platform) and any(c in _WINDOWS_BAD
                                                                                          for c in text))


def _check_app(app_arg: str | None, env: _Env, *, lasting: bool = True) -> Path:
    """The app executable the launcher will run: ``--app``, else this program when it is the frozen bundle.
    ``lasting``: refuse an app that is not in a lasting place (install only; ``status`` must still find a launcher an
    earlier copy made, for the app's Uninstall Command Line Tool)."""
    if app_arg is None:
        if not getattr(sys, "frozen", False):
            raise _Refused("launcher", "no desktop app to link to", (
                "Only the desktop app's own agentprov installs the Terminal command: use Install Command Line Tool in "
                "the app, or give --app with the app's executable (for example "
                "/Applications/AgentPROV.app/Contents/MacOS/AgentPROV).",
                "An agentprov installed with pip, uv tool or pipx is already a Terminal command."))
        app_arg = sys.executable
    app = Path(os.path.abspath(os.path.expanduser(app_arg)))
    if _bad_chars(str(app), env.platform):
        raise CliUsageError("agentprov launcher: the app's path has characters a launcher cannot quote safely "
                            "(a control character, or on Windows % or \"); move the app to a plain folder")
    want = app_name(env.platform)
    if app.name != want:
        raise CliUsageError(f"agentprov launcher: --app must name the desktop app's executable {want} (inside the "
                            f"app), not {safe_text(app.name, 80)!r}")
    if not app.is_file() or not os.access(app, os.X_OK):
        raise CliUsageError(f"agentprov launcher: no app executable at {safe_text(str(app), 300)}")
    if is_launcher(app):  # a case-insensitive file system matches AgentPROV to agentprov: never a launcher of itself
        raise CliUsageError("agentprov launcher: --app names a launcher, not the app (it would run itself)")
    transient = transient_location(app, env.platform) if lasting else None
    if transient is not None:
        raise _Refused(str(app), "the app is not in a lasting place", (
            f"The app runs from {safe_text(str(app), 300)}, {transient}; a launcher would stop working once that "
            "place is gone.",
            "Move AgentPROV.app to Applications (or another folder of your own), open it from there, and install the "
            "command again."))
    return app


def transient_location(app: Path, platform: str, *, read_only: object = None) -> str | None:
    """Why the app's path will not last (D-1130 review), or ``None``. macOS only: an app opened where it was
    downloaded runs from a random App Translocation folder that is gone at the next restart, and one opened from its
    disk image runs from a read-only volume that is gone once the image is ejected. ``read_only`` (``path -> bool``)
    is a seam."""
    if platform != "darwin":
        return None
    parts = app.parts
    if "AppTranslocation" in parts:
        return "a temporary copy macOS made because the app was opened where it was downloaded (App Translocation)"
    if len(parts) > 2 and parts[1] == "Volumes":
        volume = Path(*parts[:3])
        check = read_only if callable(read_only) else _read_only
        if check(volume):
            return "a read-only volume (the app's disk image, gone once it is ejected)"
    return None


def _read_only(path: Path) -> bool:
    try:
        return bool(os.statvfs(path).f_flag & getattr(os, "ST_RDONLY", 1))
    except (OSError, AttributeError):
        return False


class _Refused(Exception):
    def __init__(self, ident: str, status: str, lines: Sequence[str], *, mode: str = "install the Terminal command"
                 ) -> None:
        super().__init__(status)
        self.refusal = Refusal(id=ident, mode=mode, status=status,
                               lines=tuple(safe_text(x, 600) for x in lines))


def _folder(dir_arg: str | None, env: _Env) -> tuple[Path, bool]:
    """(the folder, whether it is the default)."""
    default = default_dir(env.home)
    if dir_arg is None:
        return default, True
    folder = Path(os.path.abspath(os.path.expanduser(dir_arg)))
    return folder, _norm(folder) == _norm(default)


def _whole(path: Path) -> bytes | None:
    try:
        return path.read_bytes() if _head(path) is not None else None
    except OSError:
        return None


def _same_file(a: Path, b: Path) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def _write(target: Path, data: bytes, platform: str) -> None:
    fd, tmp = tempfile.mkstemp(prefix=".agentprov-launcher-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        if not _windows(platform):
            os.chmod(tmp, 0o755)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _install(args: argparse.Namespace, env: _Env) -> dict[str, Any]:
    app = _check_app(args.app, env)
    folder, is_default = _folder(args.dir, env)
    if _bad_chars(str(folder), env.platform):
        raise CliUsageError("agentprov launcher: the folder's path has a control character")
    if not folder.exists():
        if not is_default:
            raise _Refused(str(folder), "the folder does not exist", (
                f"{folder} does not exist. Make it first, or use the default {default_dir(env.home)}.",))
        folder.mkdir(parents=True, exist_ok=True, mode=0o755)
    if not folder.is_dir():
        raise _Refused(str(folder), "not a folder", (f"{folder} is not a folder.",))
    if not os.access(folder, os.W_OK | os.X_OK):
        raise _Refused(str(folder), "the folder is not writable by this account", (
            f"{folder} needs administrator rights to write; this command never uses sudo or elevation.",
            f"Use the default {default_dir(env.home)} (no administrator rights needed)."))
    target = folder / launcher_name(env.platform)
    if _norm(target) == _norm(app) or (target.exists() and os.path.samefile(target, app)):  # APFS: case-insensitive
        raise _Refused(str(target), "the launcher would replace the app", (
            f"{target} is the app's own executable; choose another folder.",))
    if _windows(env.platform):
        for other in _WINDOWS_SHADOWS:
            if os.path.lexists(folder / other) and _same_file(folder / other, app):  # NTFS: agentprov.exe is the app
                raise _Refused(str(folder), "this is the app's own folder", (
                    f"{folder} holds the app's own executable {app.name}, which Windows would run for agentprov before "
                    f"{target.name}; choose another folder (the default is {default_dir(env.home)}).",))
            if os.path.lexists(folder / other):
                raise _Refused(str(folder / other), "another agentprov is in this folder", (
                    f"{folder / other} is {describe_other(folder / other)}; Windows would run it before "
                    f"{target.name}. Choose another folder, or remove that agentprov first.",))
    before = launcher_app(target)
    if os.path.lexists(target) and not is_launcher(target):
        raise _Refused(str(target), "another agentprov is already there", (
            f"{target} is {describe_other(target)}, not this app's launcher; it is left as it is.",
            "Remove it with the tool that installed it (pip uninstall agentprov, uv tool uninstall agentprov, pipx "
            "uninstall agentprov), or choose another folder with --dir.",))
    data = render(str(app), env.platform).encode("utf-8")
    if before is not None and _whole(target) == data:
        changed = "unchanged"
    else:
        _write(target, data, env.platform)
        changed = "installed" if before is None else "updated"
    return _report("install", target, app, changed, env)


def _report(action: str, target: Path, app: Path | str | None, changed: str, env: _Env) -> dict[str, Any]:
    on_path = _on_path(target.parent, env.environ)
    first = _first_on_path(env.environ)
    shadowed = first if first is not None and _norm(first) != _norm(target) and changed != "removed" else None
    return {"format": FORMAT, "action": action, "changed": changed, "launcher": str(target),
            "app": None if app is None else str(app), "runs": None if app is None else [str(app), "--cli"],
            "on_path": on_path, "path_hint": [] if on_path or changed == "removed" else _path_hint(target.parent, env),
            "shadowed_by": shadowed}


def _candidates(dir_arg: str | None, env: _Env) -> list[Path]:
    folder, _ = _folder(dir_arg, env)
    dirs = [folder]
    if dir_arg is None and not _windows(env.platform):
        dirs.append(Path(SYSTEM_DIR))
    out: list[Path] = []
    for d in dirs:
        if _norm(d) not in {_norm(x) for x in out}:
            out.append(d)
    return [d / launcher_name(env.platform) for d in out]


def _remove(args: argparse.Namespace, env: _Env) -> dict[str, Any]:
    removed: list[str] = []
    left: list[dict[str, str]] = []
    for target in _candidates(args.dir, env):
        if not os.path.lexists(target):
            continue
        if not is_launcher(target):
            if args.dir is not None:
                raise _Refused(str(target), "not this app's launcher", (
                    f"{target} is {describe_other(target)}; only a launcher this app made is removed.",),
                    mode="remove the Terminal command")
            left.append({"path": str(target), "is": describe_other(target)})
            continue
        try:
            target.unlink()
        except PermissionError:
            raise _Refused(str(target), "the folder is not writable by this account", (
                f"Removing {target} needs administrator rights; this command never uses sudo or elevation. Delete it "
                "yourself if you want it gone.",), mode="remove the Terminal command") from None
        removed.append(str(target))
    first = _first_on_path(env.environ)
    return {"format": FORMAT, "action": "remove", "changed": "removed" if removed else "absent", "removed": removed,
            "left": left, "shadowed_by": None, "first_on_path": first}


def _status(args: argparse.Namespace, env: _Env) -> dict[str, Any]:
    app: str | None = None
    if args.app is not None or getattr(sys, "frozen", False):
        app = str(_check_app(args.app, env, lasting=False))
    entries = []
    for target in _candidates(args.dir, env):
        exists = os.path.lexists(target)
        ours = exists and is_launcher(target)
        named = launcher_app(target) if ours else None
        entries.append({"path": str(target), "exists": exists, "launcher": ours, "app": named,
                        "app_exists": named is not None and os.path.isfile(named),
                        "current": named is not None and app is not None and _norm(named) == _norm(app),
                        "on_path": _on_path(target.parent, env.environ),
                        "is": None if not exists or ours else describe_other(target)})
    return {"format": FORMAT, "action": "status", "app": app, "entries": entries,
            "first_on_path": _first_on_path(env.environ), "default_dir": str(default_dir(env.home)),
            "system_dir_writable": not _windows(env.platform) and os.access(SYSTEM_DIR, os.W_OK | os.X_OK)}


def _text(doc: dict[str, Any]) -> str:
    out: list[str] = []
    if doc["action"] in ("install",):
        verb = {"installed": "installed", "updated": "updated", "unchanged": "already installed"}[doc["changed"]]
        out.append(f"Terminal command {verb}: {doc['launcher']}")
        out.append(f"It runs: \"{doc['app']}\" --cli ARGS")
        if doc["shadowed_by"]:
            out.append(f"Note: another agentprov comes first on PATH: {doc['shadowed_by']}; a Terminal runs that one.")
        out.extend(doc["path_hint"])
    elif doc["action"] == "remove":
        out.extend(f"Removed: {p}" for p in doc["removed"])
        if not doc["removed"]:
            out.append("No launcher of this app was found; nothing removed.")
        out.extend(f"Left as it is (not this app's launcher): {x['path']} ({x['is']})" for x in doc["left"])
    else:
        out.append(f"app: {doc['app'] or '(not the desktop app; --app names one)'}")
        for e in doc["entries"]:
            if not e["exists"]:
                state = "none"
            elif e["launcher"]:
                state = (f"this app's launcher, runs {e['app']}" + ("" if e["app_exists"] else " (missing: the app "
                         "has moved or been deleted)"))
            else:
                state = f"not a launcher: {e['is']}"
            out.append(f"{e['path']}: {state}{'' if e['on_path'] else ' [folder not on PATH]'}")
        out.append(f"first agentprov on PATH: {doc['first_on_path'] or 'none'}")
    return "".join(f"{safe_text(x, 800, redact=False)}\n" for x in out)


def register(sub: Any, shared: argparse.ArgumentParser) -> None:
    p = sub.add_parser("launcher", parents=[shared], help="install or remove the desktop app's Terminal command",
                       description=__doc__.splitlines()[0], allow_abbrev=False)
    p.set_defaults(command="launcher", handler=run_launcher, feedback=False)
    actions = p.add_subparsers(dest="launcher_action", metavar="ACTION", required=True)
    for name, help_text in (("install", "write the agentprov launcher that runs the app's own agentprov"),
                            ("remove", "delete the launcher this app made (never another agentprov)"),
                            ("status", "where a launcher is, what it runs, and whether its folder is on PATH")):
        a = actions.add_parser(name, parents=[shared], help=help_text, allow_abbrev=False)
        a.add_argument("--dir", metavar="DIR", help="the launcher's folder (default ~/.local/bin; another must exist "
                       "and be writable without administrator rights)")
        if name != "remove":
            a.add_argument("--app", metavar="EXE", help="the desktop app's executable (default: this program, when it "
                           "is the app's own agentprov)")
        a.add_argument("--format", choices=["text", "json"], default="text")


def run_launcher(ctx: Context) -> CommandResult:
    args = ctx.args
    result = CommandResult()
    env = _env(ctx)
    try:
        doc = {"install": _install, "remove": _remove, "status": _status}[args.launcher_action](args, env)
    except _Refused as exc:
        result.exit_code = 4
        result.refusal = exc.refusal
        for line in render_refusal(exc.refusal, details=None):
            result.error(line)
        return result
    except OSError as exc:
        result.exit_code = 3
        result.error(f"agentprov launcher: {type(exc).__name__}: {safe_text(exc.strerror or str(exc), 300)}")
        return result
    if args.format == "json":
        result.payload = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    else:
        result.payload = _text(doc).encode("utf-8")
    return result
