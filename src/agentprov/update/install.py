"""Installing a verified bundle, and the one-step rollback (D-1065).

The desktop app is a one-folder bundle (``gui/tools/build_bundle.py``): ``AgentPROV.app`` on macOS, an ``AgentPROV``
folder on Linux and Windows. ``agentprov update install --confirm --bundle PATH`` replaces that folder:

1. the staged download is checked again (its sha256 against ``staged.json`` and ``SHA256SUMS``, and the signature rule
   of :mod:`.verify`), then unpacked (:mod:`.unpack`) into ``.AgentPROV-update/`` **beside** the bundle, so the swap is
   a rename on one file system;
2. **macOS and Linux:** the running bundle is renamed to ``.AgentPROV-previous/<name>`` and the new one renamed into
   its place, at once (a running process keeps its open files; the user is told to quit and reopen the app now);
3. **Windows:** a running ``.exe`` and its folder cannot be renamed, so nothing is replaced while the app runs: the new
   folder and a plan wait in ``.AgentPROV-update/``, and a helper (``python -I -m agentprov.update.apply PLAN``, this
   interpreter, detached) retries the same two renames until the app has quit, for at most :data:`WAIT_S` seconds, and
   writes its result to ``$AGENTPROV_HOME/update/applied.json``.

The previous version stays in ``.AgentPROV-previous/`` (one version; an older one is removed when a newer install
succeeds). ``agentprov update rollback --yes --bundle PATH`` swaps the two back (on Windows through the same helper).
Nothing outside the bundle's parent folder and ``$AGENTPROV_HOME/update`` is written.

A **package install** (``pip``, ``uv tool``, ``pipx``) is not replaced here: :func:`package_install` names the command
that upgrades it, and :mod:`.package` installs the release's verified wheels with that installer after the user's
confirmation (D-1130); a checkout is updated by :mod:`.checkout`. The **bundle's own agentprov** (``AgentPROV
--cli``, :mod:`agentprov.cli.frozen`) is part of the bundle and is updated with it; when it is the program doing the
install, everything it needs after the swap is imported before it (a lazy import would read the new bundle's files),
and on Windows the helper runs from a copy of the new bundle in ``.AgentPROV-update-helper/`` beside the app, since a
helper running from the folder it renames could never rename it.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import plistlib
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping
from importlib import metadata
from pathlib import Path
from typing import Any, Final

from agentprov.update.releases import UpdateError, utc_text, version_key
from agentprov.update.unpack import TOP, unpack, validate_tree

__all__ = ["HELPER_DIR", "PREVIOUS_DIR", "STAGE_DIR", "bundle_version", "check_bundle", "helper_argv",
           "install_bundle", "package_install", "rollback_bundle", "swap_in", "swap_back"]

STAGE_DIR: Final = ".AgentPROV-update"
PREVIOUS_DIR: Final = ".AgentPROV-previous"
#: the Windows helper's copy of a bundle when the bundle's own agentprov installs (D-1130)
HELPER_DIR: Final = ".AgentPROV-update-helper"
PLAN_FORMAT: Final = "agentprov-update-plan/0.1"
#: how long the Windows helper waits for the app to quit
WAIT_S: Final = 1800
_MARKER: Final = ".agentprov-update"
#: the bundle's executable below its folder, per platform family
EXECUTABLE: Final = {"macos": ("Contents", "MacOS", "AgentPROV"), "linux": ("AgentPROV",), "windows": ("AgentPROV.exe",)}


def family(label: str) -> str:
    return label.split("-", 1)[0]


def check_bundle(bundle: Path, label: str) -> Path:
    """``--bundle``: the app's own folder (absolute, not a link, the platform's name, its executable present) in a
    folder this user can write."""
    fam = family(label)
    path = Path(os.path.abspath(bundle))
    if path.name != TOP[fam]:
        raise UpdateError(f"--bundle must name the app's folder ({TOP[fam]})", code="update.install.bundle",
                          exit_code=2)
    if path.is_symlink() or not path.is_dir() or not path.joinpath(*EXECUTABLE[fam]).is_file():
        raise UpdateError("--bundle is not an AgentPROV bundle folder", code="update.install.bundle", exit_code=2)
    if not os.access(path.parent, os.W_OK):
        raise UpdateError("the folder that holds the app cannot be written by this user (on macOS, an app run from "
                          "the disk image: move it to Applications first)", code="update.install.readonly", exit_code=4)
    return path


def bundle_version(bundle: Path, label: str) -> str | None:
    """The bundle's version where the bundle records it (macOS: ``Info.plist``'s ``CFBundleShortVersionString``);
    ``None`` elsewhere or when unreadable (the desktop app passes ``--gui-version``)."""
    if family(label) != "macos":
        return None
    try:
        with open(bundle / "Contents" / "Info.plist", "rb") as fh:
            data = fh.read(1024 * 1024 + 1)
        doc = plistlib.loads(data) if len(data) <= 1024 * 1024 else None
    except (OSError, plistlib.InvalidFileException, ValueError):
        return None
    value = doc.get("CFBundleShortVersionString") if isinstance(doc, dict) else None
    return value if version_key(value) is not None else None


def package_install(*, prefix: str | None = None, executable: str | None = None,
                    direct_url: str | None = None, frozen: bool | None = None) -> dict[str, Any]:
    """How this ``agentprov`` was installed and the command that upgrades it: ``bundle`` (the desktop app's own copy,
    D-1130: updated with the app), ``checkout`` (an editable install: no command, update with git), ``uv-tool``
    (``uv tool upgrade agentprov``), ``pipx`` or ``pip`` (this interpreter's ``-m pip install --upgrade agentprov``)."""
    if frozen if frozen is not None else getattr(sys, "frozen", False):
        return {"kind": "bundle", "command": None,
                "text": "this agentprov is the desktop app's own copy: it is updated with the app (About › Download "
                        "and Install…, or agentprov update install --confirm --bundle PATH)"}
    root = Path(sys.prefix if prefix is None else prefix)
    if direct_url is None:
        try:
            direct_url = metadata.distribution("agentprov").read_text("direct_url.json")
        except metadata.PackageNotFoundError:
            direct_url = None
    editable = False
    if direct_url:
        try:
            doc = json.loads(direct_url)
            editable = isinstance(doc, dict) and isinstance(doc.get("dir_info"), dict) and \
                doc["dir_info"].get("editable") is True
        except ValueError:
            editable = False
    if editable:
        return {"kind": "checkout", "command": None,
                "text": "this agentprov runs from a checkout: update it with git (git pull --ff-only on main), then "
                        "uv sync --frozen --group docs"}
    if (root / "uv-receipt.toml").is_file():
        return {"kind": "uv-tool", "command": ["uv", "tool", "upgrade", "agentprov"],
                "text": "uv tool upgrade agentprov"}
    if "pipx" in root.parts and "venvs" in root.parts:
        return {"kind": "pipx", "command": ["pipx", "upgrade", "agentprov"], "text": "pipx upgrade agentprov"}
    argv = [executable if executable is not None else sys.executable, "-m", "pip", "install", "--upgrade",
            "agentprov"]
    return {"kind": "pip", "command": argv,
            "text": subprocess.list2cmdline(argv) if os.name == "nt" else shlex.join(argv)}


# --------------------------------------------------------------------------------------------------------------
# The swaps (the Windows helper runs the same functions)
# --------------------------------------------------------------------------------------------------------------


def swap_in(bundle: Path, new: Path, previous: Path) -> None:
    """``bundle`` becomes ``previous`` and ``new`` becomes ``bundle``: two renames in one folder. An older previous
    version is set aside first and removed only after both renames succeeded; a failure puts everything back."""
    previous.parent.mkdir(exist_ok=True)
    older = previous.with_name(previous.name + ".older")
    if older.exists():
        shutil.rmtree(older)
    had_previous = previous.exists()
    if had_previous:
        os.rename(previous, older)
    try:
        os.rename(bundle, previous)
    except OSError:
        if had_previous:
            os.rename(older, previous)
        raise
    try:
        os.rename(new, bundle)
    except OSError:
        os.rename(previous, bundle)
        if had_previous:
            os.rename(older, previous)
        raise
    if had_previous:
        shutil.rmtree(older, ignore_errors=True)


def swap_back(bundle: Path, previous: Path) -> None:
    """The rollback: ``previous`` and ``bundle`` change places (three renames; a failure puts them back)."""
    aside = previous.with_name(previous.name + ".rollback")
    if aside.exists():
        shutil.rmtree(aside)
    os.rename(bundle, aside)
    try:
        os.rename(previous, bundle)
    except OSError:
        os.rename(aside, bundle)
        raise
    os.rename(aside, previous)


# --------------------------------------------------------------------------------------------------------------
# Install and rollback
# --------------------------------------------------------------------------------------------------------------


def _new_stage(parent: Path) -> Path:
    """``.AgentPROV-update`` beside the bundle, made fresh. A leftover of this module (its marker present, no waiting
    plan) is removed; anything else there refuses the install."""
    stage = parent / STAGE_DIR
    if stage.exists() or stage.is_symlink():
        if stage.is_symlink() or not (stage / _MARKER).is_file():
            raise UpdateError(f"{STAGE_DIR} beside the app is not this program's: remove it first",
                              code="update.install.stage", exit_code=4)
        if (stage / "plan.json").is_file():
            raise UpdateError("an update is already waiting for the app to quit (quit AgentPROV to apply it)",
                              code="update.install.pending", exit_code=4)
        shutil.rmtree(stage)
    stage.mkdir()
    (stage / _MARKER).write_bytes(b"D-1065\n")
    return stage


def _before_swap() -> None:
    """Import now what runs after the swap (D-1130): when the bundle's own agentprov swaps the bundle it runs from, a
    module first imported afterwards would come from the new bundle's files."""
    import agentprov.io.replace_retry  # noqa: F401
    import agentprov.update.releases  # noqa: F401


def _record(home: Path, doc: Mapping[str, Any]) -> None:
    from agentprov.io.replace_retry import atomic_write_bytes_retrying
    from agentprov.update.releases import update_dir

    path = update_dir(home) / "installed.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes_retrying(path, json.dumps(dict(doc), sort_keys=True, separators=(",", ":")).encode() + b"\n")


def _plan(stage: Path, home: Path, *, op: str, bundle: Path, previous: Path, new: Path | None,
          record: Mapping[str, Any]) -> Path:
    plan = {"format": PLAN_FORMAT, "op": op, "bundle": str(bundle), "previous": str(previous),
            "new": None if new is None else str(new), "stage": str(stage), "wait_s": WAIT_S,
            "result": str(home / "update" / "applied.json"), "record": dict(record)}
    path = stage / "plan.json"
    path.write_bytes(json.dumps(plan, sort_keys=True, indent=1).encode("utf-8") + b"\n")
    return path


def helper_argv(plan: Path, *, frozen: bool | None = None, running: Path | None = None) -> list[str]:
    """The Windows helper's argv: ``python -I -m agentprov.update.apply PLAN`` with this interpreter; in the bundle's
    own agentprov (frozen), the executable of a copy of the running bundle (``running``: the folder of this program's
    executable), made in :data:`HELPER_DIR` beside the app: the running bundle can never rename the folder it runs
    from. The copy is of the running bundle, never of the one a rollback restores (D-1130 review): that one may be older
    than D-1130 and not answer ``-m agentprov.update.apply`` at all (0.2.0's would open the app instead), while the
    running one wrote the plan and so reads it."""
    if not (frozen if frozen is not None else getattr(sys, "frozen", False)):
        return [sys.executable, "-I", "-m", "agentprov.update.apply", str(plan)]
    doc = json.loads(plan.read_bytes())
    source = running if running is not None else Path(sys.executable).resolve().parent
    if not source.joinpath(*EXECUTABLE["windows"]).is_file():
        raise UpdateError("the running app's executable was not found, so the update helper cannot be started",
                          code="update.install.stage", exit_code=3)
    bundle = Path(doc["bundle"])
    helper = bundle.parent / HELPER_DIR
    _clear_helper(bundle.parent)
    helper.mkdir()
    (helper / _MARKER).write_bytes(b"D-1130\n")
    copy = helper / source.name
    shutil.copytree(source, copy, symlinks=True)
    return [str(copy.joinpath(*EXECUTABLE["windows"])), "-I", "-m", "agentprov.update.apply", str(plan)]


def _clear_helper(parent: Path) -> None:
    """Remove a helper copy an earlier update left (its marker present); a file still in use stays until next time."""
    helper = parent / HELPER_DIR
    if helper.is_symlink():
        raise UpdateError(f"{HELPER_DIR} beside the app is a link: remove it first", code="update.install.stage",
                          exit_code=4)
    if helper.exists():
        if not (helper / _MARKER).is_file():
            raise UpdateError(f"{HELPER_DIR} beside the app is not this program's: remove it first",
                              code="update.install.stage", exit_code=4)
        shutil.rmtree(helper, ignore_errors=True)
        if helper.exists():
            raise UpdateError(f"the previous update's helper in {HELPER_DIR} is still running", code=
                              "update.install.pending", exit_code=4)


def start_helper(plan: Path) -> int:
    """Start the helper (:func:`helper_argv`; detached, no window); its pid."""
    argv = helper_argv(plan)
    flags = 0
    if os.name == "nt":
        flags = (getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                 | getattr(subprocess, "CREATE_NO_WINDOW", 0))
    proc = subprocess.Popen(argv,  # noqa: S603
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            close_fds=True, creationflags=flags, start_new_session=os.name != "nt")
    return proc.pid


def install_bundle(bundle: Path, archive: Path, *, label: str, version: str, home: Path, current: str | None,
                   run: Callable[..., Any] | None = None, helper: Callable[[Path], int] = start_helper,
                   now: dt.datetime | None = None) -> dict[str, Any]:
    """Unpack the verified ``archive`` beside ``bundle`` and swap it in (now, or on Windows after the app has quit).
    The caller has verified ``archive`` and checked ``bundle`` (:func:`check_bundle`)."""
    _before_swap()
    fam = family(label)
    previous = bundle.parent / PREVIOUS_DIR / bundle.name
    stage = _new_stage(bundle.parent)
    try:
        new = unpack(archive, stage / "new", label, run=run)
        if not new.joinpath(*EXECUTABLE[fam]).is_file():
            raise UpdateError("the new bundle has no AgentPROV executable", code="update.archive")
        found = bundle_version(new, label)
        if found is not None and found != version:
            raise UpdateError("the new bundle's version is not the release's", code="update.archive")
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    record = {"format": "agentprov-update-installed/0.1", "bundle": str(bundle), "previous": str(previous),
              "from_version": current, "to_version": version, "platform": label,
              "at": utc_text(now or dt.datetime.now(dt.UTC))}
    if fam == "windows":
        plan = _plan(stage, home, op="install", bundle=bundle, previous=previous, new=new, record=record)
        pid = helper(plan)
        _record(home, {**record, "state": "waiting", "helper_pid": pid})
        return {**record, "action": "waiting-for-quit", "helper_pid": pid, "plan": str(plan)}
    try:
        swap_in(bundle, new, previous)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    _record(home, {**record, "state": "installed"})
    return {**record, "action": "installed"}


def rollback_bundle(bundle: Path, *, label: str, home: Path, helper: Callable[[Path], int] = start_helper,
                    now: dt.datetime | None = None) -> dict[str, Any]:
    """Swap the bundle with the version kept in ``.AgentPROV-previous`` (which then holds the one rolled back from)."""
    _before_swap()
    fam = family(label)
    previous = bundle.parent / PREVIOUS_DIR / bundle.name
    if previous.is_symlink() or not previous.joinpath(*EXECUTABLE[fam]).is_file():
        raise UpdateError("there is no previous version beside the app to roll back to", code="update.rollback.none",
                          exit_code=4)
    validate_tree(previous)
    record = {"format": "agentprov-update-installed/0.1", "bundle": str(bundle), "previous": str(previous),
              "from_version": bundle_version(bundle, label), "to_version": bundle_version(previous, label),
              "platform": label, "at": utc_text(now or dt.datetime.now(dt.UTC)), "rollback": True}
    if fam == "windows":
        stage = _new_stage(bundle.parent)
        plan = _plan(stage, home, op="rollback", bundle=bundle, previous=previous, new=None, record=record)
        pid = helper(plan)
        _record(home, {**record, "state": "waiting", "helper_pid": pid})
        return {**record, "action": "waiting-for-quit", "helper_pid": pid, "plan": str(plan)}
    swap_back(bundle, previous)
    _record(home, {**record, "state": "rolled-back"})
    return {**record, "action": "rolled-back"}
