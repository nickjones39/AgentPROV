"""Check for Updates in the desktop app (D-1065, the GUI half). No Qt, no network.

The app keeps no network code (S11): every step is an ``agentprov update`` command of the configured CLI, run in the
background, and this module builds their argv and reads their JSON documents defensively (an older CLI without the
command, or an answer that is not the document, gives ``None`` and the reason, never a guess):

* ``update status --format json`` (``agentprov-update-status/0.1``, R0): the cached check, no network;
* ``update check --allow-network [--if-stale] [--bundle PATH] --gui-version V --format json``
  (``agentprov-update-check/0.1``, R2): GitHub's newest final release against this app and its CLI; ``--if-stale`` is
  the daily check at start-up (the CLI fetches at most once a local day, and not while ``update.auto_check`` is false);
* ``update download --allow-network --format json`` (``agentprov-update-download/0.1``, R2): the bundle, its
  ``SHA256SUMS`` and signature, verified by the CLI;
* ``update install --confirm --bundle PATH --gui-version V --format json`` (``agentprov-update-install/0.1``, R2): only
  after the user's confirmation; without a bundle (the app runs from a checkout or a package install),
  ``update install --format json`` only prints the upgrade command, which the app shows instead.

The check's ``behind`` flags say which part is older than the newest release (D-1070): the app itself, or only the
``agentprov`` program it runs (the configured checkout or package install, :attr:`Check.cli_only`). Replacing the
bundle cannot update that program, so for ``cli_only`` no bundle is downloaded.

The whole software (D-1130): when the program the app runs is older too and it is not the bundle's own copy (which a
bundle install updates with the app), ``update install --format json`` without a flag says how that program is
installed and which automatic path applies (:class:`Automatic`): a ``pip``, ``uv tool`` or ``pipx`` install is
upgraded from the release's verified wheels (``update download --package --allow-network``, then ``update install
--package --confirm``: the program's own installer, no dependency resolution, no index), a clean checkout on ``main``
with the project's remote is fast-forwarded (``update install --checkout --confirm --allow-network``), and anything
else gets the command to run. :class:`UpdatePlan` is the one confirmation's content: each part that will be replaced
(from which version to which, how it was verified, what is kept) and each part that cannot be, with why.

Every text the CLI returns is shown as plain, escaped text (S1, S3): :func:`agentprov_gui.text.clean` per line.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from agentprov.errors import IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

from agentprov_gui import __version__
from agentprov_gui import text as T

__all__ = [
    "AUTO_CHECK", "CHECK_FORMAT", "DOWNLOAD_FORMAT", "INSTALL_FORMAT", "LAST_NOTIFIED", "STATUS_FORMAT", "UNSIGNED_NOTE",
    "Automatic", "Check", "Download", "Install", "Part", "UpdatePlan", "app_bundle", "app_version", "check_argv",
    "checkout_install_argv", "download_argv", "install_argv", "notes_text", "notify", "package_download_argv",
    "package_install_argv", "parse_check", "parse_download", "parse_install", "plan", "plan_argv", "reason",
    "skip_argv", "status_argv",
]  # fmt: skip

CHECK_FORMAT: Final = "agentprov-update-check/0.1"
STATUS_FORMAT: Final = "agentprov-update-status/0.1"
DOWNLOAD_FORMAT: Final = "agentprov-update-download/0.1"
INSTALL_FORMAT: Final = "agentprov-update-install/0.1"
#: the settings: the daily check's standing consent (unset: on) and the newest release the app was told to skip
AUTO_CHECK: Final = "update.auto_check"
LAST_NOTIFIED: Final = "update.last_notified"
#: what the CLI says of a download checked against ``SHA256SUMS`` only (no release key listed in the package)
UNSIGNED_NOTE: Final = ("This package lists no release key, so the bundle is checked against SHA256SUMS only, which "
                        "does not prove who published it.")
#: the bundle folder per platform family, as the CLI's ``--bundle`` wants it (``agentprov.update.unpack.TOP``)
_TOP: Final = {"darwin": "AgentPROV.app", "linux": "AgentPROV", "win32": "AgentPROV"}
_RELEASE: Final = re.compile(r"\d{1,6}\.\d{1,6}\.\d{1,6}")  # the setting update.last_notified's form
_VERSION: Final = re.compile(r"\d{1,6}(?:\.\d{1,6}){0,3}(?:(?:a|b|rc)\d{1,6})?(?:\.post\d{1,6})?(?:\.dev\d{1,6})?")
_ERROR: Final = re.compile(r"\[([a-z0-9_.]+)\]")
_LIMITS: Final = IngestLimits().replace(max_json_bytes=1024 * 1024, max_json_depth=8)
NOTES_LINES: Final = 200


# ----------------------------------------------------------------------------------------------- what this app is
def app_bundle(executable: str | None = None, *, frozen: bool | None = None, platform: str | None = None) -> Path | None:
    """The desktop bundle's folder this app runs from (``AgentPROV.app`` on macOS, the ``AgentPROV`` folder on Linux
    and Windows), or ``None`` when it is not a frozen bundle (a checkout's ``uv run``, a package install): then the
    app never installs, it shows the upgrade command the CLI prints."""
    frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if not frozen:
        return None
    platform = sys.platform if platform is None else platform
    family = "darwin" if platform == "darwin" else "win32" if platform.startswith("win") else "linux"
    exe = Path(sys.executable if executable is None else executable)
    folder = exe.parents[2] if family == "darwin" and len(exe.parents) > 2 else exe.parent
    return folder if folder.name == _TOP[family] else None


def app_version() -> str | None:
    """This app's version for ``--gui-version`` (``None`` when it is not one the CLI compares)."""
    return __version__ if _VERSION.fullmatch(__version__) else None


# ----------------------------------------------------------------------------------------------- the commands
def _app(bundle: Path | None, gui: str | None) -> list[str]:
    return [*(["--bundle", str(bundle)] if bundle is not None else []), *(["--gui-version", gui] if gui else [])]


def status_argv(bundle: Path | None, gui: str | None) -> list[str]:
    """The cached check (R0, no network)."""
    return ["update", "status", *_app(bundle, gui), "--format", "json"]


def check_argv(bundle: Path | None, gui: str | None, *, if_stale: bool = False) -> list[str]:
    """Ask GitHub now (R2); ``if_stale``: the daily check at start-up."""
    return ["update", "check", "--allow-network", *(["--if-stale"] if if_stale else []), *_app(bundle, gui),
            "--format", "json"]


def download_argv() -> list[str]:
    """Download and verify this platform's bundle (R2)."""
    return ["update", "download", "--allow-network", "--format", "json"]


def install_argv(bundle: Path | None, gui: str | None) -> list[str]:
    """Install the verified download into the bundle (only after the user's confirmation), or, without a bundle, the
    command that prints how to upgrade this install."""
    if bundle is None:
        return ["update", "install", "--format", "json"]
    return ["update", "install", "--confirm", *_app(bundle, gui), "--format", "json"]


def plan_argv() -> list[str]:
    """How the agentprov program the app runs is installed and which automatic path updates it (changes nothing)."""
    return ["update", "install", "--format", "json"]


def package_download_argv() -> list[str]:
    """The release's wheels for a pip, uv tool or pipx install, verified as a bundle is (R2, D-1130)."""
    return ["update", "download", "--package", "--allow-network", "--format", "json"]


def package_install_argv() -> list[str]:
    """Install the verified wheels with the program's own installer (only after the user's confirmation)."""
    return ["update", "install", "--package", "--confirm", "--format", "json"]


def checkout_install_argv() -> list[str]:
    """Fast-forward a clean checkout on main and sync it (only after the user's confirmation; R2: git pull)."""
    return ["update", "install", "--checkout", "--confirm", "--allow-network", "--format", "json"]


def skip_argv(version: str) -> list[str]:
    """Skip This Version: the newest release the app has announced (it is not announced again)."""
    return ["settings", "set", LAST_NOTIFIED, version]


def reason(code: int, err: bytes) -> str:
    """Why a command gave no document, in plain words: no CLI (127), a CLI that could not run (124), else the CLI's
    own refusal line (``agentprov: error [code]: why`` becomes ``why (code)``), escaped."""
    if code == 127 and err == b"no CLI":
        return ("No agentprov program to run: set the AgentPROV checkout, or the agentprov installed with pip install "
                "agentprov, in Settings › General.")
    if code == 124:
        return f"agentprov could not be run or did not finish ({T.line(err.decode('ascii', 'replace'), 40)})."
    lines = [x for x in err.decode("utf-8", "replace").splitlines()
             if x.strip() and not re.match(r"(?:INFO|DEBUG) agentprov[\w.]*: ", x)]
    last = lines[-1] if lines else ""
    m = _ERROR.search(last)
    if m:
        why = last[m.end():].lstrip(": ").strip()
        return T.line(f"{why} ({m.group(1)})" if why else m.group(1), 400)
    return T.line(last, 400) if last else f"agentprov update ended with exit {code}."


def _document(code: int, out: bytes, formats: tuple[str, ...]) -> dict[str, Any] | None:
    if code != 0 or not out.strip():
        return None
    try:
        doc = strict_json_loads(out.strip(), _LIMITS)
    except IngestError:
        return None
    return doc if isinstance(doc, dict) and doc.get("format") in formats else None


def _text(value: Any, limit: int = 200) -> str | None:
    return T.clean(value, limit) if isinstance(value, str) and value else None


def _flag(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _seq(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


# ----------------------------------------------------------------------------------------------- the documents
@dataclass(frozen=True, slots=True)
class Check:
    """``agentprov-update-check/0.1`` (or the status document, its cached form), checked. Text is escaped already."""

    checked_at: str | None  # UTC, as the CLI wrote it
    fetched: bool
    core: str | None
    gui: str | None
    latest: str | None
    update_available: bool | None  # None: no component comparable
    published_at: str | None
    notes: str
    notes_truncated: bool
    platform: str | None
    asset: str | None  # this platform's bundle file name
    asset_size: int | None
    signed: bool  # the release publishes SHA256SUMS.sig
    auto_check: bool
    check_due: bool | None
    behind_core: bool | None = None  # the agentprov program the app runs is older than the newest release
    behind_gui: bool | None = None  # this app is older than it (None: not compared)

    @property
    def release(self) -> str | None:
        """The newest release as ``X.Y.Z`` (the form the setting ``update.last_notified`` holds), else ``None``."""
        return self.latest if self.latest is not None and _RELEASE.fullmatch(self.latest) else None

    @property
    def cli_only(self) -> bool:
        """Only the ``agentprov`` program the app runs is behind, not the app (D-1070): installing the app's bundle
        would not change that program, so its upgrade command is shown instead."""
        return self.behind_core is True and self.behind_gui is not True


def parse_check(code: int, out: bytes) -> Check | None:
    """``update check`` or ``update status`` with ``--format json``; ``None`` when the command failed or its answer is
    not that document (an older CLI)."""
    doc = _document(code, out, (CHECK_FORMAT, STATUS_FORMAT))
    if doc is None:
        return None
    current = _obj(doc.get("current"))
    behind = _obj(doc.get("behind"))
    assets = _seq(doc.get("assets"))
    asset = _obj(assets[0] if assets else None)
    return Check(_text(doc.get("checked_at"), 40), doc.get("fetched") is True, _text(current.get("core"), 40),
                 _text(current.get("gui"), 40), _text(doc.get("latest"), 40), _flag(doc.get("update_available")),
                 _text(doc.get("published_at"), 40), notes_text(doc.get("notes")), doc.get("notes_truncated") is True,
                 _text(doc.get("platform"), 40), _text(asset.get("name"), 200), _int(asset.get("size")),
                 isinstance(doc.get("signature_asset"), dict), doc.get("auto_check") is not False,
                 _flag(doc.get("check_due")), _flag(behind.get("core")), _flag(behind.get("gui")))


def notes_text(value: Any) -> str:
    """The release notes (the CLI's plain text, escaped and capped at 8000 characters) as display lines: each line
    escaped again where a code point would be (:func:`text.clean`), at most :data:`NOTES_LINES` lines."""
    if not isinstance(value, str) or not value.strip():
        return ""
    lines = value.split("\n")
    shown = [T.clean(x, 400) for x in lines[:NOTES_LINES]]
    if len(lines) > NOTES_LINES:
        shown.append(f"… ({len(lines) - NOTES_LINES} more lines)")
    return "\n".join(shown).strip("\n")


@dataclass(frozen=True, slots=True)
class Download:
    """``agentprov-update-download/0.1``: what was staged and how it was verified. ``kind`` ``package`` (D-1130) is
    the release's wheels for the agentprov program, with what installing them would do."""

    tag: str | None
    version: str | None
    asset: str | None
    size: int | None
    verification: str  # "sha256+signature" or "sha256"
    signed_by: str | None
    directory: str | None
    kind: str = "bundle"  # "bundle" or "package"
    wheels: tuple[str, ...] = ()
    installable: bool = False  # package: the installer can take the wheels without resolving anything
    problems: tuple[str, ...] = ()
    installer: str | None = None  # "pip", "uv pip", "pipx runpip"
    install_kind: str | None = None  # "pip", "uv-tool", "pipx"
    from_version: str | None = None
    restore: str | None = None  # the command that goes back (the previous version is not kept)

    @property
    def signed(self) -> bool:
        return "signature" in self.verification


def parse_download(code: int, out: bytes) -> Download | None:
    doc = _document(code, out, (DOWNLOAD_FORMAT,))
    if doc is None:
        return None
    asset = _obj(doc.get("asset"))
    verification = _text(doc.get("verification"), 40)
    if verification is None:
        return None  # a download the CLI did not say it verified is not one to install
    kind = "package" if doc.get("kind") == "package" else "bundle"
    wheels = tuple(T.clean(w.get("name"), 200) for w in _seq(doc.get("wheels"))[:10]
                   if isinstance(w, dict) and isinstance(w.get("name"), str))
    if kind == "package" and not wheels:
        return None
    return Download(_text(doc.get("tag"), 40), _text(doc.get("version") or doc.get("to_version"), 40),
                    _text(asset.get("name"), 200), _int(asset.get("size")), verification,
                    _text(doc.get("signed_by"), 120), _text(doc.get("dir"), 400), kind, wheels,
                    doc.get("installable") is True and kind == "package",
                    tuple(T.clean(x, 300) for x in _seq(doc.get("problems"))[:10] if isinstance(x, str)),
                    _text(doc.get("installer"), 40), _text(doc.get("install_kind"), 40),
                    _text(doc.get("from_version"), 40), _text(doc.get("restore_command"), 400))


@dataclass(frozen=True, slots=True)
class Automatic:
    """``update install``'s ``automatic`` (D-1130): which path updates the agentprov program the app runs (``how``:
    ``package``, ``checkout``, ``bundle`` or ``None``), whether it applies here, and why not."""

    how: str | None
    available: bool
    why: str | None
    installer: str | None = None
    root: str | None = None
    head: str | None = None  # checkout: the commit it is at


@dataclass(frozen=True, slots=True)
class Install:
    """``agentprov-update-install/0.1``: ``action`` is ``installed`` (quit and reopen), ``waiting-for-quit`` (Windows:
    applied once the app has quit), ``current`` (nothing to do) or ``command`` (a package install or a checkout: the
    command that upgrades it, and :attr:`automatic`, the path the app may take after the user's confirmation)."""

    action: str
    kind: str | None
    lines: tuple[str, ...]
    command: tuple[str, ...]  # the upgrade command (``command``), else empty
    text: str | None
    rollback: str | None
    to_version: str | None
    automatic: Automatic | None = None
    from_version: str | None = None
    restore: str | None = None  # package (D-1130): the command that goes back; checkout: the reset and the sync
    synced: bool | None = None  # checkout: whether uv sync ran


def parse_install(code: int, out: bytes) -> Install | None:
    doc = _document(code, out, (INSTALL_FORMAT,))
    if doc is None:
        return None
    action = doc.get("action")
    if action not in ("installed", "waiting-for-quit", "current", "command"):
        return None
    lines = _seq(doc.get("lines"))
    command = _seq(doc.get("command"))
    auto = _obj(doc.get("automatic"))
    how = auto.get("how") if auto.get("how") in ("package", "checkout", "bundle") else None
    automatic = Automatic(how, auto.get("available") is True and how in ("package", "checkout"),
                          _text(auto.get("why"), 300), _text(auto.get("installer"), 40),
                          _text(auto.get("root"), 400),
                          auto["head"][:12] if isinstance(auto.get("head"), str) and re.fullmatch(
                              r"[0-9a-f]{40,64}", auto["head"]) else None) if auto else None
    restore = doc.get("restore")
    restore_text = (" && ".join(" ".join(T.clean(a, 300) for a in c if isinstance(a, str)) for c in restore[:3]
                                if isinstance(c, list)) if isinstance(restore, list) else None)
    return Install(str(action), _text(doc.get("kind"), 40),
                   tuple(T.clean(x, 400) for x in lines[:20] if isinstance(x, str)),
                   tuple(T.clean(x, 400) for x in command[:20] if isinstance(x, str)), _text(doc.get("text"), 400),
                   _text(doc.get("rollback_command"), 400), _text(doc.get("to_version"), 40), automatic,
                   _text(doc.get("from_version"), 40), _text(doc.get("restore_command"), 400) or restore_text or None,
                   _flag(doc.get("synced")))


# ----------------------------------------------------------------------------------------------- the one confirmation
@dataclass(frozen=True, slots=True)
class Part:
    """One part an update replaces: what it is, the versions, how it was verified, what is kept, what runs."""

    name: str  # "The app" or "The agentprov program"
    detail: str  # the folder, the install kind, the checkout
    from_version: str | None
    to_version: str | None
    verified: str  # how the bytes were verified (or, for a checkout, where they come from)
    keeps: str  # what stays to go back to, or that nothing does
    argv: tuple[str, ...]  # the command that installs it, run after the confirmation
    signed: bool = True


@dataclass(frozen=True, slots=True)
class UpdatePlan:
    """What Download and Install… asks about once (D-1130): the parts it will replace and those it cannot, with why
    and the command to run instead."""

    parts: tuple[Part, ...]
    cannot: tuple[tuple[str, str, str | None], ...]  # (what, why, the command the user runs instead)
    #: what runs after the parts, said before the confirmation (the backend environments' rebuild), else ``None``
    followup: str | None = None

    @property
    def to_version(self) -> str | None:
        return next((p.to_version for p in self.parts if p.to_version), None)


def _verified(d: Download) -> str:
    return f"{d.verification}{', signed by ' + d.signed_by if d.signed_by else ''}"


def plan(*, bundle: Path | None, gui: str | None, app: Download | None, program: Install | None,
         package: Download | None, package_refused: str | None = None, core: str | None = None) -> UpdatePlan:
    """The confirmation's content from what the CLI said: the app's verified bundle (``app``), how the program is
    installed (``program``, ``update install``'s plan) and, for a package install, its verified wheels."""
    parts: list[Part] = []
    cannot: list[tuple[str, str, str | None]] = []
    if app is not None and bundle is not None:
        parts.append(Part("The app", T.line(str(bundle), 300), gui, app.version, _verified(app),
                          f"the current version is kept beside it in .AgentPROV-previous (agentprov update rollback "
                          f"--yes --bundle {T.line(str(bundle), 300)})", tuple(install_argv(bundle, gui)), app.signed))
    if program is not None:
        auto = program.automatic
        name = "The agentprov program"
        if auto is not None and auto.how == "package" and auto.available:
            if package is not None and package.installable:
                parts.append(Part(name, f"a {package.install_kind or 'package'} install", package.from_version or core,
                                  package.version, f"{_verified(package)}: {', '.join(package.wheels)}",
                                  "the previous version is not kept; to go back, run (it installs from PyPI): "
                                  f"{package.restore or 'the install command of that version'}",
                                  tuple(package_install_argv()), package.signed))
            else:
                why = ("; ".join(package.problems) if package is not None and package.problems else package_refused
                       or "the release's wheels could not be downloaded and verified")
                cannot.append((name, f"its new version needs more than the release's verified wheels ({why}), and "
                                     "nothing is fetched from PyPI", program.text))
        elif auto is not None and auto.how == "checkout" and auto.available:
            where = T.line(auto.root or "the checkout", 300)
            at = f"commit {auto.head}" if auto.head else (program.from_version or core)
            parts.append(Part(name, f"the checkout {where} (main, clean)", at, "origin/main's newest commit",
                              "git pull --ff-only origin main from the project's repository, then uv sync --frozen "
                              "--group docs; nothing is discarded (no reset, no stash, no other branch), and it is "
                              "skipped, with the reason, if main has commits origin lacks or cannot fast-forward",
                              "the old commit stays in git's history (the result names the git reset --keep that "
                              "goes back)", tuple(checkout_install_argv())))
        elif auto is not None and auto.how == "bundle":
            pass  # the app's own copy: the app's part updates it
        else:
            why = auto.why if auto is not None and auto.why else "agentprov cannot update this install itself"
            cannot.append((name, why, program.text))
    return UpdatePlan(tuple(parts), tuple(cannot))


def notify(check: Check | None, last_notified: Any) -> bool:
    """Whether the start-up notice is shown: the CLI says a newer release exists, the daily check is on, and that
    release is not the one the user chose to skip (``update.last_notified``)."""
    if check is None or check.update_available is not True or not check.auto_check or check.release is None:
        return False
    return not (isinstance(last_notified, str) and last_notified == check.release)
