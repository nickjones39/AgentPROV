"""Helpers over the synthetic test corpus."""

from __future__ import annotations

import copy
import hashlib
import os
import stat
from pathlib import Path
from typing import Any

from agentprov.corpus.reader import CorpusReader

from agentprov_gui.readmodel.executions import load_table, read_row

SPEC = "agentprov-prov/0.1"


def first_prov(final: Path) -> tuple[str, Any]:
    reader = CorpusReader.open(final)
    table = load_table(reader)
    row = read_row(reader, table, 0)
    return row.ex, reader.read_prov(row, SPEC)


def poison(doc: Any, strings: list[str]) -> tuple[Any, list[str]]:
    """A deep copy of ``doc`` whose free-text string attributes (``apv:toolName``, ``apv:name``, ``apv:args``, …) are
    replaced by hostile strings; returns the copy and the strings placed."""
    out = copy.deepcopy(doc)
    placed: list[str] = []
    k = 0
    for body in out.get("bundle", {}).values():
        for section in body.values():
            if not isinstance(section, dict):
                continue
            for attrs in section.values():
                if not isinstance(attrs, dict):
                    continue
                for name in ("apv:toolName", "apv:name", "apv:args", "apv:attackId", "apv:annotationId"):
                    if isinstance(attrs.get(name), str):
                        attrs[name] = strings[k % len(strings)]
                        placed.append(attrs[name])
                        k += 1
    return out, placed


def tree_state(root: Path) -> dict[str, tuple[int, int, int, str]]:
    """Every entry at and below ``root`` (the root itself, directories, files and symlinks) with its full mode (file type
    and permission bits, so a chmod shows up although it leaves mtime alone), size, mtime and digest: a file's sha256, a symlink's target, nothing for a directory (to prove a read changed nothing).
    Snapshot the corpora root, not only ``DIR.partial``, so a sidecar created beside a corpus shows up too."""
    out: dict[str, tuple[int, int, int, str]] = {}

    def record(p: Path) -> None:
        st = p.lstat()
        if stat.S_ISREG(st.st_mode):
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
        elif stat.S_ISLNK(st.st_mode):
            digest = os.readlink(p)
        else:
            digest = ""
        out[p.relative_to(root).as_posix()] = (st.st_mode, st.st_size, st.st_mtime_ns, digest)

    record(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(dirnames + filenames):
            record(Path(dirpath, name))
    return out
