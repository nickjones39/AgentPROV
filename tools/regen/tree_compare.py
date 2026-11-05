"""Byte-compare two corpus trees file by file (regeneration plan, D-358 at the building commit).

Usage: python -I tools/regen/tree_compare.py OLD NEW --report OUT.json

Lists every regular file under both roots (no symlinks followed), hashes each with SHA-256 and reports files only in
OLD, only in NEW, and files whose bytes differ, grouped by top-level area (``aer/``, ``sem/``, ``prov/``,
``validation/``, ``raw/``, root files). Any other entry that is not a directory is listed too: a symlink (to a file or
a directory) by its target, never followed, and any other non-regular file by its type. For ``corpus.json`` the
differing JSON pointers are listed. Exit 0 when every file is identical, or when the only difference is
``corpus.json`` and every differing pointer matches one of the ``--allow-pointer`` globs; 1 otherwise, and 1 when OLD
holds no file (nothing was compared); 2 when a root is not a directory or an entry cannot be read. Reads corpus files
as bytes (``corpus.json`` with a strict JSON parser); writes only the report. Stdlib only.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import stat
import sys
from collections import Counter
from pathlib import Path
from typing import Any


def _raise(error: OSError) -> None:
    raise error


def files(root: Path) -> dict[str, str]:
    """Every entry under ``root`` that is not a directory, by its relative path: a regular file by its SHA-256, a
    symlink (to a file or a directory) by ``symlink:<target>`` (never followed), any other entry by its file type. An
    unreadable directory raises ``OSError`` (``os.walk`` would skip it silently)."""
    if root.is_symlink() or not root.is_dir():
        raise NotADirectoryError(f"not a directory: {root}")
    out: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root, onerror=_raise, followlinks=False):
        dirnames.sort()
        # os.walk lists a symlink to a directory among dirnames and does not descend into it
        for name in [*dirnames, *filenames]:
            path = Path(dirpath) / name
            info = path.lstat()
            if stat.S_ISDIR(info.st_mode):
                continue
            if stat.S_ISLNK(info.st_mode):
                out[path.relative_to(root).as_posix()] = "symlink:" + os.readlink(path)
                continue
            if not stat.S_ISREG(info.st_mode):
                out[path.relative_to(root).as_posix()] = f"not-a-regular-file:{stat.S_IFMT(info.st_mode):o}"
                continue
            digest = hashlib.sha256()
            with open(path, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    digest.update(chunk)
            out[path.relative_to(root).as_posix()] = digest.hexdigest()
    return out


def _strict(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate key {key!r}")
        out[key] = value
    return out


def pointers(a: Any, b: Any, path: str = "") -> list[str]:
    if isinstance(a, dict) and isinstance(b, dict):
        return [p for k in sorted(set(a) | set(b)) for p in pointers(a.get(k), b.get(k), f"{path}/{k}")]
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [p for i, (x, y) in enumerate(zip(a, b, strict=True)) for p in pointers(x, y, f"{path}/{i}")]
    return [path] if a != b else []


#: D-780: the building commit is producer metadata that differs between any two builds at different commits (and a stored
#: corpus built before it was recorded lacks it); never a finding of this comparison.
BUILD_POINTERS = ("/producer/git_commit", "/producer/git_tree_clean", "/producer/git_commit_absent_reason",
                  "/producer/build_steps*")


def area(rel: str) -> str:
    return rel.split("/", 1)[0] + "/" if "/" in rel else rel


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("old", type=Path)
    ap.add_argument("new", type=Path)
    ap.add_argument("--report", required=True, type=Path)
    ap.add_argument("--allow-pointer", action="append", default=[])
    args = ap.parse_args()
    try:
        a, b = files(args.old), files(args.new)
    except OSError as exc:
        print(f"tree_compare: {exc}", file=sys.stderr)
        return 2
    only_old = sorted(set(a) - set(b))
    only_new = sorted(set(b) - set(a))
    differ = sorted(k for k in set(a) & set(b) if a[k] != b[k])
    manifest_pointers: list[str] = []
    if "corpus.json" in differ:
        load = lambda p: json.loads((p / "corpus.json").read_text(encoding="utf-8"), object_pairs_hook=_strict)  # noqa: E731
        manifest_pointers = pointers(load(args.old), load(args.new))
    unexplained = [p for p in manifest_pointers if not any(fnmatch.fnmatchcase(p, g) for g in [*args.allow_pointer, *BUILD_POINTERS])]
    other = [k for k in differ if k != "corpus.json"]
    report = {
        "format": "agentprov-regen-tree-compare/0.1",
        "files_old": len(a), "files_new": len(b), "identical": len(set(a) & set(b)) - len(differ),
        "only_old": len(only_old), "only_new": len(only_new), "differ": len(differ),
        "by_area_differ": dict(Counter(area(k) for k in differ)),
        "by_area_only_old": dict(Counter(area(k) for k in only_old)),
        "by_area_only_new": dict(Counter(area(k) for k in only_new)),
        "first_differ": differ[:20], "first_only_old": only_old[:20], "first_only_new": only_new[:20],
        "corpus_json_pointers": manifest_pointers, "corpus_json_pointers_not_allowed": unexplained,
    }
    args.report.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    ok = bool(a) and not only_old and not only_new and not other and not unexplained
    print(json.dumps({k: report[k] for k in ("files_old", "files_new", "identical", "only_old", "only_new", "differ",
                                               "by_area_differ", "corpus_json_pointers")}, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
