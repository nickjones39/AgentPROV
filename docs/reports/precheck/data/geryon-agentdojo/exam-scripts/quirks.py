"""Quirk and structure counts from pop.json (counts only)."""
import sys, json
from collections import Counter
rows = json.load(open(sys.argv[1]))
C = Counter()
for r in rows:
    C["logs"] += 1
    C[f"kind:{r['kind']}"] += 1
    C[f"final_role:{r['final_role']}"] += 1
    if r["final_null"]:
        C["final_null(mapper rule)"] += 1
        C[f"final_null_with_calls:{r['final_calls'] > 0}"] += 1
    if r["final_role"] == "assistant" and r["final_calls"]:
        C["final_assistant_with_calls_logs"] += 1; C["final_assistant_trailing_calls"] += r["final_calls"]
    C["denials"] += r["denials"]; C["denials_multiline_only"] += r["denials_dotall_only"]
    C[f"denials_cond:{r['cond']}"] += r["denials"]
    C["schema_errors"] += r["schema_errors"]; C[f"schema_errors_cond:{r['cond']}"] += r["schema_errors"]
    C["other_tool_errors"] += r["other_tool_errors"]; C[f"other_tool_errors_cond:{r['cond']}"] += r["other_tool_errors"]
    C["placeholder_present"] += r["ph_present"]; C["placeholder_nonnull"] += r["ph_nonnull"]
    C["home_hits"] += r["home_hits"]; C["home_generic"] += r["home_generic"]; C["home_in_prior_text"] += r["home_in_prior_text"]
    C["home_logs"] += r["home_hits"] > 0
    if r["kind"] == "prepass":
        C[f"prepass_security:{r['security']}"] += 1
    C[f"error_present:{r['error_present']}"] += 1
print(json.dumps(dict(sorted(C.items())), indent=0))
den = Counter(); 
for r in rows:
    den[f"{r['run_set']}/{r['logset']}"] += r["denials"]
print("denials per set", dict(sorted(den.items())))
h = Counter((r['run_set'], r['suite'], r['cond'], r['kind'], r['ut']) for r in rows if r['home_hits'])
print("home logs by set", sorted(h.items()))
fn = Counter((r['run_set'], r['logset'], r['final_calls']) for r in rows if r['final_null'])
print("final_null by set", sorted(fn.items()))
