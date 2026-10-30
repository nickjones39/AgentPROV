"""The fixture tree's size caps, read from ``tests/FIXTURES.json`` (docs/architecture K.4.1(5); DECISIONS D-360).

The caps file sits beside the tree, not in it: ``tests/fixtures/**`` is closed to agents' reads (K.4.1(4), R-42), and the
caps are policy, not fixture content.

Three caps (user decision, 2026-10-13):

* **total**: the whole fixture tree (default 16 MiB);
* **per file**: a file over 1 MiB must be listed in ``oversize_files`` with a reason;
* **per source**: a source (a top-level directory of the fixture tree) over its budget (default 512 KiB) must be listed
  in ``source_exceptions`` with its own ``budget_bytes`` and a reason.

An entry without a reason, an exception whose source is absent or within the default budget, and an oversize entry whose
file is absent or not over the per-file cap are problems too, so the file stays a true account. One absence is
excused: a listed file that the public export keeps private by the D-943 fixture rule (a non-synthetic ``SOURCE.json``
entry whose ``licence_class`` is not ``permissive``), because the exported tree lacks it by design. The checker reads
sizes and ``SOURCE.json`` metadata only, never fixture content (R-42). Standard library only.
"""

from __future__ import annotations

import json
import posixpath
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

__all__ = ["CAPS_NAME", "FORMAT", "Caps", "caps_path", "check_tree", "export_private", "load_caps", "measure", "parse_caps",
           "problems"]

CAPS_NAME: Final = "FIXTURES.json"
FORMAT: Final = "agentprov-fixture-caps/0.1"
#: The licence classes the public export keeps (D-943; ``tools/building_commit_snapshots.py``'s ``PUBLIC_CLASSES``).
PUBLIC_CLASSES: Final = frozenset({"permissive"})


@dataclass(frozen=True, slots=True)
class Caps:
    total_bytes: int
    file_bytes: int
    source_budget_bytes: int
    oversize_files: Mapping[str, str]  # path relative to the tree -> reason
    source_exceptions: Mapping[str, tuple[int, str]]  # source -> (budget_bytes, reason)


def _int(value: object, where: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{CAPS_NAME}: {where} must be a positive integer")
    return value


def parse_caps(doc: Mapping[str, Any]) -> Caps:
    """The caps of a parsed ``FIXTURES.json``; ``ValueError`` for a malformed document (reasons are checked by
    :func:`problems`, so a missing reason is reported, not raised)."""
    if doc.get("format") != FORMAT:
        raise ValueError(f"{CAPS_NAME}: format must be {FORMAT!r}")
    caps = doc.get("caps")
    if not isinstance(caps, Mapping):
        raise ValueError(f"{CAPS_NAME}: caps must be an object")
    oversize: dict[str, str] = {}
    for entry in doc.get("oversize_files", []):
        path = entry.get("path") if isinstance(entry, Mapping) else None
        if not isinstance(path, str) or path in oversize:
            raise ValueError(f"{CAPS_NAME}: an oversize entry needs a unique path")
        oversize[path] = str(entry.get("reason") or "")
    exceptions: dict[str, tuple[int, str]] = {}
    for entry in doc.get("source_exceptions", []):
        source = entry.get("source") if isinstance(entry, Mapping) else None
        if not isinstance(source, str) or source in exceptions:
            raise ValueError(f"{CAPS_NAME}: a source exception needs a unique source")
        exceptions[source] = (_int(entry.get("budget_bytes"), f"budget_bytes of {source!r}"), str(entry.get("reason") or ""))
    return Caps(_int(caps.get("total_bytes"), "caps.total_bytes"), _int(caps.get("file_bytes"), "caps.file_bytes"),
                _int(caps.get("source_budget_bytes"), "caps.source_budget_bytes"), oversize, exceptions)


def caps_path(root: Path) -> Path:
    """``tests/FIXTURES.json`` for the fixture tree ``tests/fixtures``."""
    return root.parent / CAPS_NAME


def load_caps(root: Path) -> Caps:
    return parse_caps(json.loads(caps_path(root).read_bytes()))


def measure(root: Path) -> dict[str, int]:
    """Path (relative, POSIX) -> size of every file of the tree."""
    return {p.relative_to(root).as_posix(): p.stat().st_size for p in sorted(root.rglob("*")) if p.is_file()}


def export_private(root: Path) -> set[str]:
    """Paths (relative, POSIX; a trailing ``/`` for a whole directory) that the public export leaves out of the tree at
    ``root``, by the D-943 rule ``tools/building_commit_snapshots.py`` applies: a non-synthetic ``SOURCE.json`` entry
    whose class is not public names its ``sample_file``, or its whole directory when it names none; a top-level
    ``restricted`` (copyleft) source goes as a whole. Reads ``SOURCE.json`` metadata only."""
    out: set[str] = set()
    for path in sorted(root.rglob("SOURCE.json")):
        scope = path.parent.relative_to(root).as_posix()
        data = json.loads(path.read_bytes())
        for record in data if isinstance(data, list) else [data]:
            if not isinstance(record, Mapping) or record.get("synthetic") is True:
                continue
            cls = record.get("licence_class")
            if cls in PUBLIC_CLASSES:
                continue
            sample = record.get("sample_file")
            if cls == "restricted" and "/" not in scope:
                out.add(scope + "/")
            elif isinstance(sample, str) and sample:
                out.add(posixpath.normpath(f"{scope}/{sample}"))
            else:
                out.add(scope + "/")
    return out


def _excused(path: str, private: Collection[str]) -> bool:
    return path in private or any(p.endswith("/") and path.startswith(p) for p in private)


def problems(sizes: Mapping[str, int], caps: Caps, private: Collection[str] = ()) -> list[str]:
    """Every cap violation and every stale or unreasoned entry, as short messages (paths and sizes only). ``private``
    (from :func:`export_private`) excuses a listed oversize file that is absent because the export keeps it private."""
    out: list[str] = []
    total = sum(sizes.values())
    if total > caps.total_bytes:
        out.append(f"the fixture tree holds {total} B, over the {caps.total_bytes} B cap")
    for path, size in sorted(sizes.items()):
        if size > caps.file_bytes:
            if path not in caps.oversize_files:
                out.append(f"{path}: {size} B is over the per-file cap and not listed in oversize_files")
            elif not caps.oversize_files[path].strip():
                out.append(f"{path}: the oversize entry has no reason")
    for path in sorted(caps.oversize_files):
        if path not in sizes and _excused(path, private):
            continue
        if sizes.get(path, 0) <= caps.file_bytes:
            out.append(f"{path}: oversize entry for a file that is absent or within the per-file cap")
    by_source: dict[str, int] = {}
    for path, size in sizes.items():
        if "/" in path:
            source = path.split("/", 1)[0]
            by_source[source] = by_source.get(source, 0) + size
    for source, size in sorted(by_source.items()):
        if size <= caps.source_budget_bytes:
            continue
        exception = caps.source_exceptions.get(source)
        if exception is None:
            out.append(f"{source}/: {size} B is over the {caps.source_budget_bytes} B source budget, with no exception")
        elif not exception[1].strip():
            out.append(f"{source}/: the source exception has no reason")
        elif size > exception[0]:
            out.append(f"{source}/: {size} B is over its recorded budget of {exception[0]} B")
    for source, (_budget, _reason) in sorted(caps.source_exceptions.items()):
        if by_source.get(source, 0) <= caps.source_budget_bytes:
            out.append(f"{source}/: exception for a source that is absent or within the default budget")
    return out


def check_tree(root: Path, extra: Iterable[str] = ()) -> list[str]:
    """:func:`problems` for the fixture tree at ``root`` with its ``FIXTURES.json``."""
    return [*problems(measure(root), load_caps(root), export_private(root)), *extra]
