import json,re,os,glob,sys
S="."
O="~/.agentprov/migration-work/syssearch/S2-literature/"
pool=json.load(open("pool_s1.json")); p2=json.load(open("pass2_cache.json")); p3=json.load(open("pass3_cache.json")); pc=json.load(open("probe_cache.json"))
ghv=json.load(open("ghv_cache.json")) if os.path.exists("ghv_cache.json") else {}
web={}
for f in ("ghweb_cache.json","ghweb_cache2.json","ghweb_cache3.json"):
    if os.path.exists(f): web.update({k:v for k,v in json.load(open(f)).items() if not v.get("err")})
hfz=json.load(open("hfzen_cache.json"))
zenv=json.load(open("zen_verify.json"))["records"]
queue={q[0]:q for q in json.load(open("queue.json"))}
STRONGDIR=re.compile(r"^(runs?|logs?|run_?logs?|trajector\w*|traces?|transcripts?|episodes?|rollouts?|conversations?|sessions?|rounds?|agent_?runs?|raw_?traces?)$|trajector|transcript|rollout|traces$|_traces|traces_",re.I)
MEDDIR=re.compile(r"^(results?|outputs?|raw\w*|experiments?|artifacts?|records?|evaluations?|eval\w*)$",re.I)
STR=re.compile(r"trajector|\blogs?\b|traces?|transcripts?|rollouts?|episodes?|runs\b",re.I)
OWN={"2506.12104":["https://github.com/SaFo-Lab/DRIFT"],"2602.03117":["https://github.com/leolee99/AgentDyn"],"2608.27496":["https://github.com/xhOwenMa/ROPE"],"2606.15057":["https://github.com/xhOwenMa/AutoDojo"],"2509.25624":["https://github.com/amazon-science/MultiTurnAgentAttack"],"2607.05120":["https://github.com/compsec-snu/adi"],"2410.09024":["https://huggingface.co/datasets/ai-safety-institute/AgentHarm"],"2410.02644":["https://github.com/agiresearch/ASB"]}
KNOWN={"2406.13352":"AgentDojo","2608.27496":"ROPE","2606.15057":"AutoDojo","2602.16901":"AgentLAB","2602.03117":"AgentDyn","2506.12104":"DRIFT","2410.09024":"AgentHarm","2607.05120":"ADI","2509.25624":"STAC","2606.11063":"CIAware-Bench","2410.02644":"ASB (reviewed by Agent Security Tools Survey)"}
def repo_evidence(link):
    """strong = a runs/logs/trajectories/traces/transcripts/episodes-style directory or file group holding >=3 data files;
       med = results/outputs/raw/experiments style directory with data files; generic = any data directory."""
    m=re.search(r"github\.com/([\w.-]+)/([\w.-]+)",link)
    if m:
        k=f"{m.group(1)}/{re.sub(r'.git$','',m.group(2))}".lower()
        if k in ghv and "n_dataish" in ghv[k]:
            g=ghv[k]; strong=False; med=False; sn=0
            for d,cnt,sz in g["dataish_dirs"]:
                segs=d.split("/")
                if any(STRONGDIR.search(sg) for sg in segs) and cnt>=3: strong=True; sn+=cnt
                elif any(MEDDIR.match(sg) for sg in segs) and cnt>=3: med=True
            if not strong and g["n_dataish"]>=5 and any(re.search(r"trajector|transcript|rollout|episode|(^|/)traces?(/|\.|_)",sp,re.I) for sp in g["sample"]): strong=True
            return {"kind":"github-api","url":g["url"],"strong":strong,"med":med,"generic":g["n_dataish"]>0,"n":g["n_dataish"],"detail":g["dataish_dirs"][:4],"licence":g.get("licence_line"),"gated":False,"nfiles":g["n_files"]}
        if k in web:
            w=web[k]; strong=False; med=False; sn=0
            names=[n for n,ct in w["top"]]
            for dn,dv in w["dirs"].items():
                segs=dn.split("/")
                if any(STRONGDIR.search(sg) for sg in segs) and dv["total"]>=3: strong=True; sn+=dv["total"]
                elif any(MEDDIR.match(sg) for sg in segs) and dv["total"]>=3: med=True
            # top-level strong dir that was not expanded (only first 4 log-ish dirs expanded)
            for n,ct in w["top"]:
                if ct=="directory" and STRONGDIR.search(n) and n not in w["dirs"]: strong=True
            generic=any(re.match(r"^(data|datasets?|release\w*|benchmark\w*|samples?|results?)$",s,re.I) for s in names)
            tot=sum(v["total"] for v in w["dirs"].values())
            lic=[n for n,ct in w["top"] if n.upper().startswith("LICEN")]
            return {"kind":"github-web","url":w["url"],"strong":strong,"med":med,"generic":generic,"n":tot,"detail":{d:(v["total"],[i[0] for i in v["items"][:3]]) for d,v in list(w["dirs"].items())[:4]},"licence":lic[0] if lic else None,"gated":False}
        return None
    m=re.search(r"huggingface\.co/datasets/([\w.-]+/[\w.-]+)",link)
    if m:
        r=hfz.get("hf:"+m.group(1))
        if not r or r.get("err"): return {"kind":"hf","url":link,"err":(r or {}).get("err","unverified"),"strong":False,"med":False,"generic":False,"n":0}
        files=r.get("files",[]); allf=" ".join(files)
        strong=len(re.findall(r"trajector|trace|transcript|rollout|episode|session|(^| )runs?/|(^| )logs?/|conversation",allf,re.I))>=2 or bool(re.search(r"trajector|trace|transcript|rollout|episode",m.group(1),re.I))
        return {"kind":"hf","url":r["url"],"strong":strong,"med":False,"generic":r["n_files"]>2,"n":r["n_files"],"detail":files[:5],"licence":r.get("license"),"gated":r.get("gated")}
    m=re.search(r"zenodo\.(\d+)",link) or re.search(r"zenodo\.org/records?/(\d+)",link)
    if m:
        r=hfz.get("zen:"+m.group(1)) or zenv.get(m.group(1))
        if not r or r.get("err"): return {"kind":"zenodo","url":link,"err":"unverified","strong":False,"med":False,"generic":False,"n":0}
        fl=[f for f,_ in r.get("files",[])]; allf=" ".join(fl)
        big=sum(s for _,s in r.get("files",[]))>200_000
        strong=bool(re.search(r"trajector|trace|transcript|rollout|episode|runs|logs",allf,re.I))
        return {"kind":"zenodo","url":r.get("url",link),"strong":strong,"med":False,"generic":big and not allf.lower().endswith(".pdf"),"n":r.get("n_files",0),"detail":fl[:4],"licence":r.get("license"),"gated":r.get("access")!="open"}
    return None

EXTABS=re.compile(r"(extend\w*|built on|build on|builds on|based on|fork|derived from|variant of|adapt\w*|on top of|augment\w*|port\w*)\W+(\w+\W+){0,8}agentdojo|agentdojo[- ](based|style|derived|inspired)|(extend|extends|extending|extension of|fork of|variant of)\W+(\w+\W+){0,3}agentdojo|agentdojo\W+(\w+\W+){0,6}(extension|variant)",re.I)
EXTBODY=re.compile(r"\b(we|our)\b[^.]{0,80}\b(extend|build|built|fork|adapt|modif|augment)\w*[^.]{0,80}agentdojo",re.I)
MANUAL_EXT={"2602.03117","2606.15057","2607.05120","2608.27496"}
SEC=re.compile(r"(prompt injection|injection|jailbreak|harm|misuse|safety|malicious|adversarial|red[- ]team|attack|security|unsafe|backdoor|poison|privacy|leak)",re.I)
def relation(p):
    ax=p["arxiv"]; t=(p["title"] or "")+" "+(p["abstract"] or ""); f=p["flags"]
    v=p3.get(ax,{}) if ax else {}
    nb=v.get("n_body",0) if not v.get("err") else 0
    if ax=="2406.13352": return "none"  # the root
    if ax in MANUAL_EXT: return "extends"
    if f["ad_abs"] and EXTABS.search(t): return "extends"
    if any(EXTBODY.search(s) for s in v.get("ext",[])) and nb>=5: return "extends"
    if f["ad_abs"] or nb>=5: return "uses"
    if f["ad_cit"] or f["ad_ft"] or nb>=1: return "cites_only"
    return "none"
def classify_release(p, ev_list, av_log):
    ok=[e for e in ev_list if not e.get("err")]
    title_traj=bool(re.search(r"trajector|\btraces?\b|transcripts?|rollouts?",p["title"] or "",re.I))
    abs_rel=p["flags"]["log"] and p["flags"]["rel"]
    if any(e["strong"] for e in ok): return "yes","high" if any(e["strong"] and e["kind"]!="github-web" for e in ok) else "medium"
    if any(e["med"] for e in ok) and av_log: return "yes","medium"
    if title_traj and any((e["generic"] or e["med"]) and e["n"]>=50 for e in ok): return "yes","medium"
    if any(e["med"] for e in ok) or (any(e["generic"] for e in ok) and (av_log or abs_rel or title_traj)) or (av_log and not ok): return "unclear","low"
    return "no",None
def fmt_of(ev_list):
    s=set()
    for e in ev_list:
        for d in (e.get("detail") or []):
            txt=json.dumps(d)
            for ext in ("jsonl","json","parquet","csv","eval","zip","tar","gz","zst"):
                if re.search(r"\."+ext+r"\b",txt): s.add(ext)
    return sorted(s)

def bench_name(t):
    m=re.match(r"^\W*([A-Za-z0-9][\w\-\.\+\^ ]{1,40}?)\s*[:—\-–]\s",t or "")
    if m and re.search(r"(bench|arena|dojo|gym|world|hazard|drift|attack|harm|bed|suite|eval|trap|guard|arena|dataset)",m.group(1),re.I): return m.group(1).strip()
    m=re.search(r"\b([A-Z][\w\-\+]*(?:Bench|Arena|Dojo|Gym|Harm|Hazard)[\w\-\+]*)\b",t or "")
    return m.group(1) if m else None
def venue_of(p):
    v=p.get("venue")
    if v: return v
    d=p.get("doi") or ""
    if d.startswith("10.48550"): return "arXiv"
    if d.startswith("10.5281"): return "Zenodo"
    return None
def mk(p,k):
    ax=p["arxiv"]
    return {"id": ("arxiv:"+ax) if ax else (("doi:"+p["doi"]) if p.get("doi") else k),
      "title":p["title"],"year":p["year"],"venue":venue_of(p),"doi":p.get("doi"),"arxiv":ax,
      "url":("https://arxiv.org/abs/"+ax) if ax else (p.get("url") or (("https://doi.org/"+p["doi"]) if p.get("doi") else None)),
      "relation_to_agentdojo":relation(p),"benchmark_name":bench_name(p["title"]),
      "security_topic":bool(SEC.search((p["title"] or "")+" "+(p["abstract"] or ""))),
      "found_in":p["sources"],"known_already":KNOWN.get(ax) if ax else None,"stage1_retained":not p["s1_exclusion"]}
records=[]
for k,p in pool.items():
    r=mk(p,k)
    r.update({"releases_logs":"unclear","log_location_urls":[],"format":[],"licence":None,"gated":None,"decision":"exclude","exclusion_reason":None,"stage":"title_abstract","evidence":None})
    ax=p["arxiv"]
    if p["s1_exclusion"]:
        r["exclusion_reason"]=p["s1_exclusion"]; records.append(r); continue
    # retained at stage 1
    if ax and p.get("probe") in ("links","nolinks"):
        v2=p2.get(ax)
        r["stage"]="full_text"
        if ax=="2406.13352":
            r["decision"]="exclude"; r["exclusion_reason"]="root benchmark paper (AgentDojo); its own run logs are in the ethz-spylab/agentdojo repository, handled as a known source"; r["releases_logs"]="yes"; r["log_location_urls"]=["https://github.com/ethz-spylab/agentdojo (runs/)"]; records.append(r); continue
        if p["probe"]=="nolinks" or not v2 or v2.get("err"):
            r["releases_logs"]="no"; r["exclusion_reason"]="full text: no public data/code repository link found" + ("" if (pc.get(ax) or {}).get("src")=="html" else " (only the abstract page was retrievable)"); records.append(r); continue
        q=queue.get(ax)
        links=(q[2] if q else v2.get("own_links",[]))
        if ax in OWN: links=OWN[ax]; q=q or (ax,["AD"],links)
        av_log=any(STR.search(s) for s in v2.get("av_sents",[]))
        if not q:
            r["releases_logs"]="no"; r["exclusion_reason"]="full text: links found are code-only or unrelated; no statement of releasing logs/trajectories and paper not linked to AgentDojo/security-benchmark criteria for repository inspection"; r["log_location_urls"]=[]; records.append(r); continue
        evs=[e for e in (repo_evidence(l) for l in links) if e]
        rl,conf=classify_release(p,evs,av_log)
        r["releases_logs"]=rl; r["evidence_confidence"]=conf
        r["log_location_urls"]=[e["url"] for e in evs if (e["strong"] or e["med"] or e["generic"])][:5]
        r["format"]=fmt_of(evs)
        r["licence"]=next((e["licence"] for e in evs if e.get("licence")),None)
        r["gated"]=any(bool(e.get("gated")) for e in evs) or None
        r["evidence"]={"paper_statement":[s for s in v2.get("av_sents",[]) if STR.search(s)][:2],"repos":[{"url":e["url"],"kind":e["kind"],"strong":e["strong"],"n":e["n"],"detail":e["detail"] if "detail" in e else None} for e in evs][:4]}
        if rl=="yes" and not (r["gated"] and not r["log_location_urls"]):
            r["decision"]="include"
        elif rl=="unclear":
            r["exclusion_reason"]="unconfirmed: release of logs/trajectories possible or claimed but no per-run machine-readable logs confirmed in the repository/dataset (generic data directory, unverified or unreachable link)"
        else:
            r["exclusion_reason"]="repository/dataset inspected: code, task definitions or aggregate results only; no per-run logs found"
        records.append(r); continue
    # non-arXiv retained
    doi=p.get("doi") or ""
    m=re.search(r"zenodo\.(\d+)",doi)
    r["stage"]="full_text" if m else "title_abstract"
    if m:
        z=zenv.get(m.group(1))
        if z and not z.get("err"):
            fl=[f for f,_ in z["files"]]
            ev=repo_evidence("https://zenodo.org/records/"+m.group(1))
            r["log_location_urls"]=["https://zenodo.org/records/"+m.group(1)]
            r["licence"]=z.get("license"); r["format"]=sorted({os.path.splitext(f)[1].lstrip(".") for f in fl})
            pdf_only=all(f.lower().endswith((".pdf",".html",".docx",".md")) for f in fl)
            desc=(z.get("desc") or "")
            if pdf_only or z.get("type")=="publication" and not re.search(r"trajector|execution logs|run logs|traces",desc,re.I):
                r["releases_logs"]="no"; r["exclusion_reason"]="Zenodo record holds the paper/preprint or documents only; no run logs"
            elif ev and (ev["strong"] or re.search(r"trajector|execution logs?|run logs?|\btraces?\b|per-episode|transcripts?",desc,re.I)):
                r["releases_logs"]="unclear" ; r["exclusion_reason"]="Zenodo archive described as containing runs/traces; archive contents not machine-verified (listed for manual follow-up)"
            else:
                r["releases_logs"]="no"; r["exclusion_reason"]="Zenodo record: code/package or aggregate results; no per-run logs identified from the record description"
        else:
            r["exclusion_reason"]="Zenodo record not retrievable (410/err)"
    else:
        t=(p["title"] or "")+" "+(p["abstract"] or "")
        r["exclusion_reason"]="non-arXiv publication; publisher full text not retrieved; no statement of releasing logs/trajectories in the title/abstract"
        if p["flags"]["log"] and p["flags"]["rel"]:
            r["exclusion_reason"]="non-arXiv publication; abstract mentions release of logs/data but full text and data location not retrievable automatically (manual follow-up)"
            r["releases_logs"]="unclear"
    records.append(r)

import licence
BLOCK=lambda l: l in ("none","custom-restrictive") or ("-ND" in (l or ""))
def apply_licence(r):
    urls=r.get("log_location_urls") or []
    urls=[u for u in urls if u.startswith("http") and re.search(r"github\.com|huggingface\.co|zenodo",u)]
    if not urls:
        r.setdefault("licence",None); r["licence_source"]=None
        return
    per={}
    for u in urls[:3]: per[u]=licence.for_url(u)
    prim=per[urls[0]]
    r["licence"]=prim["licence"]; r["licence_source"]=prim["licence_source"]; r["licence_per_artefact"]={u:v["licence"] for u,v in per.items()}
    if r.get("decision")=="include" and BLOCK(r["licence"]):
        why={"none":"no licence on the released artefact (no LICENSE file/dataset-card licence/README statement)","custom-restrictive":"licence does not allow redistributing derived data (custom-restrictive / evaluation-only / non-redistributable)"}.get(r["licence"],"licence forbids derivatives (ND)")
        r["decision"]="exclude"; r["exclusion_reason"]="licence: "+why+" - excluded from conversion; logs otherwise qualify"
        r["licence_excluded"]=True
    elif r.get("decision")=="include" and r["licence"]=="unknown":
        r["licence_check_needed"]=True
    if r.get("licence") and "-NC" in str(r["licence"]): r["licence_note"]="non-commercial licence: derived data may be redistributed only for non-commercial use"
for r in records:
    if r.get("log_location_urls"): apply_licence(r)
    else: r["licence"]=None; r["licence_source"]=None
