"""Which D-class rules do executions of each corpus cite, and which commits do those rules' code blocks cite?

D.5.4 ("I twins"): a D rule may be cited only for a producing code identity (or code range) its verification block lists;
profiles with unpinned harness code (``structural_rule_class = "I"``) cite ``_unverified`` twins. This lists, per corpus,
every cited D rule of the family catalogues with the number of executions citing it and the commits of its code block,
so a D rule cited for an unpinned harness stands out. Reads the rule catalogues (package data) and extractor rows.

Usage: ``python tools/analysis/phase10_rule_classes.py OUTDIR``.
"""

from __future__ import annotations

import glob
import json
import sys
import tomllib
from collections import Counter
from pathlib import Path

CORPORA = ["rope-p10", "agentdyn-a-p10", "ast-survey-agentdojo-p10", "agentdojo-upstream-head-p10", "mandate-agentdojo-eval-p10"]


def main() -> int:
    here = Path(__file__).resolve().parents[2]
    cls: dict[str, str] = {}
    code: dict[str, list[str]] = {}
    for p in glob.glob(str(here / "src/agentprov/adapters/agentdojo/rules/*.rules.toml")):
        with open(p, "rb") as fh:
            doc = tomllib.load(fh)
        for r in doc.get("rule", []):
            key = f"{r['id']}@{r['version']}"
            cls[key] = r["class"]
            code[key] = sorted({str(c.get("commit", ""))[:8] for c in r.get("code", [])})
    out = {}
    for c in CORPORA:
        p = Path(sys.argv[1]) / f"{c}.jsonl"
        if not p.exists():
            continue
        cnt: Counter[str] = Counter()
        for line in p.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            for k in r.get("rules_used") or {}:
                if cls.get(k) == "D":
                    cnt[k] += 1
        out[c] = {k: {"executions": v, "code_commits": code.get(k)} for k, v in sorted(cnt.items())}
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
