import rawload, json
d = rawload.load_all()
labels = json.load(open("docs/reports/precheck/data/mandate-agentdojo-eval/l2-sample-head.json"))["labels"]
labels = [l if isinstance(l, str) else l.get("label") for l in labels]
TR = {"send_money", "schedule_transaction", "update_scheduled_transaction"}; CQ = TR | {"update_password", "update_user_info"}
dec = allow = 0; runs = 0
for l in labels:
    x = d[l]; pipe = l.split("/")[1]; gated = TR if pipe.endswith("envelope") else CQ if pipe.endswith("intent") else set()
    res = {m["tool_call_id"]: m.get("error") for m in x["messages"] if m["role"] == "tool"}
    k = sum(1 for e in res.values() if isinstance(e, str) and e.startswith("MANDATE_DECLINE:")); dec += k; runs += bool(k)
    allow += sum(1 for m in x["messages"] if m["role"] == "assistant" for tc in (m.get("tool_calls") or []) if tc["function"] in gated and res.get(tc["id"], "x") is None)
print(len(labels), dec, runs, allow)
