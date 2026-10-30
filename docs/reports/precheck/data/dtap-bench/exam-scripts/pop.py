"""dtap-bench population tally from the L1 rows only (no raw read): counts per pair x split, judge directories,
domains, duplicates, judge-level outcomes per pair x split x domain vs the paper domain values (gap rule), H4/H5/H7/H8/
H12b/H14/H17/H18 inputs. Counts only. Usage: python -I pop.py <l1-units.jsonl> <l1-aux.jsonl> <research.json> <out.json>"""
import collections, json, math, os, sys

units, aux, research, out = sys.argv[1:5]
DOM = {"browser": "Browser", "code": "Code", "crm": "CRM", "customer-service": "CS", "finance": "Finance",
       "legal": "Legal", "medical": "Medical", "os-filesystem": "OS-FS", "research": "Research", "telecom": "Telecom",
       "travel": "Travel", "windows": "Windows", "workflow": "Workflow", "macos": "macOS"}
PV = json.load(open(research))["paper_domain_values"]["values"]


def wilson(k, n, z=1.96):
    if n == 0:
        return [None, None]
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round(100 * (c - h) / d, 2), round(100 * (c + h) / d, 2)]


rows = [json.loads(l) for l in open(units)]
dirs = collections.defaultdict(list)  # judge dir -> unit rows
traj = collections.Counter(); byfw = collections.Counter(); models = collections.Counter()
domains = collections.defaultdict(collections.Counter); sha = collections.defaultdict(list); fp = collections.defaultdict(list)
late = collections.Counter()
for r in rows:
    f = r["facets"]; pair = f"{f['framework']}|{f['model']}"
    d = os.path.dirname(r["label"]); dirs[d].append(r)
    if "judge_only_unit" in r["flags"]:
        continue
    traj[(pair, f["split_label"])] += 1; byfw[f["framework"]] += 1; models[pair] += 1
    domains[pair][(f["split_label"], f["domain"])] += 1
    sha[r["sha256"]].append(r)
    if r["fp"]:
        fp[r["fp"]].append(r)
    stem = os.path.basename(r["label"])[:8]
    if stem.isdigit() and stem > "20260505":
        late["synthetic" if "synthetic" in r["flags"] else "other"] += 1
aux_rows = {os.path.dirname(a["label"]): a for a in (json.loads(l) for l in open(aux))}

# judge-level tally: one judge per directory (aux judge file, or the judge-only unit)
cells = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))  # (pair,split,dom)->cat->[k,n]
jdirs = collections.Counter(); excl = collections.Counter(); special = collections.defaultdict(lambda: [0, 0, 0])
for d, rs in dirs.items():
    a = aux_rows.get(d)
    ref = rs[0]; f = ref["facets"]; pair = f"{f['framework']}|{f['model']}"; split = f["split_label"]
    if a is None:
        if any("judge_only_unit" in r["flags"] for r in rs):
            o = {"attack_success": ref["outcomes"].get("attack_success"), "task_success": ref["outcomes"].get("task_success")}
        else:
            excl["no_judge"] += 1; continue
    else:
        o = a["outcomes"]
    jdirs[(pair, split)] += 1
    if any("synthetic" in r["flags"] for r in rs):
        excl["synthetic"] += 1; continue
    if any("harness_error" in r["flags"] for r in rs):
        excl["harness_failure"] += 1; continue
    metric = "task_success" if split == "benign" else "attack_success"
    v = o.get(metric)
    if v is None:
        excl[f"null_{metric}"] += 1; continue
    cat = f["risk_category"]
    c = cells[(pair, split, f["domain"])][cat]; c[0] += int(v is True); c[1] += 1
    if f["domain"] == "os-filesystem" and split == "indirect" and cat == "unauthorized-access-and-illegal-interception" \
            and d.rstrip("/").endswith("/52"):
        t = o.get("task_success"); special["os_fs_ind_52"][0] += int(t is False); special["os_fs_ind_52"][1] += 1
    if cat == "Delete-sensitive-files" and split == "indirect":
        special[f"dsf_indirect|{pair}"][0] += int(v is True); special[f"dsf_indirect|{pair}"][1] += 1

res = []; pairlevel = collections.defaultdict(lambda: [0, 0])
for (pair, split, dom), cats in sorted(cells.items()):
    k = sum(c[0] for c in cats.values()); n = sum(c[1] for c in cats.values())
    pairlevel[(pair, split)][0] += k; pairlevel[(pair, split)][1] += n
    macro = 100 * sum(c[0] / c[1] for c in cats.values()) / len(cats)
    key = split if split in ("benign", "direct", "indirect") else "direct_baseline"
    pv = PV.get(f"{pair}|{key}", {}).get(DOM[dom])
    row = {"pair": pair, "split": split, "domain": dom, "k": k, "n": n, "micro": round(100 * k / n, 2),
           "cat_macro": round(macro, 2), "n_cats": len(cats), "wilson95": wilson(k, n)}
    if pv:
        p = pv[0]; row |= {"paper": p, "table": pv[1], "gap_micro": round(row["micro"] - p, 2),
                           "gap_macro": round(macro - p, 2)}
        lo, hi = row["wilson95"]
        row["flag_15pp"] = n >= 20 and abs(row["gap_micro"]) > 15
        row["flag_ci5"] = (p < lo - 5) or (p > hi + 5)
        row["flag_15pp_macro"] = n >= 20 and abs(row["gap_macro"]) > 15
    res.append(row)
withp = [r for r in res if "paper" in r]
summ = {"cells": len(res), "cells_with_paper": len(withp), "cells_n20": sum(r["n"] >= 20 for r in withp),
        "flag_15pp_micro": sum(r["flag_15pp"] for r in withp), "flag_15pp_macro": sum(r["flag_15pp_macro"] for r in withp),
        "flag_ci5_micro": sum(r["flag_ci5"] for r in withp),
        "max_abs_gap_micro": max(abs(r["gap_micro"]) for r in withp), "max_abs_gap_macro": max(abs(r["gap_macro"]) for r in withp),
        "gt30_micro": sum(abs(r["gap_micro"]) > 30 for r in withp), "gt30_macro": sum(abs(r["gap_macro"]) > 30 for r in withp)}

# duplicates: byte-identical trajectory files, and identical fingerprints across pairs / splits
bi = [g for g in sha.values() if len(g) > 1]
bi_kind = collections.Counter()
for g in bi:
    fc = {r["facets"]["file_class"] for r in g}; spl = {r["facets"]["split_label"] for r in g}
    cats = {r["facets"]["risk_category"] for r in g}; tdir = {os.path.dirname(r["label"]) for r in g}
    bi_kind["copy_(1)" if "copy" in fc else ("same_dir_rerun" if len(tdir) == 1 else
            ("cross_split" if len(spl) > 1 else ("cross_category" if len(cats) > 1 else "cross_task_same_cat")))] += 1
fpx = collections.Counter(); fpx_units = collections.Counter(); xpair = []
for g in fp.values():
    if len(g) < 2:
        continue
    pairs = {(r["facets"]["framework"], r["facets"]["model"]) for r in g}
    if len(pairs) > 1:
        fpx["cross_pair_groups"] += 1; fpx_units["cross_pair_units"] += len(g); xpair.append([r["label"] for r in g])
json.dump({"xpair_labels": xpair}, open(os.path.join(os.path.dirname(out), "xpair-labels.json"), "w"))

openclaw54 = sorted({dom for (s, dom) in domains["openclaw|gpt-5.4"]})
o54 = {f"{s}|{dom}": n for (s, dom), n in sorted(domains["openclaw|gpt-5.4"].items())}
json.dump({"traj_files_by_pair_split": {f"{p}|{s}": n for (p, s), n in sorted(traj.items())},
           "judge_dirs_by_pair_split": {f"{p}|{s}": n for (p, s), n in sorted(jdirs.items())},
           "by_framework_traj": dict(byfw), "pairs": dict(models), "late_stem_after_20260505": dict(late),
           "openclaw_gpt54_domains": openclaw54, "openclaw_gpt54_by_split_domain": o54,
           "tally_exclusions": dict(excl), "pair_level_micro": {f"{p}|{s}": [k, n, round(100 * k / n, 2)] for (p, s), (k, n) in sorted(pairlevel.items())},
           "special": {k: v[:2] for k, v in special.items()}, "gap_summary": summ, "cells": res,
           "byte_identical_traj": {"groups": len(bi), "files": sum(len(g) for g in bi), "kinds": dict(bi_kind)},
           "fp_cross_pair": dict(fpx) | dict(fpx_units)}, open(out, "w"), indent=1)
print(json.dumps({"summ": summ, "excl": excl, "bi": dict(bi_kind), "fpx": dict(fpx) | dict(fpx_units), "late": late,
                  "o54": openclaw54}, default=str))
