"""``agentprov update``: Check for Updates, a verified download and the desktop bundle's install (D-1065).

    agentprov update check --allow-network [--if-stale] [--bundle PATH] [--gui-version V] [--format text|json]
    agentprov update status [--bundle PATH] [--gui-version V] [--format text|json]
    agentprov update download --allow-network [--package] [--dir DIR] [--format text|json]
    agentprov update install [--confirm --bundle PATH | --confirm --package | --confirm --checkout --allow-network]
                             [--gui-version V] [--dir DIR] [--format text|json]
    agentprov update rollback --yes --bundle PATH [--format text|json]

``check`` asks the GitHub releases API of the public repository (nickjones39/AgentPROV) for the newest final release
and compares it with this ``agentprov`` and, with ``--bundle`` or ``--gui-version``, the desktop app; it needs
``--allow-network`` (exit 4 without it) and caches the answer in ``$AGENTPROV_HOME/update/check.json``. With
``--if-stale`` it fetches only while the setting ``update.auto_check`` is not false (unset: on) and no check was made
today (local time): the desktop app's daily check. ``status`` reads the cache only (no network).

``download`` fetches this platform's bundle, ``SHA256SUMS`` and, when published, ``SHA256SUMS.sig`` into
``$AGENTPROV_HOME/update/staging/<platform>/``, and refuses on any mismatch: the list's signature (against the release
keys in the package; ``ssh-keygen -Y verify``), the bundle's sha256, the archive's members. ``install --confirm
--bundle PATH`` checks the staged files again and replaces the app's folder, keeping the previous version beside it
for ``rollback`` (macOS and Linux at once; Windows once the app has quit). The bundle's own ``agentprov`` (``AgentPROV
--cli``) is part of it and is updated with it (D-1130).

A package install of ``agentprov`` (``pip``, ``uv tool``, ``pipx``; D-1130): ``download --package`` fetches the
release's wheels (``agentprov``, ``agentprov-capture`` and, when installed, ``agentprov-zenodo``) and verifies them as a
bundle is verified; ``install --package --confirm`` installs exactly those files with the program's own installer, with
no dependency resolution and no index (never PyPI), refusing when the new wheels need anything the installed version did
not; the previous version is not kept (the result names the command that goes back). A checkout: ``install --checkout
--confirm --allow-network`` runs ``git pull --ff-only origin main`` and ``uv sync --frozen --group docs``, only for a
clean tree on ``main`` whose remote is the project's. Without any of these, ``install`` prints the command that upgrades
this ``agentprov`` and says which automatic path applies (``automatic``); it changes nothing.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any, Final

from agentprov.cli.common import CliUsageError, CommandResult, Context, Refusal, UnsupportedCapability, safe_text

STATUS_FORMAT: Final = "agentprov-update-status/0.1"
DOWNLOAD_FORMAT: Final = "agentprov-update-download/0.1"
INSTALL_FORMAT: Final = "agentprov-update-install/0.1"
#: seams for the tests, which never open a socket or start a process: the release keys file, the ``run`` function of
#: the macOS disk-image steps, and the Windows helper's starter (``None``: the module defaults)
SIGNERS: Path | None = None
DMG_RUN: Any = None
HELPER: Any = None
#: D-1130's seams (``None``: the real ones): how this agentprov was installed (``package_install``), the installed
#: distributions (``package.installed``), ``shutil.which``, whether pip is importable, the installer's and git's ``run``,
#: and the editable install's checkout folder
KIND: Any = None
HAVE: Any = None
WHICH: Any = None
HAS_PIP: Any = None
INSTALL_RUN: Any = None
GIT_RUN: Any = None
CHECKOUT_ROOT: Any = None
#: the job records the running-job guard reads (``agentprov.jobs.record.list_jobs``; a seam for the tests)
JOBS: Any = None
#: D-1130 review seams: the extras installed here (``checkout.installed_extras``), the environment this agentprov runs
#: from (``sys.prefix``), and the folders a package install's files and commands live in (``package.install_folders``)
EXTRAS: Any = None
PREFIX: Any = None
FOLDERS: Any = None


def _install_folders(kind: str) -> list[Path]:
    from agentprov.update.package import install_folders

    return list(FOLDERS(kind) if FOLDERS is not None else install_folders(kind, which=_which()))


def _extras() -> list[str]:
    from agentprov.update.checkout import installed_extras

    return list(EXTRAS() if EXTRAS is not None else installed_extras())


def _prefix() -> str:
    import sys

    return str(PREFIX() if PREFIX is not None else sys.prefix)


def _not_busy(home: Path, folder: Path | list[Path], what: str) -> None:
    """D-1130: nothing is replaced under a running job that runs from ``folder`` (or any of a list)."""
    from agentprov.update.busy import refuse_if_busy

    refuse_if_busy(home, folder if isinstance(folder, list) else [folder], what, jobs=JOBS)


def register(sub: Any, shared: argparse.ArgumentParser) -> None:
    from agentprov.update.releases import PLATFORMS

    p = sub.add_parser("update", parents=[shared], help="check for a new release; download, verify and install it",
                       description=__doc__.splitlines()[0], allow_abbrev=False)
    p.set_defaults(command="update", handler=run_update, feedback=False)
    actions = p.add_subparsers(dest="update_action", metavar="ACTION", required=True)

    def common(parser: argparse.ArgumentParser, *, bundle: bool = True) -> None:
        if bundle:
            parser.add_argument("--bundle", metavar="PATH",
                                help="the desktop app's folder (AgentPROV.app, or the AgentPROV folder on Linux and "
                                     "Windows); the desktop app passes its own")
            parser.add_argument("--gui-version", metavar="VERSION", help="the desktop app's version (default: from "
                                "the bundle where it records it, macOS)")
        parser.add_argument("--platform", choices=PLATFORMS, help="the bundle platform (default: this machine's)")
        parser.add_argument("--format", choices=["text", "json"], default="text")

    c = actions.add_parser("check", parents=[shared], allow_abbrev=False,
                           help="ask GitHub for the newest release and compare it with what is installed (network)")
    c.add_argument("--allow-network", action="store_true", help="required (one public URL, no key)")
    c.add_argument("--if-stale", action="store_true",
                   help="fetch only when the setting update.auto_check is not false and no check was made today "
                        "(local time): the desktop app's daily check; otherwise report the cached check")
    common(c)
    s = actions.add_parser("status", parents=[shared], allow_abbrev=False,
                           help="the cached check, the setting update.auto_check and whether a check is due (no "
                                "network)")
    common(s)
    d = actions.add_parser("download", parents=[shared], allow_abbrev=False,
                           help="download this platform's bundle and SHA256SUMS (and its signature) and verify them "
                                "(network)")
    d.add_argument("--allow-network", action="store_true", help="required (GitHub's release files)")
    d.add_argument("--package", action="store_true",
                   help="the release's wheels for this agentprov's pip, uv tool or pipx install instead of the app's "
                        "bundle (D-1130)")
    d.add_argument("--dir", metavar="DIR", help="the staging folder (default: $AGENTPROV_HOME/update/staging/PLATFORM, "
                                                "or .../staging/package with --package)")
    common(d, bundle=False)
    i = actions.add_parser("install", parents=[shared], allow_abbrev=False,
                           help="install the verified download into the desktop app's folder (--confirm --bundle) or "
                                "this package install (--confirm --package), fast-forward this checkout (--confirm "
                                "--checkout), or print the command that upgrades this agentprov")
    i.add_argument("--confirm", action="store_true",
                   help="required with --bundle, --package or --checkout: replace what they name")
    i.add_argument("--package", action="store_true",
                   help="install the verified wheels download --package staged, with this program's own installer "
                        "(no dependency resolution, no index)")
    i.add_argument("--checkout", action="store_true",
                   help="git pull --ff-only origin main and uv sync --frozen --group docs in this agentprov's "
                        "checkout (clean, on main, the project's remote only); needs --allow-network")
    i.add_argument("--allow-network", action="store_true", help="required with --checkout (git pull)")
    i.add_argument("--dir", metavar="DIR", help="the staging folder download used")
    common(i)
    r = actions.add_parser("rollback", parents=[shared], allow_abbrev=False,
                           help="swap the desktop app with the version the last install kept beside it")
    r.add_argument("--yes", action="store_true", help="required: replace the app's folder")
    r.add_argument("--bundle", metavar="PATH", required=True, help="the desktop app's folder")
    r.add_argument("--platform", choices=PLATFORMS, help="the bundle platform (default: this machine's)")
    r.add_argument("--format", choices=["text", "json"], default="text")


def _payload(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"


def transport() -> Any:
    """The HTTP transport (``UrllibTransport``); a seam for the tests, which never open a socket."""
    from agentprov.raw.fetch import UrllibTransport

    return UrllibTransport()


def _signers() -> Path:
    from agentprov.update import ALLOWED_SIGNERS

    return SIGNERS if SIGNERS is not None else ALLOWED_SIGNERS


def _label(args: Any) -> str:
    from agentprov.update.releases import platform_label

    label = getattr(args, "platform", None) or platform_label()
    if label is None:
        raise UnsupportedCapability("agentprov update: no desktop bundle is built for this platform",
                                    refusal=Refusal("update.platform", "update", "unsupported",
                                                    ("no desktop bundle is built for this platform",)))
    return str(label)


def _gui(args: Any, label: str) -> str | None:
    from agentprov.update.install import bundle_version
    from agentprov.update.releases import version_key

    given = getattr(args, "gui_version", None)
    if given is not None:
        if version_key(given) is None:
            raise CliUsageError("agentprov update: --gui-version is not a version (X.Y.Z)")
        return str(given)
    bundle = getattr(args, "bundle", None)
    return bundle_version(Path(bundle), label) if bundle else None


def _allowed(args: Any, what: str) -> None:
    from agentprov.raw.fetch import NetworkRefusedError

    if not args.allow_network:
        raise NetworkRefusedError(f"agentprov update {what} reads GitHub's release of the public repository: give "
                                  "--allow-network")


def _status(home: Path, args: Any, label: str | None, now: dt.datetime) -> dict[str, Any]:
    from agentprov import settings
    from agentprov.update.releases import check_document, check_due, read_cache
    from agentprov.versions import __version__

    cached = read_cache(home)
    checked, release = cached if cached is not None else (None, None)
    auto = settings.get("update.auto_check", home=home) is not False
    return check_document(release, core=__version__, gui=_gui(args, label) if label else None, label=label,
                          checked_at=checked, fetched=False, auto_check=auto, due=check_due(checked, now))


def run_update(ctx: Context) -> CommandResult:
    from agentprov.cli.live.envs import agentprov_home

    args = ctx.args
    home = agentprov_home(ctx.env)
    result = CommandResult()
    action = args.update_action
    now = dt.datetime.now(dt.UTC)
    if action in ("check", "status"):
        from agentprov.update.releases import platform_label

        label = args.platform or platform_label()
        if action == "check":
            _allowed(args, "check")
            doc = _status(home, args, label, now)
            if args.if_stale and not (doc["auto_check"] and doc["check_due"]):
                why = "the setting update.auto_check is off" if not doc["auto_check"] else "already checked today"
                result.output(f"update: nothing fetched: {why}")
            else:
                doc = _check(home, args, label, now)
        else:
            doc = {**_status(home, args, label, now), "format": STATUS_FORMAT}
        if args.format == "json":
            result.payload = _payload(doc)
        else:
            _check_text(result, doc)
        result.counters = {"update_available": int(doc["update_available"] is True)}
    elif action == "download":
        _allowed(args, "download")
        doc = _download_package(home, args, now) if args.package else _download(home, args, now)
        if args.format == "json":
            result.payload = _payload(doc)
        elif args.package:
            for line in doc["lines"]:
                result.output(line)
        else:
            result.output(f"update: {doc['asset']['name']} of {doc['tag']} downloaded and verified "
                          f"({doc['verification']}{', signed by ' + doc['signed_by'] if doc['signed_by'] else ''}) "
                          f"into {safe_text(doc['dir'], 300)}")
            if doc["verification"] == "sha256":
                result.output("update: this package lists no release key, so the bundle is checked against "
                              "SHA256SUMS only, which does not prove who published it")
            result.output("install it with: agentprov update install --confirm --bundle PATH")
        result.counters = {"downloaded": 1}
    elif action == "install":
        doc = _install(home, args, now)
        if args.format == "json":
            result.payload = _payload(doc)
        else:
            for line in doc["lines"]:
                result.output(line)
        result.counters = {"installed": int(doc["action"] in ("installed", "waiting-for-quit"))}
    elif action == "rollback":
        doc = _rollback(home, args, now)
        if args.format == "json":
            result.payload = _payload(doc)
        else:
            for line in doc["lines"]:
                result.output(line)
        result.counters = {"rolled_back": 1}
    return result


def _check(home: Path, args: Any, label: str | None, now: dt.datetime) -> dict[str, Any]:
    from agentprov.update.releases import fetch_releases, latest_release, parse_releases, write_cache

    release = latest_release(parse_releases(fetch_releases(transport())))
    write_cache(home, release, now)
    return {**_status(home, args, label, now), "fetched": True}


def _check_text(result: CommandResult, doc: dict[str, Any]) -> None:
    current = f"agentprov {doc['current']['core']}" + (f", app {doc['current']['gui']}" if doc["current"]["gui"]
                                                       else "")
    if doc["checked_at"] is None:
        result.output(f"update: never checked ({current}); run agentprov update check --allow-network")
        return
    if doc["latest"] is None:
        result.output(f"update: no release found ({current}); checked {doc['checked_at']} UTC")
    elif doc["update_available"]:
        result.output(f"update: AgentPROV {doc['latest']} is available ({current}); published "
                      f"{doc['published_at'] or 'unknown'} UTC; {doc['release_url']}")
    else:
        result.output(f"update: up to date ({current}; newest release {doc['latest']}); checked {doc['checked_at']} "
                      "UTC")
    if doc["latest"] is not None and doc["update_available"]:
        for line in doc["notes"].split("\n")[:40]:
            result.output("  " + safe_text(line, 300))
        if doc["assets"]:
            a = doc["assets"][0]
            result.output(f"bundle for {doc['platform']}: {a['name']} ({a['size']} bytes)")
    result.output(f"daily check (update.auto_check): {'on' if doc['auto_check'] else 'off'}")


def _download(home: Path, args: Any, now: dt.datetime) -> dict[str, Any]:
    from agentprov.update.releases import fetch_releases, latest_release, parse_releases, write_cache
    from agentprov.update.stage import stage_release, staging_dir

    label = _label(args)
    release = latest_release(parse_releases(fetch_releases(transport())))
    write_cache(home, release, now)
    if release is None:
        raise CliUsageError("agentprov update download: the repository has no release")
    directory = Path(args.dir).expanduser().absolute() if args.dir else staging_dir(home, label)
    staged = stage_release(transport(), release, label, directory, signers=_signers())
    return {**staged, "format": DOWNLOAD_FORMAT, "kind": "bundle"}


# --------------------------------------------------------------------------------------------------------------
# D-1130: the package install and the checkout
# --------------------------------------------------------------------------------------------------------------


def _kind() -> dict[str, Any]:
    from agentprov.update.install import package_install

    return dict(KIND() if KIND is not None else package_install())


def _have() -> Any:
    from agentprov.update.package import installed

    return HAVE if HAVE is not None else installed


def _which() -> Any:
    import shutil

    return WHICH if WHICH is not None else shutil.which


def _installer(kind: str, wheels: list[str]) -> tuple[list[str] | None, str]:
    from agentprov.update.package import installer_argv

    return installer_argv(kind, wheels, which=_which(), has_pip=HAS_PIP)


def _checkout_root() -> Path | None:
    from agentprov.update.checkout import checkout_root

    return CHECKOUT_ROOT() if CHECKOUT_ROOT is not None else checkout_root()


def _git_run() -> dict[str, Any]:
    """``run=`` for :mod:`agentprov.update.checkout` (its own ``subprocess.run`` unless a test set :data:`GIT_RUN`)."""
    return {} if GIT_RUN is None else {"run": GIT_RUN}


def _automatic(pkg: dict[str, Any]) -> dict[str, Any]:
    """Which D-1130 path updates this agentprov here, and why not when none does (nothing is changed, no network)."""
    from agentprov.update.checkout import commands, inspect_checkout
    from agentprov.update.package import KINDS

    kind = pkg["kind"]
    if kind == "bundle":
        return {"how": "bundle", "available": False, "why": "it is the desktop app's own copy, updated with the app"}
    if kind == "checkout":
        root = _checkout_root()
        if root is None:
            return {"how": "checkout", "available": False, "why": "the editable install's folder is not an AgentPROV "
                                                                  "checkout", "argv": None}
        facts = inspect_checkout(root, which=_which(), prefix=_prefix(), **_git_run())
        extras = _extras()
        return {"how": "checkout", "available": bool(facts["ok"]), "why": facts["why"], "root": str(root),
                "branch": facts["branch"], "remote": facts["remote"], "clean": facts["clean"], "head": facts["head"],
                "extras": extras, "argv": ["update", "install", "--checkout", "--confirm", "--allow-network"],
                "commands": commands(root, extras)}
    if kind in KINDS:
        argv, how = _installer(kind, ["WHEELS"])
        return {"how": "package", "available": argv is not None, "why": None if argv is not None else how,
                "installer": how if argv is not None else None,
                "argv": ["update", "download", "--package", "--allow-network"]}
    return {"how": None, "available": False, "why": f"a {kind} install is not updated by agentprov"}


def _package_plan(kind: str, staged: dict[str, Any]) -> dict[str, Any]:
    """What ``install --package`` would run on the staged wheels, and why it would refuse."""
    from agentprov.update.package import dependency_problems, restore_command
    from agentprov.versions import __version__

    have = _have()
    argv, how = _installer(kind, [w.get("path") or str(Path(staged["dir"]) / w["name"]) for w in staged["wheels"]])
    problems = dependency_problems({w["dist"]: w["requires"] for w in staged["wheels"]}, staged["version"], have=have)
    if argv is None:
        problems.append(how)
    parts = [{"dist": w["dist"], "from_version": (have(w["dist"]) or (None,))[0], "to_version": staged["version"],
              "file": w["name"], "sha256": w["sha256"]} for w in staged["wheels"]]
    return {"install_kind": kind, "from_version": __version__, "to_version": staged["version"], "parts": parts,
            "installer": how if argv is not None else None, "installer_argv": argv, "installable": not problems,
            "problems": problems, "keeps_previous": False,
            "restore_command": restore_command(kind, __version__, have=have)}


def _package_kind() -> dict[str, Any]:
    from agentprov.update.package import KINDS
    from agentprov.update.releases import UpdateError

    pkg = _kind()
    if pkg["kind"] not in KINDS:
        raise UpdateError(f"--package upgrades a pip, uv tool or pipx install; this agentprov is a {pkg['kind']} "
                          f"install ({pkg['text']})", code="update.package.kind", exit_code=4)
    return pkg


def _verified(doc: dict[str, Any]) -> str:
    return f"{doc['verification']}{', signed by ' + doc['signed_by'] if doc.get('signed_by') else ''}"


def _download_package(home: Path, args: Any, now: dt.datetime) -> dict[str, Any]:
    from agentprov.update.package import stage_package, staging_dir
    from agentprov.update.releases import fetch_releases, latest_release, parse_releases, write_cache

    pkg = _package_kind()
    release = latest_release(parse_releases(fetch_releases(transport())))
    write_cache(home, release, now)
    if release is None:
        raise CliUsageError("agentprov update download: the repository has no release")
    directory = Path(args.dir).expanduser().absolute() if args.dir else staging_dir(home)
    staged = stage_package(transport(), release, directory, signers=_signers(), have=_have())
    plan = _package_plan(pkg["kind"], staged)
    lines = [f"update: {', '.join(w['name'] for w in staged['wheels'])} of {staged['tag']} downloaded and verified "
             f"({_verified(staged)}) into {safe_text(staged['dir'], 300)}"]
    if plan["installable"]:
        lines.append(f"install them with: agentprov update install --package --confirm ({plan['installer']}, no "
                     "dependency resolution, no index)")
    else:
        lines += [f"update: they cannot be installed without resolving anything: {safe_text('; '.join(plan['problems']), 600)}",
                  f"upgrade with: {pkg['text']}"]
    return {**staged, **plan, "format": DOWNLOAD_FORMAT, "kind": "package", "lines": lines}


def _record_package(home: Path, doc: dict[str, Any]) -> None:
    from agentprov.io.replace_retry import atomic_write_bytes_retrying
    from agentprov.update.releases import update_dir

    path = update_dir(home) / "package-installed.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes_retrying(path, json.dumps(doc, sort_keys=True, separators=(",", ":")).encode() + b"\n")


def _install_package(home: Path, args: Any, now: dt.datetime) -> dict[str, Any]:
    import agentprov.io.replace_retry  # noqa: F401  (imported before the installer replaces this package's files)
    from agentprov.update.package import install_package, load_staged_package, staging_dir
    from agentprov.update.releases import UpdateError, utc_text, version_key
    from agentprov.versions import __version__

    pkg = _package_kind()
    if not args.confirm:
        raise UpdateError("agentprov update install --package replaces this agentprov's installed files: give "
                          "--confirm", code="update.install.confirm", exit_code=4)
    directory = Path(args.dir).expanduser().absolute() if args.dir else staging_dir(home)
    staged = load_staged_package(directory, signers=_signers(), have=_have())
    new, have = version_key(staged["version"]), version_key(__version__)
    if new is not None and have is not None and new <= have:
        if new < have:
            raise UpdateError(f"the staged version {staged['version']} is older than this agentprov's {__version__}: "
                              "refused", code="update.install.downgrade", exit_code=4)
        return {"format": INSTALL_FORMAT, "kind": "package", "install_kind": pkg["kind"], "action": "current",
                "from_version": __version__, "to_version": staged["version"],
                "lines": [f"update: agentprov is already at {__version__}; nothing installed"]}
    plan = _package_plan(pkg["kind"], staged)
    if not plan["installable"]:
        raise UpdateError(f"the release's wheels cannot be installed without resolving anything ("
                          f"{'; '.join(plan['problems'])[:600]}); nothing installed: upgrade with: {pkg['text']}",
                          code="update.package.dependencies", exit_code=4)

    _not_busy(home, _install_folders(pkg["kind"]), "the agentprov install being upgraded")
    kw: dict[str, Any] = {"have": _have()}
    if INSTALL_RUN is not None:
        kw["run"] = INSTALL_RUN
    done = install_package(staged, plan["installer_argv"], **kw)
    record = {"format": "agentprov-update-package-installed/0.1", "install_kind": pkg["kind"],
              "from_version": __version__, "to_version": staged["version"], "installer": plan["installer"],
              "wheels": [{"name": w["name"], "sha256": w["sha256"]} for w in staged["wheels"]],
              "verification": staged["verification"], "signed_by": staged.get("signed_by"),
              "at": utc_text(now)}
    _record_package(home, record)
    lines = [f"update: agentprov {__version__} → {staged['version']} installed from the release's verified wheels "
             f"({_verified(staged)}) with {plan['installer']} (no dependency resolution, no index)",
             "The previous version is not kept on this machine; to go back, run (it installs from PyPI): "
             f"{plan['restore_command']}",
             "Programs already running (the desktop app's open windows, a running job) keep the old agentprov until "
             "they start it again."]
    return {**record, "format": INSTALL_FORMAT, "kind": "package", "action": "installed",
            "installer_argv": plan["installer_argv"], "installed": done["installed"],
            "keeps_previous": False, "restore_command": plan["restore_command"], "lines": lines}


def _install_checkout(home: Path, args: Any, now: dt.datetime) -> dict[str, Any]:
    from agentprov.update.checkout import commands, update_checkout
    from agentprov.update.releases import UpdateError
    from agentprov.versions import __version__

    pkg = _kind()
    if pkg["kind"] != "checkout":
        raise UpdateError(f"--checkout updates an agentprov run from a checkout; this one is a {pkg['kind']} install",
                          code="update.checkout.kind", exit_code=4)
    if not args.confirm:
        raise UpdateError("agentprov update install --checkout changes the checkout and its environment: give "
                          "--confirm", code="update.install.confirm", exit_code=4)
    _allowed(args, "install --checkout")
    root = _checkout_root()
    if root is None:
        raise UpdateError("the editable install's folder is not an AgentPROV checkout", code="update.checkout.refused",
                          exit_code=4)
    _not_busy(home, root, "the checkout being pulled and synced")
    have = _have()

    def version() -> str | None:
        got = have("agentprov")
        return got[0] if got else None

    extras = _extras()
    done = update_checkout(root, which=_which(), version=version, extras=extras, prefix=_prefix(), **_git_run())
    where = safe_text(str(root), 300)
    if not done["changed"]:
        lines = [f"update: the checkout {where} is already at origin/main ({(done['to_commit'] or '?')[:12]})"]
    else:
        lines = [f"update: the checkout {where} moved from {(done['from_commit'] or '?')[:12]} to "
                 f"{(done['to_commit'] or '?')[:12]} (git pull --ff-only origin main)"]
        if done["restore"]:
            lines.append("To go back: " + " && ".join(" ".join(c) for c in done["restore"]))
    sync = " ".join(commands(root, extras)[1])
    if done["synced"]:
        lines.append(f"Synced its environment ({sync}); agentprov is {done['to_version'] or 'unknown'} (was "
                     f"{__version__}).")
    else:
        lines.append(f"update: the environment was NOT synced: run {sync}")
    return {"format": INSTALL_FORMAT, "kind": "checkout", "action": "installed" if done["changed"] else "current",
            "from_version": __version__, **done, "lines": lines}


def _install(home: Path, args: Any, now: dt.datetime) -> dict[str, Any]:
    from agentprov.update.install import check_bundle, install_bundle
    from agentprov.update.releases import UpdateError, version_key
    from agentprov.update.stage import load_staged, staging_dir

    chosen = [n for n, v in (("--bundle", args.bundle), ("--package", args.package), ("--checkout", args.checkout))
              if v]
    if len(chosen) > 1:
        raise CliUsageError(f"agentprov update install: {' and '.join(chosen)} cannot be combined")
    if args.package:
        return _install_package(home, args, now)
    if args.checkout:
        return _install_checkout(home, args, now)
    if args.allow_network:
        raise CliUsageError("agentprov update install: --allow-network goes with --checkout")
    if args.bundle is None:
        if args.confirm:
            raise CliUsageError("agentprov update install: --confirm goes with --bundle, --package or --checkout "
                                "(without them this prints the upgrade command)")
        pkg = _kind()
        automatic = _automatic(pkg)
        lines = [f"update: {pkg['text']}"] if pkg["command"] is None else [
            f"update: agentprov is a {pkg['kind']} install; upgrade it with:", f"  {pkg['text']}"]
        if automatic["available"] and automatic["how"] == "package":
            lines.append(f"or from the release's verified wheels ({automatic['installer']}, never PyPI): agentprov "
                         "update download --package --allow-network, then agentprov update install --package --confirm")
        elif automatic["available"] and automatic["how"] == "checkout":
            lines.append("or let agentprov do it: agentprov update install --checkout --confirm --allow-network")
        elif automatic.get("why") and automatic["how"] != "bundle":
            lines.append(f"agentprov cannot do it here: {safe_text(automatic['why'], 300)}")
        return {"format": INSTALL_FORMAT, "kind": pkg["kind"], "action": "command", "command": pkg["command"],
                "text": pkg["text"], "automatic": automatic, "lines": lines}
    label = _label(args)
    bundle = check_bundle(Path(args.bundle), label)
    if not args.confirm:
        raise UpdateError("agentprov update install replaces the desktop app's folder: give --confirm",
                          code="update.install.confirm", exit_code=4)
    directory = Path(args.dir).expanduser().absolute() if args.dir else staging_dir(home, label)
    staged, archive = load_staged(directory, label, signers=_signers())
    _not_busy(home, bundle, "the app being replaced (its own agentprov)")
    current = _gui(args, label)
    new, have = version_key(staged["version"]), version_key(current)
    if have is not None and new is not None and new <= have:
        if new < have:
            raise UpdateError(f"the staged version {staged['version']} is older than the app's {current}: refused",
                              code="update.install.downgrade", exit_code=4)
        return {"format": INSTALL_FORMAT, "kind": "bundle", "action": "current", "bundle": str(bundle),
                "to_version": staged["version"], "from_version": current,
                "lines": [f"update: the app is already at {current}; nothing installed"]}
    kw: dict[str, Any] = {"run": DMG_RUN}
    if HELPER is not None:
        kw["helper"] = HELPER
    done = install_bundle(bundle, archive, label=label, version=staged["version"], home=home, current=current,
                          now=now, **kw)
    rollback = f"agentprov update rollback --yes --bundle {safe_text(str(bundle), 300)}"
    if done["action"] == "installed":
        lines = [f"update: AgentPROV {staged['version']} installed in {safe_text(str(bundle), 300)} "
                 f"({staged['verification']}); the previous version is kept for rollback",
                 "Quit AgentPROV and open it again now to start the new version (the running app is the old one "
                 "until then).", f"To go back: {rollback}"]
        restart = "quit and reopen"
    else:
        lines = [f"update: AgentPROV {staged['version']} is ready in {safe_text(str(bundle.parent), 300)} "
                 f"({staged['verification']})",
                 "Quit AgentPROV: the update is applied once it has closed (Windows cannot replace a running app); "
                 "then open it again.", f"To go back afterwards: {rollback}"]
        restart = "quit, wait, reopen"
    return {**done, "format": INSTALL_FORMAT, "kind": "bundle", "verification": staged["verification"],
            "signed_by": staged.get("signed_by"), "restart": restart, "rollback_command": rollback, "lines": lines}


def _rollback(home: Path, args: Any, now: dt.datetime) -> dict[str, Any]:
    from agentprov.update.install import check_bundle, rollback_bundle
    from agentprov.update.releases import UpdateError

    label = _label(args)
    bundle = check_bundle(Path(args.bundle), label)
    if not args.yes:
        raise UpdateError("agentprov update rollback replaces the desktop app's folder: give --yes",
                          code="update.rollback.confirm", exit_code=4)
    _not_busy(home, bundle, "the app being replaced (its own agentprov)")
    kw: dict[str, Any] = {} if HELPER is None else {"helper": HELPER}
    done = rollback_bundle(bundle, label=label, home=home, now=now, **kw)
    if done["action"] == "rolled-back":
        lines = [f"update: the app in {safe_text(str(bundle), 300)} is back at the previous version"
                 f"{' ' + done['to_version'] if done['to_version'] else ''}; quit and reopen it"]
    else:
        lines = ["update: the rollback is applied once AgentPROV has closed; quit it, then open it again"]
    return {**done, "format": INSTALL_FORMAT, "kind": "bundle", "lines": lines}
