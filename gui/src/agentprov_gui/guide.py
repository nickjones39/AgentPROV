"""The user guide Help › Docs shows (D-1010, D-1030): the checkout's, else the copy that comes with the app. No Qt.

The bundle (``gui/packaging/agentprov-gui.spec``) takes the guide from ``docs/user-guide/`` at build time:
:func:`bundle_files` names the chapters (``*.md`` without the internal ``_*.md`` checklists) and the images they show,
and they land in ``agentprov_gui/data/user-guide/`` (:data:`BUNDLED`), where ``gui/tools/build_bundle.py`` checks that
they are the guide's files, byte for byte. The copy is never committed, so it cannot drift from the guide it was built
from. A GUI run from a checkout has no copy and reads the checkout's guide.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

__all__ = ["BUNDLED", "bundle_files", "chapter_files", "pick_guide"]

#: where the bundle puts the guide (``agentprov_gui/data/user-guide`` next to the package's icons)
BUNDLED: Final = Path(__file__).resolve().parent / "data" / "user-guide"
#: a Markdown image, whose text may span lines and hold one level of brackets (as in tests/repo/test_user_guide.py)
_IMAGE: Final = re.compile(r"!\[(?:[^\]\[]|\[[^\]]*\])*\]\(\s*<?([^)\s>]+)")


def chapter_files(guide: Path) -> list[Path]:
    """The guide's chapters: ``*.md`` without the internal ``_*.md`` checklists (D-1004), the README first."""
    if not guide.is_dir():
        return []
    files = sorted(p for p in guide.glob("*.md") if not p.name.startswith("_") and p.is_file())
    files.sort(key=lambda p: (p.name != "README.md", p.name))
    return files


def bundle_files(guide: Path) -> list[str]:
    """What the bundle takes from ``guide``, as paths relative to it: the chapters, then every local image a chapter
    shows that is a file inside ``guide`` (a web address or a path outside it is left out)."""
    root = guide.resolve()
    names = [p.name for p in chapter_files(guide)]
    images: set[str] = set()
    for name in names:
        text = (guide / name).read_text(encoding="utf-8")
        for match in _IMAGE.finditer(text):
            target = match.group(1).split("#", 1)[0]
            if not target or ":" in target or target.startswith("/"):
                continue
            path = (root / target).resolve()
            if path.is_relative_to(root) and path.is_file():
                images.add(path.relative_to(root).as_posix())
    return [*names, *sorted(images)]


def pick_guide(checkout: Path | None, bundled: Path | None = BUNDLED) -> tuple[Path | None, str]:
    """``(folder, which)``: the checkout's ``docs/user-guide`` when it has chapters (``"checkout"``), else the app's
    copy (``"bundled"``), else ``(None, "none")``. The folder is resolved, so a link followed inside it compares equal
    (a macOS bundle reaches its data through symlinks)."""
    if checkout is not None and chapter_files(checkout / "docs" / "user-guide"):
        return (checkout / "docs" / "user-guide").resolve(), "checkout"
    if bundled is not None and chapter_files(bundled):
        return bundled.resolve(), "bundled"
    return None, "none"
