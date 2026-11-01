"""The user guide's copy in the core package (``src/agentprov/docs/user-guide/``), for ``agentprov assist`` (D-1030).

Usage::

    uv run python tools/sync_user_guide.py --check     # exit 1 if the copy differs from docs/user-guide/
    uv run python tools/sync_user_guide.py --write     # make the copy equal to docs/user-guide/

The ``agentprov`` wheel ships only what is under ``src/agentprov/``, so a CLI installed with ``pip install agentprov``
had no guide for the Assistant to answer from. The copy holds the guide's chapters (``docs/user-guide/*.md`` without
the internal ``_*.md`` checklists), byte for byte, and no images (the CLI shows none; the desktop bundle takes the guide
with its images from ``docs/user-guide/`` at build time). ``docs/user-guide/`` is the one that is edited; the copy is
refreshed with ``--write``, never by hand, and ``tests/repo/test_user_guide.py`` fails while it differs.

Standard library only; no network.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GUIDE = REPO / "docs" / "user-guide"
COPY = REPO / "src" / "agentprov" / "docs" / "user-guide"


def chapters(guide: Path = GUIDE) -> dict[str, bytes]:
    """The guide's chapters by file name: ``*.md`` without the internal ``_*.md`` checklists."""
    return {p.name: p.read_bytes() for p in sorted(guide.glob("*.md")) if not p.name.startswith("_")}


def differences(guide: Path = GUIDE, copy: Path = COPY) -> list[str]:
    """What differs between the guide and its copy: a chapter missing, changed or extra. Empty when they agree."""
    want = chapters(guide)
    have = {p.name: p.read_bytes() for p in sorted(copy.iterdir()) if p.is_file()} if copy.is_dir() else {}
    out = [f"missing: {name}" for name in want if name not in have]
    out += [f"changed: {name}" for name in want if name in have and have[name] != want[name]]
    out += [f"extra: {name}" for name in have if name not in want]
    return out


def write(guide: Path = GUIDE, copy: Path = COPY) -> None:
    want = chapters(guide)
    copy.mkdir(parents=True, exist_ok=True)
    for p in copy.iterdir():
        if p.is_file() and p.name not in want:
            p.unlink()
    for name, data in want.items():
        target = copy / name
        if not target.is_file() or target.read_bytes() != data:
            target.write_bytes(data)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="exit 1 if the copy differs from docs/user-guide/")
    mode.add_argument("--write", action="store_true", help="refresh the copy")
    args = ap.parse_args(argv)
    if args.write:
        write()
        return 0
    found = differences()
    for line in found:
        print(f"src/agentprov/docs/user-guide: {line}", file=sys.stderr)
    if found:
        print("run: uv run python tools/sync_user_guide.py --write", file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
