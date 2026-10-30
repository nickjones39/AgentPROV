"""Whole-population census of mcphunt head (20 trace documents, 6,786 traces) through agentprov.ingest.open_json_stream
(64 MiB element limit, as l1_scan). Counts, labels, short commit ids and truncated digests only; never a string value.

H1-H20 of prereg/mcphunt.md: per-document counts, envelopes, models, env x mechanism cells, mitigation levels,
memory package and memory-server events, paper tables 3/6/7/14-17/19/20 recount, outcome consistency, timestamps,
finish reasons, duration/tokens/turns, temperature/max tokens, canary events, guard rewrites, L1-06 named-account and
provider-key-shape classification (context booleans, digest8).
usage: uv run python -I pop.py <staging-root> <out.json>
"""
import collections, datetime, hashlib, json, os, re, sys
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), *[".."] * 6))
sys.path.insert(0, os.path.join(REPO, "tools", "precheck"))
from l1_scan import ACCOUNT_PATTERNS, GENERIC_ACCOUNTS, SECRET_PATTERNS  # noqa: E402
from agentprov.ingest.jsonstream import open_json_stream  # noqa: E402
from agentprov.ingest.limits import IngestLimits, MIB  # noqa: E402

root = os.path.expanduser(sys.argv[1]); outp = sys.argv[2]
LIM = IngestLimits().replace(max_json_element_bytes=64 * MIB, max_jsonl_line_bytes=64 * MIB)
DOCS = sorted(os.path.relpath(os.path.join(d, f), root) for sp in ("main", "mitigation", "live_guard_defense",
              "browser_replication") for d, _, fs in os.walk(os.path.join(root, sp)) for f in fs if f.endswith(".json"))
C = collections.Counter
def dd(): return collections.defaultdict(C)
out = {"docs": {}, "envelopes": {}}
T = dd()  # generic tallies: T[name][key] += 1
PLACE = ("/home/user/", "/mcphunt/", "<HOME>", "MCPHUNT-HOST", "<redacted>", "<internal-gateway>")
WORDS = ("test", "fake", "example", "dummy", "canary", "xxxx", "sample", "placeholder", "mock")
acct = collections.defaultdict(lambda: {"strings": 0, "traces": set(), "splits": C(), "ptr": C(), "in_prompt": 0,
                                         "in_env_snapshot": 0, "kind": None})
keys = collections.defaultdict(lambda: {"strings": 0, "traces": set(), "splits": C(), "ptr": C(), "ctx": C()})
ts_win = C(); dur = collections.defaultdict(list)

def walk(v, ptr, cb):
    if isinstance(v, dict):
        for k, x in v.items(): walk(x, ptr + "/" + (k if re.fullmatch(r"[A-Za-z_]\w{0,40}", str(k)) else "<key>"), cb)
    elif isinstance(v, list):
        for x in v: walk(x, ptr + "/*", cb)
    elif isinstance(v, str): cb(ptr, v)

for lab in DOCS:
    split, doc = lab.split("/")[0], os.path.basename(lab)[:-5]
    with open(os.path.join(root, lab), "rb") as fh:
        s = open_json_stream(fh, LIM, arrays=("/traces",))
        env = {k: v for k, v in s.envelope.items() if k != "traces"}
        out["envelopes"][lab] = {k: (str(v)[:12] if isinstance(v, str) else type(v).__name__) for k, v in env.items()}
        n = 0
        for it in s:
            t = it.value; n += 1; tid = f"{lab}#/traces/{it.index}"
            m, e, mech, ml, df = t.get("model"), t.get("env_type"), t.get("risk_mechanism"), t.get("mitigation_level"), t.get("defense")
            lb = t.get("labeling") or {}; cc = t.get("completion_checks") or {}; ms = t.get("measurement") or {}
            risk = bool(lb.get("any_risk")); ver = bool(cc.get("artifact_verified")); oc = t.get("outcome")
            crs = bool(lb.get("completion_requires_secret"))
            exp = ("unsafe_" if risk else "safe_") + ("success" if ver else "failure")
            T["h12"]["consistent" if oc == exp else "inconsistent"] += 1
            if e == "benign": T["h12_benign"][f"risk={risk}|outcome={oc}"] += 1
            T["model"][m] += 1; T["doc_model"][f"{lab}|{m}"] += 1
            T["cell"][f"{split}|{m}|{ml}|{df}|{e}"] += 1
            T["env_mech"][f"{split}|{m}|{e}|{mech}"] += 1
            T["envtype_taskcat"][f"{split}|{e}|{t.get('task_category')}|{t.get('expected_risk')}"] += 1
            T["ml"][ml] += 1; T["defense"][df] += 1; T["split_ml"][f"{split}|{doc}|{ml}"] += 1
            k = f"{split}|{doc}|{m}|{ml}|{e}"
            T["prop"][k] += risk; T["util"][k] += ver; T["n"][k] += 1; T["quad"][f"{k}|{oc}"] += 1
            T["taskcompleted"][k] += bool(t.get("task_completed"))
            risky = str(e).startswith("risky")
            if risky and mech != "benign_control":
                T["pv_n" if not crs else "crs_n"][f"{split}|{doc}|{ml}"] += 1
                T["pv" if not crs else "crs"][f"{split}|{doc}|{ml}"] += risk
                T["mech_prop"][f"{split}|{doc}|{ml}|{mech}"] += risk; T["mech_n"][f"{split}|{doc}|{ml}|{mech}"] += 1
            if risky:
                for sig, on in (lb.get("risk_signals") or {}).items():
                    if on: T["signals"][f"{split}|{doc}|{sig}"] += 1
                T["risky_n"][f"{split}|{doc}"] += 1
            if str(e).startswith("hard_neg"):
                T["hn"][f"{split}|{doc}|{mech == 'benign_control'}|{t.get('task_category')}"] += risk
                T["hn_n"][f"{split}|{doc}|{mech == 'benign_control'}|{t.get('task_category')}"] += 1
            # envelope-ish / measurement
            T["temp"][repr(ms.get("generation_temperature"))] += 1
            T["maxtok"][repr(ms.get("generation_max_tokens"))] += 1
            for pkg in (ms.get("mcp_versions") or {}):
                if "memory" in pkg: T["mem_pkg"][f"{split}|{pkg}"] += 1
            tl = t.get("turn_log") or []
            fr = tl[-1].get("finish_reason") if tl and isinstance(tl[-1], dict) else None
            T["finish"][repr(fr)] += 1; T["finish_trunc_turns"][f"{fr}|trunc={t.get('truncated')}|turns={t.get('num_turns') if fr == 'tool_calls' else '-'}"] += 1
            roles = C(x.get("role") for x in t.get("messages") or [] if isinstance(x, dict))
            for r_, c_ in roles.items(): T["roles"][r_] += c_
            asst = roles.get("assistant", 0)
            T["turnlog_vs_asst"]["plus1" if len(tl) == asst + 1 else ("equal" if len(tl) == asst else "other")] += 1
            if not t.get("messages"): T["degenerate"]["zero_messages"] += 1
            evs = [x for x in t.get("events") or [] if isinstance(x, dict)]
            T["events"]["total"] += len(evs)
            T["events"]["tool_calls"] += sum(len(x.get("tool_calls") or []) for x in t.get("messages") or [] if isinstance(x, dict))
            cf = 0
            for x in evs:
                T["events"]["canary_in_result"] += bool(x.get("canary_in_result")); T["events"]["canary_in_args"] += bool(x.get("canary_in_args"))
                cf += bool(x.get("canary_in_result") or x.get("canary_in_args"))
                T["events"]["flagged"] += bool(x.get("canary_in_result") or x.get("canary_in_args"))
                T["events"]["sanitized_args"] += "sanitized_args" in x
                if x.get("server") == "memory": T["mem_events"][f"{split}|success={x.get('success')}"] += 1
            T["canary_traces"]["flagged" if cf else "unflagged"] += 1
            T["canary_by_split"][f"{split}|{'flagged' if cf else 'unflagged'}"] += 1
            # time
            ct = t.get("collection_timestamp")
            T["ct_form"]["ok" if isinstance(ct, str) and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", ct) else "other"] += 1
            T["ct_max"][split] = max(T["ct_max"].get(split, ""), ct or "") if False else 0
            out.setdefault("ct_range", {}).setdefault(split, [ct, ct])
            r0 = out["ct_range"][split]; r0[0] = min(r0[0], ct); r0[1] = max(r0[1], ct)
            try:
                cte = datetime.datetime.strptime(ct, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.UTC).timestamp()
                tss = [x["timestamp"] for x in evs if isinstance(x.get("timestamp"), (int, float))]
                d_ = float(t.get("duration_s") or 0)
                if tss: ts_win["ok" if tss[0] >= cte - d_ - 5 and tss[-1] <= cte + 5 else "fail"] += 1
                else: ts_win["no_events"] += 1
            except Exception: ts_win["unparsed"] += 1
            if split == "main":
                dur["main"].append(float(t.get("duration_s") or 0)); dur["turns"].append(t.get("num_turns") or 0)
                T["tokens"]["prompt"] += ms.get("prompt_tokens") or 0; T["tokens"]["completion"] += ms.get("completion_tokens") or 0
            # L1-06 classification (never values)
            pr = (t.get("task_prompt") or "") + "".join(str(x.get("content")) for x in (t.get("messages") or [])[:2] if isinstance(x, dict))
            esn = json.dumps(t.get("env_snapshot"))
            def cb(ptr, v, tid=tid, split=split, pr=pr, esn=esn):
                for pl in PLACE:
                    if pl in v: T["placeholders"][pl] += 1
                if "sers" in v or "/home/" in v:
                    for name, rx in ACCOUNT_PATTERNS.items():
                        for mm in rx.finditer(v):
                            a = mm.group(1)
                            if a.lower() in GENERIC_ACCOUNTS: T["acct_generic"][f"{name}|{a.lower()}"] += 1; continue
                            dg = name + ":" + hashlib.sha256(a.encode()).hexdigest()[:8]
                            r = acct[dg]; r["strings"] += 1; r["traces"].add(tid); r["splits"][split] += 1
                            r["ptr"][re.sub(r"/\*", "", ptr)] += 1; r["in_prompt"] += a in pr; r["in_env_snapshot"] += a in esn
                            r["len"] = len(a); r["ascii_alpha"] = a.isascii() and a.replace(".", "").replace("-", "").isalnum()
                            r["placeholder_like"] = a.startswith("<") or a.startswith("{") or a.startswith("$") or "%" in a
                for name in ("openai-api-key", "anthropic-api-key", "google-api-key", "hf-token", "jwt", "private-key-block"):
                    for mm in SECRET_PATTERNS[name].finditer(v):
                        sv = mm.group(0); dg = name + ":" + hashlib.sha256(sv.encode()).hexdigest()[:8]
                        r = keys[dg]; r["strings"] += 1; r["traces"].add(tid); r["splits"][split] += 1; r["ptr"][ptr] += 1
                        r["ctx"]["in_prompt"] += sv in pr; r["ctx"]["in_env_snapshot"] += sv in esn
                        r["ctx"]["word_marker"] += any(w in sv.lower() for w in WORDS); r["len"] = len(sv)
                        r["ctx"]["prefix_" + sv[:8].replace("-", "_").strip("_")[:7] if name == "private-key-block" else "n/a"] += 1
            walk(t, "", cb)
            # event-level context for provider-key shapes
            for x in evs:
                blob = json.dumps(x)
                if SECRET_PATTERNS["openai-api-key"].search(blob):
                    T["openai_event_ctx"][f"{split}|{x.get('server')}|{x.get('tool')}|canary_in_result={x.get('canary_in_result')}|success={x.get('success')}"] += 1
        out["docs"][lab] = n
def mean(a): return round(sum(a) / len(a), 3) if a else None
out["tallies"] = {k: dict(sorted(v.items())) for k, v in T.items()}
out["ts_window"] = dict(ts_win)
out["main_stats"] = {"n": len(dur["main"]), "mean_duration_s": mean(dur["main"]), "sum_duration_h": round(sum(dur["main"]) / 3600, 2),
                     "mean_turns": mean(dur["turns"])}
out["named_accounts"] = {k: {**{kk: (dict(vv) if isinstance(vv, C) else (len(vv) if isinstance(vv, set) else vv)) for kk, vv in r.items()}} for k, r in sorted(acct.items())}
out["provider_key_shapes"] = {k: {kk: (dict(vv) if isinstance(vv, C) else (len(vv) if isinstance(vv, set) else vv)) for kk, vv in r.items()} for k, r in sorted(keys.items())}
json.dump(out, open(outp, "w"), indent=1, sort_keys=True, default=str)
print("docs", len(out["docs"]), "traces", sum(out["docs"].values()))
