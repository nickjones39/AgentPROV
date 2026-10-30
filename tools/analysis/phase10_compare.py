"""Cross-corpus comparison of graph shapes from the extractor rows (read-only on the rows; no corpus access).

* nodes and edges per message (core+inference union), per corpus and AER variant;
* where each PROV rule's statements land (core / inference) per corpus, normalised per execution;
* the structural shape of the same harness behaviours: an executed call, an unexecuted trailing call, a deny decision,
  a redaction, a retry-inferred attempt, a run error: the rules and bundles each produces.

Usage: ``python tools/analysis/phase10_compare.py OUTDIR``.
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

CORPORA = ["rope-p10", "agentdyn-a-p10", "agentdojo-upstream-head-p10", "mandate-agentdojo-eval-p10", "ast-survey-agentdojo-p10"]


def main() -> int:
    outdir = Path(sys.argv[1])
    result: dict = {}
    rule_place: dict[str, dict[str, float]] = defaultdict(dict)
    for c in CORPORA:
        p = outdir / f"{c}.jsonl"
        if not p.exists():
            continue
        rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line]
        per_var: dict[str, list[tuple[float, float]]] = defaultdict(list)
        for r in rows:
            n = r.get("n_messages") or 0
            if n:
                per_var[str(r.get("variant"))].append((r.get("prov_nodes", 0) / n, r.get("prov_edges", 0) / n))
        result[c] = {
            v: {"n": len(xs), "nodes_per_msg_p50": round(statistics.median(x for x, _ in xs), 2),
                "edges_per_msg_p50": round(statistics.median(y for _, y in xs), 2)}
            for v, xs in sorted(per_var.items())
        }
        rules: Counter[str] = Counter()
        for r in rows:
            rules.update(r.get("prov_rules") or {})
        for k, v in rules.items():
            rule_place[k][c] = round(v / len(rows), 3)
        # structural class of the core statements per corpus
        cls = Counter()
        for r in rows:
            cls.update(r.get("prov_classes") or {})
        tot = {b: sum(v for k, v in cls.items() if k.startswith(b + ":")) for b in ("core", "inference", "assessment")}
        result[c]["statement_share"] = {k: round(v / max(1, tot[k.split(":")[0]]), 3) for k, v in sorted(cls.items())}
        result[c]["share_core_of_core_plus_inf"] = round(tot["core"] / max(1, tot["core"] + tot["inference"]), 3)
    # rules whose placement differs between corpora (core vs inference)
    placement: dict[str, dict[str, str]] = defaultdict(dict)
    for key, per in rule_place.items():
        bundle, rule = key.split(":", 1)
        for c in per:
            placement[rule].setdefault(c, "")
            placement[rule][c] = "+".join(sorted(set(filter(None, placement[rule][c].split("+"))) | {bundle}))
    result["rule_placement"] = {r: v for r, v in sorted(placement.items())}
    result["rules_per_execution"] = {k: v for k, v in sorted(rule_place.items())}
    print(json.dumps(result, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
