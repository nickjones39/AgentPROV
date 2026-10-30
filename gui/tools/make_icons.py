"""Render every app-icon and logo file from the brand SVGs (``docs/images/brand/``; brand note
``docs/reports/gui/logo/brand.md``).

    uv run --project gui python gui/tools/make_icons.py [--check]

The SVGs are the sources; everything below is generated from them with ``rsvg-convert`` (librsvg) and, for the macOS
``.icns``, ``iconutil`` (so writing needs macOS with ``brew install librsvg``):

* ``gui/packaging/icons/``: ``AgentPROV.icns`` (macOS bundle and ``.dmg`` volume icon), ``AgentPROV.ico`` (Windows
  executable; PNG entries 16 to 256 px) and ``hicolor/<n>x<n>/apps/agentprov.png`` plus ``hicolor/scalable`` (Linux).
* ``gui/src/agentprov_gui/data/icons/``: the window icon (16 to 512 px) and the About window's mark (light and dark
  appearance, 1x and 2x).
* ``docs/user-guide/images/brand/``: the guide's header logo and favicon (``mkdocs.yml`` ``theme.logo``/``favicon``).

``icons.json`` records the sha256 of every source and output. ``--check`` needs no renderer: it fails when a source
SVG changed without a re-run, or an output no longer matches what was generated (a test runs it).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BRAND = REPO / "docs" / "images" / "brand"
PACKAGING = REPO / "gui" / "packaging" / "icons"
APP_DATA = REPO / "gui" / "src" / "agentprov_gui" / "data" / "icons"
GUIDE = REPO / "docs" / "user-guide" / "images" / "brand"
MANIFEST = PACKAGING / "icons.json"

ICON, MARK, MARK_DARK = BRAND / "agentprov-icon.svg", BRAND / "agentprov-mark.svg", BRAND / "agentprov-mark-on-dark.svg"
SOURCES = (ICON, MARK, MARK_DARK)
#: iconutil's names: icon_<n>x<n>[@2x].png
ICNS_SIZES = (16, 32, 128, 256, 512)
ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 256)  # Microsoft's minimum is 16, 24, 32, 48 and 256
HICOLOR_SIZES = (16, 24, 32, 48, 64, 128, 256, 512)
WINDOW_SIZES = (16, 32, 64, 128, 256, 512)
ABOUT_MARK = 64  # points (ui/dialogs.py); the 2x file is 128 px


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def render(svg: Path, px: int, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["rsvg-convert", "--width", str(px), "--height", str(px), "--keep-aspect-ratio",  # noqa: S603, S607
                    "--output", str(out), str(svg)], check=True)
    return out


def write_ico(pngs: dict[int, bytes], out: Path) -> None:
    """An ICO whose entries are PNG images (Windows Vista and later read them at every size)."""
    header = struct.pack("<HHH", 0, 1, len(pngs))
    offset = len(header) + 16 * len(pngs)
    entries, blobs = b"", b""
    for size, data in sorted(pngs.items()):
        dim = 0 if size >= 256 else size  # 0 means 256
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset + len(blobs))
        blobs += data
    out.write_bytes(header + entries + blobs)


def build() -> dict[str, str]:
    """Write every output; returns {path: sha256}."""
    outputs: list[Path] = []
    with tempfile.TemporaryDirectory(prefix="agentprov-icons-") as tmp:
        iconset = Path(tmp) / "AgentPROV.iconset"
        for n in ICNS_SIZES:
            render(ICON, n, iconset / f"icon_{n}x{n}.png")
            render(ICON, 2 * n, iconset / f"icon_{n}x{n}@2x.png")
        icns = PACKAGING / "AgentPROV.icns"
        icns.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["iconutil", "--convert", "icns", "--output", str(icns), str(iconset)],  # noqa: S603, S607
                       check=True)
        outputs.append(icns)
        ico = PACKAGING / "AgentPROV.ico"
        write_ico({n: render(ICON, n, Path(tmp) / f"ico-{n}.png").read_bytes() for n in ICO_SIZES}, ico)
        outputs.append(ico)
    for n in HICOLOR_SIZES:
        outputs.append(render(ICON, n, PACKAGING / "hicolor" / f"{n}x{n}" / "apps" / "agentprov.png"))
    scalable = PACKAGING / "hicolor" / "scalable" / "apps" / "agentprov.svg"
    scalable.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ICON, scalable)
    outputs.append(scalable)
    for n in WINDOW_SIZES:
        outputs.append(render(ICON, n, APP_DATA / f"agentprov-{n}.png"))
    for svg, name in ((MARK, "agentprov-mark"), (MARK_DARK, "agentprov-mark-on-dark")):
        outputs.append(render(svg, ABOUT_MARK, APP_DATA / f"{name}.png"))
        outputs.append(render(svg, 2 * ABOUT_MARK, APP_DATA / f"{name}@2x.png"))
    GUIDE.mkdir(parents=True, exist_ok=True)
    logo = GUIDE / "agentprov-mark-on-dark.svg"
    shutil.copyfile(MARK_DARK, logo)
    outputs += [logo, render(ICON, 64, GUIDE / "favicon.png")]
    return {_rel(p): _sha(p) for p in outputs}


def manifest(outputs: dict[str, str]) -> dict[str, object]:
    version = subprocess.run(["rsvg-convert", "--version"], capture_output=True, text=True,  # noqa: S607
                             check=True).stdout.split("\n")[0].strip()
    return {"generator": "gui/tools/make_icons.py", "renderer": version,
            "sources": {_rel(p): _sha(p) for p in SOURCES}, "outputs": outputs}


def check() -> list[str]:
    """Problems with the committed outputs (no renderer needed)."""
    if not MANIFEST.is_file():
        return [f"{_rel(MANIFEST)} missing: run gui/tools/make_icons.py"]
    recorded = json.loads(MANIFEST.read_text(encoding="utf-8"))
    problems = [f"{name} changed since the icons were generated: run gui/tools/make_icons.py"
                for name, digest in recorded["sources"].items() if _sha(REPO / name) != digest]
    for name, digest in recorded["outputs"].items():
        path = REPO / name
        if not path.is_file():
            problems.append(f"{name} missing")
        elif _sha(path) != digest:
            problems.append(f"{name} differs from the generated file")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="verify the committed outputs against icons.json")
    args = ap.parse_args(argv)
    if args.check:
        problems = check()
        for p in problems:
            print(f"make_icons: {p}", file=sys.stderr)
        return 1 if problems else 0
    if sys.platform != "darwin" or not shutil.which("rsvg-convert"):
        print("make_icons: writing needs macOS (iconutil) and rsvg-convert (brew install librsvg)", file=sys.stderr)
        return 2
    outputs = build()
    MANIFEST.write_text(json.dumps(manifest(outputs), indent=2) + "\n", encoding="utf-8")
    print(f"make_icons: {len(outputs)} files written; {_rel(MANIFEST)} updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
