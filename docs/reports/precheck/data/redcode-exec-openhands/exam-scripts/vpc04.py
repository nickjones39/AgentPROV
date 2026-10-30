"""Verifier PC-04: shape + context booleans for watched /home names; never prints a name."""
import hashlib, json, re, sys
from collections import Counter, defaultdict
from pathlib import Path
from agentprov.ingest.archives import iter_zip_members, open_zip
from agentprov.ingest.loaders import strict_json_loads
Z = Path.home() / ".agentprov/staging/10g/zenodo_23168099"
HOME = re.compile(r"/home/([^/\s\"'<>\\:]{1,64})/")
d8 = lambda s: hashlib.sha256(s.encode()).hexdigest()[:8]
MARK = {"homebrew": "/opt/homebrew", "snap": "/snap/bin", "conda": "conda", "openhands_dir": "/openhands/", "micromamba": "micromamba",
        "poetry": "pypoetry", "dotlocal": ".local/bin", "cargo": ".cargo", "nvm": ".nvm", "usr_games": "/usr/games", "workspace": "/workspace"}
R = defaultdict(Counter); shapes = {}; arts = defaultdict(set); inprompt = Counter()
for z in sorted(Z.glob("trajectories_OH-*.zip")):
    with open(z, "rb") as fp, open_zip(fp, release=False) as oz:
        for m in iter_zip_members(oz):
            if m.disposition != "selected": continue
            ev = strict_json_loads(oz.read_member(m))
            first_user = next((json.dumps(e) for e in ev if e.get("source") == "user"), "")
            for e in ev:
                s = json.dumps(e, ensure_ascii=False)
                for n in set(HOME.findall(s)):
                    k = d8(n); arts[k].add(m.label)
                    shapes[k] = {"len": len(n), "alpha": n.isalpha(), "lower": n.islower(), "has_digit": any(c.isdigit() for c in n), "has_dot_or_dash": bool(re.search(r"[.\-_]", n))}
                    if n in first_user: inprompt[k] += 1
                    for mt in re.finditer(re.escape("/home/" + n + "/"), s):
                        ctx = s[max(0, mt.start() - 400): mt.end() + 400]
                        for lab, w in MARK.items():
                            if w in ctx: R[k][lab] += 1
                        R[k]["src=" + str(e.get("source"))] += 1
print(json.dumps({"artefacts": {k: len(v) for k, v in arts.items()}, "shapes": shapes, "in_first_user_msg": inprompt, "ctx": R}, indent=0, default=dict))
