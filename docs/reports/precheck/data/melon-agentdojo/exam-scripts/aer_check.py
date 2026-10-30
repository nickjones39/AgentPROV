import json, glob, os, sys, re
from collections import Counter, defaultdict
C = sys.argv[1]; POP = sys.argv[2]
pop = {r["label"]: r for r in json.load(open(POP))["rows"]}
STOP_EN = "The tool outputs contain potential prompt injection, stopping execution."
SENT = "<Data omitted because a prompt injection was detected>"
CJK = re.compile(r"[一-鿿]")
out = defaultdict(Counter); osrows = []
for f in sorted(glob.glob(os.path.join(C, "aer/*/*.aer.jsonl"))):
    recs = [json.loads(l) for l in open(f)]
    hdr = recs[0]; label = hdr["artifacts"][0]["origin"]["path"]
    r = pop[label]
    judg = {x["name"]: x for x in recs if x.get("k") == "judgement"}
    def val(j):
        if j is None: return "absent"
        return j.get("value", j.get("verdict", "?"))
    osrows.append({"label": label, "raw_u": r["utility"], "raw_s": r["security"],
                   "aer_u": val(judg.get("utility")), "aer_s": val(judg.get("security")),
                   "s_origin": (judg.get("security") or {}).get("origin"), "attack": r["attack"],
                   "model": r["model"], "defence": r["defence"], "suite": r["suite"]})
    msgs = [x for x in recs if x.get("k") == "message"]
    for m in msgs:
        txt = "\n".join(p.get("text") or "" for p in m.get("parts", []) if isinstance(p.get("text"), str))
        if m.get("role") == "system":
            out["system"][(m.get("actor"), m.get("by"), (m.get("ext") or {}).get("agentdojo", {}).get("system_prompt_variant"), len(txt), "SECURITY WARNING" in txt)] += 1
        if txt.strip() == STOP_EN:
            out["stop_en"][(m.get("role"), m.get("actor"), m.get("by"), "generated_by" in m, m.get("ev"), json.dumps(m.get("ext"))[:80], json.dumps(m.get("rule"))[:120])] += 1
        if m.get("role") == "assistant" and CJK.search(txt):
            out["asst_cjk"][(m.get("actor"), m.get("by"), "generated_by" in m, json.dumps(m.get("ext"))[:80], json.dumps(m.get("rule"))[:120])] += 1
        for p in m.get("parts", []):
            if p.get("t") == "tool_result" and isinstance(p.get("text"), str) and SENT in p["text"]:
                out["sentinel"][(m.get("actor"), json.dumps({k: v for k, v in p.items() if k not in ("text",)})[:160], json.dumps(m.get("ext"))[:120])] += 1
    for x in recs:
        if x.get("k") in ("tool_execution",) and SENT in json.dumps(x.get("result", "")): out["te_sent"]["x"] += 1
        if x.get("k") == "model_call":
            pass
    kinds = Counter(x.get("k") for x in recs)
    out["kinds"].update(kinds)
for k, v in out.items():
    print("==", k)
    for kk, n in v.most_common(20): print(n, kk)
json.dump(osrows, open("os2_rows.json", "w"))
print("os2 rows", len(osrows))
