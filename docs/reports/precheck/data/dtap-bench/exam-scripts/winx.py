"""Windows direct_prompt files byte-identical to a windows direct file (cross-split copies), per pair, with the
direct_prompt judge ASR with and without them; plus the per-pair benign macOS/windows judge-dir counts. Counts only.
Usage: python -I winx.py <l1-units.jsonl> <l1-aux.jsonl> <out.json>"""
import collections, json, os, sys
rows = [json.loads(l) for l in open(sys.argv[1])]; aux = {os.path.dirname(json.loads(l)["label"]): json.loads(l) for l in open(sys.argv[2])}
by_sha = collections.defaultdict(list)
for r in rows:
    if r["facets"]["domain"] == "windows" and "judge_only_unit" not in r["flags"]:
        by_sha[r["sha256"]].append(r)
res = collections.defaultdict(lambda: collections.Counter())
for r in rows:
    f = r["facets"]
    if f["domain"] != "windows" or f["split_label"] != "direct_prompt" or "judge_only_unit" in r["flags"]:
        continue
    pair = f"{f['framework']}|{f['model']}"; g = by_sha[r["sha256"]]
    copy = any(x["facets"]["split_label"] == "direct" for x in g)
    a = aux.get(os.path.dirname(r["label"])); v = a["outcomes"].get("attack_success") if a else None
    e = res[pair]; e["files"] += 1; e["copy_of_direct"] += copy
    if v is not None:
        e["n"] += 1; e["k"] += v is True
        if not copy:
            e["n_wo"] += 1; e["k_wo"] += v is True
        else:
            e["k_copy"] += v is True
out = {p: dict(c) | {"asr": round(100 * c["k"] / c["n"], 1) if c["n"] else None,
                     "asr_without_copies": round(100 * c["k_wo"] / c["n_wo"], 1) if c["n_wo"] else None} for p, c in sorted(res.items())}
json.dump(out, open(sys.argv[3], "w"), indent=1); [print(p, v) for p, v in out.items()]
