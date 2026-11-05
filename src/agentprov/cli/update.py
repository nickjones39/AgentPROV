"""``agentprov update``: Check for Updates, a verified download and the desktop bundle's install (D-1065).

    agentprov update check --allow-network [--if-stale] [--bundle PATH] [--gui-version V] [--format text|json]
    agentprov update status [--bundle PATH] [--gui-version V] [--format text|json]
    agentprov update download --allow-network [--dir DIR] [--format text|json]
    agentprov update install [--confirm --bundle PATH] [--gui-version V] [--dir DIR] [--format text|json]
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
for ``rollback`` (macOS and Linux at once; Windows once the app has quit). Without ``--bundle`` it prints the command
that upgrades a ``pip`` or ``uv tool`` install of ``agentprov``; it never upgrades a package itself.
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
    d.add_argument("--dir", metavar="DIR", help="the staging folder (default: $AGENTPROV_HOME/update/staging/PLATFORM)")
    common(d, bundle=False)
    i = actions.add_parser("install", parents=[shared], allow_abbrev=False,
                           help="install the verified download into the desktop app's folder (--confirm --bundle), "
                                "or print the command that upgrades a pip or uv tool install")
    i.add_argument("--confirm", action="store_true", help="required with --bundle: replace the app's folder")
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
        doc = _download(home, args, now)
        if args.format == "json":
            result.payload = _payload(doc)
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
    return {**staged, "format": DOWNLOAD_FORMAT}


def _install(home: Path, args: Any, now: dt.datetime) -> dict[str, Any]:
    from agentprov.update.install import check_bundle, install_bundle, package_install
    from agentprov.update.releases import UpdateError, version_key
    from agentprov.update.stage import load_staged, staging_dir

    if args.bundle is None:
        if args.confirm:
            raise CliUsageError("agentprov update install: --confirm goes with --bundle (a package install is "
                                "upgraded by the command this prints)")
        pkg = package_install()
        lines = [f"update: {pkg['text']}"] if pkg["command"] is None else [
            f"update: agentprov is a {pkg['kind']} install; upgrade it with:", f"  {pkg['text']}"]
        return {"format": INSTALL_FORMAT, "kind": pkg["kind"], "action": "command", "command": pkg["command"],
                "text": pkg["text"], "lines": lines}
    label = _label(args)
    bundle = check_bundle(Path(args.bundle), label)
    if not args.confirm:
        raise UpdateError("agentprov update install replaces the desktop app's folder: give --confirm",
                          code="update.install.confirm", exit_code=4)
    directory = Path(args.dir).expanduser().absolute() if args.dir else staging_dir(home, label)
    staged, archive = load_staged(directory, label, signers=_signers())
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
    kw: dict[str, Any] = {} if HELPER is None else {"helper": HELPER}
    done = rollback_bundle(bundle, label=label, home=home, now=now, **kw)
    if done["action"] == "rolled-back":
        lines = [f"update: the app in {safe_text(str(bundle), 300)} is back at the previous version"
                 f"{' ' + done['to_version'] if done['to_version'] else ''}; quit and reopen it"]
    else:
        lines = ["update: the rollback is applied once AgentPROV has closed; quit it, then open it again"]
    return {**done, "format": INSTALL_FORMAT, "kind": "bundle", "lines": lines}
