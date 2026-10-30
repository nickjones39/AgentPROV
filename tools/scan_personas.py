"""Check a corpus's e-mail addresses against the benchmark's own upstream data, offline, by digest (D-810).

Usage::

    uv run python tools/scan_personas.py --corpus DIR [--corpus DIR ...] \\
        --upstream GIT_DIR COMMIT REPO_URL [--upstream ...] [--upstream-dir DIR REVISION REPO_URL ...] \\
        [--source-id ID] [--exclude PREFIX ...] [--out FILE --id PERSONA_ID]

For every distinct address in the corpus tree(s) (stored files and decoded archive members, as ``tools/release_scan.py``
reads them) it asks whether the same address, by its digest, occurs in a file of the upstream trees: the benchmark's own
data (suite definitions, task files, fixtures), never the run logs that the corpus holds (``--exclude`` the log
directories, for example ``--exclude runs/``). Each ``--upstream`` is a local git directory (a bare cache, a staging clone
or an upstream store), a commit and the repository URL recorded as evidence. ``--upstream-dir`` names a plain directory
instead (a Hugging Face dataset snapshot in the fetch cache: ``cache/hf/<owner>/<name>/<revision>``): its regular files
are read (no link followed), with the revision and the dataset URL as evidence. Every git read is plumbing
(``ls-tree``, ``cat-file --batch``) with ``GIT_NO_LAZY_FETCH=1``; a blob a partial clone does not hold is counted as absent
and never fetched. No network, no checkout, nothing written inside a corpus or an upstream tree.

Output, counts only: per corpus the distinct addresses, split into reserved (cleared by the scan itself), found in the
upstream data and **not found**; for the not-found ones, the split by layer (``raw``, ``aer``, ``prov``...) and by domain
class (``public-freemail``, ``other``) with their findings. **Never an address, local part or domain.**

With ``--out`` (and ``--id``) it writes a persona file (``agentprov-personas/0.1``, :mod:`agentprov.corpus.personas`)
with the digests of the addresses found in upstream data (reserved ones excluded), grouped by the upstream file they
occur in (the first, in path order, for an address in several), with source id, repository, commit and file as evidence.
The file holds digests only. A person reviews it before a corpus spec references it.

Exit codes: 0 ok; 1 an archive could not be read, or an upstream could not be read; 2 usage.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any, Final

sys.path.insert(0, str(Path(__file__).resolve().parent))
import release_scan as rs  # noqa: E402

from agentprov.corpus.personas import CLASS_RESERVED, PERSONA_FORMAT, address_digest, find_addresses  # noqa: E402

MAX_BLOB: Final = 16 << 20  # a larger blob is not benchmark text (a binary, a log): skipped and counted
_ENV: Final = {**{k: v for k, v in os.environ.items() if not k.startswith("GIT_")}, "GIT_NO_LAZY_FETCH": "1",
               "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}


class UpstreamError(Exception):
    pass


def _git(git_dir: Path, *args: str) -> bytes:
    done = subprocess.run(["git", "--no-pager", "--no-optional-locks", "-C", str(git_dir), *args], capture_output=True,
                          env=_ENV, check=False, timeout=600)
    if done.returncode != 0:
        raise UpstreamError(f"git {args[0]} failed in an upstream directory")
    return done.stdout


def upstream_blobs(git_dir: Path, commit: str, excluded: Sequence[str]) -> tuple[list[tuple[str, str]], int, int]:
    """``(path, blob id)`` of every blob of the tree at ``commit`` that is not under an excluded prefix and not larger than
    :data:`MAX_BLOB`, the number skipped as too large, and the number absent from the object store (never fetched)."""
    listing = _git(git_dir, "ls-tree", "-r", "-l", "-z", commit).split(b"\0")
    blobs: list[tuple[str, str]] = []
    large = absent = 0
    for entry in listing:
        if not entry:
            continue
        meta, _, raw_path = entry.partition(b"\t")
        mode, kind, blob, size = meta.split(None, 3)
        path = raw_path.decode("utf-8", "replace")
        if kind != b"blob" or any(path.startswith(prefix) for prefix in excluded):
            continue
        if not size.strip().isdigit():
            absent += 1
        elif int(size) > MAX_BLOB:
            large += 1
        else:
            blobs.append((path, blob.decode("ascii")))
    return blobs, large, absent


def _read_blobs(git_dir: Path, ids: Sequence[str]) -> Iterator[tuple[str, bytes | None]]:
    proc = subprocess.Popen(["git", "--no-pager", "-C", str(git_dir), "cat-file", "--batch"], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, env=_ENV)
    assert proc.stdin is not None and proc.stdout is not None
    try:
        for blob in ids:
            proc.stdin.write(blob.encode("ascii") + b"\n")
            proc.stdin.flush()
            header = proc.stdout.readline().split()
            if len(header) != 3 or header[1] != b"blob":
                yield blob, None  # missing (an absent blob of a partial clone): never fetched
                continue
            size = int(header[2])
            data = proc.stdout.read(size)
            proc.stdout.read(1)
            yield blob, data
    finally:
        proc.stdin.close()
        proc.stdout.close()
        proc.wait()


def upstream_addresses(git_dir: Path, commit: str, excluded: Sequence[str]) -> tuple[dict[str, str], dict[str, int]]:
    """``digest -> the first file (in path order) of the upstream tree that holds the address``, and counts of the blobs
    read, skipped as large and absent. Digests only."""
    blobs, large, absent = upstream_blobs(git_dir, commit, excluded)
    path_of = dict(sorted((blob, path) for path, blob in blobs))
    first: dict[str, str] = {}
    read = 0
    ordered = sorted(blobs)
    for blob, data in _read_blobs(git_dir, [b for _p, b in ordered]):
        if data is None:
            absent += 1
            continue
        read += 1
        for _start, raw in find_addresses(data + b"\x00", 0):
            digest = address_digest(raw)
            path = path_of[blob]
            if digest not in first or path < first[digest]:
                first[digest] = path
    return first, {"blobs_read": read, "blobs_too_large": large, "blobs_absent": absent}


def dir_addresses(directory: Path, excluded: Sequence[str]) -> tuple[dict[str, str], dict[str, int]]:
    """:func:`upstream_addresses` for a plain directory tree (regular files only, no link followed): the first file in
    path order that holds each address, and counts of the files read and skipped as too large."""
    first: dict[str, str] = {}
    read = large = 0
    files = sorted(p for p in directory.rglob("*") if p.is_file() and not p.is_symlink())
    for path in files:
        relative = path.relative_to(directory).as_posix()
        if any(relative.startswith(prefix) for prefix in excluded):
            continue
        if path.stat().st_size > MAX_BLOB:
            large += 1
            continue
        read += 1
        for _start, raw in find_addresses(path.read_bytes() + b"\x00", 0):
            digest = address_digest(raw)
            if digest not in first or relative < first[digest]:
                first[digest] = relative
    return first, {"blobs_read": read, "blobs_too_large": large, "blobs_absent": 0}


def write_persona_file(out: Path, persona_id: str, source_id: str, found: dict[str, tuple[str, str, str]]) -> None:
    """``found``: digest -> (repo url, commit, file). One group per (repo, commit, file)."""
    groups: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for digest, key in found.items():
        groups[key].append(digest)
    lines = [f'format = "{PERSONA_FORMAT}"', f'id = "{persona_id}"']
    for (repo, commit, path), digests in sorted(groups.items()):
        lines += ["", "[[group]]", f'source_id = "{source_id}"', f'repo = "{repo}"', f'commit = "{commit}"',
                  f"file = {json.dumps(path)}", "addresses = ["]
        lines += [f'  "{d}",' for d in sorted(digests)]
        lines.append("]")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def report(name: str, table: dict[str, rs.AddressStat], upstream: dict[str, str]) -> dict[str, Any]:
    reserved = [d for d, s in table.items() if s.klass == CLASS_RESERVED]
    found = [d for d, s in table.items() if s.klass != CLASS_RESERVED and d in upstream]
    missing = [d for d, s in table.items() if s.klass != CLASS_RESERVED and d not in upstream]
    by_stage: Counter[str] = Counter()
    findings_by_stage: Counter[str] = Counter()
    by_class: Counter[str] = Counter()
    findings_by_class: Counter[str] = Counter()
    for d in missing:
        stat = table[d]
        by_class[stat.klass] += 1
        findings_by_class[stat.klass] += len(stat.findings)
        for stage in stat.stages:
            by_stage[stage] += 1
        for _c, where, _line in stat.findings:
            findings_by_stage[rs.stage_of(where)] += 1
    return {"corpus": name, "distinct_addresses": len(table), "reserved": len(reserved), "found_in_upstream": len(found),
            "not_found": len(missing), "not_found_by_class": dict(sorted(by_class.items())),
            "not_found_findings_by_class": dict(sorted(findings_by_class.items())),
            "not_found_addresses_by_stage": dict(sorted(by_stage.items())),
            "not_found_findings_by_stage": dict(sorted(findings_by_stage.items())),
            "findings_total": len({f for s in table.values() for f in s.findings})}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scan_personas.py", description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--corpus", action="append", required=True, type=Path, metavar="DIR")
    parser.add_argument("--upstream", action="append", nargs=3, default=[], metavar=("GIT_DIR", "COMMIT", "REPO_URL"))
    parser.add_argument("--upstream-dir", action="append", nargs=3, default=[], metavar=("DIR", "REVISION", "REPO_URL"))
    parser.add_argument("--exclude", action="append", default=[], metavar="PREFIX",
                        help="an upstream path prefix that is run data, not benchmark data (for example runs/)")
    parser.add_argument("--source-id", default="unknown")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--id", dest="persona_id")
    parser.add_argument("--workers", type=int)
    args = parser.parse_args(argv)
    if bool(args.out) != bool(args.persona_id):
        print("scan_personas: --out and --id go together", file=sys.stderr)
        return 2
    if not args.upstream and not args.upstream_dir:
        print("scan_personas: give at least one --upstream or --upstream-dir", file=sys.stderr)
        return 2
    upstream: dict[str, str] = {}
    evidence: dict[str, tuple[str, str, str]] = {}
    status = 0
    sources = [(git_dir, commit, repo, False) for git_dir, commit, repo in args.upstream]
    sources += [(directory, revision, repo, True) for directory, revision, repo in args.upstream_dir]
    for git_dir, commit, repo, plain in sources:
        try:
            first, counts = (dir_addresses(Path(git_dir), args.exclude) if plain
                             else upstream_addresses(Path(git_dir), commit, args.exclude))
        except (UpstreamError, OSError, ValueError) as exc:
            print(f"scan_personas: cannot read an upstream ({type(exc).__name__}: {exc})", file=sys.stderr)
            status = 1
            continue
        print(json.dumps({"upstream": repo, "commit": commit, "distinct_addresses": len(first), **counts}, sort_keys=True))
        for digest, path in first.items():
            upstream.setdefault(digest, path)
            evidence.setdefault(digest, (repo, commit, path))
    found_in_any: dict[str, tuple[str, str, str]] = {}
    for corpus in args.corpus:
        table: dict[str, rs.AddressStat] = {}
        name = corpus.name.removesuffix(".partial")
        unread = rs.collect_addresses(Path(os.path.realpath(corpus)), name, table, workers=args.workers)
        row = report(name, table, upstream)
        row["archives_unread"] = unread
        print(json.dumps(row, sort_keys=True))
        status = status or (1 if unread else 0)
        for digest, stat in table.items():
            if stat.klass != CLASS_RESERVED and digest in evidence:
                found_in_any[digest] = evidence[digest]
    if args.out:
        write_persona_file(args.out, args.persona_id, args.source_id, found_in_any)
        print(f"scan_personas: wrote {len(found_in_any)} digest(s) to {args.out.name}", file=sys.stderr)
    return status


if __name__ == "__main__":
    sys.exit(main())
