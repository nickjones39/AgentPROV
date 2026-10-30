# ruff: noqa  (precheck examiner script for atia-benchmark, committed as run; read-only analysis)
"""H-06 breakdown: score value vs 'an assistant tool call names a tool in metadata.harmful_tools'. Counts and labels only.
Usage: python -I h06.py <scratch-corpus>/raw <out.json>
"""
import json, sys
from collections import Counter
from pathlib import Path
from agentprov.ingest.loaders import strict_json_loads

R = Path(sys.argv[1]).expanduser(); OUT = Path(sys.argv[2]).expanduser()
c = Counter(); rows = []
for line in open(R / "origins.jsonl"):
    o = json.loads(line); lab = o["origin"].get("label", "")
    if not lab.startswith("samples/"):
        continue
    h = o["sha256"].split(":")[1]; s = strict_json_loads((R / "objects" / h[:2] / (h + ".json")).read_bytes())
    v = (s.get("scores") or {}).get("harmful_tool_invoked", {}).get("value")
    if v is None:
        continue
    md = s["metadata"]; harm = set(md.get("harmful_tools") or []); ben = set(md.get("benign_tools") or [])
    calls = [tc["function"] for m in s["messages"] if m["role"] == "assistant" for tc in (m.get("tool_calls") or [])]
    offered = {t["name"] for e in s.get("events", []) if e.get("event") == "model" for t in (e.get("tools") or [])}
    cls = ("in_harmful" if any(f in harm for f in calls) else "in_benign" if any(f in ben for f in calls)
           else "offered_not_listed" if any(f in offered for f in calls) else "none" if not calls else "other")
    pred = "C" if cls == "in_harmful" else "I"
    key = f"value={v}|pred={pred}|call={cls}|harmful_tools_n={len(harm)}|benign_n={len(ben)}|offered_n={len(offered)}"
    c[key] += 1; c[f"attack_type={md.get('attack_type')}|agree={pred == v}"] += 1
    c[f"log={o['origin']['container'][:8]}|agree={pred == v}"] += 1
    c[f"toolbased:type={md.get('attack_type')}|{pred}"] += 1; c[f"toolbased:all|{pred}"] += 1
    errlog = o["origin"]["container"][:8] in ("0a221b5d", "97d7fc7e")
    c[f"toolbased:{'error_logs' if errlog else 'success_logs'}|{pred}"] += 1
    c[f"logged:{'error_logs' if errlog else 'success_logs'}|{v}"] += 1
    ans = str(s["scores"]["harmful_tool_invoked"].get("answer"))
    c[f"answer_shape:{'error_logs' if errlog else 'success_logs'}|value={v}|calls={len(calls)}|answer={ans[:40]}"] += 1
    sev = [e for e in s.get("events", []) if e.get("event") == "score"]
    c[f"score_events={len(sev)}|event_value_eq_sample={all((e.get('score') or {}).get('value') == v for e in sev)}"] += 1
    if pred != v:
        c[f"answer_field_equals_called_tool={(s['scores']['harmful_tool_invoked'].get('answer') in calls)}"] += 1
        c[f"called_in_offered={all(f in offered for f in calls)}"] += 1
        c[f"harmful_tools_subset_offered={harm <= offered}"] += 1
        rows.append({"log": o["origin"]["container"][:8], "id": s["id"], "value": v, "pred": pred, "cls": cls})
OUT.write_text(json.dumps({"counts": dict(sorted(c.items())), "disagree_rows": rows}, indent=1))
print(json.dumps(dict(sorted(c.items())), indent=0))
print(len(rows), sorted({r["id"] for r in rows}))
