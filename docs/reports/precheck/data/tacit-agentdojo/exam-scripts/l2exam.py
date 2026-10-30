import collections as co, glob, json, os, re, sys
W = os.path.expanduser("~/.agentprov/migration-work/precheck/tacit-agentdojo")
corp = f"{W}/{sys.argv[1]}"
rows = {json.loads(l)["label"]: json.loads(l) for l in open(f"{W}/l1-units-head.jsonl")}
flags = json.load(open(f"{W}/exam/census-labels.json"))
ex = [json.loads(l) for l in open(f"{corp}/executions.jsonl")]
R = co.defaultdict(co.Counter); os2 = []
for e in ex:
    recs = [json.loads(l) for l in open(f"{corp}/{e['paths']['aer']}")]
    head = recs[0]; label = head["artifacts"][0]["origin"]["path"]; raw = rows[label]["outcomes"]
    f = flags.get(label, {})
    for k, v in f.items():
        if v: R["sampled_label_flags"][k] += 1
    m = {r["name"]: r.get("value") for r in recs if r.get("k") == "judgement"}
    for name in ("utility", "security"):
        R["os2"]["same" if m.get(name, "absent") == raw[name] else "differ"] += 1
        if m.get(name, "absent") != raw[name]: os2.append((label, name, m.get(name, "absent"), raw[name]))
    for r in recs:
        R["k"][r.get("k")] += 1; R["ev"][f"{r.get('k')}:{r.get('ev')}"] += 1
        for rule in r.get("rule", []) if isinstance(r.get("rule"), list) else []:
            base = rule.split("#")[0]; R["rules"][base] += 1
        if r.get("k") == "actor" and r.get("model"): R["model"][json.dumps(r["model"], sort_keys=True)] += 1
        if r.get("k") == "message" and isinstance(r.get("ext"), dict) and "local_model_tag_count" in json.dumps(r["ext"]): R["ext_tag_count"]["msgs"] += 1
        if r.get("k") == "execution":
            R["task"][json.dumps({k: r.get("task", {}).get(k) for k in ("benchmark", "suite", "defense_id", "attack_id", "attack")}, sort_keys=True)] += 1
    R["issues"].update(e["issues"])
    txt = open(f"{corp}/{e['paths']['aer']}").read() + open(f"{corp}/{e['paths']['sem']['agentdojo.suites@2']}").read() + open(f"{corp}/{e['paths']['prov']['agentprov-prov/0.1']['json']}").read()
    R["redaction"]["/home/ or /Users/ hits"] += len(re.findall(r"/home/[^/\s\"]+/|/Users/[^/\s\"]+/", txt))
    for l in open(f"{corp}/{e['paths']['sem']['agentdojo.suites@2']}"):
        s = json.loads(l); R["sem_kind"][s.get("k") or s.get("kind") or s.get("type") or "?"] += 1
        for kk in ("label", "name", "annotation", "tag"):
            if isinstance(s.get(kk), str): R["sem_" + kk][s[kk]] += 1
out = {k: dict(v) for k, v in R.items()}; out["os2_differ"] = os2; out["n"] = len(ex)
d_rules = [r for r in out["rules"] if not r.endswith("_unverified@1") and not r.split("@")[0].endswith("_unverified")]
out["rules_without_unverified_suffix"] = sorted(d_rules)
print(json.dumps(out, indent=1, sort_keys=True))
