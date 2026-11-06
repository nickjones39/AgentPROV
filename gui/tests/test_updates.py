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


class FakeCli:
    """The controller's runner: answers by the command's first words, records every argv (never runs anything)."""

    def __init__(self, answers: dict[str, tuple[int, bytes, bytes]]) -> None:
        self.answers = answers
        self.ran: list[list[str]] = []

    def __call__(self, argv: list[str], timeout: float) -> tuple[int, bytes, bytes]:
        self.ran.append(list(argv))
        key = " ".join(argv[:2])
        if key == "settings list":
            return self.answers.get(key, (0, json.dumps({"values": {}}).encode(), b""))
        return self.answers.get(key, (2, b"", b"agentprov: error [usage]: no such command"))

    def words(self) -> list[str]:
        return [" ".join(a[:2]) for a in self.ran]


def _controller(qapp: Any, cli: FakeCli, *, bundle: Path | None = APP, confirm: bool | None = True) -> Any:
    from agentprov_gui.ui.updates import UpdateController

    c = UpdateController(cli, bundle=bundle, gui="0.1.1")
    c.asked = []  # type: ignore[attr-defined]

    def ask(parent: Any, download: Any, where: Path, current: str | None) -> bool:
        c.asked.append((download, where, current))  # type: ignore[attr-defined]
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
    ((download, where, current),) = c.asked
    assert where == APP and current == "0.1.1" and download.verification == "sha256"
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
    c = _controller(qapp, cli, bundle=None, confirm=None)
    dlg = _about(qapp, c)
    sec = dlg.updates_section
    assert sec.install_btn.text() == "Show the Upgrade Command" and sec.install_btn.isEnabled()
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
    c = _controller(qapp, cli, confirm=None)
    dlg = _about(qapp, c)
    sec = dlg.updates_section
    assert not c.bundle_update and sec.install_btn.text() == "Show the Upgrade Command"
    assert sec.install_btn.accessibleName() == "Show the Upgrade Command" and "Settings › General" in \
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
    assert download is not None and not ui.confirm_install(None, download, APP, "0.1.1")
    ((text, informative),) = seen
    assert text == "Install AgentPROV 0.3.0?"
    for part in (str(APP), "0.1.1", ".AgentPROV-previous", "agentprov update rollback --yes --bundle", U.UNSIGNED_NOTE):
        assert part in informative


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
    for part in ("AgentPROV 0.3.0, which is current", "0.1.1", "Settings › General", "nothing is downloaded"):
        assert part in summary
    assert dlg.update_btn.text() == "Show the Upgrade Command" and dlg.update_btn.isDefault()
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
