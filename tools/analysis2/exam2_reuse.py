"""Examination 2: run the first analysis' tools (``tools/analysis/``) on other corpora without editing them.

The first-analysis tools hard-code their five corpora in a module constant ``CORPORA``; this wrapper imports a tool,
replaces the constant and calls its ``main``. ``rules`` is a generalised copy of ``phase10_rule_classes`` that reads the
rule catalogues of every adapter family (the original reads only the agentdojo family).

Usage: ``python tools/analysis2/exam2_reuse.py {aggregate|compare|rules} FEATURES_DIR CORPUS_NAME [...]``.
"""

from __future__ import annotations

import glob
import json
import sys
import tomllib
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE / "tools" / "analysis"))


def rules(indir: Path, corpora: list[str]) -> int:
    cls: dict[str, str] = {}
    code: dict[str, list[str]] = {}
    for p in glob.glob(str(HERE / "src/agentprov/adapters/*/rules/*.rules.toml")):
        with open(p, "rb") as fh:
            doc = tomllib.load(fh)
        for r in doc.get("rule", []):
            key = f"{r['id']}@{r['version']}"
            cls[key] = r["class"]
            code[key] = sorted({str(c.get("commit", ""))[:8] for c in r.get("code", [])})
    out = {}
    for c in corpora:
        p = indir / f"{c}.jsonl"
        cnt: Counter[str] = Counter()
        unknown: Counter[str] = Counter()
        for line in p.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            for k in r.get("rules_used") or {}:
                if cls.get(k) == "D":
                    cnt[k] += 1
                elif k not in cls:
                    unknown[k.split(".")[0]] += 1
        out[c] = {"D_rules": {k: {"executions": v, "code_commits": code.get(k)} for k, v in sorted(cnt.items())},
                  "rules_not_in_any_family_catalogue_by_namespace": dict(unknown)}
    print(json.dumps(out, indent=1))
    return 0


def main() -> int:
    which, indir, corpora = sys.argv[1], Path(sys.argv[2]), sys.argv[3:]
    if which == "rules":
        return rules(indir, corpora)
    mod = __import__({"aggregate": "phase10_aggregate", "compare": "phase10_compare"}[which])
    mod.CORPORA = list(corpora)
    sys.argv = [mod.__file__, "--in", str(indir)] if which == "aggregate" else [mod.__file__, str(indir)]
    return int(mod.main() or 0)


if __name__ == "__main__":
    raise SystemExit(main())
