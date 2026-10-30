"""Verifier PC-01: shape/context stats only, never prints a token or a name."""
import hashlib, json, math, re, sys
from collections import Counter
from pathlib import Path
from agentprov.ingest.archives import iter_zip_members, open_zip
Z = Path.home() / ".agentprov/staging/10g/zenodo_23168099"
HF = re.compile(r"(?<![A-Za-z0-9_])hf_[A-Za-z0-9]{30,}")
d8 = lambda s: hashlib.sha256(s.encode()).hexdigest()[:8]
R = {"hits": [], "members": 0, "supp_hits_by_top": Counter(), "traj_hits": Counter(), "bash_members": []}
def ent(s):
    c = Counter(s); return round(-sum(v/len(s)*math.log2(v/len(s)) for v in c.values()), 2)
with open(Z / "agent-execution-decisions-supp.zip", "rb") as fp, open_zip(fp, release=False) as oz:
    for m in iter_zip_members(oz):
        R["members"] += 1
        lab = m.label or ""; p = lab.split("/")
        if p[-1].startswith(".bash") or "history" in p[-1].lower():
            R["bash_members"].append({"depth": len(p), "top": p[0], "name": p[-1][:14], "size": getattr(m, "size", None), "disp": m.disposition})
        try: t = oz.read_member(m).decode("utf-8")
        except Exception: continue
        for mt in HF.finditer(t):
            v = mt.group(0); body = v[3:]
            line = t[t.rfind("\n", 0, mt.start())+1: t.find("\n", mt.end()) if t.find("\n", mt.end()) >= 0 else len(t)]
            pre = line[:line.find(v)]
            R["supp_hits_by_top"][p[0]] += 1
            if p[0] != "environment" or len(p) != 3: continue
            R["hits"].append({"d8": d8(v), "len": len(v), "upper": sum(c.isupper() for c in body), "lower": sum(c.islower() for c in body),
              "digit": sum(c.isdigit() for c in body), "entropy": ent(body), "max_run": max(len(x.group()) for x in re.finditer(r"(.)\1*", body)),
              "pre_words": sorted(set(re.findall(r"(?i)export|HF_TOKEN|HUGGING\w*|login|--token|hf auth|huggingface-cli|echo|=|git|curl", pre))),
              "file": p[-1][:14], "member_digest": d8(t), "lines": t.count("\n")})
for z in sorted(Z.glob("trajectories_OH-*.zip")):
    with open(z, "rb") as fp, open_zip(fp, release=False) as oz:
        for m in iter_zip_members(oz):
            try: t = oz.read_member(m).decode("utf-8")
            except Exception: continue
            for mt in HF.finditer(t): R["traj_hits"][d8(mt.group(0))] += 1
R["supp_hits_by_top"] = dict(R["supp_hits_by_top"]); R["traj_hits"] = dict(R["traj_hits"])
Path(sys.argv[1]).write_text(json.dumps(R, indent=1)); print(json.dumps(R))
