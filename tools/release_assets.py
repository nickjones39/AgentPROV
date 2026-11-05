"""The GitHub Release's files and their ``SHA256SUMS`` (D-1065), as ``.github/workflows/release.yml`` assembles them.

Usage::

    python3 tools/release_assets.py --tag vX.Y.Z --commit SHA --bundles DIR [--dist DIR] [--source FILE] --out DIR

``--bundles`` holds the ``bundles.yml`` run's artifacts, one folder per leg, each with its package and
``bundle-report.json``. Every one of the six bundles (:data:`BUNDLES`) must be there, and each report must say the build
passed (``ok``), name the tag's version for the app and the core, the tag's commit with a clean tree, and the
package's sha256, which is checked against the file. A package is copied under its release name (the Windows x64
bundle is built as ``windows-amd64`` and released as ``windows-x64``). ``--dist`` adds the sdists and wheels and
``--source`` the source archive. ``SHA256SUMS`` then lists every file in ``--out``: ``<sha256>  <name>``, LF, sorted by
name (the v0.1.0 and v0.1.1 format, which ``agentprov update`` reads strictly). Nothing is signed here.

Standard library only (the runner's ``python3``); it never imports ``agentprov``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

BUNDLES = ("AgentPROV-macos-arm64.dmg", "AgentPROV-macos-x86_64.dmg", "AgentPROV-windows-x64.zip",
           "AgentPROV-windows-arm64.zip", "AgentPROV-linux-x86_64.tar.gz", "AgentPROV-linux-aarch64.tar.gz")
#: the names a leg builds under (gui/tools/build_bundle.py package) -> the release name
RENAMES = {"AgentPROV-windows-amd64.zip": "AgentPROV-windows-x64.zip"}
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,199}")
_PACKAGE = re.compile(r"AgentPROV-(macos|windows|linux)-[a-z0-9_]+\.(dmg|zip|tar\.gz)")


class ReleaseError(Exception):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def collect_bundles(root: Path, *, version: str, commit: str) -> dict[str, Path]:
    """The six bundles under ``root`` by release name, each checked against its ``bundle-report.json``."""
    found: dict[str, Path] = {}
    for report_path in sorted(root.rglob("bundle-report.json")):
        report = json.loads(report_path.read_text(encoding="utf-8"))
        packages = sorted(p for p in report_path.parent.iterdir() if _PACKAGE.fullmatch(p.name))
        if len(packages) != 1:
            raise ReleaseError(f"{report_path.parent.name}: expected one package beside bundle-report.json")
        package = packages[0]
        where = report_path.parent.name
        if report.get("ok") is not True:
            raise ReleaseError(f"{where}: the bundle's build checks did not pass")
        versions = report.get("versions") or {}
        if versions.get("agentprov-gui") != version or versions.get("agentprov") != version:
            raise ReleaseError(f"{where}: the bundle is not version {version}")
        source = report.get("source") or {}
        if source.get("commit") != commit or source.get("tree_clean") is not True:
            raise ReleaseError(f"{where}: the bundle was not built from the tag's commit with a clean tree")
        if (report.get("package") or {}).get("sha256") != sha256(package):
            raise ReleaseError(f"{where}: the package's sha256 is not the report's")
        name = RENAMES.get(package.name, package.name)
        if name in found:
            raise ReleaseError(f"{name} is built twice")
        found[name] = package
    missing = sorted(set(BUNDLES) - set(found))
    extra = sorted(set(found) - set(BUNDLES))
    if missing or extra:
        raise ReleaseError(f"the bundles run does not hold the six bundles (missing {missing}, unexpected {extra})")
    return found


def sums_text(directory: Path) -> str:
    lines = []
    for path in sorted(directory.iterdir(), key=lambda p: p.name):
        if path.name in ("SHA256SUMS", "SHA256SUMS.sig"):
            continue
        if not path.is_file() or path.is_symlink() or not _NAME.fullmatch(path.name):
            raise ReleaseError(f"not a release file: {path.name}")
        lines.append(f"{sha256(path)}  {path.name}\n")
    if not lines:
        raise ReleaseError("no release files")
    return "".join(lines)


def assemble(*, tag: str, commit: str, bundles: Path, dist: Path | None, source: Path | None, out: Path) -> Path:
    m = re.fullmatch(r"v(\d+\.\d+\.\d+)", tag)
    if m is None or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ReleaseError("--tag must be vX.Y.Z and --commit a full commit id")
    out.mkdir(parents=True, exist_ok=False)
    for name, path in collect_bundles(bundles, version=m.group(1), commit=commit).items():
        shutil.copyfile(path, out / name)
    extra = sorted(dist.iterdir()) if dist is not None else []
    for path in [*extra, *([source] if source is not None else [])]:
        if path.is_file() and (path.suffix == ".whl" or path.name.endswith(".tar.gz")):
            if (out / path.name).exists():
                raise ReleaseError(f"{path.name} twice")
            shutil.copyfile(path, out / path.name)
    target = out / "SHA256SUMS"
    target.write_bytes(sums_text(out).encode("ascii"))
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--bundles", required=True, type=Path)
    parser.add_argument("--dist", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        sums = assemble(tag=args.tag, commit=args.commit, bundles=args.bundles, dist=args.dist, source=args.source,
                        out=args.out)
    except (ReleaseError, OSError, ValueError) as exc:
        print(f"release_assets: {exc}", file=sys.stderr)
        return 1
    print(sums.read_text(encoding="ascii"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
