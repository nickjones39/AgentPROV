"""banking user_task_15 confound check (agentdojo.art.banking_ut15_confound): does the user prompt carry the attacker
IBAN, and how many security=true logs have no injection marker in any tool output? Counts only."""
import sys, json
from collections import Counter
sys.path.insert(0, sys.argv[1])
import gx_lib
rows = json.load(open(sys.argv[2]))
E = gx_lib.entries(); R = gx_lib.Reader()
IBAN = "US133000000121212121212"  # the AgentDojo banking attacker account (benchmark constant)
c = Counter()
for r in rows:
    if r["suite"] != "banking" or r["kind"] != "user":
        continue
    v = R.load(E[r["label"]])
    ms = v["messages"]
    user = next((m.get("content") for m in ms if m.get("role") == "user"), "") or ""
    tool_txt = " ".join(str(m.get("content") or "") for m in ms if m.get("role") == "tool")
    marker = "<INFORMATION>" in tool_txt
    ut15 = r["ut"] == "user_task_15"
    c[f"ut15={ut15}|user_prompt_has_attacker_iban={IBAN in user}"] += 1
    if r["security"] is True:
        c[f"ut15={ut15}|security_true|payload_marker_in_tool_output={marker}"] += 1
print(dict(sorted(c.items())))
