"""Pre-check examiner, redcode-exec-openhands: H-18 scenario-summary key-set variants by arm, and csv risky-level
subtotal rows against the sum of their scenario rows. Counts only. Usage: uv run python -I agg2.py OUT.json"""
import csv, io, json, re, sys
from collections import Counter, defaultdict
from pathlib import Path
from agentprov.ingest.archives import iter_zip_members, open_zip
from agentprov.ingest.loaders import strict_json_loads

Z = Path.home() / ".agentprov/staging/10g/zenodo_23168099/agent-execution-decisions-supp.zip"
R = {"keyset_by_arm": defaultdict(Counter), "subtotals": Counter()}
with open(Z, "rb") as fp, open_zip(fp, release=False) as oz:
    for m in iter_zip_members(oz):
        lab = m.label or ""
        mm = re.match(r"^results/OH/([^/]+)/(S[123])/(python|bash)/", lab)
        if not mm: continue
        arm = "/".join(mm.groups())
        if re.search(r"/summary/scenario_\d+_summary\.json$", lab):
            d = strict_json_loads(oz.read_member(m))
            R["keyset_by_arm"][arm]["+".join(k for k in ("duration_sec", "jsonfile") if k in d) or "neither"] += 1
        elif lab.endswith("per_scenario.csv"):
            rows = list(csv.DictReader(io.StringIO(oz.read_member(m).decode())))
            sc = [r for r in rows if (r["scenario"] or "").isdigit()]
            for r in rows:
                if (r["scenario"] or "").isdigit(): continue
                lvl = r["risky_level"]
                grp = [x for x in sc if not lvl or x["risky_level"] == lvl]
                ok = all(int(r[k]) == sum(int(x[k]) for x in grp) for k in ("success", "reject", "fail", "total"))
                R["subtotals"][f"{'average' if not lvl else 'level'}:{ok}"] += 1
R = {k: {a: dict(v) for a, v in R[k].items()} if k == "keyset_by_arm" else dict(R[k]) for k in R}
Path(sys.argv[1]).write_text(json.dumps(R, indent=1, sort_keys=True)); print(json.dumps(R, sort_keys=True))
