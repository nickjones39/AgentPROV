# ruff: noqa  (precheck examiner script for ast-survey-agentharm, committed as run; read-only analysis)
"""DL-1 delta: stored corpus vs fresh scratch import, matched by execution id (read-only, counts only).

AER: records matched by (k, id); per normalised pointer: executions and record counts; value transitions only for
whitelisted short label keys (actor, ev, rule ids, versions). SEM: stored @1 vs new @2 file, annotations matched by id.
PROV: per top-level section statement counts, and leaf-multiset differences by normalised path (values never kept).
Index rows: differing keys.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[3])))  # tools/analysis2
from exam2_p9diff import _leaves  # noqa: E402

OLD = Path(sys.argv[1]).expanduser()
NEW = Path(sys.argv[2]).expanduser()
OUT = Path(sys.argv[4])
LABEL_KEYS = {"actor", "ev", "rule", "by", "version", "rules", "role", "kind", "type", "verdict", "transmitted"}


def norm(k: str) -> str:
    if k.isdigit():
        return "*"
    return k


def walk(a, b, path, out, trans, depth=0):
    if a == b:
        return
    if isinstance(a, dict) and isinstance(b, dict) and depth < 10:
        for k in set(a) | set(b):
            p = f"{path}/{norm(k)}"
            if k not in a:
                out.add(p + ":added")
                if isinstance(b[k], (str, int)) and (k in LABEL_KEYS or path.endswith(("/unk", "/evf"))) and len(str(b[k])) < 80:
                    trans[(p, "-", str(b[k]))] += 1
            elif k not in b:
                out.add(p + ":removed")
            else:
                walk(a[k], b[k], p, out, trans, depth + 1)
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b) and depth < 10:
        for x, y in zip(a, b):
            walk(x, y, f"{path}/*", out, trans, depth + 1)
    else:
        out.add(path + ":changed")
        last = path.rsplit("/", 1)[-1]
        if last in LABEL_KEYS or last == "*":
            sa, sb = json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True)
            if len(sa) < 100 and len(sb) < 100 and "/Users/" not in sa + sb and "/home/" not in sa + sb:
                trans[(path, sa, sb)] += 1


def recs(p: Path):
    d = {}
    for i, line in enumerate(p.read_bytes().splitlines()):
        if not line:
            continue
        r = json.loads(line)
        d[(r.get("k"), r.get("id", f"#{i}"))] = r
    return d


def one(pair):
    o, n = pair
    res = {"aer": set(), "sem": set(), "prov": set(), "trans": Counter(), "prov_sec": Counter(), "prov_leaf": Counter(),
           "rec_counts": Counter(), "index": set(), "bytes_equal": {}}
    for key in set(o) | set(n):
        if key in ("paths", "digests"):
            continue
        if o.get(key) != n.get(key):
            res["index"].add(f"/{key}")
    for k in ("aer", "validation"):
        res["bytes_equal"][k] = o["digests"].get(k) == n["digests"].get(k)
    ao, an = recs(OLD / o["paths"]["aer"]), recs(NEW / n["paths"]["aer"])
    for key in set(ao) | set(an):
        kind = key[0]
        if key not in ao:
            res["aer"].add(f"{kind}:record_added")
            res["rec_counts"][f"{kind}:added"] += 1
            continue
        if key not in an:
            res["aer"].add(f"{kind}:record_removed")
            res["rec_counts"][f"{kind}:removed"] += 1
            continue
        s = set()
        walk(ao[key], an[key], kind, s, res["trans"])
        if s:
            res["rec_counts"][f"{kind}:changed"] += 1
        res["aer"] |= s
    so = list((o["paths"].get("sem") or {}).values())
    sn = list((n["paths"].get("sem") or {}).values())
    if so and sn:
        ro, rn = recs(OLD / so[0]), recs(NEW / sn[0])
        for key in set(ro) | set(rn):
            if key not in ro:
                res["sem"].add(f"{key[0]}:added")
            elif key not in rn:
                res["sem"].add(f"{key[0]}:removed")
            else:
                s = set()
                walk(ro[key], rn[key], f"{key[0]}:{rn[key].get('type', '')}", s, res["trans"])
                res["sem"] |= s
    po = OLD / o["paths"]["prov"]["agentprov-prov/0.1"]["json"]
    pn = NEW / n["paths"]["prov"]["agentprov-prov/0.1"]["json"]
    da, db = json.loads(po.read_bytes()), json.loads(pn.read_bytes())

    def sec_counts(doc, tag):
        c = Counter()
        for sec, v in doc.items():
            if sec == "prefix":
                continue
            if sec == "bundle":
                for bk, bv in v.items():
                    btag = re.sub(r"\.[a-z2-7]{16,}$", "", bk)
                    btag = re.sub(r"^xd:bundle\.", "", btag)
                    for s2, v2 in bv.items():
                        if s2 != "prefix":
                            c[f"bundle:{btag}/{s2}"] += len(v2)
            else:
                c[f"top/{sec}"] += len(v)
        return c

    ca, cb = sec_counts(da, "o"), sec_counts(db, "n")
    for k in set(ca) | set(cb):
        if ca[k] != cb[k]:
            res["prov_sec"][f"{k}:{cb[k] - ca[k]:+d}"] += 1
            res["prov"].add(f"count:{k}")
    la, lb = _leaves(da), _leaves(db)
    if la != lb:
        for (path, _v), cnt in (la - lb).items():
            res["prov_leaf"][f"-{path}"] += cnt
        for (path, _v), cnt in (lb - la).items():
            res["prov_leaf"][f"+{path}"] += cnt
        res["prov"].add("leaves_differ")
    return res


def main():
    oi = {json.loads(x)["ex"]: json.loads(x) for x in (OLD / "executions.jsonl").read_bytes().splitlines() if x}
    ni = {json.loads(x)["ex"]: json.loads(x) for x in (NEW / "executions.jsonl").read_bytes().splitlines() if x}
    common = sorted(set(oi) & set(ni))
    agg = {k: Counter() for k in ("aer", "sem", "prov", "index", "prov_sec")}
    trans, leaf, rc, beq = Counter(), Counter(), Counter(), Counter()
    with Pool(2) as pool:
        for r in pool.imap_unordered(one, [(oi[e], ni[e]) for e in common], chunksize=16):
            for k in ("aer", "sem", "prov", "index"):
                for s in r[k]:
                    agg[k][s] += 1
            for s, c in r["prov_sec"].items():
                agg["prov_sec"][s] += c
            trans.update(r["trans"])
            leaf.update(r["prov_leaf"])
            rc.update(r["rec_counts"])
            for k, v in r["bytes_equal"].items():
                beq[f"{k}={v}"] += 1
    rep = {"old": OLD.name, "new": NEW.name, "common": len(common), "only_old": len(set(oi) - set(ni)),
           "only_new": len(set(ni) - set(oi)), "digest_equal": dict(beq),
           "executions_by_pointer": {k: dict(sorted(v.items())) for k, v in agg.items()},
           "record_counts": dict(sorted(rc.items())),
           "label_transitions": {f"{p} | {a} -> {b}": c for (p, a, b), c in sorted(trans.items())},
           "prov_leaf_paths": dict(sorted(leaf.items()))}
    OUT.write_text(json.dumps(rep, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
