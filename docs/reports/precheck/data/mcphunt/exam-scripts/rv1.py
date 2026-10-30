"""Table 7 recount (mitigation risky_v1 risk tasks): per rv1/gpt54 document, propagation by (benign_control?,
expected_risk, task_id alpha prefix); labels and counts only.
usage: uv run python -I rv1.py <staging-root> <out.json>
"""
import collections, json, os, re, sys
from agentprov.ingest.jsonstream import open_json_stream
from agentprov.ingest.limits import IngestLimits, MIB
root, outp = os.path.expanduser(sys.argv[1]), sys.argv[2]
LIM = IngestLimits().replace(max_json_element_bytes=64 * MIB, max_jsonl_line_bytes=64 * MIB)
out = {}
for f in sorted(os.listdir(os.path.join(root, "mitigation"))) + ["../main/gpt_5_4.json"]:
    n = collections.Counter(); p = collections.Counter()
    with open(os.path.join(root, "mitigation", f), "rb") as fh:
        for it in open_json_stream(fh, LIM, arrays=("/traces",)):
            t = it.value
            if t.get("env_type") != "risky_v1": continue
            pre = re.match(r"[A-Za-z_]+", str(t.get("task_id")) or "")
            k = f"bc={t.get('risk_mechanism') == 'benign_control'}|exp={t.get('expected_risk')}|pfx={pre.group(0)[:20] if pre else None}"
            n[k] += 1; p[k] += bool((t.get("labeling") or {}).get("any_risk"))
    out[f] = {k: [p[k], n[k]] for k in sorted(n)}
json.dump(out, open(outp, "w"), indent=1); print(json.dumps(out)[:4000])
