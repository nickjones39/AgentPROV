"""Follow-ups of checks.py (counts and labels only, never a value): (a) banking user_task_5 logs per arm: tool messages,
proposed and executed send_money/schedule_transaction calls (any recipient / the Spotify IBAN), to tell a #161 vacuous pass
from an arm whose logs do not record tool messages; (b) the drift L1-06 hit: suite/task facets, keyword class, character
classes of the token and the number of other logs of the pin whose bytes contain it; (c) H7 call-like final text on the
clean arms; (d) run-error logs: first word of the error string only.
Usage (repo root): uv run python -I docs/reports/precheck/data/dca-agentdojo/exam-scripts/extra.py OUT.json"""
import json, os, re, sys
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from zipread import Z
W = os.path.expanduser("~/.agentprov/migration-work/precheck/dca-agentdojo")
SPOT = "se3550000000054910000003"; TR = ("send_money", "schedule_transaction")
CALLLIKE = re.compile(r"<tool_call>|<function|\"(?:name|function)\"\s*:\s*\"|```(?:json|python)?\s*\{")
SECRX = re.compile(r"(?i)(api[_-]?key|secret|token|passw(?:or)?d)[\"']?\s{0,3}[:=]\s{0,3}[\"']?([A-Za-z0-9_\-/+=.]{16,})")
def text(c):
    if isinstance(c, str): return c
    if isinstance(c, list): return "".join(b.get("content") or "" for b in c if isinstance(b, dict) and isinstance(b.get("content"), str))
    return ""
z = Z(verify=False); rows = []
for part in ("v1", "drift"): rows += [json.loads(l) for l in open(f"{W}/l1-units-{part}.jsonl")]
ut5 = defaultdict(Counter); clean = defaultdict(Counter); errs = Counter(); hit = None
for u in rows:
    f = u["facets"]; md = f["model_dir"]
    need = (f["suite"] == "banking" and f["task_dir"] == "user_task_5") or f["task_kind"] == "user" and f["attack_dir"] == "none" \
        or u["outcomes"]["error_present"] or "secret_like" in u["flags"]
    if not need: continue
    x = z.json(u["label"]); ms = x.get("messages") or x.get("conversations") or []
    if f["suite"] == "banking" and f["task_dir"] == "user_task_5":
        c = ut5[f"{md}|{f['attack_dir']}"]; c["n"] += 1
        c["tool_msgs"] += sum(m.get("role") == "tool" for m in ms)
        pr = [tc for m in ms if m.get("role") == "assistant" for tc in (m.get("tool_calls") or []) if tc.get("function") in TR]
        ex = [m.get("tool_call") or {} for m in ms if m.get("role") == "tool" and m.get("error") is None and (m.get("tool_call") or {}).get("function") in TR]
        c["logs_proposed_transfer"] += bool(pr); c["logs_executed_transfer"] += bool(ex)
        c["logs_executed_spotify"] += any(str((t.get("args") or {}).get("recipient", "")).lower() == SPOT for t in ex)
        c["logs_without_tool_msgs"] += not any(m.get("role") == "tool" for m in ms)
    if f["task_kind"] == "user" and f["attack_dir"] == "none":
        fin = [m for m in ms if m.get("role") == "assistant"]; fin = fin[-1] if fin else None
        c = clean[md]; c["n"] += 1
        c["final_calllike_no_calls"] += fin is not None and not fin.get("tool_calls") and bool(CALLLIKE.search(text(fin.get("content"))))
    if u["outcomes"]["error_present"]:
        errs[str(x.get("error")).split(":")[0].split()[0][:40]] += 1
    if "secret_like" in u["flags"]:
        m = SECRX.search(x.get("initial_checklist") or ""); tok = m.group(2)
        hit = {"suite": f["suite"], "task_dir": f["task_dir"], "file": f["file"], "arm": md, "keyword_class": m.group(1).lower(),
               "token_len": len(tok), "token_classes": sorted({"lower" if ch.islower() else "upper" if ch.isupper() else "digit" if ch.isdigit() else "punct" for ch in tok}),
               "token_is_hex": bool(re.fullmatch(r"[0-9a-fA-F]+", tok))}
        tb = tok.encode(); hit["other_logs_containing_token"] = sum(1 for v in rows if v["label"] != u["label"] and tb in z.read(v["label"]))
out = {"ut5": {k: dict(v) for k, v in sorted(ut5.items())}, "clean_h7": {k: dict(v) for k, v in sorted(clean.items())},
       "error_first_word": dict(errs), "drift_secret_hit": hit}
json.dump(out, open(sys.argv[1], "w"), indent=1, sort_keys=True); print(json.dumps(out, sort_keys=True))
