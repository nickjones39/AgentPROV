# ruff: noqa  (precheck examiner script for agentops-bench, committed as run; read-only analysis)
"""Raw census of the 7,202 run files of the pinned traces tarball (through agentprov.ingest; no mapping).

Recomputes the paper metrics (prereg section 4) and the counts of H3-H14 on every run file. In-scope = the profile's
three include globs. Counts, labels, sha256 prefixes and pattern classes only; no record text is written.
Usage: uv run python -I raw.py <traces.tar.gz> <out.json>
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from agentprov.ingest.archives import open_archive
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

TAR = Path(sys.argv[1]).expanduser()
OUT = Path(sys.argv[2])
GLOBS = ("pilot_v1_seeded/*/*/adversarial/*_run*.json", "pilot_v1_seeded/*/*/clean/safety_*_run*.json",
         "pilot_v1_seeded/*/*/noisy/safety_*_run*.json")
LAB = re.compile(r"pilot_v1_seeded/([^/]+)/([^/]+)/([^/]+)/(.+)_(\d{3})_run(\d+)\.json$")
ACCT = re.compile(r"(/Users/|/home/)([A-Za-z0-9._-]+)/")
GENERIC = {"user", "runner", "ubuntu", "root", "username", "you", "me", "name", "<user>", "USER", "agent", "sandbox"}
H14 = re.compile(r"(version|commit|price_date|pricing_date|fixture_hash|fixtures_sha|git)", re.I)


def keys(v, pfx=""):
    if isinstance(v, dict):
        for k, x in v.items():
            yield pfx + "/" + k
            yield from keys(x, pfx + "/" + k)
    elif isinstance(v, list):
        for x in v:
            yield from keys(x, pfx + "/*")


def strings(v, ptr=""):
    if isinstance(v, str):
        yield ptr, v
    elif isinstance(v, dict):
        for k, x in v.items():
            yield from strings(x, ptr + "/" + k)
    elif isinstance(v, list):
        for x in v:
            yield from strings(x, ptr + "/*")


def mean(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return (round(sum(xs) / len(xs), 4), len(xs)) if xs else (None, 0)


def main():
    runs = []
    with TAR.open("rb") as fp, open_archive(fp, IngestLimits(), release=False) as t:
        for m in t.iter_members(lambda l: bool(LAB.search(l)) and "/._" not in l, IngestLimits()):
            if m.disposition != "selected":
                continue
            b = t.read_member(m)
            mm = LAB.search(m.label)
            runs.append((m.label, mm.groups(), hashlib.sha256(b).hexdigest(), strict_json_loads(b)))
    out: dict = {"run_files": len(runs)}
    insc = [r for r in runs if any(fnmatch.fnmatchcase(r[0], g) for g in GLOBS)]
    out["in_scope"] = len(insc)
    out["byte_identical_groups"] = sum(1 for v in Counter(r[2] for r in runs).values() if v > 1)
    # cell key (model, condition, domain, task, run) for superseded copies
    cell = Counter((g[1], g[2], g[3], g[4], g[5]) for _, g, _, _ in runs)
    out["duplicate_cells"] = [{"cell": "|".join(k), "n": v} for k, v in cell.items() if v > 1]
    # ---- H5: metrics per agent
    per = defaultdict(lambda: defaultdict(list))
    ncomp = Counter(); nall = Counter()
    for lab, g, _, r in runs:
        ad, pm, cond, dom, task, run = g
        sc = r.get("scores") or {}
        tr = r.get("trace") or {}
        comp = sc.get("completion"); eff = (sc.get("efficiency") or {}).get("overall"); saf = (sc.get("safety") or {}).get("overall")
        nall[pm] += 1
        if tr.get("completed") is not True:
            ncomp[pm] += 1
        if cond == "adversarial":
            per[pm]["adv_completion"].append(comp); per[pm]["adv_efficiency"].append(eff); per[pm]["adv_safety"].append(saf)
        if dom == "safety":
            per[pm]["safety_domain_completion"].append(comp)
    out["metrics"] = {pm: {k: mean(v) for k, v in d.items()} for pm, d in sorted(per.items())}
    out["not_completed_all_files"] = {pm: [ncomp[pm], nall[pm]] for pm in sorted(nall)}
    # ---- H3 timestamps per agent_dir
    ts = defaultdict(list)
    for lab, g, _, r in runs:
        for s in (r.get("trace") or {}).get("steps") or ():
            for c in s.get("tool_calls") or ():
                if isinstance(c.get("timestamp"), str):
                    ts[g[0]].append(c["timestamp"])
    out["ts_by_agent_dir"] = {k: {"n": len(v), "min": min(v), "max": max(v)} for k, v in sorted(ts.items())}
    # ---- H4 seeded RNG (in scope)
    first = defaultdict(dict)
    for lab, g, _, r in insc:
        steps = (r.get("trace") or {}).get("steps") or ()
        res = [x for s in steps for x in (s.get("tool_results") or ())]
        if not res:
            continue
        f = res[0]
        rs = f.get("result")
        err = isinstance(rs, str) and rs.startswith("Error:")
        p = f.get("injected_payload") or ""
        first[(g[2], g[3], g[4], g[5])][g[1]] = (f.get("injected_failure") or None, err,
                                                 hashlib.sha256(p.encode()).hexdigest()[:12] if p else None)
    comp_cells = [v for v in first.values() if len(v) >= 2]
    agree_f = sum(1 for v in comp_cells if len({x[0] for x in v.values()}) == 1)
    pc = [{k: x for k, x in v.items() if x[0] is None and not x[1]} for v in comp_cells]
    pc = [v for v in pc if len(v) >= 2]
    agree_p = sum(1 for v in pc if len({x[2] for x in v.values()}) == 1)
    out["H4"] = {"comparable_cells": len(comp_cells), "failure_agree": agree_f, "payload_cells": len(pc), "payload_agree": agree_p}
    # ---- H6 CNA
    old = new = n6 = 0
    for lab, g, _, r in insc:
        sc = r.get("scores") or {}
        comp = sc.get("completion"); cna = sc.get("cost_normalized_accuracy")
        cost = (sc.get("cost") or {}).get("cost_usd") if isinstance(sc.get("cost"), dict) else None
        if not isinstance(comp, (int, float)) or comp <= 0 or not isinstance(cna, (int, float)) or not isinstance(cost, (int, float)):
            continue
        n6 += 1
        old += abs(cna - round(comp / max(cost, 1e-4), 4)) <= 1e-4
        new += abs(cna - round(comp * math.exp(-0.105 * cost), 4)) <= 1e-4
    out["H6"] = {"n": n6, "old_formula": old, "exp_formula": new}
    # ---- H7 / H11 safety default and payloads
    h7 = Counter(); pay = Counter(); suffix = 0; npay = 0; nonadv = 0; inj_eq = 0; inj_n = 0; runs_pay = 0
    for lab, g, _, r in insc:
        cond = g[2]
        res = [x for s in (r.get("trace") or {}).get("steps") or () for x in (s.get("tool_results") or ())]
        ps = [x.get("injected_payload") for x in res if x.get("injected_payload")]
        saf = ((r.get("scores") or {}).get("safety") or {})
        for x in res:
            p = x.get("injected_payload")
            if p:
                npay += 1; pay[hashlib.sha256(p.encode()).hexdigest()[:12]] += 1
                rs = x.get("result")
                suffix += isinstance(rs, str) and rs.endswith("\n\n" + p)
                nonadv += cond != "adversarial"
        runs_pay += bool(ps)
        if "injections_present" in saf:
            inj_n += 1; inj_eq += saf.get("injections_present") == len(ps)
        if cond != "adversarial" or not ps:
            h7["default_runs"] += 1
            h7["default_safety_1"] += saf.get("overall") == 1.0
    out["H7"] = dict(h7)
    out["H11"] = {"payload_results": npay, "runs_with_payload": runs_pay, "distinct_payloads": len(pay),
                  "ends_with_sep_payload": suffix, "non_adversarial": nonadv, "injections_present_eq": [inj_eq, inj_n],
                  "per_payload_results": dict(sorted(pay.items()))}
    # ---- H8 degenerate
    h8 = Counter()
    for lab, g, _, r in insc:
        tr = r.get("trace") or {}
        e = tr.get("error")
        empty = not (tr.get("steps") or ())
        h8["empty"] += empty
        h8["empty_with_error"] += empty and bool(e)
        if e:
            es = str(e)
            h8["err"] += 1
            h8["err:loop_stuck" if "Loop stuck" in es else "err:timeout" if "imeout" in es else "err:other"] += 1
    out["H8"] = dict(h8)
    # ---- H12 account paths (in scope): tool name and pointer classes, names by digest only
    h12 = Counter(); names = defaultdict(set); runs12 = defaultdict(set)
    for lab, g, _, r in insc:
        for s in (r.get("trace") or {}).get("steps") or ():
            for x in s.get("tool_results") or ():
                for ptr, v in strings(x.get("result"), "/result"):
                    for m in ACCT.finditer(v):
                        if m.group(2) in GENERIC:
                            continue
                        k = f"{m.group(1).strip('/')}|{x.get('tool_name')}|{re.sub(r'/[0-9]+', '/*', ptr)}"
                        h12[k] += 1; names[m.group(1)].add(hashlib.sha256(m.group(2).encode()).hexdigest()[:8]); runs12[k].add(lab)
        for ptr, v in strings({k: r.get(k) for k in r if k != "trace"}):
            if ACCT.search(v):
                h12["identity_or_header:" + ptr] += 1
    out["H12"] = {"by_class": {k: {"strings": v, "runs": len(runs12[k])} for k, v in sorted(h12.items())},
                  "distinct_names": {k: len(v) for k, v in names.items()}}
    # ---- H14 version-like keys
    kc = Counter()
    for lab, g, _, r in runs:
        for k in set(keys({kk: vv for kk, vv in r.items() if kk != "trace"})):
            if H14.search(k.rsplit("/", 1)[-1]):
                kc[re.sub(r"/[0-9]+", "/*", k)] += 1
    out["H14_version_like_keys"] = dict(kc)
    out["top_level_keys"] = dict(Counter(k for _, _, _, r in runs for k in r))
    OUT.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
