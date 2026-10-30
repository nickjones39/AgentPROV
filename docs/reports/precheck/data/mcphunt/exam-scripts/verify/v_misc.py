import json, os, sys, collections
from agentprov.ingest.jsonstream import open_json_stream
from agentprov.ingest.limits import IngestLimits, MIB
root = os.path.expanduser(sys.argv[1]); LIM = IngestLimits().replace(max_json_element_bytes=64*MIB, max_jsonl_line_bytes=64*MIB)
C = collections.Counter(); ff = collections.Counter(); n = collections.Counter(); win = collections.Counter(); ml = collections.Counter()
for sp in ("main", "mitigation", "live_guard_defense", "browser_replication"):
    for f in sorted(os.listdir(os.path.join(root, sp))):
        if not f.endswith(".json"): continue
        with open(os.path.join(root, sp, f), "rb") as fh:
            for it in open_json_stream(fh, LIM, arrays=("/traces",)):
                t = it.value; s = json.dumps(t, ensure_ascii=False); n[sp] += 1
                ff[sp] += "\ufffd" in s
                win[sp] += ("C:\\\\Users" in s or "C:/Users" in s)
                ml[t.get("mitigation_level")] += 1
                ev = [e for e in t.get("events") or [] if isinstance(e, dict)]
                C["canary_traces"] += any(e.get("canary_in_result") or e.get("canary_in_args") for e in ev)
                C["canary_events"] += sum(bool(e.get("canary_in_result") or e.get("canary_in_args")) for e in ev)
                C["sanitized_args"] += sum(bool(e.get("sanitized_args")) for e in ev) if any("sanitized_args" in e for e in ev) else 0
                msgs = t.get("messages") or []
                fr = [m.get("finish_reason") for m in msgs if isinstance(m, dict) and m.get("finish_reason")]
                C["fin_" + str(t.get("finish_reason") or (fr[-1] if fr else None))] += 1
print(json.dumps({"n": n, "fffd": ff, "windows_users_paths": win, "ml": ml, "c": C}, indent=0))
