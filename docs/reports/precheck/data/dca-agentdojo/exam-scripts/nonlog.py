"""L1-06/L1-10 supplement: the 125 non-log members of the pin (code, scripts, tables, docs; 10 are profile context
artefacts, 115 not selected), scanned with l1_scan's SECRET_PATTERNS and ACCOUNT_PATTERNS. Counts by class and member
directory only; account names are reduced to generic / operator / named-non-operator and a truncated digest.
Usage (repo root): uv run python -I docs/reports/precheck/data/dca-agentdojo/exam-scripts/nonlog.py OUT.json"""
import hashlib, json, os, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../../../../tools/precheck"))
from zipread import Z
from l1_scan import SECRET_PATTERNS, ACCOUNT_PATTERNS, GENERIC_ACCOUNTS
z = Z(verify=False); op = os.path.basename(os.path.expanduser("~")).lower()
R = Counter(); files = Counter(); named = Counter(); n = 0
for lab in z.m:
    if "/results/logs/" in lab: continue
    n += 1; t = z.read(lab).decode("utf-8", "replace"); d = "/".join(lab.split("/")[1:3]); hit = False
    for k, rx in SECRET_PATTERNS.items():
        c = len(rx.findall(t))
        if c: R[f"secret:{k}|{d}"] += c; hit = True
    for k, rx in ACCOUNT_PATTERNS.items():
        for m in rx.finditer(t):
            a = m.group(1).lower(); cls = "generic" if a in GENERIC_ACCOUNTS else "operator" if a == op else "named"
            R[f"account:{k}:{cls}|{d}"] += 1; hit = True
            if cls == "named": named[hashlib.sha256(a.encode()).hexdigest()[:8]] += 1
    files["with_hit" if hit else "clean"] += 1
out = {"members_scanned": n, "files": dict(files), "hits": dict(sorted(R.items())), "named_account_digests": dict(named)}
json.dump(out, open(sys.argv[1], "w"), indent=1, sort_keys=True); print(json.dumps(out, sort_keys=True))
# characterise each generic-credential-assignment hit (no value): member, keyword, token length, placeholder-like, env-ref
import re
rx = re.compile(r"(?i)(api[_-]?key|secret|token|passw(?:or)?d)[\"']?\s{0,3}[:=]\s{0,3}[\"']?([A-Za-z0-9_\-/+=.]{16,})")
ch = []
for lab in z.m:
    if "/results/logs/" in lab: continue
    for m in rx.finditer(z.read(lab).decode("utf-8", "replace")):
        tok = m.group(2)
        ch.append({"member_dir": "/".join(lab.split("/")[1:3]), "member_ext": lab.rsplit(".", 1)[-1], "keyword": m.group(1).lower(), "len": len(tok),
                   "placeholder_like": bool(re.search(r"(?i)your|xxx|dummy|placeholder|example|empty|ollama|changeme|not[_-]?needed|local", tok)),
                   "env_or_attr_ref": bool(re.search(r"(?i)environ|getenv|args\.|config\.|self\.|_key$|_KEY$", tok)), "has_digit": any(c.isdigit() for c in tok)})
out["generic_assignment_hits"] = ch
json.dump(out, open(sys.argv[1], "w"), indent=1, sort_keys=True); print(json.dumps(ch))
