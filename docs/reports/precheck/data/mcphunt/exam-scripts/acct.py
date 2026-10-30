"""Classify the L1-06 named-account and provider-key-shape hits of mcphunt head without printing any value.

Per hit: trace label, canary-flagged (D-289 withheld) or not, env_type, risk_mechanism, first pointer where the name
appears in message order (model-authored tool-call argument before any tool result = model-introduced), whether the
name matches a fixed list of generic/service words (word printed only then), and for provider-key shapes boolean
context (assignment key before it, prefix class, distinct-character count).
usage: uv run python -I acct.py <staging-root> <pop.json> <out.json>
"""
import hashlib, json, os, re, sys
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), *[".."] * 6))
sys.path.insert(0, os.path.join(REPO, "tools", "precheck"))
from l1_scan import ACCOUNT_PATTERNS, GENERIC_ACCOUNTS, SECRET_PATTERNS  # noqa: E402
from agentprov.ingest.jsonstream import open_json_stream  # noqa: E402
from agentprov.ingest.limits import IngestLimits, MIB  # noqa: E402
root, popp, outp = os.path.expanduser(sys.argv[1]), sys.argv[2], sys.argv[3]
pop = json.load(open(popp))
WORDS = ("deploy appuser service www git postgres mysql project projects workspace ci build daemon backup data devops "
         "ops server prod staging admin1 administrator mcphunt mcp agentuser webapp web api app1 home docs sysadmin "
         "developer dev1 team company acme corp jdoe johndoe janedoe alice bob carol dave eve frank user2 me runneradmin "
         "public owner local localuser operator analyst engineer research researcher student hunter canary secret "
         "victim attacker target host pi debian centos fedora kali vagrant ec2 azureuser gcp cloud "
         "deployer appadmin dbadmin svc service1 bot ubuntu1 lab labuser test1 tester qa").split()
WD = {hashlib.sha256(w.encode()).hexdigest()[:8]: w for w in WORDS}
want = {k.split(":", 1)[1]: k for k in pop["named_accounts"]}
kwant = {k.split(":", 1)[1]: k for k in pop["provider_key_shapes"] if k.startswith("openai")}
LIM = IngestLimits().replace(max_json_element_bytes=64 * MIB, max_jsonl_line_bytes=64 * MIB)
docs = sorted({lab.split("#")[0] for v in ()} | set(pop["docs"]))
out = {"accounts": {}, "keys": []}
for lab in docs:
    with open(os.path.join(root, lab), "rb") as fh:
        for it in open_json_stream(fh, LIM, arrays=("/traces",)):
            t = it.value; blob = json.dumps(t)
            if "/home/" not in blob and "sers" not in blob and "sk-" not in blob: continue
            flagged = any(e.get("canary_in_result") or e.get("canary_in_args") for e in t.get("events") or [] if isinstance(e, dict))
            seq = []  # message-order strings with a pointer kind
            for i, m in enumerate(t.get("messages") or []):
                seq.append((f"msg[{m.get('role')}].content", str(m.get("content"))))
                for c in m.get("tool_calls") or []:
                    seq.append(("msg.tool_call.arguments", str((c.get("function") or {}).get("arguments"))))
            for name, rx in ACCOUNT_PATTERNS.items():
                for kind, s in seq:
                    for mm in rx.finditer(s):
                        a = mm.group(1)
                        if a.lower() in GENERIC_ACCOUNTS: continue
                        dg = hashlib.sha256(a.encode()).hexdigest()[:8]
                        key = want.get(dg)
                        if not key: continue
                        r = out["accounts"].setdefault(key, {"generic_word": WD.get(hashlib.sha256(a.lower().encode()).hexdigest()[:8]), "traces": {}})
                        tr = r["traces"].setdefault(f"{lab}#/traces/{it.index}", {"canary_flagged": flagged, "env_type": t.get("env_type"),
                              "risk_mechanism": t.get("risk_mechanism"), "first_kind": kind, "kinds": {}})
                        tr["kinds"][kind] = tr["kinds"].get(kind, 0) + 1
            for e in t.get("events") or []:
                rf = str(e.get("result_full"))
                for mm in SECRET_PATTERNS["openai-api-key"].finditer(rf):
                    sv = mm.group(0); dg = hashlib.sha256(sv.encode()).hexdigest()[:8]
                    if dg not in kwant: continue
                    pre = rf[max(0, mm.start() - 40):mm.start()]
                    out["keys"].append({"key": kwant[dg], "trace": f"{lab}#/traces/{it.index}", "canary_flagged": flagged,
                        "server": e.get("server"), "tool": e.get("tool"), "success": e.get("success"),
                        "assignment_before": bool(re.search(r"(?i)(api[_-]?key|token|secret)\s*[=:]\s*['\"]?$", pre)),
                        "openai_env_name_before": "OPENAI" in pre.upper(), "proj_prefix": sv.startswith("sk-proj-"),
                        "distinct_chars": len(set(sv[3:])), "len": len(sv),
                        "in_task_prompt_or_args": sv in str(t.get("task_prompt")) or sv in json.dumps(e.get("args"))})
json.dump(out, open(outp, "w"), indent=1, sort_keys=True)
print(json.dumps(out, indent=0)[:6000])
