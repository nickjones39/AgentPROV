# PyInstaller spec for the AgentPROV desktop GUI (G5; design §13, macos-design §8). One-folder, never one-file
# (LGPL relinking). Build with gui/tools/build_bundle.py, which also runs the bundle checks.
# -*- mode: python -*-
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

HERE = Path(SPECPATH)  # noqa: F821 - injected by PyInstaller
GUI = HERE.parent
VERSION = "0.1.0"
#: rendered from docs/images/brand/ by gui/tools/make_icons.py (brand note: docs/reports/gui/logo/brand.md)
ICONS = HERE / "icons"

#: design §13: never bundled (a build check also fails on any of their libraries)
EXCLUDED = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel",
    "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtQuickControls2", "PySide6.QtQml", "PySide6.QtNetwork",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtPdf",
    "PySide6.QtPdfWidgets", "tkinter",
]

datas = [
    (str(GUI / "src" / "agentprov_gui" / "data"), "agentprov_gui/data"),
    (str(HERE / "licenses"), "licenses"),
    (str(GUI / "THIRD_PARTY_NOTICES.md"), "."),
    *collect_data_files("agentprov"),  # the core's package data (profiles, schemas, rule catalogues): read-only
]
if sys.platform.startswith("linux"):  # the desktop entry's icons (install-desktop-entry.sh copies them)
    datas.append((str(ICONS / "hicolor"), "share/icons/hicolor"))
hidden = [
    "agentprov_gui.preview.__main__",
    *collect_submodules("agentprov_gui"),
]

a = Analysis(  # noqa: F821
    [str(HERE / "entry.py")], pathex=[str(GUI / "src")], datas=datas, hiddenimports=hidden, excludes=EXCLUDED,
    noarchive=False,
)
#: binaries the module excludes do not catch: Qt's TUIO touch plugin (touch input over UDP) links QtNetwork; the GUI
#: needs neither, and the build check fails on any QtNetwork file. macOS spells them libqtuiotouchplugin and QtNetwork,
#: Windows qtuiotouchplugin.dll and Qt6Network.dll, Linux libqtuiotouchplugin.so and libQt6Network.so.6 (G5 P-7)
_DROP = ("qtuiotouchplugin", "QtNetwork", "Qt6Network")
a.binaries = [b for b in a.binaries if not any(d in b[0] for d in _DROP)]
a.datas = [d for d in a.datas if not any(x in d[0] for x in _DROP)]
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz, a.scripts, [], exclude_binaries=True, name="AgentPROV", console=False, debug=False, strip=False, upx=False,
    icon=str(ICONS / "AgentPROV.ico") if sys.platform == "win32" else None,  # the .exe's Explorer and taskbar icon
    codesign_identity=None,  # no Developer ID here: an unsigned development build (PyInstaller signs it ad hoc)
    entitlements_file=None,  # macos-design §8: start with none
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="AgentPROV")  # noqa: F821
if sys.platform == "darwin":
    app = BUNDLE(  # noqa: F821
        coll, name="AgentPROV.app", bundle_identifier="org.agentprov.gui", version=VERSION,
        icon=str(ICONS / "AgentPROV.icns"),  # Finder and Dock; a full tile, so macOS 26+ shows it unplated
        info_plist={"CFBundleShortVersionString": VERSION, "CFBundleVersion": VERSION, "NSHighResolutionCapable": True,
                    "LSMinimumSystemVersion": "15.0", "NSRequiresAquaSystemAppearance": False,
                    "LSApplicationCategoryType": "public.app-category.developer-tools"},
    )
