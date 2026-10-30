"""Code ranges of the ``agentdojo`` catalogue's code citations over AgentDojo's history (deferrals part B, input to part C).

    uv run python tools/agentdojo/code_ranges.py --report FILE [--store DIR] [--index FILE]

Offline (``GIT_NO_LAZY_FETCH=1``, isolated git configuration), over the full-history store and the full-history index.

**Question.** D.5.4 cites a D rule at D only for a record whose producing code its catalogue ``code`` list cites. A
``v0.k11`` log introduced after the 2024-06 pin ``c274885`` (D-84: 10,732 head logs) was written by code no pin covers,
so it cites the ``_unverified`` twins. Part C proposes to let a rule declare a ``verified`` assumption over a **code
range** (AER-V34 widened). This tool measures what such a range would rest on: for every code citation at ``c274885``
of an active ``agentdojo`` rule, is the cited passage (its exact lines, as text) present, unchanged, at **every** commit
from ``c274885`` to each later introducing commit of a ``v0.k11`` log (``git rev-list c274885..<commit>``, the commits a
producing state could have been taken from after the pin), at the same package-relative path (the package was renamed
``function_calling_pi`` -> ``agentgym`` -> ``agentdojo``)?

**Not shown by this tool.** That the producing code of a log lies inside the range: the introducing commit bounds it
from above only (D.6.16), and a log could have been produced by code older than the pin. Part C's design states how a
range assumption treats that (docs/reports/aer-0.2/).

Output: per citation, the introducing commits where the passage holds over the whole range; per rule, the number of
head-only ``v0.k11`` logs for which every citation of the rule holds. Counts, commit ids and paths only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import re
import tomllib
from collections import Counter
from pathlib import Path
from typing import Any

from agentprov.adapters.agentdojo.dialect import classify
from agentprov.errors import AgentProvError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

PIN = "c274885610efaaafec38b6d3eb07152ba7ff3f94"
HEAD = "089ed468cf3ed0322acc66b0211f26d9d90dbf60"
REPO = "https://github.com/ethz-spylab/agentdojo"
PACKAGES = ("src/function_calling_pi/", "src/agentgym/", "src/agentdojo/")
HOME = Path(os.environ.get("AGENTPROV_HOME", Path.home() / ".agentprov"))
STORE = HOME / "upstream" / "github.com" / "ethz-spylab" / "agentdojo.git"
INDEX = STORE.parent / "agentdojo.index" / f"full-{HEAD}.jsonl"
CATALOGUE = Path(__file__).resolve().parents[2] / "src/agentprov/adapters/agentdojo/rules/agentdojo.rules.toml"
_ENV = {"PATH": os.environ.get("PATH", ""), "GIT_NO_LAZY_FETCH": "1", "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}


def git(store: Path, *args: str, data: bytes | None = None) -> bytes:
    return subprocess.run(["git", "--git-dir", str(store), *args], input=data, capture_output=True, check=True, env=_ENV,
                          timeout=1800).stdout


class Blobs:
    """Blob reader with a cache (``git cat-file --batch`` per request batch; SHA-1 checked)."""

    def __init__(self, store: Path) -> None:
        self.store, self.cache = store, {}

    def get(self, oids: list[str]) -> dict[str, bytes]:
        todo = sorted({o for o in oids if o not in self.cache})
        if todo:
            stream = git(self.store, "cat-file", "--batch", data="".join(f"{o}\n" for o in todo).encode())
            pos = 0
            for oid in todo:
                end = stream.index(b"\n", pos)
                head = stream[pos:end].split()
                size = int(head[2])
                body = stream[end + 1 : end + 1 + size]
                pos = end + 2 + size
                if hashlib.sha1(b"blob %d\0" % size + body, usedforsecurity=False).hexdigest() != oid:
                    raise SystemExit(f"blob {oid} does not hash to its id")
                self.cache[oid] = body
        return {o: self.cache[o] for o in oids}


def relative(path: str) -> str | None:
    return next((path[len(p):] for p in PACKAGES if path.startswith(p)), None)


def file_blob(store: Path, commit: str, rel: str) -> str | None:
    """The blob of the package-relative file ``rel`` at ``commit`` (whichever package name the commit uses)."""
    listing = git(store, "ls-tree", commit, "--", *(p + rel for p in PACKAGES)).decode().splitlines()
    blobs = [line.split()[2] for line in listing if line.strip()]
    return blobs[0] if len(blobs) == 1 else None


def citations() -> list[dict[str, Any]]:
    """Every code citation at the 2024-06 pin of an active, class-D ``agentdojo`` rule."""
    doc = tomllib.loads(CATALOGUE.read_text(encoding="utf-8"))
    out = []
    for rule in doc.get("rule", ()):
        if rule.get("status") != "active" or rule.get("class") != "D":
            continue
        for ref in rule.get("code", ()):
            if ref.get("commit") == PIN and ref.get("repo") == REPO and relative(str(ref.get("path"))) and ref.get("lines"):
                out.append({"rule": f"{rule['id']}@{rule['version']}", "path": ref["path"], "lines": str(ref["lines"])})
    return out


def passage(text: bytes, lines: str) -> bytes:
    first, _, last = lines.partition("-")
    rows = text.split(b"\n")
    return b"\n".join(rows[int(first) - 1 : int(last or first)])


_PKG = re.compile(rb"\b(function_calling_pi|agentgym|agentdojo)\b")
_WS = re.compile(rb"\s+")


def normalised(text: bytes) -> bytes:
    """The ``normalised`` measure: the package name unified and every run of whitespace collapsed (a renamed import or a
    re-wrapped line is not a change of the code's behaviour; anything else is)."""
    return _WS.sub(b" ", _PKG.sub(b"PKG", text)).strip()


def rfc3339(epoch: int) -> str:
    from agentprov.raw.history import rfc3339_utc

    return rfc3339_utc(epoch)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", type=Path, default=STORE)
    parser.add_argument("--index", type=Path, default=INDEX)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    blobs = Blobs(args.store)
    rows = [json.loads(line) for line in args.index.read_bytes().splitlines()[1:]]
    head_only = [r for r in rows if r["pins"] == ["head"]]
    data = blobs.get([r["b"] for r in head_only])
    limits = IngestLimits()
    intro_of: Counter[str] = Counter()
    for row in head_only:
        try:
            sniff = classify(strict_json_loads(data[row["b"]], limits))
        except AgentProvError:
            continue
        if sniff.match and sniff.variant == "v0.k11":
            intro_of[row["c"]] += 1
    blobs.cache.clear()
    ranges = {c: git(args.store, "rev-list", f"{PIN}..{c}").decode().split() for c in intro_of}
    commits = sorted({c for r in ranges.values() for c in r} | {PIN})
    epoch = {c: int(t) for c, t in (line.split() for line in git(args.store, "log", "--format=%H %ct", HEAD).decode().splitlines())}
    intro_dates = {c: epoch.get(c) for c in intro_of}
    cites = citations()
    results = []
    holds_by_rule: dict[str, tuple[set[str], set[str]]] = {}
    for cite in cites:
        rel = relative(cite["path"])
        assert rel is not None
        at_pin = file_blob(args.store, PIN, rel)
        if at_pin is None:
            results.append({**cite, "error": "the cited file is not at the pin"})
            holds_by_rule[cite["rule"]] = (set(), set())
            continue
        wanted = passage(blobs.get([at_pin])[at_pin], cite["lines"])
        loose = normalised(wanted)
        present: dict[str, bool] = {}
        similar: dict[str, bool] = {}
        for commit in commits:
            blob = file_blob(args.store, commit, rel)
            text = blobs.get([blob])[blob] if blob is not None else None
            present[commit] = text is not None and wanted in text
            similar[commit] = text is not None and loose in normalised(text)
        holds = {c for c, rng in ranges.items() if all(present[x] for x in rng)}
        holds_loose = {c for c, rng in ranges.items() if all(similar[x] for x in rng)}
        strict, relaxed = holds_by_rule.get(cite["rule"], (set(intro_of), set(intro_of)))
        holds_by_rule[cite["rule"]] = (strict & holds, relaxed & holds_loose)
        lost = sorted((epoch[c], c) for c, ok in similar.items() if not ok and c != PIN)
        results.append({**cite, "passage_sha256": hashlib.sha256(wanted).hexdigest(),
                        "first_commit_without_it": lost[0][1] if lost else None,
                        "first_date_without_it": rfc3339(lost[0][0]) if lost else None,
                        "exact": {"introducing_commits_held": len(holds), "logs_held": sum(intro_of[c] for c in holds),
                                  "commits_without_it": sum(1 for ok in present.values() if not ok)},
                        "normalised": {"introducing_commits_held": len(holds_loose),
                                       "logs_held": sum(intro_of[c] for c in holds_loose),
                                       "commits_without_it": sum(1 for ok in similar.values() if not ok)}})
    rules = {rid: {"citations": sum(1 for c in cites if c["rule"] == rid),
                   "exact_logs_held": sum(intro_of[c] for c in held[0]),
                   "normalised_logs_held": sum(intro_of[c] for c in held[1])} for rid, held in sorted(holds_by_rule.items())}
    report = {
        "format": "agentprov-code-ranges/1", "pin": PIN, "head": HEAD, "head_only_v0k11_logs": sum(intro_of.values()),
        "introducing_commits": {c: {"logs": n, "date": rfc3339(intro_dates[c]) if intro_dates[c] else None}
                                for c, n in sorted(intro_of.items())},
        "commits_examined": len(commits), "rules": rules, "citations": results,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"logs": report["head_only_v0k11_logs"], "intro": len(intro_of), "citations": len(results),
                      "exact_full": sum(1 for r in rules.values() if r["exact_logs_held"] == report["head_only_v0k11_logs"]),
                      "normalised_full": sum(1 for r in rules.values() if r["normalised_logs_held"] == report["head_only_v0k11_logs"])}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
