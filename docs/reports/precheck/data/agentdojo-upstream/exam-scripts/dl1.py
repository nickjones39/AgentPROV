"""agentdojo-upstream DL-1: stored p10 corpus vs fresh scratch import on the same execution ids.

Counts, normalised pointers and rule ids only (no content). Usage: dl1.py PART OUT.json
"""
import json, re, sys, tomllib
from collections import Counter, defaultdict
from pathlib import Path

HOME = Path.home() / ".agentprov"
part = sys.argv[1]
out = Path(sys.argv[2])
OLD = HOME / "corpora" / f"agentdojo-upstream-{part}-p10.partial"
NEW = HOME / "migration-work/precheck/agentdojo-upstream" / f"l2-{part}-j2.partial"

cat = tomllib.loads(Path("src/agentprov/adapters/agentdojo/rules/agentdojo.rules.toml").read_text())
RULES = {r["id"]: r for r in cat["rule"]}
TWINS = {i for i in RULES if i.endswith("_unverified") and i[: -len("_unverified")] in RULES}
C6 = {i for i in TWINS if not RULES[i[: -len("_unverified")]].get("code")}
NATIVE_I_UNVERIFIED = sorted(i for i in RULES if i.endswith("_unverified") and i not in TWINS)

new_idx = {r["ex"]: r for r in (json.loads(x) for x in (NEW / "executions.jsonl").read_bytes().splitlines() if x)}
old_idx = {}
with open(OLD / "executions.jsonl", "rb") as f:
    for x in f:
        if x.strip():
            r = json.loads(x)
            if r["ex"] in new_idx:
                old_idx[r["ex"]] = r


def npath(path):
    return re.sub(r"/\d+(?=/|$)", "/*", path)


LABEL_KEYS = {"ev", "rule", "version", "origin", "status", "completeness", "unit", "by", "kind", "name", "variant", "b",
              "benchmark", "role", "actor", "subject", "agentdojo", "aer"}


def leafdiff(a, b, path, out, trans):
    if a == b:
        return
    if isinstance(a, dict) and isinstance(b, dict):
        for k in set(a) | set(b):
            p = f"{path}/{k}"
            if k not in a:
                out.add(npath(p) + ":added")
                v = b[k]
                trans[(npath(p), "added=" + (json.dumps(v) if isinstance(v, (str, int, bool)) and len(str(v)) < 60 else "<" + type(v).__name__ + ">"))] += 1
            elif k not in b:
                out.add(npath(p) + ":removed")
            else:
                leafdiff(a[k], b[k], p, out, trans)
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b) and not all(isinstance(x, str) for x in a + b):
        for i, (x, y) in enumerate(zip(a, b)):
            leafdiff(x, y, f"{path}/{i}", out, trans)
    else:
        np_ = npath(path)
        out.add(np_ + ":changed")
        last = path.rsplit("/", 1)[-1]
        if isinstance(a, list) and isinstance(b, list) and all(isinstance(x, str) for x in a + b):
            for x in sorted(set(a) - set(b)):
                trans[(np_, "-" + x)] += 1
            for x in sorted(set(b) - set(a)):
                trans[(np_, "+" + x)] += 1
        elif last in ("sha256", "records_sha256", "aer_digest"):
            trans[(np_, "<digest changed>")] += 1
        elif last in LABEL_KEYS or "/evf/" in path or path.startswith("/evf"):
            av = a if not isinstance(a, str) or len(a) < 80 else "<str>"
            bv = b if not isinstance(b, str) or len(b) < 80 else "<str>"
            trans[(np_, f"{json.dumps(av)} -> {json.dumps(bv)}")] += 1


def aer_records(p):
    return {(r["k"], r.get("id")): r for r in (json.loads(x) for x in p.read_bytes().splitlines() if x)}


def bclass(name):
    n = name.split(":", 1)[-1]
    m = re.match(r"bundle\.(core|inf|assess)\.?(.*)$", n)
    if not m:
        return "top"
    kind, rest = m.groups()
    rest = re.sub(r"\.[a-z2-7]{16,}$", "", rest)
    return f"{kind}:{rest}" if kind != "core" else "core"


def ev_of(st):
    e = st.get("apv:evidenceClass")
    return e.get("$", "none").replace("apv:", "") if isinstance(e, dict) else "none"


def walk_doc(doc):
    yield "top", doc
    for bn, bd in (doc.get("bundle") or {}).items():
        yield bclass(bn), bd


def prov_profile(doc):
    c = Counter()
    for b, sections in walk_doc(doc):
        for sec, items in sections.items():
            if sec in ("bundle", "prefix") or not isinstance(items, dict):
                continue
            for _k, st in items.items():
                if isinstance(st, dict):
                    rules = st.get("apv:rule")
                    for rl in rules if isinstance(rules, list) else [rules]:
                        c[(b, sec, ev_of(st), str(rl))] += 1
    return c


def prov_attrs(doc):
    out = {}
    for b, sections in walk_doc(doc):
        for sec, items in sections.items():
            if sec in ("bundle", "prefix") or not isinstance(items, dict):
                continue
            for k, st in items.items():
                if isinstance(st, dict) and not k.startswith("_:") and not re.search(r"\.[a-z2-7]{12,}$", k):
                    out[(b, sec, re.sub(r"[0-9a-f]{64}", "<sha>", k))] = st
    return out


S = defaultdict(set)  # signature -> executions
N = Counter()  # signature -> occurrences
twin_ex = {}
aer_bytes_equal = 0
for ex, nr in sorted(new_idx.items()):
    orow = old_idx.get(ex)
    if orow is None:
        continue
    for k in set(nr) | set(orow):
        if k in ("digests", "paths", "stages"):
            continue
        a, b = orow.get(k), nr.get(k)
        if a != b:
            if k == "issues":
                for x in sorted(set(a or []) ^ set(b or [])):
                    sig = ("index", k, ("+" if x in (b or []) else "-") + x); S[sig].add(ex); N[sig] += 1
            else:
                sig = ("index", k, f"{json.dumps(a)[:80]} -> {json.dumps(b)[:80]}"); S[sig].add(ex); N[sig] += 1
    if orow.get("stages") != nr.get("stages"):
        sig = ("index", "stages", "sem profile ref " + ",".join(orow["stages"].get("sem", {})) + " -> " + ",".join(nr["stages"].get("sem", {})))
        S[sig].add(ex); N[sig] += 1
    po_, pn_ = OLD / orow["paths"]["aer"], NEW / nr["paths"]["aer"]
    aer_bytes_equal += po_.read_bytes() == pn_.read_bytes()
    ro, rn = aer_records(po_), aer_records(pn_)
    for key in set(ro) | set(rn):
        if key not in ro:
            sig = ("aer", key[0], "record_added"); S[sig].add(ex); N[sig] += 1; continue
        if key not in rn:
            sig = ("aer", key[0], "record_removed"); S[sig].add(ex); N[sig] += 1; continue
        s, t = set(), Counter()
        leafdiff(ro[key], rn[key], "", s, t)
        for (p, v), n in t.items():
            sig = ("aer", key[0], p, v); S[sig].add(ex); N[sig] += n
        for x in s:
            sig = ("aer_ptr", key[0], x); S[sig].add(ex); N[sig] += 1
    cited = {x.split("@", 1)[0] for r in rn.values() for x in r.get("rule") or []}
    twin_ex[ex] = sorted(cited & TWINS)
    # SEM: header leaf diff + annotation multiset (type, ev, rule, scalar value)
    so = [json.loads(x) for x in (OLD / list(orow["paths"]["sem"].values())[0]).read_bytes().splitlines() if x]
    sn = [json.loads(x) for x in (NEW / list(nr["paths"]["sem"].values())[0]).read_bytes().splitlines() if x]
    ho = next(r for r in so if r.get("k") == "sem"); hn = next(r for r in sn if r.get("k") == "sem")
    s, t = set(), Counter(); leafdiff(ho, hn, "", s, t)
    for x in s:
        sig = ("sem_header", x); S[sig].add(ex); N[sig] += 1
    def ann(rs):
        c = Counter()
        for r in rs:
            if r.get("k") != "sem" and r.get("k") != "seal":
                v = r.get("value")
                c[(r.get("k"), str(r.get("type")), str(r.get("ev")), ",".join(r.get("rule") or []),
                   json.dumps(v) if isinstance(v, (str, bool, int)) or v is None else "<obj>")] += 1
        return c
    co, cn = ann(so), ann(sn)
    for key in set(co) | set(cn):
        d = cn[key] - co[key]
        if d:
            sig = ("sem_ann", "|".join(key), "+" if d > 0 else "-"); S[sig].add(ex); N[sig] += abs(d)
    # PROV
    po = json.loads((OLD / orow["paths"]["prov"]["agentprov-prov/0.1"]["json"]).read_bytes())
    pn = json.loads((NEW / nr["paths"]["prov"]["agentprov-prov/0.1"]["json"]).read_bytes())
    co, cn = prov_profile(po), prov_profile(pn)
    for key in set(co) | set(cn):
        d = cn[key] - co[key]
        if d:
            sig = ("prov_stmt",) + key + ("+" if d > 0 else "-",); S[sig].add(ex); N[sig] += abs(d)
    ao, an_ = prov_attrs(po), prov_attrs(pn)
    for key in set(ao) & set(an_):
        for at in set(ao[key]) ^ set(an_[key]):
            sig = ("prov_attr", key[0], key[1], at, "added" if at in an_[key] else "removed"); S[sig].add(ex); N[sig] += 1
        for at in set(ao[key]) & set(an_[key]):
            if at in ("apv:evidenceClass", "apv:basisRule", "apv:method", "apv:afterEvidenceClass", "apv:origin") and ao[key][at] != an_[key][at]:
                sig = ("prov_attr", key[0], key[1], at, f"{json.dumps(ao[key][at])[:90]} -> {json.dumps(an_[key][at])[:90]}")
                S[sig].add(ex); N[sig] += 1
    for key in set(ao) ^ set(an_):
        sig = ("prov_attr", key[0], key[1], "<statement>", "added" if key in an_ else "removed"); S[sig].add(ex); N[sig] += 1
    def bundles(d):
        return {re.sub(r"\.[a-z2-7]{16,}$", "", b.split(":", 1)[1]) for b in d.get("bundle", {})}
    bo, bn = bundles(po), bundles(pn)
    for b in bo ^ bn:
        sig = ("prov_bundle", b, "added" if b in bn else "removed"); S[sig].add(ex); N[sig] += 1

res = {"part": part, "old": OLD.name, "new": NEW.name, "executions_new": len(new_idx), "matched": len(old_idx),
       "aer_bytes_equal": aer_bytes_equal,
       "signatures": [[list(k), N[k], len(S[k])] for k in sorted(S, key=lambda k: [str(x) for x in k])],
       "twins": {"catalogue_twins": len(TWINS), "c6_twins": sorted(C6), "native_I_rules_named_unverified": NATIVE_I_UNVERIFIED,
                 "executions_citing_non_c6_twin": sum(1 for v in twin_ex.values() if set(v) - C6),
                 "by_twin": dict(sorted(Counter(x for v in twin_ex.values() for x in v).items()))}}
json.dump({"res": res, "twin_ex": twin_ex}, open(out, "w"), indent=1, sort_keys=True)
print(json.dumps({k: res[k] for k in ("matched", "aer_bytes_equal")}), len(res["signatures"]), "signatures")
