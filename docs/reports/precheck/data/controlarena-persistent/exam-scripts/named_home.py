"""Distinct /home/<name>/ account names in the named-home log of batch-runs (L1-06 account:home-dir:named).

Reads the pinned tar.zst through agentprov.ingest (streaming, no extraction); prints counts, a generic/named split and
truncated sha256 digests of names only, never a name. Usage: uv run python -I named_home.py <tar.zst> <label-substring>
"""
import collections, hashlib, io, json, re, sys
sys.path.insert(0, "tools/precheck")
from agentprov.ingest.archives import iter_zip_members, open_archive, open_zip
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.paths import open_evidence
import l1_scan as L

path, want = sys.argv[1], sys.argv[2]
lim = IngestLimits().replace(max_artefact_bytes=1 << 40, max_member_bytes=1 << 31)
rx = re.compile(r"/home/([^/\s\"'<>\\]{1,64})/"); ux = re.compile(r"/Users/([^/\s\"'<>\\]{1,64})/")
d, f = path.rsplit("/", 1)
out = {"logs": 0}
with open_evidence(d, f, lim) as h:
    arc = open_archive(h, lim, release=False)
    for m in iter_zip_members(arc, lambda lab: lab.endswith(".eval") and want in lab, lim, lambda lab: None):
        if m.disposition != "selected" or m.label is None or want not in m.label:
            continue
        data = arc.read_member(m); out["logs"] += 1
        z = open_zip(io.BytesIO(data), lim, release=False, depth=2)
        names = collections.Counter(); users = collections.Counter()
        for zm in iter_zip_members(z, lambda lab: lab.endswith(".json"), lim, lambda lab: None):
            if zm.disposition != "selected":
                continue
            txt = z.read_member(zm).decode("utf-8", "replace")
            names.update(rx.findall(txt)); users.update(ux.findall(txt))
        named = {n: c for n, c in names.items() if n.lower() not in L.GENERIC_ACCOUNTS}
        out.update({"home_occurrences": sum(names.values()), "distinct_home": len(names),
                    "generic_distinct": len(names) - len(named),
                    "named": {hashlib.sha256(n.encode()).hexdigest()[:10]: {"occ": c, "len": len(n), "lower_alpha": n.isalpha() and n.islower()} for n, c in named.items()},
                    "users_dir_occurrences": sum(users.values())})
print(json.dumps(out, indent=1))
