"""D-1065: ``agentprov update`` end to end against a fake GitHub (no socket), with simulated bundles for each
platform family: the check and its daily cache, the verified download, install and rollback, and the Windows helper."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

import pytest

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import update_support as us  # noqa: E402

from agentprov.cli import update as update_cmd  # noqa: E402
from agentprov.cli.main import main  # noqa: E402
from agentprov.update import apply as A  # noqa: E402
from agentprov.update import install as I  # noqa: E402
from agentprov.update import releases as R  # noqa: E402
from agentprov.versions import __version__  # noqa: E402

NEW = "9.0.0"  # newer than any installed version under test
TAG = f"v{NEW}"


class Run(NamedTuple):
    code: int
    out: str
    err: str


@pytest.fixture
def cli(capsys: pytest.CaptureFixture[str], home: Path) -> Callable[..., Run]:
    def run(*argv: str) -> Run:
        capsys.readouterr()
        code = main([*argv, "--progress", "off"])
        out, err = capsys.readouterr()
        return Run(code, out, err)

    return run


def _github(tmp_path: Path, label: str, archive: Path | None, *, sums: bytes | None = None, sig: bytes | None = None,
            extra_releases: tuple[dict[str, Any], ...] = ()) -> us.FakeTransport:
    """A fake GitHub serving one release with this platform's bundle, SHA256SUMS (correct unless given) and a
    signature when given."""
    name = R.bundle_asset_name(label)
    files: dict[str, bytes] = {}
    if archive is not None:
        files[name] = archive.read_bytes()
    if sums is None and archive is not None:
        sums = f"{hashlib.sha256(files[name]).hexdigest()}  {name}\n".encode()
    if sums is not None:
        files["SHA256SUMS"] = sums
    if sig is not None:
        files["SHA256SUMS.sig"] = sig
    routes: dict[str, Any] = {R.API_URL: us.answer(us.release(TAG, [(n, len(b)) for n, b in files.items()]),
                                                   *extra_releases)}
    routes.update({f"{us.REPO_DL}/{TAG}/{n}": b for n, b in files.items()})
    return us.FakeTransport(routes)


@pytest.fixture
def github(monkeypatch: pytest.MonkeyPatch, no_keys: Path) -> Callable[[us.FakeTransport], us.FakeTransport]:
    """Install a fake transport (and the no-key signers file) into the CLI's seams."""
    monkeypatch.setattr(update_cmd, "SIGNERS", no_keys)

    def use(t: us.FakeTransport) -> us.FakeTransport:
        monkeypatch.setattr(update_cmd, "transport", lambda: t)
        return t

    return use


# ---------------------------------------------------------------------------------------------- check and status


def test_check_needs_allow_network(cli: Callable[..., Run]) -> None:
    run = cli("update", "check")
    assert run.code == 4 and "--allow-network" in run.err


def test_check_reports_a_newer_release_and_caches_it(cli: Callable[..., Run], github, tmp_path: Path,
                                                     home: Path) -> None:
    t = github(_github(tmp_path, "macos-arm64", us.linux_tar(tmp_path / "x.tar.gz")))
    run = cli("update", "check", "--allow-network", "--platform", "linux-x86_64", "--gui-version", "0.1.1",
              "--format", "json")
    assert run.code == 0, run.err
    doc = json.loads(run.out)
    assert doc["format"] == "agentprov-update-check/0.1" and doc["fetched"] is True
    assert (doc["latest"], doc["tag"], doc["update_available"]) == (NEW, TAG, True)
    assert doc["current"] == {"core": __version__, "gui": "0.1.1"} and doc["behind"] == {"core": True, "gui": True}
    assert doc["assets"] == [] and doc["checksum_asset"]["name"] == "SHA256SUMS"  # no linux bundle in this release
    assert doc["release_url"] == f"https://github.com/nickjones39/AgentPROV/releases/tag/{TAG}"
    assert len(t.calls) == 1 and (home / "update" / "check.json").is_file()
    status = json.loads(cli("update", "status", "--platform", "macos-arm64", "--format", "json").out)
    assert status["format"] == "agentprov-update-status/0.1" and status["fetched"] is False
    assert status["latest"] == NEW and status["assets"][0]["name"] == "AgentPROV-macos-arm64.dmg"
    assert status["check_due"] is False and len(t.calls) == 1  # status never fetches
    text = cli("update", "check", "--allow-network", "--platform", "linux-x86_64")
    assert f"AgentPROV {NEW} is available" in text.err and "Release notes." in text.err


def test_if_stale_fetches_once_a_day_and_never_when_switched_off(cli: Callable[..., Run], github,
                                                                 tmp_path: Path) -> None:
    t = github(_github(tmp_path, "linux-x86_64", None, sums=b""))
    assert cli("update", "check", "--allow-network", "--if-stale").code == 0
    assert len(t.calls) == 1
    again = cli("update", "check", "--allow-network", "--if-stale", "--format", "json")
    assert again.code == 0 and len(t.calls) == 1 and json.loads(again.out)["fetched"] is False
    assert "already checked today" in again.err
    assert cli("settings", "set", "update.auto_check", "false").code == 0
    (Path(os.environ["AGENTPROV_HOME"]) / "update" / "check.json").unlink()
    off = cli("update", "check", "--allow-network", "--if-stale", "--format", "json")
    assert off.code == 0 and len(t.calls) == 1 and json.loads(off.out)["auto_check"] is False
    assert "update.auto_check is off" in off.err
    assert cli("update", "check", "--allow-network").code == 0 and len(t.calls) == 2  # an explicit check still runs


def test_the_last_notified_setting_takes_a_version_only(cli: Callable[..., Run]) -> None:
    assert cli("settings", "set", "update.last_notified", "0.1.2").code == 0
    assert cli("settings", "set", "update.last_notified", "latest").code == 2


def test_a_hostile_answer_fails_the_check_and_keeps_the_old_cache(cli: Callable[..., Run], github,
                                                                  tmp_path: Path) -> None:
    github(_github(tmp_path, "linux-x86_64", us.linux_tar(tmp_path / "x.tar.gz")))
    assert cli("update", "check", "--allow-network").code == 0
    bad = us.answer(us.release(TAG, [("AgentPROV-linux-x86_64.tar.gz", 5)],
                               url_for=lambda t, n: f"https://evil.example/{n}"))
    github(us.FakeTransport({R.API_URL: bad}))
    run = cli("update", "check", "--allow-network")
    assert run.code == 1 and "update.response.host" in run.err
    assert json.loads(cli("update", "status", "--format", "json").out)["latest"] == NEW


# ---------------------------------------------------------------------------------------------- download


def test_download_verifies_and_stages(cli: Callable[..., Run], github, tmp_path: Path, home: Path) -> None:
    t = github(_github(tmp_path, "linux-x86_64", us.linux_tar(tmp_path / "AgentPROV-linux-x86_64.tar.gz", NEW)))
    run = cli("update", "download", "--allow-network", "--platform", "linux-x86_64", "--format", "json")
    assert run.code == 0, run.err
    doc = json.loads(run.out)
    staged = home / "update" / "staging" / "linux-x86_64"
    assert doc["format"] == "agentprov-update-download/0.1" and doc["dir"] == str(staged)
    assert (doc["verification"], doc["signed_by"], doc["version"]) == ("sha256", None, NEW)
    assert (staged / "AgentPROV-linux-x86_64.tar.gz").is_file() and (staged / "staged.json").is_file()
    order = [u.rsplit("/", 1)[-1] for u, _ in t.calls]
    assert order[1:] == ["SHA256SUMS", "AgentPROV-linux-x86_64.tar.gz"]  # the list before the bundle
    assert all(hosts == R.DOWNLOAD_HOSTS for _, hosts in t.calls[1:])
    assert "SHA256SUMS only" in cli("update", "download", "--allow-network", "--platform", "linux-x86_64").err


def test_download_needs_allow_network(cli: Callable[..., Run]) -> None:
    assert cli("update", "download").code == 4


@pytest.mark.parametrize("case", ["bad checksum", "not listed", "no SHA256SUMS", "traversal"])
def test_download_refuses_and_keeps_nothing(cli: Callable[..., Run], github, tmp_path: Path, home: Path,
                                            case: str) -> None:
    label = "linux-x86_64"
    extra = [us.tar_entry("AgentPROV/../../evil", data=b"x")] if case == "traversal" else []
    archive = us.linux_tar(tmp_path / "AgentPROV-linux-x86_64.tar.gz", NEW, extra=extra)
    sums = {"bad checksum": b"0" * 64 + b"  AgentPROV-linux-x86_64.tar.gz\n",
            "not listed": b"0" * 64 + b"  other.zip\n"}.get(case)
    t = _github(tmp_path, label, archive, sums=sums)
    if case == "no SHA256SUMS":
        t.routes[R.API_URL] = us.answer(us.release(TAG, [("AgentPROV-linux-x86_64.tar.gz", archive.stat().st_size)]))
    github(t)
    run = cli("update", "download", "--allow-network", "--platform", label)
    assert run.code == 1, run.err
    assert {"bad checksum": "update.verify.sha256", "not listed": "update.verify.missing",
            "no SHA256SUMS": "update.verify.missing", "traversal": "update.archive"}[case] in run.err
    assert not (home / "update" / "staging" / label).exists()
    assert not (tmp_path.parent / "evil").exists()


def test_with_a_listed_key_a_bad_or_missing_signature_is_refused(cli: Callable[..., Run], github, tmp_path: Path,
                                                                monkeypatch: pytest.MonkeyPatch) -> None:
    signers = tmp_path / "signers"
    signers.write_text('rel namespaces="file" ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExample\n')
    archive = us.linux_tar(tmp_path / "AgentPROV-linux-x86_64.tar.gz", NEW)
    github(_github(tmp_path, "linux-x86_64", archive))
    monkeypatch.setattr(update_cmd, "SIGNERS", signers)
    unsigned = cli("update", "download", "--allow-network", "--platform", "linux-x86_64")
    assert unsigned.code == 1 and "update.verify.unsigned" in unsigned.err
    github(_github(tmp_path, "linux-x86_64", archive, sig=b"-----BEGIN SSH SIGNATURE-----\nbad\n"))
    import agentprov.update.verify as V

    monkeypatch.setattr(V.shutil, "which", lambda _n: "ssh-keygen")
    monkeypatch.setattr(V.subprocess, "run", lambda argv, **kw: __import__("subprocess").CompletedProcess(argv, 255))
    bad = cli("update", "download", "--allow-network", "--platform", "linux-x86_64")
    assert bad.code == 1 and "update.verify.signature" in bad.err


# ---------------------------------------------------------------------------------------------- install, rollback


def _linux_bundle(root: Path, version: str) -> Path:
    bundle = root / "AgentPROV"
    (bundle / "_internal").mkdir(parents=True)
    (bundle / "AgentPROV").write_text(f"#!/bin/sh\necho {version}\n")
    (bundle / "AgentPROV").chmod(0o755)
    return bundle


def _windows_bundle(root: Path, version: str) -> Path:
    bundle = root / "AgentPROV"
    bundle.mkdir(parents=True)
    (bundle / "AgentPROV.exe").write_bytes(f"MZ {version}".encode())
    return bundle


def test_install_and_rollback_on_linux(cli: Callable[..., Run], github, tmp_path: Path, home: Path) -> None:
    github(_github(tmp_path, "linux-x86_64", us.linux_tar(tmp_path / "AgentPROV-linux-x86_64.tar.gz", NEW)))
    bundle = _linux_bundle(tmp_path / "apps", "0.1.1")
    assert cli("update", "download", "--allow-network", "--platform", "linux-x86_64").code == 0
    refused = cli("update", "install", "--bundle", str(bundle), "--platform", "linux-x86_64")
    assert refused.code == 4 and "--confirm" in refused.err and "0.1.1" in (bundle / "AgentPROV").read_text()
    run = cli("update", "install", "--confirm", "--bundle", str(bundle), "--platform", "linux-x86_64",
              "--gui-version", "0.1.1", "--format", "json")
    assert run.code == 0, run.err
    doc = json.loads(run.out)
    assert (doc["action"], doc["from_version"], doc["to_version"], doc["restart"]) == ("installed", "0.1.1", NEW,
                                                                                      "quit and reopen")
    assert NEW in (bundle / "AgentPROV").read_text() and os.access(bundle / "AgentPROV", os.X_OK)
    previous = tmp_path / "apps" / ".AgentPROV-previous" / "AgentPROV"
    assert "0.1.1" in (previous / "AgentPROV").read_text()
    assert not (tmp_path / "apps" / ".AgentPROV-update").exists()
    assert json.loads((home / "update" / "installed.json").read_text())["state"] == "installed"
    assert "rollback --yes --bundle" in doc["rollback_command"]
    assert cli("update", "rollback", "--bundle", str(bundle), "--platform", "linux-x86_64").code == 4
    back = cli("update", "rollback", "--yes", "--bundle", str(bundle), "--platform", "linux-x86_64")
    assert back.code == 0, back.err
    assert "0.1.1" in (bundle / "AgentPROV").read_text() and NEW in (previous / "AgentPROV").read_text()


def test_install_on_macos_from_the_disk_image(cli: Callable[..., Run], github, tmp_path: Path,
                                              monkeypatch: pytest.MonkeyPatch) -> None:
    dmg = tmp_path / "AgentPROV-macos-arm64.dmg"
    dmg.write_bytes(b"a disk image")
    github(_github(tmp_path, "macos-arm64", dmg))
    new_app = us.macos_app(tmp_path / "release", NEW)
    log: list[list[str]] = []
    monkeypatch.setattr(update_cmd, "DMG_RUN", us.dmg_run(new_app, log))
    bundle = us.macos_app(tmp_path / "Applications", "0.1.1")
    assert cli("update", "download", "--allow-network", "--platform", "macos-arm64").code == 0
    assert log == []  # a disk image is not attached at download
    run = cli("update", "install", "--confirm", "--bundle", str(bundle), "--platform", "macos-arm64", "--format",
              "json")
    assert run.code == 0, run.err
    doc = json.loads(run.out)
    assert (doc["from_version"], doc["to_version"]) == ("0.1.1", NEW)  # read from Info.plist
    assert I.bundle_version(bundle, "macos-arm64") == NEW
    assert I.bundle_version(tmp_path / "Applications" / ".AgentPROV-previous" / "AgentPROV.app", "macos-arm64") == \
        "0.1.1"
    same = cli("update", "install", "--confirm", "--bundle", str(bundle), "--platform", "macos-arm64", "--format",
               "json")
    assert same.code == 0 and json.loads(same.out)["action"] == "current"


def test_a_downgrade_and_a_wrong_bundle_path_are_refused(cli: Callable[..., Run], github, tmp_path: Path) -> None:
    github(_github(tmp_path, "linux-x86_64", us.linux_tar(tmp_path / "AgentPROV-linux-x86_64.tar.gz", NEW)))
    bundle = _linux_bundle(tmp_path / "apps", "99.0.0")
    assert cli("update", "download", "--allow-network", "--platform", "linux-x86_64").code == 0
    down = cli("update", "install", "--confirm", "--bundle", str(bundle), "--platform", "linux-x86_64",
               "--gui-version", "99.0.0")
    assert down.code == 4 and "update.install.downgrade" in down.err
    other = tmp_path / "apps" / "Other"
    other.mkdir()
    assert cli("update", "install", "--confirm", "--bundle", str(other), "--platform", "linux-x86_64").code == 2


def test_install_without_a_download_says_so(cli: Callable[..., Run], tmp_path: Path) -> None:
    bundle = _linux_bundle(tmp_path / "apps", "0.1.1")
    run = cli("update", "install", "--confirm", "--bundle", str(bundle), "--platform", "linux-x86_64")
    assert run.code == 4 and "update download" in run.err


def test_a_staged_archive_changed_after_download_is_refused(cli: Callable[..., Run], github, tmp_path: Path,
                                                            home: Path) -> None:
    github(_github(tmp_path, "linux-x86_64", us.linux_tar(tmp_path / "AgentPROV-linux-x86_64.tar.gz", NEW)))
    bundle = _linux_bundle(tmp_path / "apps", "0.1.1")
    assert cli("update", "download", "--allow-network", "--platform", "linux-x86_64").code == 0
    staged = home / "update" / "staging" / "linux-x86_64" / "AgentPROV-linux-x86_64.tar.gz"
    us.linux_tar(staged.with_name("swap.tar.gz"), "6.6.6").replace(staged)
    run = cli("update", "install", "--confirm", "--bundle", str(bundle), "--platform", "linux-x86_64")
    assert run.code == 1 and "update.verify.sha256" in run.err
    assert "0.1.1" in (bundle / "AgentPROV").read_text()


def test_on_windows_the_swap_waits_for_the_app_to_quit(cli: Callable[..., Run], github, tmp_path: Path,
                                                       home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    github(_github(tmp_path, "windows-x64", us.windows_zip(tmp_path / "AgentPROV-windows-x64.zip", NEW)))
    plans: list[Path] = []
    monkeypatch.setattr(update_cmd, "HELPER", lambda plan: plans.append(plan) or 4242)
    bundle = _windows_bundle(tmp_path / "apps", "0.1.1")
    assert cli("update", "download", "--allow-network", "--platform", "windows-x64").code == 0
    run = cli("update", "install", "--confirm", "--bundle", str(bundle), "--platform", "windows-x64",
              "--gui-version", "0.1.1", "--format", "json")
    assert run.code == 0, run.err
    doc = json.loads(run.out)
    assert doc["action"] == "waiting-for-quit" and doc["helper_pid"] == 4242 and len(plans) == 1
    assert (bundle / "AgentPROV.exe").read_bytes() == b"MZ 0.1.1"  # nothing replaced while the app runs
    again = cli("update", "install", "--confirm", "--bundle", str(bundle), "--platform", "windows-x64",
                "--gui-version", "0.1.1")
    assert again.code == 4 and "update.install.pending" in again.err
    # the helper: the app still runs twice (a sharing violation), then it has quit
    real, failures = I.swap_in, [PermissionError(32, "in use"), PermissionError(32, "in use")]

    def swap(*a: Path) -> None:
        if failures:
            raise failures.pop()
        real(*a)

    monkeypatch.setattr(A, "swap_in", swap)
    slept: list[float] = []
    outcome = A.apply(plans[0], sleep=slept.append)
    assert outcome["state"] == "installed" and outcome["attempts"] == 3 and slept == [2.0, 2.0]
    assert (bundle / "AgentPROV.exe").read_bytes() == f"MZ {NEW}".encode()
    assert (tmp_path / "apps" / ".AgentPROV-previous" / "AgentPROV" / "AgentPROV.exe").read_bytes() == b"MZ 0.1.1"
    assert not (tmp_path / "apps" / ".AgentPROV-update").exists()
    assert json.loads((home / "update" / "applied.json").read_text())["state"] == "installed"
    back = cli("update", "rollback", "--yes", "--bundle", str(bundle), "--platform", "windows-x64", "--format", "json")
    assert back.code == 0 and json.loads(back.out)["action"] == "waiting-for-quit"
    assert A.apply(plans[1], sleep=slept.append)["state"] == "rolled-back"
    assert (bundle / "AgentPROV.exe").read_bytes() == b"MZ 0.1.1"


def test_the_helper_gives_up_after_the_wait_and_says_so(tmp_path: Path, home: Path,
                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = _windows_bundle(tmp_path / "apps", "0.1.1")
    new = _windows_bundle(tmp_path / "apps" / ".AgentPROV-update" / "new", NEW)
    stage = tmp_path / "apps" / ".AgentPROV-update"
    plan = I._plan(stage, home, op="install", bundle=bundle, previous=bundle.parent / ".AgentPROV-previous" /
                   "AgentPROV", new=new, record={"to_version": NEW})

    def busy(*_a: Path) -> None:
        raise PermissionError(32, "in use")

    monkeypatch.setattr(A, "swap_in", busy)
    ticks = iter(range(0, 10_000, 1000))
    outcome = A.apply(plan, sleep=lambda _s: None, clock=lambda: float(next(ticks)))
    assert outcome["state"] == "failed" and outcome["error"] == "PermissionError"
    assert (bundle / "AgentPROV.exe").read_bytes() == b"MZ 0.1.1" and not plan.exists()


def test_a_forged_plan_is_not_run(tmp_path: Path) -> None:
    stage = tmp_path / ".AgentPROV-update"
    stage.mkdir()
    plan = stage / "plan.json"
    plan.write_text(json.dumps({"format": I.PLAN_FORMAT, "op": "install", "bundle": "/elsewhere/AgentPROV",
                                "previous": "/x", "new": "/y", "stage": str(stage), "wait_s": 1,
                                "result": str(tmp_path / "r.json"), "record": {}}))
    assert A.main([str(plan)]) == 1 and not (tmp_path / "r.json").exists()


def test_swap_in_puts_everything_back_when_the_second_rename_fails(tmp_path: Path,
                                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = _linux_bundle(tmp_path / "apps", "0.1.1")
    new = _linux_bundle(tmp_path / "stage", NEW)
    previous = tmp_path / "apps" / ".AgentPROV-previous" / "AgentPROV"
    _linux_bundle(previous.parent / "old", "0.1.0").rename(previous)
    real = os.rename

    def rename(src: Any, dst: Any) -> None:
        if Path(src) == new:
            raise OSError("disk full")
        real(src, dst)

    monkeypatch.setattr(I.os, "rename", rename)
    with pytest.raises(OSError):
        I.swap_in(bundle, new, previous)
    assert "0.1.1" in (bundle / "AgentPROV").read_text() and "0.1.0" in (previous / "AgentPROV").read_text()


# ---------------------------------------------------------------------------------------------- package installs


def test_a_package_install_gets_its_upgrade_command(cli: Callable[..., Run]) -> None:
    run = cli("update", "install", "--format", "json")
    doc = json.loads(run.out)
    assert run.code == 0 and doc["action"] == "command" and doc["kind"] in ("checkout", "uv-tool", "pipx", "pip")
    assert cli("update", "install", "--confirm").code == 2  # --confirm goes with --bundle


@pytest.mark.parametrize(("setup", "kind", "command"), [
    ("uv", "uv-tool", ["uv", "tool", "upgrade", "agentprov"]),
    ("pipx", "pipx", ["pipx", "upgrade", "agentprov"]),
    ("pip", "pip", ["/venv/bin/python", "-m", "pip", "install", "--upgrade", "agentprov"]),
    ("editable", "checkout", None),
])
def test_the_package_install_kind(tmp_path: Path, setup: str, kind: str, command: list[str] | None) -> None:
    prefix = tmp_path / ("pipx/venvs/agentprov" if setup == "pipx" else "venv")
    prefix.mkdir(parents=True)
    if setup == "uv":
        (prefix / "uv-receipt.toml").write_text("[tool]\n")
    direct = json.dumps({"url": "file:///repo", "dir_info": {"editable": True}}) if setup == "editable" else ""
    got = I.package_install(prefix=str(prefix), executable="/venv/bin/python", direct_url=direct)
    assert (got["kind"], got["command"]) == (kind, command)
