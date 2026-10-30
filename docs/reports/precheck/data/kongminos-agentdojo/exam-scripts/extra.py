"""kongminos-agentdojo follow-ups to pop.py: H3 per (suite, IT) tool-sentence coverage and payload exposure (<INFORMATION>
marker in a tool result), call-function sequences of the 4 attacked successes, the 33 empty-final logs (duration, time,
benign twin), H6 per-log tag excess, sample overlap. Counts/labels/function names only.
Usage (repo root): GIT_NO_LAZY_FETCH=1 GIT_ALLOW_PROTOCOL=file uv run python -I <this> POP.json SAMPLE.json OUT.json"""
import json, os, sys, statistics
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kx_lib  # noqa: E402

def text(m):
    c = m.get("content")
    if isinstance(c, str): return c
    return "".join(str(b.get("content") or "") for b in (c or []) if isinstance(b, dict))

pop = json.load(open(sys.argv[1])); samp = json.load(open(sys.argv[2]))
slabels = set(samp["labels"])
E = kx_lib.entries(); R = kx_lib.Reader()
rows = [json.loads(l) for l in open(kx_lib.W / "l1-units-head.jsonl")]
h3 = defaultdict(Counter); dur = defaultdict(list); exposure = Counter(); h6 = Counter(); succ = {}
nf = {r["label"] for r in pop["null_final"]}; nf_rows = []
for u in rows:
    f = u["facets"]; lab = u["label"]; x = R.load(E[lab]); ms = x.get("messages") or []
    arm = "attacked" if f["attack_dir"] != "none" else ("prepass" if f["task_kind"] == "prepass" else "benign")
    calls = [tc.get("function") for m in ms for tc in (m.get("tool_calls") or [])]
    exposed = any("<INFORMATION>" in text(m) for m in ms if m.get("role") == "tool")
    if arm == "attacked":
        pl = " ".join(str(v) for v in (x.get("injections") or {}).values())
        k = f"{f['suite']}|{f['file']}"
        h3[k]["logs"] += 1; h3[k]["tool_sentence"] += "use the tool" in pl.lower(); h3[k]["exposed"] += exposed
        h3[k]["success"] += x.get("security") is True
        exposure[f"{f['suite']}|exposed:{exposed}|zero_calls:{not calls}"] += 1
        exposure[f"success|exposed:{exposed}"] += x.get("security") is True
        if x.get("security") is True:
            succ[lab] = {"functions": calls, "exposed": exposed, "utility": x.get("utility")}
    if lab in nf:
        nf_rows.append({"label": lab, "duration_s": round(x.get("duration") or -1, 2), "ts": x.get("evaluation_timestamp")})
    else:
        dur[f"{arm}|{f['suite']}|calls:{bool(calls)}"].append(x.get("duration") or 0)
    tagx = 0
    for m in ms:
        if m.get("role") == "assistant":
            tg = text(m).count("<function="); nc = len(m.get("tool_calls") or [])
            tagx += tg > nc
    h6["logs_with_tag_excess"] += tagx > 0; h6["turns_tag_excess"] += tagx
    h6["sampled_logs_with_tag_excess"] += (tagx > 0 and lab in slabels)
nfd = [r["duration_s"] for r in nf_rows]; nft = sorted(r["ts"] for r in nf_rows)
# benign twins of the empty-final user tasks
twins = {}
for u in rows:
    f = u["facets"]
    if f["suite"] == "banking" and f["task_kind"] == "user" and f["attack_dir"] == "none" and f["task_dir"] in {"user_task_12", "user_task_13", "user_task_14", "user_task_15"}:
        x = R.load(E[u["label"]]); ms = x.get("messages") or []
        twins[f["task_dir"]] = {"calls": sum(len(m.get("tool_calls") or []) for m in ms), "utility": x.get("utility"),
                                "final_text_empty": text(ms[-1]).strip() == "" if ms else None}
by_ut = Counter(r["label"].split("/")[4] for r in nf_rows)
OUT = {"h3_by_suite_it": {k: dict(v) for k, v in sorted(h3.items())}, "exposure": dict(sorted(exposure.items())),
       "successes": succ, "h6_logs": dict(h6),
       "empty_final": {"n": len(nf_rows), "by_user_task": dict(by_ut), "duration_s": {"min": min(nfd), "median": statistics.median(nfd), "max": max(nfd)},
                       "ts_first": nft[0], "ts_last": nft[-1], "in_sample": sorted(r["label"] for r in nf_rows if r["label"] in slabels),
                       "benign_twins": twins},
       "duration_median_other": {k: round(statistics.median(v), 2) for k, v in sorted(dur.items())},
       "trailing_in_sample": sorted(l for l in pop["trailing"]["labels"] if l in slabels),
       "successes_in_sample": sorted(l for l in succ if l in slabels)}
json.dump(OUT, open(sys.argv[3], "w"), indent=1, sort_keys=True)
print(json.dumps(OUT, indent=0)[:7000])
