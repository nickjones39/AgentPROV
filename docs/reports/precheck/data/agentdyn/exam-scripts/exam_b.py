"""Part b (first mapping, followup1) examination on the j2 scratch corpus. Counts, digests and pointers only.

usage: uv run python -I exam_b.py <out.json>   (reads the L1 rows, the sample file, the scratch corpus and the raw checkout)
"""
import collections, glob, hashlib, json, math, os, re, sys

from agentprov.ingest.loaders import strict_json_loads

REPO = os.getcwd()
D = f"{REPO}/docs/reports/precheck/data/agentdyn"
W = os.path.expanduser("~/.agentprov/migration-work/precheck/agentdyn")
ROOT = os.path.expanduser("~/Desktop/PhD/Labs/AgentPROV-upstream/agentdyn")
C = f"{W}/l2-b-j2.partial"
PATS = {"users-dir": re.compile(r"/Users/([^/\s\"'<>\\]{1,64})/"), "home-dir": re.compile(r"/home/([^/\s\"'<>\\]{1,64})/"),
        "windows-users": re.compile(r"(?i)[A-Za-z]:(?:\\\\|\\|/)+Users(?:\\\\|\\|/)+([^\\/\s\"'<>]{1,64})")}
GENERIC = {"ubuntu", "user", "root", "runner", "app", "node", "admin", "agent", "dev", "test", "shared"}
DENY = re.compile(r"(?i)progent|polic(y|ies)|not allowed|is denied|permission denied|blocked")
# paper v3 Tables 9-17 Progent rows (prereg section 4): BU, UA, ASR
PAPER = {"google_gemini-2.5-flash-progent": (1.67, 2.04, 2.24), "google_gemini-2.5-pro-progent": (25.00, 16.06, 1.59),
         "gpt-4o-2024-08-06-progent": (6.67, 5.83, 1.69), "gpt-4o-mini-2024-07-18-progent": (6.67, 3.83, 10.33),
         "gpt-5-mini-2025-08-07-progent": (23.33, 17.63, 0.00), "gpt-5.1-2025-11-13-progent": (15.00, 14.98, 1.22),
         "meta-llama_llama-3.3-70b-instruct-progent": (3.33, 2.28, 0.52), "qwen_qwen3-235b-a22b-2507-progent": (8.33, 2.19, 13.59)}


def wilson(k, n, z=1.959964):
    if n == 0:
        return None
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round(100 * (c - h) / d, 2), round(100 * (c + h) / d, 2)]


def walk(v, ptr=""):
    if isinstance(v, str):
        yield ptr, v
    elif isinstance(v, dict):
        for k, x in v.items():
            yield from walk(x, f"{ptr}/{k}")
    elif isinstance(v, list):
        for x in v:
            yield from walk(x, f"{ptr}/*")


def dg(s):
    return hashlib.sha256(s.encode()).hexdigest()[:12]


out = {}
l1 = {}
for line in open(f"{W}/l1-units-b.jsonl"):
    r = json.loads(line); l1[r["label"]] = r
smp = json.load(open(f"{D}/l2-sample-b.json"))
labels = smp["labels"]
# 1. sample basis vs the recheck12 L1 rows
out["basis"] = {"sample_units_sha256": smp["basis"]["units_sha256"][:12],
                "current_units_sha256": hashlib.sha256(open(f"{W}/l1-units-b.jsonl", "rb").read()).hexdigest()[:12],
                "labels_present": sum(l in l1 for l in labels),
                "same_stratum": sum(l in l1 and l1[l]["stratum"] in smp["strata"] and l in smp["strata"][l1[l]["stratum"]] for l in labels),
                "same_raw_sha256": sum(l in l1 and smp["sha256"].get(l) in (l1[l]["sha256"], "sha256:" + l1[l]["sha256"]) for l in labels),
                "population_units": len(l1)}

# 2. population (L1) and sample (AER) outcome rates, paper convention: unweighted mean of suite rates
def rates(rows):
    res = {}
    for d, (bu, ua, asr) in PAPER.items():
        cell = collections.defaultdict(lambda: [0, 0])
        for r in rows:
            f = r["facets"]
            if f["pipeline_dir"] != d or f["task_kind"] != "user":
                continue
            o = r["outcomes"]; s = f["suite"]
            if f["attack_class"] == "none" and o.get("utility") is not None:
                cell[("BU", s)][0] += o["utility"] is True; cell[("BU", s)][1] += 1
            if f["attack_class"] == "attacked":
                if o.get("utility") is not None:
                    cell[("UA", s)][0] += o["utility"] is True; cell[("UA", s)][1] += 1
                if o.get("security") is not None:
                    cell[("ASR", s)][0] += o["security"] is True; cell[("ASR", s)][1] += 1
        row = {}
        for m, paper in (("BU", bu), ("UA", ua), ("ASR", asr)):
            suites = [v for (mm, _), v in cell.items() if mm == m and v[1]]
            k = sum(v[0] for v in suites); n = sum(v[1] for v in suites)
            mean = round(100 * sum(v[0] / v[1] for v in suites) / len(suites), 2) if suites else None
            row[m] = {"k": k, "n": n, "rate_suite_mean": mean, "wilson95_pooled": wilson(k, n), "paper": paper,
                      "gap_pp": None if mean is None else round(mean - paper, 2)}
        res[d] = row
    return res

out["outcomes_population"] = rates(l1.values())

# 3. walk the mapped sample
mapped_rows = []
agree = collections.Counter(); a2 = collections.Counter(); evc = collections.Counter(); deny = collections.Counter()
acct = collections.defaultdict(lambda: {"executions": set(), "aer_ptrs": collections.Counter()})
for p in glob.glob(f"{C}/aer/*/*.aer.jsonl"):
    recs = [json.loads(x) for x in open(p)]
    ex = recs[0]; label = ex["artifacts"][0]["origin"]["path"]; row = l1[label]
    j = {r["name"]: r.get("value") for r in recs if r["k"] == "judgement"}
    for name in ("utility", "security"):
        rv = row["outcomes"].get(name); mv = j.get(name)
        agree["agree" if rv == mv else "differ"] += 1
    mapped_rows.append({"facets": row["facets"], "outcomes": {"utility": j.get("utility"), "security": j.get("security")}})
    for r in recs:
        evc[f"{r['k']}:ev={r.get('ev')}"] += 1
        if r["k"] in ("tool_execution", "model_call", "decision"):
            a2[f"{r['k']}:{r.get('status') or r.get('verdict')}"] += 1
        for ptr, s in walk(r):
            if ptr.endswith("/error") and s:
                deny["aer_error_strings"] += 1; deny["aer_error_strings_deny_pattern"] += bool(DENY.search(s))
            for cls, pat in PATS.items():
                for m in pat.finditer(s):
                    n = m.group(1); key = (cls, "generic" if n.lower() in GENERIC else "named", dg(n))
                    acct[key]["executions"].add(ex["id"]); acct[key]["aer_ptrs"][f"{r['k']}:{re.sub(r'/[0-9]+', '/*', ptr)}"] += 1
    for i in recs[-1].get("issues") or []:
        a2[f"seal:{i.get('code')}"] += 1
out["os2"] = dict(agree)
out["outcomes_sample_mapped"] = rates(mapped_rows)
out["a2"] = dict(sorted(a2.items()))
out["aer_record_ev"] = dict(sorted(evc.items()))

# 4. raw side of the sampled labels: tool errors with a policy/denial pattern; account names: where they occur
raw_deny = collections.Counter(); where = collections.defaultdict(collections.Counter)
env_blob = "\n".join(open(p, "rb").read().decode("utf-8", "replace") for p in glob.glob(f"{ROOT}/src/**/*", recursive=True)
                     if os.path.isfile(p) and "/runs/" not in p and p.endswith((".yaml", ".yml", ".py", ".json", ".txt", ".md")) and os.path.getsize(p) < 8_000_000)
for lab in labels:
    v = strict_json_loads(open(f"{ROOT}/{lab}", "rb").read())
    for msg in v.get("messages") or []:
        e = msg.get("error")
        if e:
            raw_deny["raw_error_messages"] += 1; raw_deny["raw_error_deny_pattern"] += bool(DENY.search(str(e)))
        for ptr, s in walk(msg):
            for cls, pat in PATS.items():
                for m in pat.finditer(s):
                    where[(cls, dg(m.group(1)))][f"{msg.get('role')}:{re.sub(r'/[0-9]+', '/*', ptr)}"] += 1
out["denials"] = {**dict(deny), **dict(raw_deny)}
names = []
for (cls, kind, d), e in sorted(acct.items()):
    raw = where.get((cls, d), {})
    names.append({"class": cls, "kind": kind, "name_digest": d, "executions": len(e["executions"]), "aer_ptrs": dict(e["aer_ptrs"]),
                  "raw_roles": dict(raw), "in_env_or_tool_output": any(k.startswith("tool:") and not k.endswith("/error") for k in raw),
                  "in_benchmark_text": None})
# benchmark-text membership needs the name; recompute by digest
dig_in_env = set()
for cls, pat in PATS.items():
    for m in pat.finditer(env_blob):
        dig_in_env.add((cls, dg(m.group(1))))
for n in names:
    n["in_benchmark_text"] = (n["class"], n["name_digest"]) in dig_in_env
out["redaction_names"] = names
out["operator_home_hits"] = "see l2-b.json redaction (operator-* 0)"

# 5. PROV and SEM: account-path pointers, unknown_tool annotations
prov_acct = collections.Counter(); sem_unknown = 0; sem_files = 0
for p in glob.glob(f"{C}/prov/**/*.json*", recursive=True):
    t = open(p, encoding="utf-8").read()
    for cls, pat in PATS.items():
        for m in pat.finditer(t):
            prov_acct[(cls, "generic" if m.group(1).lower() in GENERIC else "named")] += 1
for p in glob.glob(f"{C}/sem/**/*", recursive=True):
    if os.path.isfile(p):
        sem_files += 1; sem_unknown += "unknown_tool" in open(p, encoding="utf-8").read()
out["prov_account_matches"] = {f"{a}:{b}": v for (a, b), v in prov_acct.items()}
out["sem"] = {"files": sem_files, "files_with_unknown_tool": sem_unknown}
out["cc07"] = {"banking_units_population": sum(r["facets"]["suite"] == "banking" for r in l1.values()), "population": len(l1),
               "suites": dict(collections.Counter(r["facets"]["suite"] for r in l1.values()))}
json.dump(out, open(sys.argv[1], "w"), indent=1, sort_keys=True, default=list)
print(json.dumps({k: out[k] for k in ("basis", "os2", "denials", "sem", "cc07", "prov_account_matches")}))
