# ruff: noqa  (precheck examiner script for whistlebench, read-only; counts only)
"""AER pass over the j2 scratch corpus: judge models per experiment, mapped judgements per log vs the L1 raw tallies,
token-shaped values in actor records (count only). Usage: aer_pass.py <corpus> <l1-units.jsonl> <out.json>"""
import json, re, sys, hashlib
from collections import Counter, defaultdict
from multiprocessing import Pool
from pathlib import Path
from agentprov.aer.reader import load_aer
ROOT=Path(sys.argv[1]).expanduser(); GH=re.compile(r"(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{30,}")
ACC=re.compile(r"/(?:Users|home)/([^/\s\"'<>\\]{1,64})/"); GEN={"ubuntu","user","root","runner","app","node","admin","agent","dev","test","shared"}
ORIG={}
for l in open(ROOT/"raw/origins.jsonl"):
    o=json.loads(l); c=(o.get("origin") or {}).get("container")
    if c: ORIG[o["sha256"]]="sha256:"+c.removeprefix("sha256:")
L1={}
for l in open(Path(sys.argv[2]).expanduser()):
    r=json.loads(l); L1["sha256:"+r["sha256"].removeprefix("sha256:")]=r
def one(row):
    a=load_aer(ROOT/row["paths"]["aer"],verify=True)
    prim=ORIG.get(next(x["sha256"] for x in row["raw"] if x["role"]=="primary"))
    out={"prim":prim,"judges":[],"j":{},"tok":Counter(),"acct":Counter()}
    for tier,rel in (("aer",row["paths"]["aer"]),("prov",row["paths"]["prov"]["agentprov-prov/0.1"]["json"])):
        txt=(ROOT/rel).read_text(encoding="utf-8",errors="replace")
        for m in ACC.finditer(txt):
            if m.group(1).lower() not in GEN: out["acct"][f"{tier}:{hashlib.sha256(m.group(1).encode()).hexdigest()[:8]}"]+=1
        out["acct"][f"{tier}:gh-token"]+=len(GH.findall(txt))
    for r in a.records:
        k=r.get("k")
        if k=="actor":
            if r.get("kind")=="judge": out["judges"].append((r.get("model") or {}).get("requested"))
            s=json.dumps(r)
            if GH.search(s):
                for p in ("code","ext"): 
                    if GH.search(json.dumps(r.get(p))): out["tok"][f"actor:{r['id']}:{p}"]+=1
        elif k=="judgement":
            out["j"][r.get("name")]=r.get("value")
    if GH.search(json.dumps(a.header)): out["tok"]["header"]+=1
    return out
if __name__=="__main__":
    rows=[json.loads(l) for l in open(ROOT/"executions.jsonl")]
    with Pool(2) as p: res=p.map(one,rows,chunksize=50)
    lab_of={}
    for s,r in L1.items(): lab_of[s]=r
    acct=defaultdict(lambda: {"strings":0,"executions":0,"exps":set()}); judge=Counter(); tok=Counter(); per_log=defaultdict(Counter); miss=0
    for o in res:
        r=lab_of.get(o["prim"])
        if r is None: miss+=1; continue
        exp=r["facets"]["experiment"]
        judge[f"{exp}|{'+'.join(sorted(set(filter(None,o['judges'])))) or 'none'}"]+=1
        for k,v in o["tok"].items(): tok[f"{exp}|{k}"]+=1
        for k,v in o["acct"].items():
            if v: acct[k]["strings"]+=v; acct[k]["executions"]+=1; acct[k]["exps"].add(exp)
        for n,v in o["j"].items():
            if n.startswith(("email_whistleblowing.","refusal","test_awareness.","deliberation_analysis","gov_snitching","media_snitching","internal_snitching")):
                per_log[r["label"]][f"score.{n}={json.dumps(v)}"]+=1
    # mapping check: AER judgement tallies per sampled log vs the L1 raw tallies of the same label
    cmp=Counter(); bad=[]
    for lab,c in per_log.items():
        r=next(x for x in L1.values() if x["label"]==lab)
        raw=Counter({f"{k}={v}" if not k.startswith("score.") else f"{k}={v}":n for k,d in r["outcomes"].items() for v,n in d.items()})
        if raw==c: cmp["equal"]+=1
        else: cmp["differ"]+=1; bad.append(lab)
    json.dump({"executions":len(res),"unmatched_primary":miss,"judge_models_by_experiment":dict(sorted(judge.items())),
               "token_shaped_in_aer_by_experiment":dict(sorted(tok.items())),"judgement_vs_l1_raw_per_log":dict(cmp),"differ_labels":bad[:20],"account_digests_in_outputs":{k:{**v,"exps":sorted(v["exps"])} for k,v in sorted(acct.items())}},
              open(sys.argv[3],"w"),indent=1)
    print(dict(cmp), miss)
