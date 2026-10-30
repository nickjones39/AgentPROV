"""Where does the arm directory (e2e/<condition>[_runN]) appear in the scratch AER/SEM/PROV? Counts and pointers only."""
import collections
import glob
import json
import re
import sys

root = sys.argv[1]
ARM = re.compile(r"e2e/(?:tap|seeded_pair|baseline|persona_v3)\w*")
ptrs = collections.Counter()
ext_keys = collections.Counter()
task_attack = collections.Counter()


def walk(o, p, hits):
    if isinstance(o, dict):
        for k, v in o.items():
            walk(v, p + "/" + k, hits)
    elif isinstance(o, list):
        for v in o:
            walk(v, p + "/*", hits)
    elif isinstance(o, str) and ARM.search(o):
        hits.add(p)


for f in glob.glob(root + "/aer/*/*.aer.jsonl"):
    with open(f) as fh:
        for line in fh:
            r = json.loads(line)
            hits = set()
            walk(r, "", hits)
            for h in hits:
                ptrs[("aer", r.get("k"), h)] += 1
            if r.get("k") == "execution":
                t = r.get("task", {})
                task_attack[("attack_id_null" if t.get("attack_id") is None else "attack_id_set")] += 1
                for k in sorted(r.get("ext", {}).get("agentdojo", {})):
                    ext_keys[k] += 1
for kind, pat in (("sem", "/sem/*/*/*.jsonl"), ("prov", "/prov/*/*/*.json")):
    for f in glob.glob(root + pat):
        with open(f) as fh:
            s = fh.read()
        ptrs[(kind, "files_with_arm_string", "")] += 1 if ARM.search(s) else 0
        ptrs[(kind, "files", "")] += 1
for k, v in sorted(ptrs.items()):
    print(k, v)
print("ext.agentdojo keys:", dict(ext_keys))
print("task.attack_id:", dict(task_attack))
