# ruff: noqa  (precheck examiner script for fragfuse-agentharm; item-16 rule citations and their evidence class; counts only)
"""Usage: python -I item16.py <corpus>"""
import json, sys
from collections import Counter
from pathlib import Path
from agentprov.aer.reader import load_aer

ROOT = Path(sys.argv[1]).expanduser()
RID = "inspect.tool_event_message_id_first_of_batch@1"
c = Counter()
for line in (ROOT / "executions.jsonl").read_bytes().splitlines():
    row = json.loads(line)
    aer = load_aer(ROOT / row["paths"]["aer"], verify=True)
    hit = False
    for x in aer.records:
        s = json.dumps(x.get("rules") or x.get("rule") or "")
        if RID in s:
            hit = True
            c[f"record:{x.get('k')}"] += 1
            c[f"evf_generated_by:{(x.get('evf') or {}).get('/generated_by')}"] += 1
    c["executions_citing"] += hit
    c["executions"] += 1
print(json.dumps(dict(c), sort_keys=True))
