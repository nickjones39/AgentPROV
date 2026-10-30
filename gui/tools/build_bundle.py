"""Build the GUI bundle and run the G5 checks (design §13, macos-design §8; D-399).

    uv run --project gui python gui/tools/build_bundle.py [--out DIR] [--no-build] [--sign-identity NAME]

The build goes outside the repository (default ``$AGENTPROV_HOME/migration-work/gui-g5``). It runs only under
CPython 3.14 (:data:`PYTHON`): ``gui/.python-version`` pins 3.14.8, the core's release floor, because ``uv --project gui``
ignores the repository root's ``.python-version`` and would otherwise freeze the newest CPython (G5 clean-machine
report, Linux arm64: 3.15.1). The report names the interpreter. The checks:

1. **Excluded modules:** no ``QtWebEngine*``, ``QtQuick*``, ``QtQml*``, ``QtNetwork``, ``QtMultimedia``, ``Qt3D*`` or
   ``QtPdf`` library or Python module in the bundle.
2. **LGPL:** ``licenses/LGPL-3.0.txt`` and ``licenses/GPL-3.0.txt`` present with their canonical sha256, plus
   ``THIRD_PARTY_NOTICES.md``; Qt is dynamic (the frameworks are separate files).
3. **Launcher SDK (D-441):** the main executable's ``LC_BUILD_VERSION`` SDK (``otool -l``); macOS 27 needs ≥ 26 for the
   current look. PyInstaller lowers the executable's SDK field to the Python library's (uv's CPython 3.14: SDK 15),
   for Tk's sake (tkinter is excluded here). When the installed bootloader was really built with SDK ≥ 26
   (``gui/tools/install_bootloader.py``), the field is restored to that SDK with ``vtool`` and the bundle is re-signed
   ad hoc; never to a value the bootloader was not built with.
4. **Signature (D-657):** the bundle is signed ad hoc, which is the G5 target (no Apple Developer ID is bought). It
   starts on this Mac; on another Mac, Gatekeeper refuses the first launch: System Settings › Privacy & Security ›
   Open Anyway (macOS 15 and later no longer offer Control-click › Open for this; D-944 §5). Signing is a
   no-op unless ``--sign-identity NAME`` names a codesigning identity of the login keychain. Then the bundle is signed
   with it and the hardened runtime, and notarisation is still a separate, manual step. ``codesign -dv`` reports
   which signature the bundle has.
5. **Smoke start:** the bundle's executable with ``--smoke`` under ``QT_QPA_PLATFORM=offscreen`` and a scratch
   ``AGENTPROV_HOME`` exits 0; ``--preview-helper`` exits on EOF.

**Provenance of the bundle** (v0.1.0 plan §3): the report names the GUI's and the bundled core's version and the commit
it was built from: the checkout's ``HEAD`` (with whether the tree was clean), or, for a build from a ``git archive``
(the G5 VMs), the commit in the archive's pax comment, given with ``--source-archive``.

**Per OS** (G5 cross-platform note §2.7, P-7). Every check takes the platform (``darwin``, ``win32``, ``linux``) and
works on a file tree, so each is unit-tested on any host with fixture trees:

* **Layout:** ``AgentPROV.app`` (macOS); ``AgentPROV/AgentPROV.exe`` + ``_internal`` (Windows);
  ``AgentPROV/AgentPROV`` + ``_internal`` (Linux).
* **Qt is dynamic:** QtCore is a separate file (``QtCore.framework``, ``Qt6Core.dll``, ``libQt6Core.so.6``).
* **Linux:** the ``xcb`` platform plugin is present, and no bundled ELF file needs a glibc above
  :data:`GLIBC_FLOOR` (the newest ``GLIBC_x.y`` version string in any ``.so`` or the executable).
* **Signature:** ad hoc on macOS; **unsigned** on Windows (no certificate is bought; SmartScreen asks once: More info ›
  Run anyway) and on Linux (the package's sha256 is in the report).
* **Icon** (brand note ``docs/reports/gui/logo/brand.md``): the ``.app`` carries ``AgentPROV.icns`` as its
  ``CFBundleIconFile``; ``AgentPROV.exe`` embeds the ``.ico``'s images; the Linux folder has the desktop entry, its
  installer script and the hicolor icons. The files come from ``gui/packaging/icons/`` (``gui/tools/make_icons.py``).
* **Package:** a ``.dmg`` on macOS (``hdiutil``: the app, an Applications link and the icon as the volume icon), a
  ``.zip`` of the folder on Windows and a ``.tar.gz`` on Linux (executable bits kept), each with its sha256.

Exit 0 when every check passes; a JSON report is written next to the bundle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform as _platform
import plistlib
import re
import shutil
import stat
import subprocess
import sys
import sysconfig
import tarfile
import tempfile
import zipfile
from pathlib import Path

GUI = Path(__file__).resolve().parent.parent
SPEC = GUI / "packaging" / "agentprov-gui.spec"
ICONS = GUI / "packaging" / "icons"
LINUX_DESKTOP = ("org.agentprov.gui.desktop", "install-desktop-entry.sh")  # from gui/packaging/linux/
#: the 32-byte FinderInfo of a folder with a custom icon: kHasCustomIcon (0x0400) in the flags at offset 8
_CUSTOM_ICON = "00" * 8 + "0400" + "00" * 22
LICENCES = {"LGPL-3.0.txt": "e3a994d82e644b03a792a930f574002658412f62407f5fee083f2555c5f23118",
            "GPL-3.0.txt": "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986"}
#: macOS names Qt libraries QtX; Windows and Linux name them Qt6X (Qt6Quick.dll, libQt6WebEngineCore.so.6)
EXCLUDED = re.compile(r"Qt6?(WebEngine|Quick|Qml|Network|Multimedia|3D|Pdf)", re.IGNORECASE)
MIN_SDK = (26, 0)
#: the newest glibc a Linux bundle may need by default: Ubuntu 22.04's (G5 note §1); ``--glibc-floor`` raises it for a
#: leg built on a newer image (D-750: ``ubuntu-24.04-arm``, glibc 2.39)
GLIBC_FLOOR = (2, 35)
_GLIBC = re.compile(rb"GLIBC_(\d+)\.(\d+)")
#: the only CPython minor version a bundle is built with (``gui/.python-version`` pins the patch)
PYTHON = (3, 14)
_QT_CORE = {"darwin": "QtCore.framework", "win32": "Qt6Core.dll", "linux": "libQt6Core.so.6"}


def _sh(argv: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, check=False, timeout=600, **kw)  # type: ignore[call-overload]  # noqa: S603 - fixed tool argv


def bootloader_sdk() -> tuple[int, int] | None:
    import PyInstaller

    return launcher_sdk(Path(PyInstaller.__file__).resolve().parent / "bootloader" / "Darwin-64bit" / "runw")


def restore_sdk(app: Path) -> str:
    """Set the executable's SDK field back to the bootloader's real SDK (≥ 26 only), then re-sign ad hoc."""
    if sys.platform != "darwin":
        return "n/a"
    real = bootloader_sdk()
    if real is None or real < MIN_SDK:
        return f"kept: the bootloader's SDK is {real} (rebuild it, gui/tools/install_bootloader.py)"
    exe = _executable(app)
    tmp = exe.with_name(exe.name + ".sdk")
    done = _sh(["xcrun", "vtool", "-set-build-version", "macos", "11.0", f"{real[0]}.{real[1]}", "-replace",
                "-output", str(tmp), str(exe)])
    if done.returncode != 0:
        tmp.unlink(missing_ok=True)
        return "failed: vtool"
    os.replace(tmp, exe)
    exe.chmod(0o755)
    sign = _sh(["codesign", "--force", "--deep", "-s", "-", str(app)])
    return f"restored to {real[0]}.{real[1]}" if sign.returncode == 0 else "failed: codesign"


def sign(app: Path, identity: str | None) -> str:
    """D-657: ad hoc unless an identity is given (then that identity, the hardened runtime and a secure timestamp)."""
    if sys.platform != "darwin" or not identity:
        return "ad hoc (no --sign-identity)"
    done = _sh(["codesign", "--force", "--deep", "--options", "runtime", "--timestamp", "-s", identity, str(app)])
    return "signed" if done.returncode == 0 else f"failed: codesign ({done.stderr.strip()[-200:]})"


def bundle_path(dist: Path, platform: str = sys.platform) -> Path:
    return dist / ("AgentPROV.app" if platform == "darwin" else "AgentPROV")


def build(out: Path) -> Path:
    done = _sh([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", str(out / "dist"),
                "--workpath", str(out / "work"), str(SPEC)], cwd=str(GUI))
    (out / "pyinstaller.log").write_text(done.stdout + done.stderr, encoding="utf-8")
    if done.returncode != 0:
        raise SystemExit(f"build_bundle: PyInstaller failed (exit {done.returncode}); see {out / 'pyinstaller.log'}")
    return bundle_path(out / "dist")


def _resources(app: Path, platform: str = sys.platform) -> Path:
    return app / "Contents" / "Resources" if platform == "darwin" else app / "_internal"


def _executable(app: Path, platform: str = sys.platform) -> Path:
    if platform == "darwin":
        return app / "Contents" / "MacOS" / "AgentPROV"
    return app / ("AgentPROV.exe" if platform == "win32" else "AgentPROV")


def _library(p: Path) -> bool:
    """A shared library or extension module (``.so.6`` included: Linux's versioned names)."""
    return p.suffix in ("", ".dylib", ".so", ".dll", ".pyd") or ".so." in p.name


def size_mb(app: Path) -> float:
    """The bundle's size in MB: each regular file once. Symlinks are skipped, not followed: PyInstaller's macOS layout
    links files between ``Frameworks/`` and ``Resources/``, and following them counted those files twice."""
    total = 0
    for p in app.rglob("*"):
        st = p.lstat()
        if stat.S_ISREG(st.st_mode):
            total += st.st_size
    return round(total / 1e6, 1)


def check_excluded(app: Path) -> list[str]:
    return sorted(str(p.relative_to(app)) for p in app.rglob("*")
                  if EXCLUDED.search(p.name) and (p.is_dir() or _library(p)))


def add_linux_desktop(app: Path) -> None:
    """Linux: the desktop entry and its installer script go beside the executable (PyInstaller puts data files under
    ``_internal``, where a user would not look)."""
    for name in LINUX_DESKTOP:
        shutil.copyfile(GUI / "packaging" / "linux" / name, app / name)
    (app / LINUX_DESKTOP[1]).chmod(0o755)


def _ico_images(ico: Path) -> list[bytes]:
    """The images of an ICO file (PNG entries, as make_icons writes them)."""
    data = ico.read_bytes()
    count = int.from_bytes(data[4:6], "little")
    out = []
    for i in range(count):
        size = int.from_bytes(data[6 + 16 * i + 8:6 + 16 * i + 12], "little")
        offset = int.from_bytes(data[6 + 16 * i + 12:6 + 16 * i + 16], "little")
        out.append(data[offset:offset + size])
    return out


def check_icon(app: Path, platform: str = sys.platform, icons: Path = ICONS) -> list[str]:
    """The bundle shows the AgentPROV icon: the ``.icns`` named by ``Info.plist`` (macOS), the ``.ico``'s images
    inside the executable (Windows: PyInstaller copies them into its icon resources), and the desktop entry with its
    script and icons (Linux)."""
    if platform == "darwin":
        plist = app / "Contents" / "Info.plist"
        name = plistlib.loads(plist.read_bytes()).get("CFBundleIconFile") if plist.is_file() else None
        if not name:
            return ["Info.plist names no CFBundleIconFile"]
        icns = app / "Contents" / "Resources" / (name if name.endswith(".icns") else f"{name}.icns")
        if not icns.is_file() or icns.read_bytes() != (icons / "AgentPROV.icns").read_bytes():
            return [f"{icns.name} is not gui/packaging/icons/AgentPROV.icns"]
        return []
    if platform == "win32":
        exe = _executable(app, platform).read_bytes() if _executable(app, platform).is_file() else b""
        missing = [i for i, image in enumerate(_ico_images(icons / "AgentPROV.ico")) if image not in exe]
        return [f"AgentPROV.exe lacks {len(missing)} of the .ico's images"] if missing else []
    bad = [name for name in LINUX_DESKTOP if not (app / name).is_file()]
    if not (app / "_internal" / "share" / "icons" / "hicolor" / "256x256" / "apps" / "agentprov.png").is_file():
        bad.append("hicolor icons")
    return [f"{name} missing" for name in bad]


def check_layout(app: Path, platform: str = sys.platform) -> list[str]:
    """The folder a user unpacks: the executable, and (Windows, Linux) the ``_internal`` folder beside it."""
    bad = [] if _executable(app, platform).is_file() else [f"executable {_executable(app, platform).name} missing"]
    if platform != "darwin" and not (app / "_internal").is_dir():
        bad.append("_internal missing")
    return bad


def check_qt_dynamic(app: Path, platform: str = sys.platform) -> list[str]:
    """LGPL: Qt is linked dynamically, so QtCore is a separate, replaceable file of the bundle."""
    name = _QT_CORE.get(platform)
    return [] if name is None or any(p.name == name for p in app.rglob(name)) else [f"{name} not found"]


def check_linux_plugins(app: Path) -> list[str]:
    """The ``xcb`` platform plugin (X11, and XWayland); Wayland's own plugin is optional."""
    return [] if any(app.rglob("libqxcb.so")) else ["platforms/libqxcb.so missing"]


def glibc_required(app: Path) -> tuple[int, int] | None:
    """The newest ``GLIBC_x.y`` symbol version any bundled ELF file names (``None`` when none does)."""
    best: tuple[int, int] | None = None
    for p in app.rglob("*"):
        if not p.is_file() or not (_library(p) or p == app / "AgentPROV"):
            continue
        with open(p, "rb") as fh:
            if fh.read(4) != b"\x7fELF":
                continue
            data = fh.read()
        for m in _GLIBC.finditer(data):
            version = (int(m.group(1)), int(m.group(2)))
            best = version if best is None or version > best else best
    return best


def make_dmg(app: Path, target: Path, icons: Path = ICONS) -> Path:
    """A compressed disk image: the app, a link to /Applications to drag it onto, and the app icon as the volume's
    icon (``.VolumeIcon.icns`` plus the custom-icon Finder flag on the volume root, set while it is mounted)."""

    def run(argv: list[str]) -> None:
        if _sh(argv).returncode != 0:
            raise SystemExit(f"build_bundle: {' '.join(argv[:2])} failed")

    with tempfile.TemporaryDirectory(prefix="agentprov-dmg-") as tmp:
        stage, mount, rw = Path(tmp) / "AgentPROV", Path(tmp) / "mnt", Path(tmp) / "rw.dmg"
        stage.mkdir()
        mount.mkdir()
        run(["ditto", str(app), str(stage / app.name)])  # ditto keeps the signature and extended attributes
        (stage / "Applications").symlink_to("/Applications")
        shutil.copyfile(icons / "AgentPROV.icns", stage / ".VolumeIcon.icns")
        run(["hdiutil", "create", "-quiet", "-ov", "-volname", "AgentPROV", "-fs", "HFS+", "-format", "UDRW",
             "-srcfolder", str(stage), str(rw)])
        run(["hdiutil", "attach", "-quiet", "-nobrowse", "-noautoopen", "-mountpoint", str(mount), str(rw)])
        try:
            run(["xattr", "-wx", "com.apple.FinderInfo", _CUSTOM_ICON, str(mount)])
        finally:
            run(["hdiutil", "detach", "-quiet", str(mount)])
        run(["hdiutil", "convert", "-quiet", "-ov", "-format", "UDZO", "-o", str(target), str(rw)])
    return target


def interpreter_arch() -> str:
    """The architecture a Windows or Linux bundle is built for: this interpreter's (``sysconfig``), not the host's.
    Under Windows 11 ARM64's x64 emulation ``platform.machine()`` names the host (``ARM64``) although an x64 Python
    builds an x64 bundle (G5 clean-machine run, Windows x64)."""
    plat = sysconfig.get_platform()  # win-amd64, win-arm64, linux-x86_64, linux-aarch64
    return plat.rsplit("-", 1)[-1] if "-" in plat else (_platform.machine() or "unknown")


def package(app: Path, out: Path, platform: str = sys.platform, machine: str | None = None) -> Path:
    """The file a user downloads: a dmg (macOS), a zip (Windows) or a tar.gz (Linux, executable bits kept)."""
    if platform == "darwin":
        arch = (machine or _platform.machine() or "unknown").lower()
        return make_dmg(app, out / f"AgentPROV-macos-{arch}.dmg")
    arch = (machine or interpreter_arch()).lower()
    if platform == "win32":
        target = out / f"AgentPROV-windows-{arch}.zip"
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in sorted(app.rglob("*")):
                if p.is_file():
                    zf.write(p, Path(app.name) / p.relative_to(app))
        return target
    target = out / f"AgentPROV-linux-{arch}.tar.gz"
    with tarfile.open(target, "w:gz") as tf:
        tf.add(app, arcname=app.name)
    return target


def check_licences(app: Path, platform: str = sys.platform) -> list[str]:
    bad = []
    roots = [_resources(app, platform), app / "Contents" / "Frameworks"] if platform == "darwin" else [
        _resources(app, platform)]
    for name, digest in LICENCES.items():
        found = [r / "licenses" / name for r in roots if (r / "licenses" / name).is_file()]
        if not found or hashlib.sha256(found[0].read_bytes()).hexdigest() != digest:
            bad.append(name)
    if not any((r / "THIRD_PARTY_NOTICES.md").is_file() for r in roots):
        bad.append("THIRD_PARTY_NOTICES.md")
    return bad


def launcher_sdk(exe: Path) -> tuple[int, int] | None:
    if sys.platform != "darwin":
        return None
    out = _sh(["otool", "-l", str(exe)]).stdout
    m = re.search(r"cmd LC_BUILD_VERSION.*?\n\s*sdk (\d+)\.(\d+)", out, re.S) or re.search(
        r"cmd LC_VERSION_MIN_MACOSX.*?\n\s*sdk (\d+)\.(\d+)", out, re.S)
    return (int(m.group(1)), int(m.group(2))) if m else None


def signature(app: Path, platform: str = sys.platform) -> str:
    if platform == "win32":
        return "unsigned (no certificate is bought: SmartScreen asks once, More info › Run anyway)"
    if platform != "darwin":
        return "none (the package's sha256 is in this report)"
    out = _sh(["codesign", "-dv", "--verbose=2", str(app)]).stderr
    if "Authority=Developer ID Application" in out:
        return "Developer ID"
    if "Signature=adhoc" in out:
        return "ad hoc (D-657: on another Mac, open the first launch with System Settings › Privacy & Security › Open Anyway)"
    return "unsigned" if "not signed" in out else "other: " + out.strip().splitlines()[-1][:120] if out.strip() else "?"


def smoke(app: Path) -> dict[str, object]:
    exe = _executable(app)
    with tempfile.TemporaryDirectory(prefix="agentprov-g5-") as home:
        env = {"PATH": os.environ.get("PATH", ""), "HOME": home, "AGENTPROV_HOME": home, "QT_QPA_PLATFORM": "offscreen",
               # a Windows process needs these to start at all (the runner's own values; never a key)
               **{k: os.environ[k] for k in ("SystemRoot", "TEMP", "TMP", "LOCALAPPDATA", "APPDATA") if k in os.environ}}
        gui = _sh([str(exe), "--smoke"], env=env)
        preview = _sh([str(exe), "--preview-helper", home], env=env, input="")
    return {"gui": gui.returncode, "gui_stderr_tail": gui.stderr[-500:], "preview_helper": preview.returncode}


def build_source(archive: Path | None = None, repo: Path = GUI.parent) -> dict[str, object]:
    """The commit the bundle is built from: a ``git archive``'s pax comment (``--source-archive``), else the checkout's
    ``HEAD`` and whether its tree is clean, else unknown (``None``, never guessed)."""
    if archive is not None:
        with tarfile.open(archive, mode="r:*") as tar:
            comment = tar.pax_headers.get("comment")
        commit = comment if comment and re.fullmatch(r"[0-9a-f]{40}", comment) else None
        return {"commit": commit, "basis": "git archive pax comment", "tree_clean": None}
    head = _sh(["git", "-C", str(repo), "rev-parse", "--verify", "HEAD^{commit}"])
    if head.returncode != 0:
        return {"commit": None, "basis": "no git checkout", "tree_clean": None}
    status = _sh(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no"])
    return {"commit": head.stdout.strip(), "basis": "checkout HEAD",
            "tree_clean": status.returncode == 0 and not status.stdout.strip()}


def versions() -> dict[str, str | None]:
    """The GUI's and the bundled core's distribution versions (the environment PyInstaller freezes)."""
    from importlib import metadata

    out: dict[str, str | None] = {}
    for name in ("agentprov-gui", "agentprov"):
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            out[name] = None
    return out


def check_python(version: tuple[int, ...] = tuple(sys.version_info), implementation: str = sys.implementation.name
                 ) -> str | None:
    """Why this interpreter may not build a bundle, or None."""
    if implementation != "cpython" or tuple(version[:2]) != PYTHON:
        found = ".".join(map(str, version[:3]))
        return (f"build_bundle: bundles are built with CPython {'.'.join(map(str, PYTHON))}.x (gui/.python-version), "
                f"not {implementation} {found} ({sys.executable})")
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    home = Path(os.environ.get("AGENTPROV_HOME", Path.home() / ".agentprov")).expanduser()
    ap.add_argument("--out", type=Path, default=home / "migration-work" / "gui-g5")
    ap.add_argument("--no-build", action="store_true", help="check an existing bundle only")
    ap.add_argument("--glibc-floor", metavar="X.Y", default=".".join(map(str, GLIBC_FLOOR)),
                    help="Linux: fail when a bundled file needs a newer glibc (default %(default)s)")
    ap.add_argument("--source-archive", type=Path, metavar="TAR",
                    help="the git archive the tree was unpacked from (G5 VMs): its commit goes into the report")
    ap.add_argument("--sign-identity", metavar="NAME",
                    help="a codesigning identity (e.g. 'Developer ID Application: …'); default: ad hoc (D-657)")
    args = ap.parse_args(argv)
    if not re.fullmatch(r"\d{1,2}\.\d{1,3}", args.glibc_floor):
        ap.error("--glibc-floor is X.Y")
    floor = tuple(int(x) for x in args.glibc_floor.split("."))
    refused = check_python()
    if refused:
        raise SystemExit(refused)
    args.out.mkdir(parents=True, exist_ok=True)
    app = bundle_path(args.out / "dist") if args.no_build else build(args.out)
    if sys.platform.startswith("linux"):
        add_linux_desktop(app)
    restored = restore_sdk(app)
    signing = sign(app, args.sign_identity)  # after the SDK step, which re-signs ad hoc
    sdk = launcher_sdk(_executable(app))
    smoked = smoke(app)
    linux = sys.platform.startswith("linux")
    glibc = glibc_required(app) if linux else None
    report = {"bundle": str(app), "platform": sys.platform, "versions": versions(),
              "source": build_source(args.source_archive),
              "python": f"{sys.implementation.name} {_platform.python_version()}", "layout_problems": check_layout(app),
              "qt_dynamic_problems": check_qt_dynamic(app), "plugins_missing": check_linux_plugins(app) if linux else [],
              "glibc_required": ".".join(map(str, glibc)) if glibc else None,
              "glibc_floor": args.glibc_floor, "glibc_above_floor": glibc is not None and glibc > floor,
              "excluded_found": check_excluded(app), "licences_missing": check_licences(app),
              "icon_problems": check_icon(app),
              "launcher_sdk": ".".join(map(str, sdk)) if sdk else None, "launcher_sdk_step": restored,
              "signing_step": signing, "signature": signature(app),
              "smoke": smoked,
              "size_mb": size_mb(app)}
    ok = (not report["excluded_found"] and not report["licences_missing"] and not signing.startswith("failed")
          and not report["layout_problems"] and not report["qt_dynamic_problems"] and not report["plugins_missing"]
          and not report["icon_problems"]
          and not report["glibc_above_floor"] and all(smoked[k] == 0 for k in ("gui", "preview_helper")))
    if ok:
        packed = package(app, args.out)
        report["package"] = {"path": str(packed), "sha256": hashlib.sha256(packed.read_bytes()).hexdigest()}
    report["sdk_current"] = sdk is not None and sdk >= MIN_SDK
    report["ok"] = ok
    (args.out / "bundle-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
