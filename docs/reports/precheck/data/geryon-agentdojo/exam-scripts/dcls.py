"""Evidence-class audit on the j2 sample: D-class statements and their basis rules; agentdojo D rules cited natively
(not via the _unverified twin) in PROV or AER (verified_code = [] means none should be). Counts only."""
import sys, json, re
from collections import Counter
from pathlib import Path
sys.path.insert(0, __import__("os").getcwd() + "/tools/precheck")  # run from the repository root
import l2_check
C = Path.home() / ".agentprov/migration-work/precheck/geryon-agentdojo/l2-head-j2.partial"
REF = re.compile(r"(?:agentdojo|aer|apv)[A-Za-z0-9_.:-]*@[0-9]+")
dstat = Counter(); native_d = Counter(); twin = Counter(); aer_native_d = Counter(); allcls = Counter()
def cls_of(ref):
    name, _, ver = ref.partition("#")[0].rsplit("/", 1)[-1].partition("@")
    name = name.rsplit(":", 1)[-1]
    return name, ver, l2_check._rule_cls(name, ver)
for line in open(C / "executions.jsonl"):
    r = json.loads(line)
    doc = json.load(open(C / r["paths"]["prov"]["agentprov-prov/0.1"]["json"]))
    s = json.dumps(doc)
    for ref in set(REF.findall(s)):
        name, ver, c = cls_of(ref)
        allcls[f"{c}"] += 1
        if c == "D" and name.startswith("agentdojo."):
            native_d[name + "@" + ver] += 1
        if l2_check.is_twin(ref):
            twin[name] += 1
    for x in open(C / r["paths"]["aer"]):
        for ref in set(REF.findall(x)):
            name, ver, c = cls_of(ref)
            if c == "D" and name.startswith("agentdojo."):
                aer_native_d[name + "@" + ver] += 1
print("distinct-ref-per-doc classes", dict(allcls))
print("PROV docs citing a native agentdojo D rule", dict(native_d.most_common()))
print("AER records citing a native agentdojo D rule", dict(aer_native_d.most_common()))
print("twins (docs)", len(twin), sum(twin.values()))
