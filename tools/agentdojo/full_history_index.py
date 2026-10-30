"""Build the full-history index of AgentDojo's run logs and cross-check the pinned indexes (deferrals part B; D.6.16).

    uv run python tools/agentdojo/full_history_index.py [--store DIR] [--blobless DIR] [--out FILE] [--report FILE]

Offline. Reads the **full** history store (bare, all blobs, no checkout; fetched with the user's consent on 2026-10-12,
logged in ``acquisitions.jsonl``; default ``$AGENTPROV_HOME/upstream/github.com/ethz-spylab/agentdojo.git``) with
``GIT_NO_LAZY_FETCH=1`` and an isolated git configuration, and:

1. builds :class:`agentprov.raw.history.FullHistoryIndex`: every ``(path, blob)`` the history of the head pin
   ``089ed468`` ever added under ``runs/``, with its introducing commit (the rule of the pinned indexes) and the pins
   whose tree still holds it. Rows held by no pin are the superseded versions (the planned ``history`` part);
2. recomputes each pin's :class:`~agentprov.raw.history.HistoryIndex` from the full store exactly as
   ``Fetcher._compute_history_index`` does and compares it **byte for byte** with the index cached beside the blobless
   store (``$AGENTPROV_HOME/cache/git-history/.../agentdojo.index/<commit>.jsonl``), which the shipped history table and
   D-84 rest on; and checks that the full index agrees with each pinned index row for row;
3. writes the index (default beside the store, ``agentdojo.index/full-<commit>.jsonl``: derived data, never committed)
   and a JSON report of counts and digests only (no log content).

Exit 0 when every check holds.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from agentprov.raw.history import (
    HistoryIndex,
    build_full_index,
    build_index,
    introducing_commits,
    parse_history_log,
    parse_plain_ls_tree,
)

REPO = "https://github.com/ethz-spylab/agentdojo"
PINS = {"2024-06": "c274885610efaaafec38b6d3eb07152ba7ff3f94", "head": "089ed468cf3ed0322acc66b0211f26d9d90dbf60"}
HOME = Path(os.environ.get("AGENTPROV_HOME", Path.home() / ".agentprov"))
STORE = HOME / "upstream" / "github.com" / "ethz-spylab" / "agentdojo.git"
BLOBLESS = HOME / "cache" / "git-history" / "github.com" / "ethz-spylab" / "agentdojo.index"
PREFIX = "runs/"
_ENV = {"PATH": os.environ.get("PATH", ""), "GIT_NO_LAZY_FETCH": "1", "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}


def git(store: Path, *args: str) -> bytes:
    return subprocess.run(["git", "--git-dir", str(store), *args], capture_output=True, check=True, env=_ENV,
                          timeout=1800).stdout


def tree_of(store: Path, commit: str) -> tuple[str, dict[str, str], int]:
    tree_id = git(store, "rev-parse", "--verify", f"{commit}^{{tree}}").decode().strip()
    tree, skipped = parse_plain_ls_tree(git(store, "ls-tree", "-r", "-z", "--full-tree", commit))
    return tree_id, tree, skipped


def history_log(store: Path, commit: str) -> bytes:
    return git(store, "log", "--format=%x01%H %P %ct", "--raw", "-z", "--no-renames", "--no-ext-diff", "--root", "-m",
               "--abbrev=40", commit, "--")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", type=Path, default=STORE)
    parser.add_argument("--blobless", type=Path, default=BLOBLESS, help="the cached pinned indexes to cross-check")
    parser.add_argument("--out", type=Path, help="index file (default: <store>/../agentdojo.index/full-<head>.jsonl)")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    head = PINS["head"]
    missing = git(args.store, "rev-list", "--objects", "--missing=print", head).count(b"\n?")
    report: dict[str, Any] = {"format": "agentprov-full-history-check/1", "repo": REPO, "head": head, "prefix": PREFIX,
                              "missing_objects": missing, "pins": {}}
    walked = int(git(args.store, "rev-list", "--count", head, "--").decode().strip())
    log = history_log(args.store, head)
    trees: dict[str, dict[str, str]] = {}
    ok = missing == 0
    for role, commit in PINS.items():
        tree_id, tree, skipped = tree_of(args.store, commit)
        trees[role] = tree
        pin_log = log if commit == head else history_log(args.store, commit)
        pin_walked = walked if commit == head else int(git(args.store, "rev-list", "--count", commit, "--").decode().strip())
        index = build_index(REPO, commit, tree_id, tree, introducing_commits(parse_history_log(pin_log), tree),
                            history_commits=pin_walked, skipped_paths=skipped)
        cached = args.blobless / f"{commit}.jsonl"
        data = index.to_bytes()
        same = cached.is_file() and cached.read_bytes() == data
        HistoryIndex.from_bytes(data, expect_repo=REPO, expect_commit=commit)
        report["pins"][role] = {"commit": commit, "tree": tree_id, "entries": len(index.rows),
                                "index_sha256": hashlib.sha256(data).hexdigest(),
                                "cached_sha256": hashlib.sha256(cached.read_bytes()).hexdigest() if cached.is_file() else None,
                                "equal_to_blobless_index": same}
        ok = ok and same
    full = build_full_index(REPO, head, PREFIX, trees, PINS,
                            introducing_commits(parse_history_log(log), None, prefix=PREFIX), history_commits=walked)
    for role, commit in PINS.items():
        pinned = HistoryIndex.from_bytes((args.blobless / f"{commit}.jsonl").read_bytes())
        under_prefix = {k: v for k, v in pinned.rows.items() if k[0].startswith(PREFIX)}
        agree = full.pinned_rows(role) == under_prefix
        report["pins"][role]["full_index_agrees_row_for_row"] = agree
        ok = ok and agree
    data = full.to_bytes()
    out = args.out or args.store.parent / "agentdojo.index" / f"full-{head}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    held = Counter(len(roles) for _c, roles in full.rows.values())
    logs = [k for k in full.rows if k[0].endswith(".json")]
    report.update(
        entries=len(full.rows), json_logs=len(logs), superseded=held[0], held_by_one_pin=held[1], held_by_both_pins=held[2],
        superseded_json_logs=sum(1 for k in logs if not full.rows[k][1]),
        introducing_commits=len(full.commits), history_commits=walked,
        first_introduced=min(full.commits.values()), last_introduced=max(full.commits.values()),
        index_file=str(out).replace(str(Path.home()), "<home>"), index_sha256=hashlib.sha256(data).hexdigest(), passed=ok,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("entries", "json_logs", "superseded_json_logs", "passed")}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
