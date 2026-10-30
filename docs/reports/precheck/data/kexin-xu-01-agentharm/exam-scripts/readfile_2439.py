# ruff: noqa  (precheck examiner script for kexin-xu-01-agentharm; read-only; counts only)
"""H-09 / #2439: of the failed read_file tool executions in the j2 scratch corpus, how many name a file that the benchmark
bundles (basename present under src/inspect_evals/agentharm at the pin, git blobs)? Counts only.
Usage: uv run python -I readfile_2439.py <repo-root> <bare> <commit> <scratch corpus> <out.json>"""
import json, sys
from collections import Counter
from pathlib import Path
ROOT = Path(sys.argv[1]); sys.path.insert(0, str(ROOT / "tools/precheck"))
from l1_scan import GitSource  # noqa: E402
BARE, COMMIT, C, OUT = sys.argv[2], sys.argv[3], Path(sys.argv[4]).expanduser(), Path(sys.argv[5])
names = {e.label.rsplit("/", 1)[-1] for e in GitSource(Path(BARE), COMMIT, ["src/inspect_evals/agentharm"]).entries()}
c = Counter()
for line in (C / "executions.jsonl").read_text().splitlines():
    r = json.loads(line)
    recs = [json.loads(x) for x in (C / r["paths"]["aer"]).read_text().splitlines() if x]
    split = "B" if recs[0]["task"]["suite"].endswith("benign") else "H"
    for x in recs:
        if x.get("k") == "tool_execution" and x.get("name") == "read_file":
            fp = str((x.get("args") or {}).get("file") or (x.get("args") or {}).get("file_path") or (x.get("args") or {}).get("path") or "")
            b = fp.replace("\\", "/").rsplit("/", 1)[-1]
            c[f"{split}:{x.get('status')}:{'bundled_name' if b in names else 'other_name'}"] += 1
OUT.write_text(json.dumps(dict(sorted(c.items())), indent=1) + "\n"); print(dict(sorted(c.items())))
