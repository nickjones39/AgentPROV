"""Check for Updates in the app (D-1065, the GUI half): About's Updates section, the confirmed install, the start-up
notice once per release, Settings › Updates and the commands each runs.

Every ``agentprov update`` result here is a fake CLI answer handed to the controller's runner: no test opens a socket,
starts the real CLI's update commands or installs anything. The documents have the CLI's shapes
(``agentprov-update-check/0.1``, ``-download/0.1``, ``-install/0.1``; ``src/agentprov/cli/update.py``).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from conftest import hostile_strings

APP = Path("/Applications/AgentPROV.app")


def wait(app: Any, cond: Any, timeout: float = 30) -> None:
    from PySide6.QtCore import QEventLoop, QThreadPool

    end = time.monotonic() + timeout
    while not cond():
        assert time.monotonic() < end, "timed out"
        QThreadPool.globalInstance().waitForDone(50)
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
        time.sleep(0.005)


def check_doc(*, latest: str | None = "0.3.0", available: bool | None = True, notes: str = "Fixes.\nNew things.",
              checked: str | None = "2026-11-05T01:02:03Z", auto: bool = True, fmt: str = "agentprov-update-check/0.1",
              asset: bool = True, signed: bool = False, behind: dict[str, Any] | None = None,
              current: dict[str, Any] | None = None) -> bytes:
    doc = {"format": fmt, "repository": "nickjones39/AgentPROV", "checked_at": checked, "fetched": True,
           "current": current or {"core": "0.1.1", "gui": "0.1.1"}, "latest": latest,
           "tag": f"v{latest}" if latest else None, "update_available": available,
           "behind": {"core": available, "gui": available} if behind is None else behind,
           "published_at": "2026-11-04T22:00:00Z", "release_url": "https://github.com/x/y", "notes": notes,
           "notes_truncated": False, "platform": "macos-arm64",
           "assets": [{"name": "AgentPROV-0.3.0-macos-arm64.dmg", "size": 123, "url": "u"}] if asset else [],
           "checksum_asset": {"name": "SHA256SUMS", "size": 1, "url": "u"},
           "signature_asset": {"name": "SHA256SUMS.sig", "size": 1, "url": "u"} if signed else None,
           "auto_check": auto, "check_due": False}
    return json.dumps(doc).encode() + b"\n"


def download_doc(verification: str = "sha256", signed_by: str | None = None) -> bytes:
    return json.dumps({"format": "agentprov-update-download/0.1", "tag": "v0.3.0", "version": "0.3.0",
                       "platform": "macos-arm64", "asset": {"name": "AgentPROV-0.3.0-macos-arm64.dmg", "size": 123,
                                                            "sha256": "a" * 64},
                       "verification": verification, "signed_by": signed_by, "dir": "/h/update/staging/x"}).encode()


def install_doc(action: str = "installed") -> bytes:
    lines = {"installed": ["update: AgentPROV 0.3.0 installed in /Applications/AgentPROV.app (sha256); the previous "
                           "version is kept for rollback",
                           "Quit AgentPROV and open it again now to start the new version (the running app is the old "
                           "one until then).", "To go back: agentprov update rollback --yes --bundle "
                           "/Applications/AgentPROV.app"],
             "waiting-for-quit": ["update: AgentPROV 0.3.0 is ready in C:\\Apps (sha256)",
                                  "Quit AgentPROV: the update is applied once it has closed (Windows cannot replace a "
                                  "running app); then open it again."],
             "command": ["update: agentprov is a uv-tool install; upgrade it with:", "  uv tool upgrade agentprov"]}
    doc: dict[str, Any] = {"format": "agentprov-update-install/0.1", "action": action, "lines": lines[action]}
    if action == "command":
        doc.update(kind="uv-tool", command=["uv", "tool", "upgrade", "agentprov"], text="uv tool upgrade agentprov")
    else:
        doc.update(kind="bundle", to_version="0.3.0", rollback_command="agentprov update rollback --yes --bundle X")
    return json.dumps(doc).encode()


def plan_doc(kind: str = "pip", *, available: bool = True, why: str | None = None) -> bytes:
    """``update install --format json`` without a flag (D-1130): how the program is installed, the automatic path."""
    how = "checkout" if kind == "checkout" else "package"
    auto: dict[str, Any] = {"how": how, "available": available, "why": why,
                            "installer": "pip" if how == "package" and available else None}
    if how == "checkout":
        auto.update(root="/Users/me/AgentPROV", head="c" * 40, argv=["update", "install", "--checkout", "--confirm",
                                                                     "--allow-network"])
    text = {"pip": "python -m pip install --upgrade agentprov", "checkout": "git pull --ff-only, then uv sync"}[kind]
    return json.dumps({"format": "agentprov-update-install/0.1", "action": "command", "kind": kind,
                       "command": None if kind == "checkout" else ["python", "-m", "pip", "install", "--upgrade",
                                                                   "agentprov"],
                       "text": text, "automatic": auto, "lines": [f"update: {text}"]}).encode()


def package_doc(*, installable: bool = True) -> bytes:
    """``update download --package --format json`` (D-1130): the program's verified wheels and the install plan."""
    return json.dumps({"format": "agentprov-update-download/0.1", "kind": "package", "tag": "v0.3.0",
                       "version": "0.3.0", "to_version": "0.3.0", "from_version": "0.1.1", "install_kind": "pip",
                       "verification": "sha256+signature", "signed_by": "agentprov-release", "dir": "/h/pkg",
                       "wheels": [{"name": "agentprov_capture-0.3.0-py3-none-any.whl"},
                                  {"name": "agentprov-0.3.0-py3-none-any.whl"}],
                       "installable": installable, "installer": "pip",
                       "problems": [] if installable else ["agentprov 0.3.0 needs numpy>=2, which the installed "
                                                           "version did not"],
                       "keeps_previous": False,
                       "restore_command": "/venv/bin/python -m pip install agentprov==0.1.1"}).encode()


def program_doc(kind: str = "package") -> bytes:
    """``update install --package|--checkout --confirm --format json``: the program's update, made."""
    return json.dumps({"format": "agentprov-update-install/0.1", "kind": kind, "action": "installed",
                       "from_version": "0.1.1", "to_version": "0.3.0",
                       "lines": [f"update: agentprov 0.1.1 → 0.3.0 ({kind})"]}).encode()


class FakeCli:
    """The controller's runner: answers by the command's first words, records every argv (never runs anything)."""

    def __init__(self, answers: dict[str, tuple[int, bytes, bytes]]) -> None:
        self.answers = answers
        self.ran: list[list[str]] = []
        self.timeouts: list[float | None] = []
        self.raise_for: str | None = None  # a flag whose install raises (the worker's failure path)

    def __call__(self, argv: list[str], timeout: float | None) -> tuple[int, bytes, bytes]:
        self.ran.append(list(argv))
        self.timeouts.append(timeout)
        if self.raise_for is not None and self.raise_for in argv and "--confirm" in argv:
            raise RuntimeError("the CLI process could not be started")
        key = " ".join(argv[:2])
        flag = next((f for f in ("--package", "--checkout", "--bundle") if f in argv), None)
        if flag is not None and f"{key} {flag}" in self.answers:  # D-1130: the install and download kinds
            return self.answers[f"{key} {flag}"]
        if key == "settings list":
            return self.answers.get(key, (0, json.dumps({"values": {}}).encode(), b""))
        return self.answers.get(key, (2, b"", b"agentprov: error [usage]: no such command"))

    def words(self) -> list[str]:
        return [" ".join(a[:2]) for a in self.ran]


def _controller(qapp: Any, cli: FakeCli, *, bundle: Path | None = APP, confirm: bool | None = True,
                program: str = "bundled") -> Any:
    """``program``: which agentprov the app runs (``bundled``: the bundle's own copy, which the bundle install
    updates; ``installed`` or ``checkout``: a program with its own update, D-1130)."""
    from agentprov_gui.ui.updates import UpdateController

    c = UpdateController(cli, bundle=bundle, gui="0.1.1", program=lambda: program)
    c.asked = []  # type: ignore[attr-defined]

    def ask(parent: Any, plan: Any) -> bool:
        c.asked.append(plan)  # type: ignore[attr-defined]
        assert confirm is not None, "no confirmation expected"
        return confirm

    c.confirm = ask
    return c


# ---------------------------------------------------------------------------------------------- the module (no Qt)
def test_the_commands_and_the_bundle() -> None:
    from agentprov_gui import updates as U

    assert U.status_argv(APP, "0.1.1") == ["update", "status", "--bundle", str(APP), "--gui-version", "0.1.1",
                                           "--format", "json"]
    assert U.check_argv(None, "0.1.1", if_stale=True) == ["update", "check", "--allow-network", "--if-stale",
                                                         "--gui-version", "0.1.1", "--format", "json"]
    assert U.download_argv() == ["update", "download", "--allow-network", "--format", "json"]
    assert U.install_argv(APP, "0.1.1") == ["update", "install", "--confirm", "--bundle", str(APP), "--gui-version",
                                            "0.1.1", "--format", "json"]
    assert U.install_argv(None, "0.1.1") == ["update", "install", "--format", "json"]  # never --confirm without one
    assert U.skip_argv("0.3.0") == ["settings", "set", "update.last_notified", "0.3.0"]
    mac = "/Applications/AgentPROV.app/Contents/MacOS/AgentPROV"
    assert U.app_bundle(mac, frozen=True, platform="darwin") == APP
    assert U.app_bundle("/opt/AgentPROV/AgentPROV", frozen=True, platform="linux") == Path("/opt/AgentPROV")
    assert U.app_bundle("C:/Apps/AgentPROV/AgentPROV.exe", frozen=True, platform="win32") == Path("C:/Apps/AgentPROV")
    assert U.app_bundle(mac, frozen=False, platform="darwin") is None  # a checkout's or a package's app
    assert U.app_bundle("/usr/bin/python3", frozen=True, platform="linux") is None  # not the bundle's folder
    assert U.app_bundle() is None and U.app_version() is not None  # these tests do not run frozen


def test_the_check_document_is_read_defensively() -> None:
    from agentprov_gui import updates as U

    c = U.parse_check(0, check_doc())
    assert c is not None and c.latest == "0.3.0" and c.release == "0.3.0" and c.update_available is True
    assert c.asset == "AgentPROV-0.3.0-macos-arm64.dmg" and c.gui == "0.1.1" and not c.signed
    status = U.parse_check(0, check_doc(fmt="agentprov-update-status/0.1", checked=None))
    assert status is not None and status.checked_at is None
    for code, out in ((2, b""), (0, b"not json"), (0, json.dumps({"format": "other"}).encode()),
                      (0, json.dumps([1]).encode())):
        assert U.parse_check(code, out) is None  # an older CLI, or not the document: never a guess
    assert U.parse_download(0, json.dumps({"format": "agentprov-update-download/0.1"}).encode()) is None
    assert U.parse_install(0, json.dumps({"format": "agentprov-update-install/0.1", "action": "x"}).encode()) is None
    for hostile in hostile_strings():
        got = U.parse_check(0, check_doc(notes=hostile, latest=hostile))
        assert got is not None and chr(0x202E) not in got.notes and chr(0x1B) not in got.notes
        assert got.release is None  # not X.Y.Z: never stored as update.last_notified
    long = U.notes_text("\n".join(f"line {i}" for i in range(500)))
    assert long.count("\n") == U.NOTES_LINES and long.endswith("(300 more lines)")


def test_the_notice_rules() -> None:
    from agentprov_gui import updates as U

    assert U.notify(U.parse_check(0, check_doc()), None)
    assert U.notify(U.parse_check(0, check_doc()), "0.2.0")
    assert not U.notify(U.parse_check(0, check_doc()), "0.3.0")  # skipped
    assert not U.notify(U.parse_check(0, check_doc(auto=False)), None)  # the daily check is off
    assert not U.notify(U.parse_check(0, check_doc(available=False)), None)
    assert not U.notify(U.parse_check(0, check_doc(available=None)), None)  # not comparable
    assert not U.notify(None, None)
    assert U.notify(U.parse_check(0, check_doc(behind=CLI_ONLY)), None)  # still told, as a CLI upgrade (D-1070)


#: the 2026-11-06 case: the app is current, the agentprov program it runs (a stale checkout .venv) is not
CLI_ONLY: dict[str, Any] = {"core": True, "gui": False}
CLI_ONLY_CURRENT: dict[str, Any] = {"core": "0.1.1", "gui": "0.3.0"}


def test_the_behind_flags_say_which_part_is_old() -> None:
    from agentprov_gui import updates as U

    both = U.parse_check(0, check_doc())
    assert both is not None and both.behind_core is True and both.behind_gui is True and not both.cli_only
    cli = U.parse_check(0, check_doc(behind=CLI_ONLY, current=CLI_ONLY_CURRENT))
    assert cli is not None and cli.cli_only and cli.core == "0.1.1" and cli.gui == "0.3.0"
    unknown_gui = U.parse_check(0, check_doc(behind={"core": True, "gui": None}))  # no --gui-version compared
    assert unknown_gui is not None and unknown_gui.cli_only
    for behind in ({"core": False, "gui": True}, {"core": None, "gui": None}, {"core": "yes", "gui": 1}, {}):
        got = U.parse_check(0, check_doc(behind=behind))
        assert got is not None and not got.cli_only  # only a real true core and no true gui count
    old = json.loads(check_doc())
    del old["behind"]  # a CLI that does not say: the bundle path as before
    got = U.parse_check(0, json.dumps(old).encode())
    assert got is not None and got.behind_core is None and got.behind_gui is None and not got.cli_only


def test_the_reason_is_the_cli_s_own_line() -> None:
    from agentprov_gui import updates as U

    err = (b"INFO agentprov.cli: start command=update\nagentprov: error [update.verify.sha256]: the sha256 is not "
           b"the one SHA256SUMS lists: refused\nINFO agentprov.cli: end command=update exit_code=1\n")
    assert U.reason(1, err) == "the sha256 is not the one SHA256SUMS lists: refused (update.verify.sha256)"
    assert "Settings › General" in U.reason(127, b"no CLI")
    assert "could not be run" in U.reason(124, b"TimeoutExpired")
    assert U.reason(3, b"") == "agentprov update ended with exit 3."


# ---------------------------------------------------------------------------------------------- About
def _about(qapp: Any, controller: Any) -> Any:
    from agentprov_gui.ui.dialogs import AboutDialog

    dlg = AboutDialog(None, updates=controller)
    wait(qapp, lambda: not controller.busy)
    return dlg


def test_about_shows_the_cached_check_and_checks_on_request(qapp: Any) -> None:
    cli = FakeCli({"update status": (0, check_doc(fmt="agentprov-update-status/0.1", available=False, latest="0.1.1"),
                                     b""),
                   "update check": (0, check_doc(), b"")})
    c = _controller(qapp, cli)
    dlg = _about(qapp, c)
    sec = dlg.updates_section
    assert cli.words() == ["update status"]  # no network until asked
    assert sec.badge.text() == "Up to date" and not sec.install_btn.isEnabled() and sec.notes_row.isHidden()
    sec.check_btn.click()
    wait(qapp, lambda: not c.busy)
    assert cli.ran[-1] == ["update", "check", "--allow-network", "--bundle", str(APP), "--gui-version", "0.1.1",
                           "--format", "json"]
    assert sec.badge.text() == "Update available" and sec.install_btn.isEnabled()
    assert sec.notes.toPlainText() == "Fixes.\nNew things." and not sec.notes_row.isHidden()
    assert "AgentPROV 0.3.0" in sec.latest.text() and "up to date" not in sec.last.text()
    shown = [list(argv) for _c, argv in sec.command.commands]
    assert ["update", "download", "--allow-network", "--format", "json"] in shown and any(
        a[:3] == ["update", "install", "--confirm"] for a in shown)  # every action's terminal command
    dlg.deleteLater()


def test_a_failed_check_says_why_and_keeps_the_last_result(qapp: Any) -> None:
    cli = FakeCli({"update status": (0, check_doc(), b""),
                   "update check": (1, b"", b"agentprov: error [raw.fetch.http]: the server answered 503\n")})
    c = _controller(qapp, cli)
    dlg = _about(qapp, c)
    c.check_now()
    wait(qapp, lambda: not c.busy)
    sec = dlg.updates_section
    assert "the server answered 503 (raw.fetch.http)" in sec.status.text() and sec.badge.text() == "Update available"
    dlg.deleteLater()


def test_download_confirm_install(qapp: Any) -> None:
    cli = FakeCli({"update status": (0, check_doc(), b""), "update download": (0, download_doc(), b""),
                   "update install": (0, install_doc(), b"")})
    c = _controller(qapp, cli)
    dlg = _about(qapp, c)
    dlg.updates_section.install_btn.click()
    wait(qapp, lambda: not c.busy and len(cli.ran) >= 3)
    assert cli.words() == ["update status", "update download", "update install"]
    assert cli.ran[2] == ["update", "install", "--confirm", "--bundle", str(APP), "--gui-version", "0.1.1",
                          "--format", "json"]
    (plan,) = c.asked
    (part,) = plan.parts  # the app's own agentprov is updated with it: one part
    assert (part.name, part.detail, part.from_version, part.to_version) == ("The app", str(APP), "0.1.1", "0.3.0")
    assert part.verified == "sha256" and ".AgentPROV-previous" in part.keeps and not part.signed and not plan.cannot
    text = dlg.updates_section.result.text()
    assert "does not prove who published it" in text  # unsigned: said, not hidden
    assert "Quit AgentPROV and open it again" in text and "rollback" in text
    # the running app is the old one: no second install (it would replace the version kept for rollback)
    assert not dlg.updates_section.install_btn.isEnabled() and not c.download_and_install(dlg)
    assert len(cli.ran) == 3
    dlg.deleteLater()


def test_a_declined_confirmation_installs_nothing(qapp: Any) -> None:
    cli = FakeCli({"update status": (0, check_doc(), b""),
                   "update download": (0, download_doc("sha256+signature", "agentprov-release"), b"")})
    c = _controller(qapp, cli, confirm=False)
    dlg = _about(qapp, c)
    c.download_and_install(dlg)
    wait(qapp, lambda: not c.busy and c.asked)
    assert cli.words() == ["update status", "update download"] and "Not installed" in c.status_line
    assert "signed by agentprov-release" in c.result[0] and not any("prove" in x for x in c.result)
    dlg.deleteLater()


def test_a_refused_download_asks_nothing(qapp: Any) -> None:
    cli = FakeCli({"update status": (0, check_doc(), b""),
                   "update download": (1, b"", b"agentprov: error [update.verify.signature]: the signature does not "
                                               b"verify: refused\n")})
    c = _controller(qapp, cli, confirm=None)
    dlg = _about(qapp, c)
    c.download_and_install(dlg)
    wait(qapp, lambda: not c.busy and len(cli.ran) == 2)
    assert "nothing is installed" in c.status_line and "(update.verify.signature)" in c.status_line
    dlg.deleteLater()


def test_windows_is_applied_after_quit(qapp: Any) -> None:
    cli = FakeCli({"update status": (0, check_doc(), b""), "update download": (0, download_doc(), b""),
                   "update install": (0, install_doc("waiting-for-quit"), b"")})
    c = _controller(qapp, cli)
    c.download_and_install()
    wait(qapp, lambda: not c.busy and len(cli.ran) >= 2 and c.install is not None)
    assert c.install.action == "waiting-for-quit" and any("applied once it has closed" in x for x in c.result)


def test_without_a_bundle_the_upgrade_command_is_shown_not_run(qapp: Any) -> None:
    cli = FakeCli({"update status": (0, check_doc(), b""), "update install": (0, install_doc("command"), b"")})
    c = _controller(qapp, cli, bundle=None, confirm=None, program="installed")
    dlg = _about(qapp, c)
    sec = dlg.updates_section
    assert sec.install_btn.text() == "Update agentprov…" and sec.install_btn.isEnabled()
    sec.install_btn.click()
    wait(qapp, lambda: not c.busy and c.install is not None)
    assert cli.ran[-1] == ["update", "install", "--format", "json"]  # no --bundle, no --confirm
    assert "uv tool upgrade agentprov" in sec.result.text()
    assert ["uv", "tool", "upgrade", "agentprov"] in [list(argv) for _c, argv in sec.command.commands]
    assert not any("--bundle" in argv for _c, argv in sec.command.commands)
    dlg.deleteLater()


def test_only_the_cli_behind_shows_its_upgrade_command_not_a_bundle_install(qapp: Any) -> None:
    """D-1070: the app is current and only the agentprov it runs is behind; replacing the bundle would not change that
    program, so a bundle app shows its upgrade command (no download, no --bundle, no --confirm)."""
    cli = FakeCli({"update status": (0, check_doc(behind=CLI_ONLY, current=CLI_ONLY_CURRENT, asset=False), b""),
                   "update install": (0, install_doc("command"), b"")})
    c = _controller(qapp, cli, confirm=None, program="checkout")
    dlg = _about(qapp, c)
    sec = dlg.updates_section
    assert not c.bundle_update and sec.install_btn.text() == "Update agentprov…"
    assert sec.install_btn.accessibleName() == "Update agentprov…" and "Settings › General" in \
        sec.install_btn.toolTip()
    assert sec.install_btn.isEnabled()  # no bundle asset needed: nothing is downloaded
    assert "the agentprov this app runs is out of date" in sec.last.text()
    shown = [list(argv) for _c, argv in sec.command.commands]
    assert ["update", "install", "--format", "json"] in shown
    assert not any("download" in argv or "--confirm" in argv for argv in shown)
    sec.install_btn.click()
    wait(qapp, lambda: not c.busy and c.install is not None)
    assert cli.words() == ["update status", "update install"]  # never update download
    assert cli.ran[-1] == ["update", "install", "--format", "json"] and not c.asked  # type: ignore[attr-defined]
    assert "uv tool upgrade agentprov" in sec.result.text()
    dlg.deleteLater()


def test_the_app_behind_still_installs_the_bundle(qapp: Any) -> None:
    """D-1070 changes nothing when the app itself is behind, whatever the agentprov program is."""
    for behind in ({"core": True, "gui": True}, {"core": False, "gui": True}):
        c = _controller(qapp, FakeCli({"update status": (0, check_doc(behind=behind), b"")}))
        dlg = _about(qapp, c)
        assert c.bundle_update and dlg.updates_section.install_btn.text() == "Download and Install…"
        assert "the agentprov this app runs" not in dlg.updates_section.last.text()
        dlg.deleteLater()


def test_no_bundle_for_this_platform_disables_the_install(qapp: Any) -> None:
    c = _controller(qapp, FakeCli({"update status": (0, check_doc(asset=False), b"")}))
    dlg = _about(qapp, c)
    assert not dlg.updates_section.install_btn.isEnabled() and "no bundle" in dlg.updates_section.latest.text()
    dlg.deleteLater()


def test_the_confirmation_names_what_is_replaced(qapp: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from agentprov_gui import updates as U
    from agentprov_gui.ui import updates as ui

    seen: list[tuple[str, str]] = []
    monkeypatch.setattr(ui, "choose", lambda parent, title, text, informative, keep, other, tips: (
        seen.append((text, informative)), False)[1])
    download = U.parse_download(0, download_doc())
    plan = U.plan(bundle=APP, gui="0.1.1", app=download, program=U.parse_install(0, plan_doc("pip")),
                  package=U.parse_download(0, package_doc()), core="0.1.1")
    assert download is not None and not ui.confirm_update(None, plan)
    ((text, informative),) = seen
    assert text == "Install AgentPROV 0.3.0?"
    from dataclasses import replace

    seen_plan = replace(plan, followup="Then the rebuild runs as a job.")
    assert not ui.confirm_update(None, seen_plan)
    assert "Then the rebuild runs as a job." in seen[-1][1]
    seen.clear()
    assert not ui.confirm_update(None, plan)
    for part in (str(APP), "0.1.1 → 0.3.0", ".AgentPROV-previous", "agentprov update rollback --yes --bundle",
                 U.UNSIGNED_NOTE, "The agentprov program (a pip install)", "agentprov-0.3.0-py3-none-any.whl",
                 "previous version is not kept", "python -m pip install agentprov==0.1.1"):
        assert part in informative, part
    seen.clear()
    plan = U.plan(bundle=None, gui="0.1.1", app=None, program=U.parse_install(0, plan_doc("pip")),
                  package=U.parse_download(0, package_doc(installable=False)), core="0.1.1")
    assert not plan.parts and plan.cannot and "needs numpy" in plan.cannot[0][1]


# ---------------------------------------------------------------------------------------------- the whole software
def _loaded(qapp: Any, c: Any) -> Any:
    """The controller with its cached check read (``update status``), as About reads it first."""
    c.load_status()
    wait(qapp, lambda: not c.busy and c.check is not None)
    return c


def test_the_app_and_its_package_install_update_in_one_confirmed_flow(qapp: Any) -> None:
    """D-1130: both behind, the program a pip install: ask how it is installed, download and verify the bundle and the
    wheels, ask once naming both parts, then install the app and then the program."""
    cli = FakeCli({"update status": (0, check_doc(), b""), "update install": (0, plan_doc("pip"), b""),
                   "update download": (0, download_doc(), b""), "update download --package": (0, package_doc(), b""),
                   "update install --bundle": (0, install_doc(), b""),
                   "update install --package": (0, program_doc(), b"")})
    c = _controller(qapp, cli, program="installed")
    after: list[list[str]] = []
    c.after_update = after.append
    c.followup = lambda plan: "Then the stale backend environments are rebuilt." if any(
        p.name == "The agentprov program" for p in plan.parts) else None
    dlg = _about(qapp, c)
    assert c.program_update and c.bundle_update
    dlg.updates_section.install_btn.click()
    wait(qapp, lambda: not c.busy and c.program_install is not None and bool(after))
    assert after == [["The app", "The agentprov program"]]  # the step after the installs runs once, at the end
    assert cli.ran[1:] == [["update", "install", "--format", "json"],
                           ["update", "download", "--allow-network", "--format", "json"],
                           ["update", "download", "--package", "--allow-network", "--format", "json"],
                           ["update", "install", "--confirm", "--bundle", str(APP), "--gui-version", "0.1.1",
                            "--format", "json"],
                           ["update", "install", "--package", "--confirm", "--format", "json"]]
    (plan,) = c.asked
    app, program = plan.parts
    assert (app.name, program.name) == ("The app", "The agentprov program") and not plan.cannot
    assert plan.followup == "Then the stale backend environments are rebuilt."  # said before the confirmation
    assert (program.from_version, program.to_version, program.detail) == ("0.1.1", "0.3.0", "a pip install")
    assert "signed by agentprov-release" in program.verified and "agentprov-0.3.0-py3-none-any.whl" in program.verified
    assert "not kept" in program.keeps and "agentprov==0.1.1" in program.keeps
    text = dlg.updates_section.result.text()
    assert "Quit AgentPROV and open it again" in text and "agentprov 0.1.1 → 0.3.0 (package)" in text
    shown = [list(argv) for _c, argv in dlg.updates_section.command.commands]
    assert ["update", "install", "--package", "--confirm", "--format", "json"] in shown
    assert not dlg.updates_section.install_btn.isEnabled() and c.installed
    dlg.deleteLater()


def test_a_declined_whole_update_installs_nothing(qapp: Any) -> None:
    cli = FakeCli({"update status": (0, check_doc(), b""), "update install": (0, plan_doc("pip"), b""),
                   "update download": (0, download_doc(), b""), "update download --package": (0, package_doc(), b"")})
    c = _loaded(qapp, _controller(qapp, cli, program="installed", confirm=False))
    c.download_and_install()
    wait(qapp, lambda: not c.busy and c.asked)
    assert cli.words()[1:] == ["update install", "update download", "update download"]
    assert not any("--confirm" in argv for argv in cli.ran) and "Not installed" in c.status_line


def test_a_package_that_cannot_be_installed_is_named_and_the_app_still_offered(qapp: Any) -> None:
    for answer, why in (((0, package_doc(installable=False), b""), "needs numpy"),
                        ((1, b"", b"agentprov: error [update.verify.sha256]: a wheel's sha256 is not the listed one\n"),
                         "update.verify.sha256")):
        cli = FakeCli({"update status": (0, check_doc(), b""), "update install": (0, plan_doc("pip"), b""),
                       "update download": (0, download_doc(), b""), "update download --package": answer,
                       "update install --bundle": (0, install_doc(), b"")})
        c = _loaded(qapp, _controller(qapp, cli, program="installed"))
        c.download_and_install()
        wait(qapp, lambda c=c: not c.busy and c.install is not None)
        (plan,) = c.asked
        assert [p.name for p in plan.parts] == ["The app"] and plan.cannot[0][0] == "The agentprov program"
        assert why in plan.cannot[0][1] and plan.cannot[0][2] == "python -m pip install --upgrade agentprov"
        assert not any("--package" in argv and "--confirm" in argv for argv in cli.ran)  # never attempted
        assert any("Run this command in a terminal: python -m pip" in x for x in c.result)


def test_a_clean_checkout_is_fast_forwarded_after_the_confirmation(qapp: Any) -> None:
    cli = FakeCli({"update status": (0, check_doc(behind=CLI_ONLY, current=CLI_ONLY_CURRENT), b""),
                   "update install": (0, plan_doc("checkout"), b""),
                   "update install --checkout": (0, program_doc("checkout"), b"")})
    c = _controller(qapp, cli, bundle=None, program="checkout")
    dlg = _about(qapp, c)
    assert dlg.updates_section.install_btn.text() == "Update agentprov…"
    c.download_and_install()
    wait(qapp, lambda: not c.busy and c.program_install is not None)
    assert cli.ran[1:] == [["update", "install", "--format", "json"],
                           ["update", "install", "--checkout", "--confirm", "--allow-network", "--format", "json"]]
    ((part,), ) = [p.parts for p in c.asked]
    assert part.detail == "the checkout /Users/me/AgentPROV (main, clean)" and "git pull --ff-only" in part.verified
    assert part.from_version == "commit " + "c" * 12 and "nothing is discarded" in part.verified
    assert "updated" in c.status_line
    dlg.deleteLater()


def test_a_dirty_checkout_gets_the_command_and_nothing_runs(qapp: Any) -> None:
    cli = FakeCli({"update status": (0, check_doc(behind=CLI_ONLY, current=CLI_ONLY_CURRENT), b""),
                   "update install": (0, plan_doc("checkout", available=False, why="the checkout has changes or "
                                                  "untracked files: a tree with work in it is never touched"), b"")})
    c = _loaded(qapp, _controller(qapp, cli, bundle=None, program="checkout", confirm=None))
    c.download_and_install()
    wait(qapp, lambda: not c.busy and c.install is not None)
    assert cli.words() == ["update status", "update install"] and not c.asked  # type: ignore[attr-defined]
    assert any("never touched" in x for x in c.result) and any("git pull --ff-only" in x for x in c.result)


def test_the_bundles_own_agentprov_is_not_asked_about(qapp: Any) -> None:
    """The app runs its own copy: the bundle install updates it, so no plan query and no wheel download."""
    cli = FakeCli({"update status": (0, check_doc(), b""), "update download": (0, download_doc(), b""),
                   "update install --bundle": (0, install_doc(), b"")})
    c = _loaded(qapp, _controller(qapp, cli, program="bundled"))
    assert not c.program_update and c.check is not None and c.check.behind_core
    c.download_and_install()
    wait(qapp, lambda: not c.busy and c.install is not None)
    assert cli.words() == ["update status", "update download", "update install"] and "--bundle" in cli.ran[-1]


def test_the_cli_locator_falls_back_to_the_bundles_own_agentprov(tmp_path: Path,
                                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    """D-1130: the checkout, else an installed agentprov, else (in a bundle) the app's own; or always the app's own."""
    import sys

    from agentprov_gui.jobs import manager as M

    exe = tmp_path / "AgentPROV.app" / "Contents" / "MacOS" / "AgentPROV"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"x")
    assert M.bundled_program(frozen=False) == ()
    assert M.bundled_program(frozen=True, executable=str(exe)) == (str(exe), "--cli")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    monkeypatch.setattr(M, "installed_program", lambda *a, **k: None)
    try:
        own = M.CliLocator.for_checkout(None)
        assert own.program == (str(exe), "--cli") and own.bundled and own.kind == "bundled" and own.python == ()
        assert "updated with the app" in own.describe() and own.cwd_for(["run"]) is None
        monkeypatch.setattr(M, "installed_program", lambda *a, **k: tmp_path / "agentprov")
        assert M.CliLocator.for_checkout(None).kind == "installed"  # an installed one comes first
        M.set_cli_choice("bundled")
        assert M.CliLocator.for_checkout(tmp_path).kind == "bundled"  # chosen: even with a checkout set
        M.set_cli_choice("nonsense")
        assert M._cli_choice == "auto"
    finally:
        M.set_cli_choice("auto")


def test_the_cli_choice_setting(qapp: Any, tmp_path: Path) -> None:
    from PySide6.QtCore import QSettings

    from agentprov_gui.settings import Settings
    from agentprov_gui.ui.dialogs import SettingsDialog

    settings = Settings(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    assert settings.cli_choice == "auto"
    settings.cli_choice = "bundled"
    assert settings.cli_choice == "bundled"
    settings.cli_choice = "other"
    assert settings.cli_choice == "auto"
    dlg = SettingsDialog(settings)
    assert not dlg.cli_choice.isEnabled()  # these tests do not run frozen: there is no copy of the app's own
    dlg.deleteLater()


# ---------------------------------------------------------------------------------------------- the start-up check
def test_the_startup_check_tells_once_per_release(qapp: Any) -> None:
    def run(values: dict[str, Any], answer: tuple[int, bytes, bytes]) -> tuple[FakeCli, list[Any]]:
        cli = FakeCli({"settings list": (0, json.dumps({"values": values}).encode(), b""), "update check": answer})
        c = _controller(qapp, cli)
        told: list[Any] = []
        c.notice.connect(told.append)
        c.startup()
        wait(qapp, lambda: not c.busy)
        return cli, told

    cli, told = run({}, (0, check_doc(), b""))
    assert cli.ran[0] == ["settings", "list", "--prefix", "update.", "--format", "json"]
    assert cli.ran[1] == ["update", "check", "--allow-network", "--if-stale", "--bundle", str(APP), "--gui-version",
                          "0.1.1", "--format", "json"] and len(told) == 1 and told[0].latest == "0.3.0"
    cli, told = run({"update.last_notified": "0.3.0"}, (0, check_doc(), b""))
    assert not told  # skipped
    cli, told = run({"update.auto_check": False}, (0, check_doc(), b""))
    assert cli.words() == ["settings list"] and not told  # off: not even the cached answer is announced
    cli, told = run({}, (1, b"", b"agentprov: error [raw.fetch.network]: no route to host\n"))
    assert not told  # offline: silent


def test_the_notice_and_skip(qapp: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from agentprov_gui import updates as U
    from agentprov_gui.ui.safe import SafeLabel
    from agentprov_gui.ui.updates import UpdateNotice
    from test_tooltip_coverage import _report, gaps

    check = U.parse_check(0, check_doc(notes=hostile_strings()[0]))
    assert check is not None
    dlg = UpdateNotice(check)
    found = gaps(dlg, minimum=3)
    assert not found, _report(found)
    assert dlg.windowTitle() == "Software Update"
    assert "AgentPROV 0.3.0 is available" in [lab.text() for lab in dlg.findChildren(SafeLabel)]
    assert dlg.notes.toPlainText() == check.notes and dlg.update_btn.isDefault()  # plain text, never rendered
    dlg.skip_btn.click()
    assert dlg.choice == "skip"
    cli = FakeCli({"settings set": (0, b"", b"")})
    c = _controller(qapp, cli)
    c.skip("0.3.0")
    wait(qapp, lambda: not c.busy)
    assert cli.ran == [["settings", "set", "update.last_notified", "0.3.0"]] and not c.status_line


def test_the_notice_when_only_the_cli_is_behind(qapp: Any) -> None:
    """D-1070: the notice names the current app, the older agentprov program and the newest release, and its primary
    button shows the upgrade command (choice ``update``: About then takes the command path)."""
    from agentprov_gui import updates as U
    from agentprov_gui.ui.safe import SafeLabel
    from agentprov_gui.ui.updates import UpdateNotice
    from test_tooltip_coverage import _report, gaps

    check = U.parse_check(0, check_doc(behind=CLI_ONLY, current=CLI_ONLY_CURRENT))
    assert check is not None and check.cli_only
    dlg = UpdateNotice(check)
    found = gaps(dlg, minimum=3)
    assert not found, _report(found)
    texts = [lab.text() for lab in dlg.findChildren(SafeLabel)]
    assert "The agentprov this app runs is out of date" in texts
    assert "AgentPROV 0.3.0 is available" not in texts
    summary = " ".join(texts)
    for part in ("AgentPROV 0.3.0, which is current", "0.1.1", "Settings › General", "never PyPI",
                 "The app itself is not downloaded or replaced"):
        assert part in summary
    assert dlg.update_btn.text() == "Update agentprov…" and dlg.update_btn.isDefault()
    assert "without --bundle" in dlg.update_btn.toolTip()
    dlg.update_btn.click()
    assert dlg.choice == "update"
    plain = UpdateNotice(U.parse_check(0, check_doc()))  # the app behind: unchanged
    assert plain.update_btn.text() == "Update Now"
    assert "AgentPROV 0.3.0 is available" in [lab.text() for lab in plain.findChildren(SafeLabel)]
    dlg.deleteLater()
    plain.deleteLater()


def test_the_main_window_routes_the_notice(qapp: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from PySide6.QtCore import QSettings

    from agentprov_gui import updates as U
    from agentprov_gui.settings import Settings
    from agentprov_gui.ui import mainwindow, updates

    settings = Settings(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    win = mainwindow.MainWindow(settings, cache_dir=tmp_path / "c", home=tmp_path / "home")
    assert "Check for Updates…" in [a.text() for a in win.findChildren(type(win.action_map["openCorpus"]))]
    cli = FakeCli({"settings set": (0, b"", b"")})
    win.updates.run = cli
    opened: list[dict[str, bool]] = []
    monkeypatch.setattr(win, "_about", lambda **kw: opened.append(kw))
    for choice in ("later", "skip", "update"):
        monkeypatch.setattr(updates.UpdateNotice, "exec", lambda self, c=choice: setattr(self, "choice", c) or 0)
        win._update_notice(U.parse_check(0, check_doc()))
        wait(qapp, lambda: not win.updates.busy)
    assert cli.ran == [["settings", "set", "update.last_notified", "0.3.0"]] and opened == [{"install": True}]
    win.close()
    win.deleteLater()


# ---------------------------------------------------------------------------------------------- Settings › Updates
def test_the_settings_switch(qapp: Any, tmp_path: Path, fake_checkout: Path) -> None:
    from agentprov_gui.ui.settings_panes import UpdatesPane

    pane = UpdatesPane(fake_checkout)
    wait(qapp, lambda: pane.loaded is not None)
    assert pane.auto_check.isChecked() and pane.values() == {}
    pane.loaded = {"update.last_notified": "0.3.0"}
    pane.auto_check.setChecked(False)
    assert pane.values() == {"update.last_notified": "0.3.0", "update.auto_check": False}  # the skip is kept
    pane.show_command()
    assert [list(argv) for _c, argv in pane.command.commands] == [["settings", "set", "update.auto_check", "false"]]
    pane.save()
    pane2 = UpdatesPane(fake_checkout)
    wait(qapp, lambda: pane2.loaded is not None)
    assert pane2.loaded == {"update.auto_check": False} and not pane2.auto_check.isChecked()
    pane2.auto_check.setChecked(True)
    assert pane2.values() == {}  # on is the default: OK unsets it
    pane.deleteLater()
    pane2.deleteLater()


# ---------------------------------------------------------------------------------------------- D-1130 review
def _both(**extra: tuple[int, bytes, bytes]) -> FakeCli:
    return FakeCli({"update status": (0, check_doc(), b""), "update install": (0, plan_doc("pip"), b""),
                    "update download": (0, download_doc(), b""), "update download --package": (0, package_doc(), b""),
                    "update install --bundle": (0, install_doc(), b""),
                    "update install --package": (0, program_doc(), b""), **extra})


def test_a_failed_app_part_is_still_reported_when_the_program_part_succeeds(qapp: Any) -> None:
    """The app refused under a running job, the program updated: the status and the outcome name both."""
    busy = b"agentprov: error [update.install.busy]: 1 running job runs from the app being replaced: job-1 (import)\n"
    cli = _both(**{"update install --bundle": (4, b"", busy)})
    c = _loaded(qapp, _controller(qapp, cli, program="installed"))
    after: list[list[str]] = []
    c.after_update = after.append
    c.download_and_install()
    wait(qapp, lambda: not c.busy and bool(after))
    assert after == [["The agentprov program"]]
    assert "The agentprov program is updated" in c.status_line and "Not updated: the app" in c.status_line
    assert any(line.startswith("The app was not updated") and "update.install.busy" in line for line in c.result)
    assert any("agentprov 0.1.1 → 0.3.0" in line for line in c.result)


@pytest.mark.parametrize(("action", "quit_line"), [("installed", "Installed. Quit AgentPROV and open it again"),
                                                   ("waiting-for-quit", "Ready. Quit AgentPROV")])
@pytest.mark.parametrize("program_ok", [True, False])
def test_the_app_parts_quit_instruction_survives_the_program_part(qapp: Any, action: str, quit_line: str,
                                                                  program_ok: bool) -> None:
    """The app installed (or, on Windows, is ready once it quits), then the program part ran: the status keeps the
    instruction to quit and reopen, whatever the program part's outcome, and adds the program's own line. Each part's
    start writes its own progress line, so the status of the moment cannot tell what the app part said."""
    failed = (1, b"", b"agentprov: error [y]: no\n")
    cli = _both(**{"update install --bundle": (0, install_doc(action), b""),
                   **({} if program_ok else {"update install --package": failed})})
    c = _loaded(qapp, _controller(qapp, cli, program="installed"))
    after: list[list[str]] = []
    c.after_update = after.append
    c.download_and_install()
    wait(qapp, lambda: not c.busy and bool(after))
    assert c.status_line.startswith(quit_line), c.status_line
    assert ("The agentprov program is updated" if program_ok else "The agentprov program was not updated") \
        in c.status_line


def test_a_part_whose_command_cannot_run_does_not_stop_the_next_one(qapp: Any) -> None:
    cli = _both()
    cli.raise_for = "--bundle"
    c = _loaded(qapp, _controller(qapp, cli, program="installed"))
    after: list[list[str]] = []
    c.after_update = after.append
    c.download_and_install()
    wait(qapp, lambda: not c.busy and bool(after))
    assert after == [["The agentprov program"]]  # called once, with the part that did install
    assert any("--package" in a and "--confirm" in a for a in cli.ran)
    assert any(line.startswith("The app was not updated") for line in c.result)


def test_nothing_updated_says_so(qapp: Any) -> None:
    cli = _both(**{"update install --bundle": (1, b"", b"agentprov: error [x]: no\n"),
                   "update install --package": (1, b"", b"agentprov: error [y]: no\n")})
    c = _loaded(qapp, _controller(qapp, cli, program="installed"))
    after: list[list[str]] = []
    c.after_update = after.append
    c.download_and_install()
    wait(qapp, lambda: not c.busy and after == [[]])
    assert c.status_line.startswith("Nothing was updated: the app; the agentprov program")


def test_the_confirmed_installs_are_never_killed_by_a_time_limit(qapp: Any) -> None:
    cli = _both()
    c = _loaded(qapp, _controller(qapp, cli, program="installed"))
    c.download_and_install()
    wait(qapp, lambda: not c.busy and c.program_install is not None)
    limits = {" ".join(a[:3]): t for a, t in zip(cli.ran, cli.timeouts, strict=True)}
    assert [t for a, t in zip(cli.ran, cli.timeouts, strict=True) if "--confirm" in a] == [None, None]
    assert limits["update install --format"] == 1800.0  # the plan query, which changes nothing, keeps its limit


def test_a_cli_changed_while_the_update_was_prepared_installs_nothing(qapp: Any) -> None:
    """Settings › General changed the agentprov to run between the plan and Install: the confirmation described
    another program, so nothing is installed."""
    cli = _both()
    c = _loaded(qapp, _controller(qapp, cli, program="installed"))
    which = {"cli": "checkout A"}
    c.identity = lambda: which["cli"]

    def ask(parent: Any, plan: Any) -> bool:
        which["cli"] = "checkout B"
        return True

    c.confirm = ask
    c.download_and_install()
    wait(qapp, lambda: not c.busy and "changed while the update" in c.status_line)
    assert not any("--confirm" in a for a in cli.ran)


def test_prepare_runs_once_before_the_first_part_installs(qapp: Any) -> None:
    cli = _both()
    c = _loaded(qapp, _controller(qapp, cli, program="installed"))
    seen: list[int] = []
    c.prepare = lambda: seen.append(sum("--confirm" in a for a in cli.ran))
    c.download_and_install()
    wait(qapp, lambda: not c.busy and c.program_install is not None)
    assert seen == [0]


def test_a_pulled_checkout_whose_sync_failed_says_so(qapp: Any) -> None:
    doc = json.loads(program_doc("checkout"))
    doc["synced"] = False
    cli = FakeCli({"update status": (0, check_doc(behind=CLI_ONLY, current=CLI_ONLY_CURRENT), b""),
                   "update install": (0, plan_doc("checkout"), b""),
                   "update install --checkout": (0, json.dumps(doc).encode(), b"")})
    c = _loaded(qapp, _controller(qapp, cli, bundle=None, program="checkout"))
    c.download_and_install()
    wait(qapp, lambda: not c.busy and c.program_install is not None)
    assert "NOT synced" in c.status_line and "updated;" not in c.status_line


def test_the_checkout_part_names_its_source_not_a_verification(qapp: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from agentprov_gui import updates as U
    from agentprov_gui.ui import updates as ui

    seen: list[str] = []
    monkeypatch.setattr(ui, "choose", lambda parent, title, text, informative, keep, other, tips: (
        seen.append(informative), False)[1])
    plan = U.plan(bundle=None, gui="0.1.1", app=None, program=U.parse_install(0, plan_doc("checkout")), package=None,
                  core="0.1.1")
    assert not ui.confirm_update(None, plan)
    assert "Source: " in seen[0] and "Verified: " not in seen[0]
    seen.clear()
    plan = U.plan(bundle=None, gui="0.1.1", app=None, program=U.parse_install(0, plan_doc("pip")),
                  package=U.parse_download(0, package_doc()), core="0.1.1")
    assert not ui.confirm_update(None, plan)
    assert "Verified: " in seen[0]


def test_the_install_argv_carries_this_apps_version_not_the_checks() -> None:
    from agentprov_gui import updates as U

    download = U.parse_download(0, download_doc())
    plan = U.plan(bundle=APP, gui="0.1.1", app=download, program=None, package=None, core=None)
    (part,) = plan.parts
    assert part.argv[part.argv.index("--gui-version") + 1] == "0.1.1"
