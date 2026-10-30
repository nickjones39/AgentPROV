# ruff: noqa  (precheck examiner script for autogen-guard-placement, committed as run; read-only analysis)
"""Account-path and secret-shape screen of all 109 zip members (the raw store keeps the whole deposit), plus AER actor
identity tally. Counts, member-class labels and 8-hex digests of account names only.
Usage: python -I acct.py <zip> <scratch corpus> <out.json>"""
import hashlib, json, re, sys
from collections import Counter
from pathlib import Path
from agentprov.ingest.archives import iter_zip_members, open_zip
from agentprov.ingest.limits import IngestLimits
ACC = re.compile(rb"(?:/Users/|/home/|C:\\\\Users\\\\)([A-Za-z0-9._-]{2,})")
SEC = re.compile(rb"(?:sk-[A-Za-z0-9_-]{20,}|hf_[A-Za-z0-9]{30,}|ghp_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|xox[bp]-[A-Za-z0-9-]{10,})")
out = {"members": 0, "acct_hits_by_member_ext": Counter(), "acct_names_sha8": Counter(), "secret_hits_by_member_ext": Counter()}
with Path(sys.argv[1]).expanduser().open("rb") as fp, open_zip(fp, IngestLimits(), release=False) as z:
    for m in iter_zip_members(z):
        out["members"] += 1
        b = z.read_member(m)
        ext = m.label.rsplit(".", 1)[-1] if "." in m.label.rsplit("/", 1)[-1] else "<none>"
        for h in ACC.finditer(b):
            out["acct_hits_by_member_ext"][ext] += 1
            out["acct_names_sha8"][hashlib.sha256(h.group(1)).hexdigest()[:8] + (":user" if h.group(1) in (b"user", b"runner") else "")] += 1
        for h in SEC.finditer(b):
            out["secret_hits_by_member_ext"][ext] += 1
C = Path(sys.argv[2]).expanduser()
act = Counter()
for line in (C / "executions.jsonl").read_text().splitlines():
    e = json.loads(line)
    for x in (C / e["paths"]["aer"]).read_text().splitlines():
        a = json.loads(x)
        if a.get("k") == "actor":
            act[f"{a.get('kind')}:{a.get('name') or a.get('id')}"] += 1
        if a.get("k") == "model_call":
            mo = a.get("model") or {}
            act[f"model_call:requested={mo.get('requested')}:served={mo.get('served', 'absent')}"] += 1
out["aer_actors"] = act
Path(sys.argv[3]).write_text(json.dumps(out, indent=1, sort_keys=True, default=dict) + "\n")
