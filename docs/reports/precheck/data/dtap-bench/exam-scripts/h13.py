"""H13: ASR over the 12 legal indirect tasks of DecodingTrust-Agent issue #23 (judge-level, L1 aux rows), vs the rest of
legal indirect. Counts only. Usage: python -I h13.py <l1-aux.jsonl> <out.json>"""
import collections, json, sys
T = {"biased_sentencing": {3, 6, 14, 15, 16, 17}, "conflict_concealment": {13, 14, 15, 16},
     "instruction_hijack": {15}, "negotiation_sabotage": {15}}
c = collections.defaultdict(lambda: [0, 0]); per_task = collections.defaultdict(lambda: [0, 0])
for l in open(sys.argv[1]):
    a = json.loads(l); p = a["label"].split("/")
    if len(p) < 8 or p[2] != "legal" or p[4] != "indirect":
        continue
    v = a["outcomes"].get("attack_success")
    if v is None:
        continue
    hit = p[5] in T and p[6].isdigit() and int(p[6]) in T[p[5]]
    k = ("issue23" if hit else "other") + "|" + p[0] + "/" + p[1]
    c[k][0] += int(v is True); c[k][1] += 1
    if hit:
        per_task[p[5] + "/" + p[6]][0] += int(v is True); per_task[p[5] + "/" + p[6]][1] += 1
tot = {g: [sum(v[0] for k, v in c.items() if k.startswith(g)), sum(v[1] for k, v in c.items() if k.startswith(g))] for g in ("issue23", "other")}
json.dump({"by_group_pair": {k: v for k, v in sorted(c.items())}, "totals": tot, "per_task": dict(sorted(per_task.items()))}, open(sys.argv[2], "w"), indent=1)
print(json.dumps({"totals": tot, "per_task": per_task}))
