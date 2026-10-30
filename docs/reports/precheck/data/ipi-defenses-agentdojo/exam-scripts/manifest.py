"""H11: docs/MANIFEST.sha256 of the deposit against the level-1 zip members (agentprov.ingest.archives, in memory, no
extraction). Listed paths are matched against member labels by suffix. Counts only. Usage (repo root): uv run python -I manifest.py"""
import hashlib, json, re
from pathlib import Path
from agentprov.ingest.archives import iter_zip_members, open_archive
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.paths import open_evidence
Z = Path.home() / ".agentprov/staging/10c/zenodo-22011266"
lim = IngestLimits().replace(max_artefact_bytes=1 << 40)
fh = open_evidence(str(Z), "AgentSecurity-IPIDefenses-v4.0.zip", lim)
arc = open_archive(fh, lim, release=False)
digests = {}
man = None
for m in iter_zip_members(arc, None, lim):
    if m.disposition != "selected": continue
    data = arc.read_member(m)
    digests[m.label] = hashlib.sha256(data).hexdigest()
    if m.label.endswith("docs/MANIFEST.sha256"): man = data.decode("utf-8", "replace")
lines = [l for l in (man or "").splitlines() if l.strip() and not l.startswith("#")]
res = {"members_level1": len(digests), "manifest_found": man is not None, "manifest_lines": len(lines), "match": 0, "mismatch": 0,
       "listed_not_found": 0, "members_not_listed": 0, "tars_listed_and_matching": 0, "unparsed_lines": 0}
listed = set()
for l in lines:
    mm = re.match(r"^([0-9a-fA-F]{64})\s+\*?(.+)$", l.strip())
    if not mm: res["unparsed_lines"] += 1; continue
    h, p = mm.group(1).lower(), mm.group(2).strip().lstrip("./")
    cands = [k for k in digests if k == p or k.endswith("/" + p)]
    if not cands: res["listed_not_found"] += 1; continue
    listed.update(cands)
    if digests[cands[0]] == h:
        res["match"] += 1; res["tars_listed_and_matching"] += p.endswith(".tar.gz")
    else: res["mismatch"] += 1
res["members_not_listed"] = len([k for k in digests if k not in listed and not k.endswith("MANIFEST.sha256")])
print(json.dumps(res))
