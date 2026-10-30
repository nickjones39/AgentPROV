"""Install a locally built PyInstaller bootloader into the GUI venv (macOS; D-441, macos-design §8 "Launcher SDK").

    uv run --project gui python gui/tools/install_bootloader.py SDIST_DIR

``SDIST_DIR`` is an extracted ``pyinstaller-<version>`` source package of the **same version** as the venv's PyInstaller,
whose bootloader was built there with ``cd bootloader && ./waf all`` and the current Xcode. The four macOS binaries
(``run``, ``run_d``, ``runw``, ``runw_d``) are copied over the venv's prebuilt ones, which are kept as ``*.prebuilt``.
It refuses a bootloader linked against an SDK older than 26 (the current look on macOS 27 needs it). ``uv sync
--reinstall-package pyinstaller`` restores the prebuilt files.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

import PyInstaller

NAMES = ("run", "run_d", "runw", "runw_d")
MIN_SDK = (26, 0)


def sdk(path: Path) -> tuple[int, int] | None:
    out = subprocess.run(["otool", "-l", str(path)], capture_output=True, text=True, check=False).stdout  # noqa: S603, S607
    m = re.search(r"cmd LC_BUILD_VERSION.*?\n\s*sdk (\d+)\.(\d+)", out, re.S)
    return (int(m.group(1)), int(m.group(2))) if m else None


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or sys.platform != "darwin":
        print("usage (macOS): install_bootloader.py SDIST_DIR", file=sys.stderr)
        return 2
    src_root = Path(args[0])
    version = PyInstaller.__version__
    if not src_root.name.endswith(f"-{version}"):
        print(f"install_bootloader: the source is not pyinstaller-{version}", file=sys.stderr)
        return 2
    src = src_root / "PyInstaller" / "bootloader" / "Darwin-64bit"
    dst = Path(PyInstaller.__file__).resolve().parent / "bootloader" / "Darwin-64bit"
    for name in NAMES:
        found = sdk(src / name)
        if found is None or found < MIN_SDK:
            print(f"install_bootloader: {name} is linked against SDK {found}, not >= 26", file=sys.stderr)
            return 1
    for name in NAMES:
        backup = dst / f"{name}.prebuilt"
        if not backup.exists():
            shutil.copy2(dst / name, backup)
        shutil.copy2(src / name, dst / name)
        digest = hashlib.sha256((dst / name).read_bytes()).hexdigest()
        print(f"install_bootloader: {name} sdk {'.'.join(map(str, sdk(dst / name) or ()))} sha256 {digest[:16]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
