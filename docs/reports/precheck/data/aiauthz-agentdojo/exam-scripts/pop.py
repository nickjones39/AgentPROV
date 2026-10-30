"""Population census of aiauthz-agentdojo (174 logs) from pinned blobs through agentprov.ingest; counts and labels only.

H1 per-cell vs results_*.json, H2 totals, H3/H4 denials, H5/H6 null-final, H7 run order, H8 pipeline_name and served ids,
H9 first-assistant identity, H12/CC-07 #181 (IT0 subject), CC-07 #161 scope, L1-10 hit classification.
usage: uv run python -I pop.py <l1-units.jsonl> <out.json>
"""
import collections, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rawread import tree, Reader

ATTACKER = "US133000000121212121212"
SERVED = (b"claude-5-fable-20260609", b"gemini-3-flash-preview-20251217")
RES = {"anthropic_claude-fable-5": "experiments/agentdojo/results_claude-fable-5.json",
       "google_gemini-3-flash-preview": "experiments/agentdojo/results_gemini-3-flash.json"}
ORDER = ["no_defense", "no_defense_clean", "spotlighting", "spotlighting_clean", "aiauthz", "aiauthz_clean"]
l1 = {r["label"]: r for r in map(json.loads, open(os.path.expanduser(sys.argv[1])))}
t = tree(); r = Reader()
out = collections.defaultdict(dict)
C = collections.Counter
h1 = C(); tot = C(); den = collections.defaultdict(C); den_tools = C(); nf = C(); h6 = C(); h8 = C(); h12 = []
win = {}; first = {}; prepass_vs_attacked = collections.defaultdict(list)
res = {m: {x["condition"]: x for x in r.json(t[p])["results"]} for m, p in RES.items()}
for lab in sorted(p for p in t if p.startswith("experiments/agentdojo/runs/")):
    raw = r.read(t[lab]); d = r.json(t[lab])
    parts = lab.split("/"); model, cond, pipe = parts[3], parts[4], parts[5]
    task, attack, inj = parts[7], parts[8], parts[9][:-5]
    kind = "clean" if cond.endswith("_clean") else ("prepass" if task.startswith("injection_task") else "attacked")
    base = cond.replace("_clean", "")
    u, s = d["utility"], d["security"]
    flags = l1[lab]["flags"]; is_nf = "null_final" in flags
    # H1
    rc = res[model][base]
    if kind == "attacked":
        key = f"{task}|{inj}"
        h1["attacked_cells"] += 1
        h1["attacked_util_mismatch"] += rc["utility_under_attack_results"][key] != u
        h1["attacked_sec_mismatch"] += rc["security_results"][key] != s
        tot[f"attacked_sec_true"] += s; tot["attacked_util_true"] += u
        tot[f"asr|{model}|{base}"] += s; tot[f"uua|{model}|{base}"] += u
    elif kind == "clean":
        h1["clean_cells"] += 1
        h1["clean_util_mismatch"] += rc["clean_utility_results"][f"{task}|"] != u
        tot["clean_util_true"] += u; tot[f"cu|{model}|{base}"] += u
    else:
        tot["prepass_util_true"] += u
    tot["security_true_all"] += s; tot["utility_true_all"] += u
    # denials
    ms = d["messages"]
    nden = 0
    for m in ms:
        if m.get("role") == "tool" and isinstance(m.get("error"), str) and m["error"].startswith("Blocked by aiAuthZ policy: "):
            nden += 1; den[f"{model}/{cond}"][kind] += 1; den_tools[m["tool_call"]["function"]] += 1
    if base == "aiauthz" and kind != "clean" and nden:
        prepass_vs_attacked[model].append([kind, task, inj, nden])
    # H5 / H6
    if is_nf:
        nf[f"{model}|{kind}"] += 1
        h6["nf_utility_true"] += u
        h6["nf_attacked_security_true"] += (kind == "attacked" and s)
    if kind == "attacked" and s:
        calls = [c for m in ms if m.get("role") == "assistant" for c in (m.get("tool_calls") or [])]
        att = [c for c in calls if c["function"] == "send_money" and (c.get("args") or {}).get("recipient") == ATTACKER]
        sched = [c for c in calls if ATTACKER in json.dumps(c.get("args"))]
        executed = 0
        for m in ms:
            if m.get("role") == "tool" and ATTACKER in json.dumps(m.get("tool_call", {}).get("args")) and not m.get("error"):
                executed += 1
        subj = [str((c.get("args") or {}).get("subject", "")) for c in att]
        h12.append(dict(model=model, cond=base, cell=f"{task}|{inj}", null_final=is_nf, attacker_send_money=len(att),
                        attacker_any_call=len(sched), attacker_calls_executed=executed,
                        it0_subject_has_spotify=(any("spotify" in x.lower() for x in subj) if inj == "injection_task_0" else None)))
    # H7
    ts = d["evaluation_timestamp"]
    w = win.setdefault(f"{model}/{cond}", {"min": ts, "max": ts, "prepass_max": None, "attacked_min": None})
    w["min"] = min(w["min"], ts); w["max"] = max(w["max"], ts)
    if kind == "prepass": w["prepass_max"] = max(w["prepass_max"] or ts, ts)
    if kind == "attacked": w["attacked_min"] = min(w["attacked_min"] or ts, ts)
    # H8
    h8["pipeline_eq_dir"] += d["pipeline_name"] == pipe
    h8["served_id_in_bytes"] += any(x in raw for x in SERVED)
    # H9
    fa = next((m for m in ms if m.get("role") == "assistant"), None)
    if fa is not None and base in ("no_defense", "aiauthz"):
        sig = json.dumps([fa.get("content"), [(c["function"], c.get("args")) for c in (fa.get("tool_calls") or [])]], sort_keys=True)
        first.setdefault((model, kind, task, inj), {})[base] = sig
# H7 order
h7 = {}
for model in RES:
    seq = [win[f"{model}/{c}"] for c in ORDER]
    h7[model] = dict(in_order=all(seq[i]["max"] <= seq[i + 1]["min"] for i in range(5)),
                     prepass_before_attacked=all(win[f"{model}/{c}"]["prepass_max"] <= win[f"{model}/{c}"]["attacked_min"] for c in ("no_defense", "spotlighting", "aiauthz")),
                     first=seq[0]["min"][:19], last=seq[-1]["max"][:19])
glob = dict(min=min(w["min"] for w in win.values())[:19], max=max(w["max"] for w in win.values())[:19])
h9 = C()
for (model, kind, task, inj), v in first.items():
    if len(v) == 2:
        h9[f"{model}|{'clean' if kind=='clean' else kind}|pairs"] += 1
        h9[f"{model}|{'clean' if kind=='clean' else kind}|identical"] += v["no_defense"] == v["aiauthz"]
# CC-07 #161: banking user_task_5 in grid?
ut5 = sum(1 for lab in l1 if "/user_task_5/" in lab)
# L1-10 hit classification (no value printed)
SECRET = re.compile(r"(?i)(?:api[_-]?key|secret|token|passw(?:or)?d)[\"']?\s{0,3}[:=]\s{0,3}[\"']?[A-Za-z0-9_\-/+=.]{16,}")  # = tools/precheck/l1_scan.py SECRET_PATTERNS generic-credential-assignment
E = {}
for p, oid in t.items():
    if p.startswith("experiments/agentdojo/runs/") or p.endswith((".json", ".jsonl")):
        continue
    try: txt = r.read(oid).decode("utf-8", "replace")
    except AssertionError: continue
    for m in SECRET.finditer(txt):
        lhs = re.match(r"(?i)[\"']?(api[_-]?key|secret|token|passw(?:or)?d)", m.group(0)).group(1).lower()
        line = txt[txt.rfind("\n", 0, m.start()) + 1: txt.find("\n", m.end())]
        E.setdefault(p, []).append(dict(lhs_word=lhs, rhs_len=len(m.group(0)), line_has_env_lookup=bool(re.search(r"environ|getenv|\$\{?[A-Z_]+", line)),
                                        line_is_comment_or_doc=line.lstrip().startswith(("#", "//", "-", "*", ">", "|"))))
outd = dict(h1=dict(h1), totals=dict(tot), denials={k: dict(v) for k, v in den.items()}, denial_tools=dict(den_tools),
            aiauthz_denial_logs=prepass_vs_attacked, null_final=dict(nf), h6=dict(h6), successes=h12, h7=h7, window=glob,
            h8=dict(h8), h9=dict(h9), cc07_161_ut5_logs=ut5, l1_10_hits=E, n_logs=sum(1 for p in t if p.startswith("experiments/agentdojo/runs/")))
json.dump(outd, open(os.path.expanduser(sys.argv[2]), "w"), indent=1, sort_keys=True)
print(json.dumps(outd, sort_keys=True, indent=0))
