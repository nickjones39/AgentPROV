"""G5 note P-7: ``build_bundle.py``'s per-OS checks on fixture trees, so the Windows and Linux layouts are tested on
any host before a runner builds them: the layout, the excluded Qt modules (Linux's ``.so.6`` names included), Qt as
separate replaceable files, the licence texts, the ``xcb`` plugin, the glibc floor, the signature wording and the
package each OS ships (a dmg on macOS, a zip on Windows, a tar.gz on Linux) and the icon each carries."""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

GUI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GUI / "tools"))

import build_bundle as bb  # noqa: E402

LICENCES = GUI / "packaging" / "licenses"
ICONS = GUI / "packaging" / "icons"


def _touch(path: Path, data: bytes = b"") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _bundle(root: Path, platform: str) -> Path:
    """A minimal well-formed bundle of ``platform``."""
    app = bb.bundle_path(root / "dist", platform)
    if platform == "darwin":
        _touch(app / "Contents" / "MacOS" / "AgentPROV")
        (app / "Contents" / "Frameworks" / "QtCore.framework").mkdir(parents=True)
        _touch(app / "Contents" / "Info.plist", plistlib.dumps({"CFBundleIconFile": "AgentPROV.icns"}))
        shutil.copy(ICONS / "AgentPROV.icns", _touch(app / "Contents" / "Resources" / "AgentPROV.icns"))
    elif platform == "win32":  # PyInstaller copies the .ico's images into the executable's icon resources
        _touch(app / "AgentPROV.exe", b"MZ" + b"".join(bb._ico_images(ICONS / "AgentPROV.ico")))
    else:
        _touch(app / "AgentPROV", b"\x7fELF GLIBC_2.17")
        bb.add_linux_desktop(app)
        shutil.copytree(ICONS / "hicolor", app / "_internal" / "share" / "icons" / "hicolor")
    if platform != "darwin":
        _touch(app / "_internal" / "PySide6" / ("Qt6Core.dll" if platform == "win32" else "Qt" / Path("lib") /
                                                "libQt6Core.so.6"), b"\x7fELF GLIBC_2.28")
        if platform == "linux":
            _touch(app / "_internal" / "PySide6" / "Qt" / "plugins" / "platforms" / "libqxcb.so", b"\x7fELF")
    licences = bb._resources(app, platform) / "licenses"
    licences.mkdir(parents=True, exist_ok=True)
    for name in bb.LICENCES:
        shutil.copy(LICENCES / name, licences / name)
    _touch(bb._resources(app, platform) / "THIRD_PARTY_NOTICES.md", b"notices")
    return app


@pytest.mark.parametrize("platform", ["darwin", "win32", "linux"])
def test_a_well_formed_bundle_passes_every_check(tmp_path: Path, platform: str) -> None:
    app = _bundle(tmp_path, platform)
    assert bb.check_layout(app, platform) == []
    assert bb.check_qt_dynamic(app, platform) == []
    assert bb.check_licences(app, platform) == []
    assert bb.check_excluded(app) == []
    assert bb.check_icon(app, platform) == []
    if platform == "linux":
        assert bb.check_linux_plugins(app) == [] and bb.glibc_required(app) == (2, 28)


def test_the_windows_executable_is_the_exe(tmp_path: Path) -> None:
    app = _bundle(tmp_path, "win32")
    assert bb._executable(app, "win32").name == "AgentPROV.exe"
    (app / "AgentPROV.exe").unlink()
    assert bb.check_layout(app, "win32") == ["executable AgentPROV.exe missing"]
    shutil.rmtree(app / "_internal")
    assert "_internal missing" in bb.check_layout(app, "win32")


@pytest.mark.parametrize(("platform", "name"), [
    ("linux", "libQt6WebEngineCore.so.6"), ("linux", "libQt6Network.so.6.10.0"), ("win32", "Qt6Quick.dll"),
    ("win32", "QtQml.pyd"), ("darwin", "QtPdf.framework"),
])
def test_excluded_qt_modules_are_found_on_every_os(tmp_path: Path, platform: str, name: str) -> None:
    app = _bundle(tmp_path, platform)
    target = bb._resources(app, platform) / name
    if name.endswith(".framework"):
        target.mkdir(parents=True)
    else:
        _touch(target)
    _touch(bb._resources(app, platform) / "QtQuick-notes.txt")  # not a library: ignored
    assert bb.check_excluded(app) == [str(target.relative_to(app))]


@pytest.mark.parametrize("platform", ["darwin", "win32", "linux"])
def test_a_missing_qt_core_or_licence_fails(tmp_path: Path, platform: str) -> None:
    app = _bundle(tmp_path, platform)
    for core in app.rglob(bb._QT_CORE[platform]):
        shutil.rmtree(core) if core.is_dir() else core.unlink()
    assert bb.check_qt_dynamic(app, platform) == [f"{bb._QT_CORE[platform]} not found"]
    (bb._resources(app, platform) / "licenses" / "LGPL-3.0.txt").write_text("not the licence")
    (bb._resources(app, platform) / "THIRD_PARTY_NOTICES.md").unlink()
    assert bb.check_licences(app, platform) == ["LGPL-3.0.txt", "THIRD_PARTY_NOTICES.md"]


def test_linux_needs_the_xcb_plugin(tmp_path: Path) -> None:
    app = _bundle(tmp_path, "linux")
    next(app.rglob("libqxcb.so")).unlink()
    assert bb.check_linux_plugins(app) == ["platforms/libqxcb.so missing"]


def test_the_glibc_floor_reads_elf_files_only(tmp_path: Path) -> None:
    app = _bundle(tmp_path, "linux")
    _touch(app / "_internal" / "libnew.so.1", b"\x7fELF\x00GLIBC_2.17\x00GLIBC_2.38\x00GLIBC_2.4\x00")
    _touch(app / "_internal" / "readme.so", b"text GLIBC_2.99")  # not ELF: ignored
    assert bb.glibc_required(app) == (2, 38) and bb.glibc_required(app) > bb.GLIBC_FLOOR
    assert bb.GLIBC_FLOOR == (2, 35)


def test_the_signature_wording_off_macos(tmp_path: Path) -> None:
    assert "unsigned" in bb.signature(tmp_path, "win32") and "Run anyway" in bb.signature(tmp_path, "win32")
    assert "sha256" in bb.signature(tmp_path, "linux")


def test_the_ad_hoc_macos_wording_is_open_anyway(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    done = subprocess.CompletedProcess([], 0, "", "Signature=adhoc\n")
    monkeypatch.setattr(bb, "_sh", lambda *_a, **_k: done)
    wording = bb.signature(tmp_path, "darwin")
    assert "Open Anyway" in wording and "right-click" not in wording  # D-944 §5: macOS 15 and later


def test_the_report_names_the_source_commit_of_a_git_archive(tmp_path: Path) -> None:
    commit = "0123456789abcdef0123456789abcdef01234567"
    archive = tmp_path / "checkout.tar.gz"
    with tarfile.open(archive, "w:gz", format=tarfile.PAX_FORMAT, pax_headers={"comment": commit}) as tar:
        info = tarfile.TarInfo("README.md")
        tar.addfile(info)
    assert bb.build_source(archive) == {"commit": commit, "basis": "git archive pax comment", "tree_clean": None}
    with tarfile.open(plain := tmp_path / "plain.tar.gz", "w:gz") as tar:
        tar.addfile(tarfile.TarInfo("README.md"))
    assert bb.build_source(plain)["commit"] is None  # never guessed


def test_the_report_names_the_checkout_head_or_nothing(tmp_path: Path) -> None:
    here = bb.build_source()
    if here["basis"] == "checkout HEAD":
        assert isinstance(here["commit"], str) and len(here["commit"]) == 40 and isinstance(here["tree_clean"], bool)
    assert bb.build_source(repo=tmp_path) == {"commit": None, "basis": "no git checkout", "tree_clean": None}
    assert set(bb.versions()) == {"agentprov-gui", "agentprov"}


def test_each_os_ships_its_package(tmp_path: Path) -> None:
    linux = _bundle(tmp_path / "l", "linux")
    (linux / "AgentPROV").chmod(0o755)
    tgz = bb.package(linux, tmp_path, "linux", "x86_64")
    assert tgz is not None and tgz.name == "AgentPROV-linux-x86_64.tar.gz"
    with tarfile.open(tgz) as tf:
        exe = tf.getmember("AgentPROV/AgentPROV")
        assert exe.mode & 0o111 and all(m.name.startswith("AgentPROV") for m in tf.getmembers())
    win = _bundle(tmp_path / "w", "win32")
    archive = bb.package(win, tmp_path, "win32", "AMD64")
    assert archive is not None and archive.name == "AgentPROV-windows-amd64.zip"
    with zipfile.ZipFile(archive) as zf:
        assert "AgentPROV/AgentPROV.exe" in zf.namelist()
    made: list[Path] = []
    real = bb.make_dmg
    bb.make_dmg = lambda app, target, icons=ICONS: made.append(target) or target  # type: ignore[assignment]
    try:
        dmg = bb.package(_bundle(tmp_path / "m", "darwin"), tmp_path, "darwin", "arm64")
    finally:
        bb.make_dmg = real
    assert dmg.name == "AgentPROV-macos-arm64.dmg" and made == [dmg]


@pytest.mark.parametrize("platform", ["darwin", "win32", "linux"])
def test_a_bundle_without_the_icon_fails(tmp_path: Path, platform: str) -> None:
    app = _bundle(tmp_path, platform)
    if platform == "darwin":
        (app / "Contents" / "Resources" / "AgentPROV.icns").write_bytes(b"icns")
        assert bb.check_icon(app, platform) == ["AgentPROV.icns is not gui/packaging/icons/AgentPROV.icns"]
        (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps({}))
        assert bb.check_icon(app, platform) == ["Info.plist names no CFBundleIconFile"]
    elif platform == "win32":
        (app / "AgentPROV.exe").write_bytes(b"MZ no icon")
        assert bb.check_icon(app, platform) == [f"AgentPROV.exe lacks {len(bb._ico_images(ICONS / 'AgentPROV.ico'))} "
                                                "of the .ico's images"]
    else:
        (app / "install-desktop-entry.sh").unlink()
        shutil.rmtree(app / "_internal" / "share")
        assert bb.check_icon(app, platform) == ["install-desktop-entry.sh missing", "hicolor icons missing"]


def test_the_dmg_carries_the_app_icon_as_its_volume_icon(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The dmg steps: stage the app with an Applications link and .VolumeIcon.icns, set the volume's custom-icon flag
    while it is mounted (and detach even if that fails), then compress."""
    calls: list[list[str]] = []
    staged: dict[str, bool] = {}

    def sh(argv: list[str], **_k: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        if argv[:2] == ["hdiutil", "create"]:
            stage = Path(argv[argv.index("-srcfolder") + 1])
            staged["icon"] = (stage / ".VolumeIcon.icns").read_bytes() == (ICONS / "AgentPROV.icns").read_bytes()
            staged["link"] = os.readlink(stage / "Applications") == "/Applications"
        return subprocess.CompletedProcess(argv, 1 if argv[0] == "xattr" and fail else 0, "", "")

    monkeypatch.setattr(bb, "_sh", sh)
    fail = False
    app = _bundle(tmp_path, "darwin")
    bb.make_dmg(app, tmp_path / "AgentPROV.dmg")
    assert [c[:2] for c in calls] == [["ditto", str(app)], ["hdiutil", "create"], ["hdiutil", "attach"],
                                      ["xattr", "-wx"], ["hdiutil", "detach"], ["hdiutil", "convert"]]
    assert staged == {"icon": True, "link": True}
    assert calls[3][2:4] == ["com.apple.FinderInfo", "0" * 16 + "0400" + "0" * 44]
    calls.clear()
    fail = True
    with pytest.raises(SystemExit, match="xattr -wx failed"):
        bb.make_dmg(app, tmp_path / "AgentPROV.dmg")
    assert calls[-1][:2] == ["hdiutil", "detach"]


@pytest.mark.skipif(sys.platform == "win32", reason="a POSIX sh script")
def test_the_linux_desktop_entry_installs_for_the_user(tmp_path: Path) -> None:
    app = _bundle(tmp_path / "b", "linux")
    (app / "AgentPROV").chmod(0o755)
    data = tmp_path / "data"
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(tmp_path), "XDG_DATA_HOME": str(data)}
    done = subprocess.run(["sh", str(app / "install-desktop-entry.sh")], env=env, capture_output=True, text=True,
                          check=False)
    assert done.returncode == 0, done.stderr
    entry = (data / "applications" / "org.agentprov.gui.desktop").read_text()
    assert f'Exec="{app.resolve()}/AgentPROV"' in entry.splitlines() and "Icon=agentprov" in entry
    assert (data / "icons" / "hicolor" / "256x256" / "apps" / "agentprov.png").is_file()
    assert (data / "icons" / "hicolor" / "scalable" / "apps" / "agentprov.svg").is_file()
    done = subprocess.run(["sh", str(app / "install-desktop-entry.sh"), "--remove"], env=env, capture_output=True,
                          text=True, check=False)
    assert done.returncode == 0 and not (data / "applications" / "org.agentprov.gui.desktop").exists()
    assert not (data / "icons" / "hicolor" / "256x256" / "apps" / "agentprov.png").exists()
    odd = tmp_path / "b$x"
    shutil.copytree(app, odd / "AgentPROV")
    done = subprocess.run(["sh", str(odd / "AgentPROV" / "install-desktop-entry.sh")], env=env, capture_output=True,
                          text=True, check=False)
    assert done.returncode == 1 and "cannot quote" in done.stderr


def test_the_icons_match_their_svg_sources() -> None:
    """``make_icons.py --check``: every generated icon file is the one rendered from the current brand SVGs."""
    import make_icons

    assert make_icons.check() == []


def test_size_counts_each_regular_file_once(tmp_path: Path) -> None:
    """The report's size (build log 46): PyInstaller's macOS layout links files between ``Frameworks/`` and
    ``Resources/``; a symlink pair (a file link and a directory link) is counted once, not followed."""
    app = _bundle(tmp_path, "darwin")
    base = bb.size_mb(app)  # the fixture's own files (the licence texts)
    lib = _touch(app / "Contents" / "Frameworks" / "libbig.dylib", b"x" * 2_000_000)
    data = _touch(app / "Contents" / "Frameworks" / "data" / "blob.bin", b"y" * 500_000)
    (app / "Contents" / "Resources").mkdir(parents=True, exist_ok=True)
    (app / "Contents" / "Resources" / "libbig.dylib").symlink_to(lib)
    (app / "Contents" / "Resources" / "data").symlink_to(data.parent, target_is_directory=True)
    assert abs(bb.size_mb(app) - base - 2.5) < 0.15
    # the old count followed the file link (rglob does not descend a directory link): 2.0 MB counted twice
    following = sum(p.stat().st_size for p in app.rglob("*") if p.is_file()) / 1e6
    assert abs(following - base - 4.5) < 0.15


def test_only_cpython_3_14_builds_a_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The G5 clean-machine Linux build froze CPython 3.15.1: ``uv --project gui`` ignores the root's
    ``.python-version``. ``gui/.python-version`` pins 3.14.8 and the build refuses any other minor version, before
    PyInstaller runs."""
    assert (GUI / ".python-version").read_text(encoding="utf-8").strip() == "3.14.8"
    assert bb.check_python((3, 14, 8), "cpython") is None
    assert bb.check_python((3, 14, 0, "final", 0), "cpython") is None
    for version, implementation in (((3, 15, 1), "cpython"), ((3, 13, 9), "cpython"), ((3, 14, 8), "pypy")):
        refused = bb.check_python(version, implementation)
        assert refused is not None and f"{implementation} {'.'.join(map(str, version))}" in refused
    monkeypatch.setattr(bb, "check_python", lambda: "build_bundle: not this interpreter")
    monkeypatch.setattr(bb, "build", lambda out: pytest.fail("built under a refused interpreter"))
    with pytest.raises(SystemExit, match="not this interpreter"):
        bb.main(["--out", str(tmp_path)])
    assert not (tmp_path / "bundle-report.json").exists()


@pytest.mark.parametrize(("plat", "arch"), [("win-amd64", "amd64"), ("win-arm64", "arm64"),
                                            ("linux-x86_64", "x86_64"), ("linux-aarch64", "aarch64")])
def test_the_package_is_named_for_the_interpreter_not_the_host(plat: str, arch: str, tmp_path: Path,
                                                              monkeypatch: pytest.MonkeyPatch) -> None:
    """G5 clean-machine run (Windows x64 under Windows 11 ARM64's emulation): an x64 bundle came out as
    ``AgentPROV-windows-arm64.zip`` because ``platform.machine()`` names the host."""
    monkeypatch.setattr(bb.sysconfig, "get_platform", lambda: plat)
    monkeypatch.setattr(bb._platform, "machine", lambda: "ARM64")  # the emulating host
    assert bb.interpreter_arch() == arch
    os_name = "win32" if plat.startswith("win") else "linux"
    packed = bb.package(_bundle(tmp_path, os_name), tmp_path, os_name)
    assert packed.name.endswith(f"-{arch}.zip" if os_name == "win32" else f"-{arch}.tar.gz")
