"""Examination 2, U14 follow-up: machine-specific strings in corpus files (read-only; counts and file kinds only).

Searches the bytes of every file of a corpus except the raw objects (which are upstream data) for the importing
machine's home directory, the corpus home, temporary-directory prefixes and the analyst's user name, and separately for
any ``/Users/<name>`` or ``/home/<name>`` path (benchmark content can hold such paths). Reports counts per file kind and
the distinct ``/Users/<name>``/``/home/<name>`` prefixes (names only, they are data).

Usage: ``python tools/analysis2/exam2_pathgrep.py --out REPORT.json CORPUS_DIR [...]``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter
from pathlib import Path

MACHINE = [re.escape(os.path.expanduser("~")).encode(), rb"\.agentprov/", rb"/private/tmp/", rb"/private/var/folders/",
           rb"/var/folders/", rb"migration-work/", rb"worktrees/agent-"]
MACHINE_RX = re.compile(b"|".join(MACHINE))
HOMES = re.compile(rb"/(?:Users|home)/([A-Za-z0-9._-]{1,40})")


def kind(rel: str) -> str:
    if rel.startswith("aer/"):
        return "aer"
    if rel.startswith("sem/"):
        return "sem"
    if rel.startswith("prov/"):
        return "prov"
    return rel


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("corpora", nargs="+")
    a = ap.parse_args()
    rep = {}
    for c in a.corpora:
        root = Path(c).expanduser()
        m: Counter = Counter()
        homes: Counter = Counter()
        files: Counter = Counter()
        for dp, _dn, fn in os.walk(root):
            rel_dir = os.path.relpath(dp, root)
            if rel_dir.startswith("raw/objects") or rel_dir.startswith("raw/tmp"):
                continue
            for f in fn:
                p = Path(dp) / f
                rel = os.path.relpath(p, root)
                data = p.read_bytes()
                k = kind(rel)
                files[k] += 1
                n = len(MACHINE_RX.findall(data))
                if n:
                    m[k] += n
                    m[f"files|{k}"] += 1
                for h in HOMES.findall(data):
                    homes[f"{k}|{h.decode('ascii', 'replace')}"] += 1
        rep[root.name] = {"files": dict(files), "machine_specific_hits": dict(m), "home_paths": dict(homes.most_common(30))}
    Path(a.out).write_text(json.dumps(rep, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
