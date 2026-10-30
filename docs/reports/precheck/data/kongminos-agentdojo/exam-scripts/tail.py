"""kongminos-agentdojo: (a) logs in the empty-final time window and their state; (b) the no-call assistant turns that hold
a <function= tag (parse-dropped final calls): logs, arms, outcomes, whether JSON inside the tag parses. Counts/labels only.
Usage (repo root): GIT_NO_LAZY_FETCH=1 GIT_ALLOW_PROTOCOL=file uv run python -I <this> OUT.json"""
import json, os, re, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kx_lib  # noqa: E402
TAG = re.compile(r"<function\s*=\s*([^>]+)>(.*?)(</function>|$)", re.S)
def text(m):
    c = m.get("content")
    if isinstance(c, str): return c
    return "".join(str(b.get("content") or "") for b in (c or []) if isinstance(b, dict))
E = kx_lib.entries(); R = kx_lib.Reader()
rows = [json.loads(l) for l in open(kx_lib.W / "l1-units-head.jsonl")]
win = Counter(); drop = []; dropc = Counter()
for u in rows:
    f = u["facets"]; x = R.load(E[u["label"]]); ms = x.get("messages") or []
    t = x.get("evaluation_timestamp") or ""
    last = ms[-1] if ms else {}
    empty = last.get("role") == "assistant" and not last.get("tool_calls") and text(last).strip() == ""
    if t >= "2026-08-21 14:56:34":
        win[f"{f['suite']}|{f['task_dir']}|empty:{empty}"] += 1
    for m in ms:
        if m.get("role") == "assistant" and not m.get("tool_calls") and "<function=" in text(m):
            mt = TAG.search(text(m)); ok = None; closed = None
            if mt:
                closed = bool(mt.group(3))
                try: json.loads(mt.group(2).strip() or "{}"); ok = True
                except Exception: ok = False
            arm = "attacked" if f["attack_dir"] != "none" else ("prepass" if f["task_kind"] == "prepass" else "benign")
            dropc[f"{arm}|{f['suite']}|json_ok:{ok}|closed:{closed}|util:{x.get('utility')}|sec:{x.get('security')}|is_last:{m is last}"] += 1
            drop.append(u["label"])
OUT = {"window_from": "2026-08-21 14:56:34", "window": dict(sorted(win.items())), "dropped_tag_turns": len(drop), "dropped_tag_logs": len(set(drop)),
       "dropped_by": dict(sorted(dropc.items())), "dropped_labels": sorted(set(drop))}
json.dump(OUT, open(sys.argv[1], "w"), indent=1, sort_keys=True); print(json.dumps({k: v for k, v in OUT.items() if k != "dropped_labels"}, indent=0))
