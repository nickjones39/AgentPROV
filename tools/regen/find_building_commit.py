"""Find the AgentPROV commits that could have built a corpus (regeneration plan, D-358 at the building commit).

Usage: python -I tools/regen/find_building_commit.py CORPUS_DIR [--repo .] [--rev-list-args ...]

A working corpus records no commit (``corpus.json`` has ``producer.agentprov_version`` and the lockfile digest only), but
its ``derivation.json`` records, per stage, the SHA-256 code digests of the package directories that ran
(H.8.2(2): ``sha256(JCS([[relpath, sha256(file)], ...]))`` over ``.py``/``.toml``/``.json``/``.ttl`` files, CRLF normalised).
This tool recomputes those digests from git trees for every commit reachable from any ref and prints the commits whose
lockfile and stage digests all match. Read-only git plumbing (``ls-tree``, ``cat-file --batch``); nothing is checked out.
The digest construction is a copy of ``agentprov.corpus.derive.code_sha256`` (its JCS of a list of string pairs is plain
compact JSON with sorted entries and ASCII-safe strings, which holds for these relpaths and hex digests).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

PKG = "src/agentprov/"
SUFFIXES = (".py", ".toml", ".json", ".ttl")

# (stage, digest field, dirs, exclude); the family dir of the aer stage is filled in from the recorded adapter id
STAGES = [
    ("aer", "engine_code_sha256", ["adapters/runner", "aer"], []),
    ("prov", "engine_code_sha256", ["prov", "vocab"], ["prov/compat/"]),
    ("validation", "engine_code_sha256", ["validate", "aer/validate.py", "aer/accounting.py", "sem/validate.py"], []),
]


class Blobs:
    def __init__(self, repo: str) -> None:
        env = dict(os.environ, GIT_NO_LAZY_FETCH="1")
        self.proc = subprocess.Popen(["git", "-C", repo, "cat-file", "--batch"], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, env=env)
        self.cache: dict[str, str] = {}

    def sha256(self, oid: str) -> str:
        if oid not in self.cache:
            assert self.proc.stdin and self.proc.stdout
            self.proc.stdin.write(oid.encode() + b"\n")
            self.proc.stdin.flush()
            header = self.proc.stdout.readline().split()
            size = int(header[2])
            data = self.proc.stdout.read(size)
            self.proc.stdout.read(1)
            self.cache[oid] = hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()
        return self.cache[oid]


def tree(repo: str, commit: str) -> dict[str, str]:
    out = subprocess.run(["git", "-C", repo, "ls-tree", "-r", commit, "--", PKG, "uv.lock"], capture_output=True,
                         text=True, check=True, env=dict(os.environ, GIT_NO_LAZY_FETCH="1")).stdout
    files: dict[str, str] = {}
    for line in out.splitlines():
        meta, path = line.split("\t", 1)
        _mode, kind, oid = meta.split()
        if kind == "blob":
            files[path] = oid
    return files


def code_digest(files: dict[str, str], blobs: Blobs, dirs: list[str], exclude: list[str]) -> str:
    entries = []
    for directory in dirs:
        prefix = PKG + directory
        for path, oid in files.items():
            if not (path == prefix or path.startswith(prefix.rstrip("/") + "/")):
                continue
            rel = path[len(PKG):]
            if not rel.endswith(SUFFIXES) or "__pycache__" in rel or any(rel.startswith(e) for e in exclude):
                continue
            entries.append([rel, blobs.sha256(oid)])
    payload = json.dumps(sorted(entries), separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus", type=Path)
    ap.add_argument("--repo", default=".")
    args = ap.parse_args()
    deriv = json.loads((args.corpus / "derivation.json").read_text(encoding="utf-8"))
    stages = {s["stage"]: s for s in deriv["stages"]}
    lock = deriv.get("lockfile_sha256")
    family = str(stages["aer"]["adapter"]).split(".", 1)[0]
    checks = [("aer", "adapter_code_sha256", [f"adapters/{family}"], [])] + STAGES
    commits = subprocess.run(["git", "-C", args.repo, "rev-list", "--all", "--date-order"], capture_output=True,
                             text=True, check=True).stdout.split()
    blobs = Blobs(args.repo)
    hits = []
    for commit in commits:
        files = tree(args.repo, commit)
        if "uv.lock" not in files or "sha256:" + blobs.sha256(files["uv.lock"]) != lock:
            continue
        ok = all(code_digest(files, blobs, dirs, exc) == stages[stage].get(field)
                 for stage, field, dirs, exc in checks if stage in stages)
        if ok:
            hits.append(commit)
    for commit in hits:
        line = subprocess.run(["git", "-C", args.repo, "log", "-1", "--format=%H %ci %s", commit], capture_output=True,
                              text=True, check=True).stdout.strip()
        print(line)
    print(json.dumps({"corpus": args.corpus.name, "lockfile": lock, "commits_scanned": len(commits),
                      "matches": len(hits)}), file=sys.stderr)
    return 0 if hits else 1


if __name__ == "__main__":
    sys.exit(main())
