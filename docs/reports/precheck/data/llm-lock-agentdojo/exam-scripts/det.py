"""llm-lock-agentdojo detector-decision consistency (H7/H8 follow-on, PC-03/PC-04); counts only.

Per arm: tool outputs that carry the attack payload (normalised 40-char prefix of any value of the log's `injections`)
and reach the agent unredacted; sentinel redactions in attacked vs benign (attack none) runs; aborts in benign runs;
whether the aborted output carries the payload; aborts whose last turn has several outputs (product issue
detector_abort_output_unrecorded); label classes of llm/multiclass results at abort vs elsewhere.
Raw logs read by blob id from the staged bare clone (lazy fetch off), sha256-checked, strict agentprov.ingest parse.
Usage: uv run python -I det.py <l1-units-head.jsonl> <bare repo> <commit> <out.json>
"""
from __future__ import annotations
import hashlib, json, os, re, sys
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pop_io import tree, Reader, text  # noqa: E402
from agentprov.ingest.loaders import strict_json_loads

UNITS, BARE, COMMIT, OUT = sys.argv[1:5]
SENT = "<Data omitted because a prompt injection was detected>"
WS = re.compile(r"\s+")
LBL = re.compile(r"^[A-Za-z_]{1,12}$")
t = tree(BARE, COMMIT); r = Reader(BARE)
A = defaultdict(Counter)
for ln in open(UNITS, encoding="utf-8"):
    row = json.loads(ln); f = row["facets"]; arm, att = f["model_dir"], f["attack_dir"]
    raw = r.read(t[row["label"]]); assert hashlib.sha256(raw).hexdigest() == row["sha256"]
    x = strict_json_loads(raw); ms = x["messages"]; a = A[arm]
    kind = "benign" if att == "none" else ("dos" if att == "dos" else "attacked")
    marks = [WS.sub(" ", v)[:40] for v in (x.get("injections") or {}).values() if isinstance(v, str) and len(v) >= 20] if kind != "benign" else []
    outs = [m for m in ms if m.get("role") == "tool"]
    for m in outs:
        tx = text(m.get("content")); red = SENT in tx
        a[f"{kind}|outputs"] += 1; a[f"{kind}|redacted"] += red
        if marks and not red and any(mk in WS.sub(" ", tx) for mk in marks): a[f"{kind}|payload_unredacted"] += 1
    a[f"{kind}|logs"] += 1
    if marks and any(any(mk in WS.sub(" ", text(m.get("content"))) for mk in marks) for m in outs): a[f"{kind}|logs_payload_reached"] += 1
    if any(SENT in text(m.get("content")) for m in outs): a[f"{kind}|logs_with_redaction"] += 1
    if ms[-1].get("role") == "tool":
        k = 0
        for m in reversed(ms):
            if m.get("role") != "tool": break
            k += 1
        a[f"{kind}|aborts"] += 1; a[f"{kind}|aborts_multi_output"] += k > 1
        if marks and k == 1: a[f"{kind}|abort_single_output_has_payload"] += any(mk in WS.sub(" ", text(ms[-1].get("content"))) for mk in marks); a[f"{kind}|abort_single_output"] += 1
    for key in ("classification_result", "secondary_classification_result"):
        v = x.get(key)
        if isinstance(v, list) and v:
            ab = ms[-1].get("role") == "tool"
            for i, y in enumerate(v):
                lab = y if isinstance(y, str) and LBL.match(y) else "other"
                pos = "abort_last" if ab and i == len(v) - 1 else "elsewhere"
                a[f"{key}|{pos}|{lab}"] += 1
r.close()
out = {"corpus_id": "llm-lock-agentdojo", "pin": COMMIT[:8], "arms": {k: dict(sorted(v.items())) for k, v in sorted(A.items())}}
json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1); print(json.dumps(out, indent=1))
