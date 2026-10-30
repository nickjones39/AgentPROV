"""Examination 2: aggregate ``exam2_scan.py`` outputs into per-corpus summaries (counts, distributions, ex ids).

Usage: ``python tools/analysis2/exam2_merge.py --scan-dir DIR --out-dir DATA_DIR CORPUS_NAME [...]``.
Writes ``scan-<corpus>.json`` per corpus and ``p07-shared-statements.json`` (cross-document and cross-corpus variants of
shared top-level statements).
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

LISTS = ("p01_strict", "p02", "p03_c51", "p05_trigger", "p05_attr", "a05_present_nofound", "a05_found_notpresent")


def pct(hist: Counter, q: float) -> int | None:
    total = sum(hist.values())
    if not total:
        return None
    acc = 0
    for v in sorted(hist):
        acc += hist[v]
        if acc >= q * total:
            return v
    return max(hist)


def summarise(path: Path) -> tuple[dict[str, Any], dict[str, Counter], dict[str, str]]:
    c: Counter = Counter()
    hits: Counter = Counter()
    exh: dict[str, list] = {}
    lists: dict[str, list] = defaultdict(list)
    list_counts: Counter = Counter()
    comps = [Counter(), Counter(), Counter()]
    deg: dict[str, Counter] = defaultdict(Counter)
    shared: dict[str, Counter] = defaultdict(Counter)
    shared_ex: dict[str, str] = {}
    prefix: Counter = Counter()
    by_model: dict[str, Counter] = defaultdict(Counter)
    errors: list[str] = []
    n = 0
    for line in path.open(encoding="utf-8"):
        d = json.loads(line)
        n += 1
        if "error" in d:
            errors.append(f"{d['ex']}:{d['error']}")
            continue
        c.update(d["c"])
        hits.update(d["hits"])
        for k, v in d.get("exh", {}).items():
            lst = exh.setdefault(k, [])
            if len(lst) < 3:
                lst.append([d["ex"], v[0]])
        for k in LISTS:
            if d.get(k):
                list_counts[k] += 1
                if len(lists[k]) < 10:
                    lists[k].append(d["ex"])
        if "p09_components" in d:
            for i, v in enumerate(d["p09_components"]):
                comps[i][v] += 1
        for cls, h in (d.get("p09_deghist") or {}).items():
            deg[cls].update({int(k): v for k, v in h.items()})
        for sec, key, dig in d.get("p07_shared") or ():
            kk = f"{sec}|{key}"
            shared[kk][dig] += 1
            shared_ex.setdefault(f"{kk}|{dig}", d["ex"])
        for p, iri in d.get("p07_prefix") or ():
            prefix[f"{p}={iri}"] += 1
        m = d.get("model") or "<none>"
        for k, v in d["c"].items():
            if k.startswith(("a03|", "a05x|")):
                by_model[m][k] += v
        by_model[m]["executions"] += 1
    flat = {k: v for k, v in c.items() if not k.startswith(("p09deg|", "a01k|", "a01t|"))}
    degsum = {}
    for cls, h in sorted(deg.items()):
        degsum[cls] = {"nodes": sum(h.values()), "zero": h.get(0, 0), "p50": pct(h, 0.5), "p95": pct(h, 0.95), "max": max(h)}
    io: dict[str, Counter] = defaultdict(Counter)
    for k, v in c.items():
        if k.startswith("p09deg|"):
            _, sec, d_, val = k.split("|")
            io[f"{sec}|{d_}"][int(val)] += v
    iosum = {k: {"nodes": sum(h.values()), "zero": h.get(0, 0), "p50": pct(h, 0.5), "p95": pct(h, 0.95), "max": max(h)}
             for k, h in sorted(io.items())}
    tools: dict[str, Counter] = defaultdict(Counter)
    types: dict[str, Counter] = defaultdict(Counter)
    for k, v in c.items():
        if k.startswith("a01k|"):
            _, tool, ks = k.split("|", 2)
            tools[tool][ks] += v
        elif k.startswith("a01t|"):
            _, tool, key, t = k.split("|", 3)
            types[f"{tool}.{key}"][t] += v
    drift = {t: {"calls": sum(ks.values()), "keysets": len(ks)} for t, ks in tools.items() if len(ks) > 1}
    tunion = {k: dict(v) for k, v in types.items() if len(v) > 1}
    variants = {k: dict(v) for k, v in shared.items() if len(v) > 1}
    summary = {
        "executions": n,
        "analysis_errors": errors[:20],
        "analysis_error_count": len(errors),
        "counters": dict(sorted(flat.items())),
        "hits": dict(sorted(hits.items())),
        "hit_exemplars": exh,
        "per_execution_lists": {k: {"executions": list_counts[k], "examples": lists[k]} for k in LISTS},
        "components": {name: {"p50": pct(h, 0.5), "p95": pct(h, 0.95), "max": max(h) if h else None, "min": min(h) if h else None,
                              "hist": dict(sorted(h.items()))}
                       for name, h in zip(("core", "core+inf", "core+inf+attr"), comps, strict=True)},
        "degree_by_class": degsum,
        "degree_in_out": iosum,
        "tools": {"distinct": len(tools), "with_keyset_drift": drift, "type_unions": tunion},
        "shared_statements": {"keys": len(shared), "keys_with_variants": len(variants), "variants": variants},
        "prefixes": dict(prefix),
        "by_model": {m: dict(v) for m, v in sorted(by_model.items())},
    }
    return summary, shared, shared_ex


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan-dir", required=True, type=Path)
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("corpora", nargs="+")
    a = ap.parse_args()
    cross: dict[str, dict[str, Counter]] = defaultdict(dict)
    cross_ex: dict[str, str] = {}
    for name in a.corpora:
        s, shared, sex = summarise(a.scan_dir / f"{name}.jsonl")
        (a.out_dir / f"scan-{name}.json").write_text(json.dumps(s, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        for k, v in shared.items():
            cross[k][name] = v
        for k, v in sex.items():
            cross_ex.setdefault(k, f"{name}:{v}")
        print(name, "merged")
    rep: dict[str, Any] = {"keys": len(cross), "in_several_corpora": 0, "variant_across_corpora": {}, "variant_within": {}}
    for k, per in sorted(cross.items()):
        digs = Counter()
        for v in per.values():
            digs.update(v)
        if len(per) > 1:
            rep["in_several_corpora"] += 1
        if len(digs) > 1:
            entry = {c: dict(v) for c, v in per.items()}
            if any(len(v) > 1 for v in per.values()):
                rep["variant_within"][k] = entry
            else:
                rep["variant_across_corpora"][k] = entry
    rep["examples"] = {k: v for k, v in list(cross_ex.items()) if k.rsplit("|", 1)[0] in rep["variant_across_corpora"] or k.rsplit("|", 1)[0] in rep["variant_within"]}
    (a.out_dir / "p07-shared-statements.json").write_text(json.dumps(rep, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
