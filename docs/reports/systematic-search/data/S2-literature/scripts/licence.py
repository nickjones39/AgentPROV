import json,re,os,time,urllib.request,urllib.error
C="licence_cache.json"
cache=json.load(open(C)) if os.path.exists(C) else {}
def get(u,n=6000):
    try:
        with urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"agentprov-litsearch/0.1"}),timeout=30) as r: return r.read(n).decode("utf8","replace")
    except Exception: return None
def spdx_from_text(t):
    s=re.sub(r"\s+"," ",t or "")
    L=s.lower()
    if re.search(r"creative commons|cc[- ]by|cc0",L):
        if "cc0" in L or "public domain dedication" in L: return "CC0-1.0"
        v="4.0" if "4.0" in L else ("3.0" if "3.0" in L else "4.0")
        nc="noncommercial" in L.replace("-","").replace(" ","") or "non-commercial" in L or "-nc" in L
        sa="sharealike" in L.replace("-","").replace(" ","")
        nd="noderiv" in L.replace("-","").replace(" ","")
        return "CC-BY"+("-NC" if nc else "")+("-SA" if sa else "")+("-ND" if nd else "")+"-"+v
    if "permission is hereby granted, free of charge" in L or re.search(r"\bmit license\b",L): return "MIT"
    if "apache license" in L and "2.0" in L: return "Apache-2.0"
    if "gnu affero" in L: return "AGPL-3.0"
    if "gnu lesser" in L: return "LGPL-3.0"
    if "gnu general public license" in L: return "GPL-3.0" if "version 3" in L else "GPL-2.0"
    if "mozilla public license" in L: return "MPL-2.0"
    if "redistribution and use in source and binary forms" in L:
        return "BSD-3-Clause" if "neither the name" in L or "endorse" in L else "BSD-2-Clause"
    if "unlicense" in L or "this is free and unencumbered software" in L: return "Unlicense"
    if re.search(r"\bisc license\b",L): return "ISC"
    if re.search(r"open data commons|odc-by",L): return "ODC-By-1.0"
    if re.search(r"evaluation[- ]only|only (be )?used? for (the )?evaluation|for evaluation purposes only|non[- ]?redistributable|do not redistribute|non-?commercial|research (purposes )?only|academic use only|all rights reserved|not (be )?redistribut|no (commercial|redistribution)|permission of the authors",L): return "custom-restrictive"
    return None
HFMAP={"mit":"MIT","apache-2.0":"Apache-2.0","apache2.0":"Apache-2.0","apache2":"Apache-2.0","cc-by-4.0":"CC-BY-4.0","cc-by-sa-4.0":"CC-BY-SA-4.0","cc-by-nc-4.0":"CC-BY-NC-4.0","cc-by-nc-sa-4.0":"CC-BY-NC-SA-4.0","cc-by-nc-nd-4.0":"CC-BY-NC-ND-4.0","cc0-1.0":"CC0-1.0","cc-zero":"CC0-1.0","mit-license":"MIT","odc-by":"ODC-By-1.0","bsd-3-clause":"BSD-3-Clause","bsd-2-clause":"BSD-2-Clause","gpl-3.0":"GPL-3.0","agpl-3.0":"AGPL-3.0","agpl-3.0-or-later":"AGPL-3.0","openrail":"custom-restrictive","cc-by-3.0":"CC-BY-3.0","cc":"unknown","cc-by-nd-4.0":"CC-BY-ND-4.0","bsd":"BSD-3-Clause"}
def github(o,r):
    k=f"gh:{o}/{r}".lower()
    if k in cache: return cache[k]
    found=[]
    for nm in ("LICENSE","LICENSE.md","LICENSE.txt","LICENCE","COPYING","LICENSE-DATA","LICENSE_DATA","LICENSE-DATA.txt","LICENSE-CODE","LICENSE.rst","license","License.md","LICENSE-MIT","LICENSE-APACHE"):
        t=get(f"https://raw.githubusercontent.com/{o}/{r}/HEAD/{nm}",5000)
        time.sleep(0.15)
        if t and len(t)>20 and "<html" not in t[:200].lower(): found.append((nm,spdx_from_text(t),t[:80].replace("\n"," ")))
    res=None
    data=[f for f in found if "DATA" in f[0].upper()]
    main=[f for f in found if "DATA" not in f[0].upper() and "CODE" not in f[0].upper()] or [f for f in found if "CODE" in f[0].upper()]
    if found:
        pick=(data or main)[0]
        lic=pick[1] or "unknown"
        res={"licence":lic,"licence_source":f"repo file {pick[0]}"+(f" (also {', '.join(f[0] for f in found if f!=pick)})" if len(found)>1 else "")+("; data-specific licence file" if data else "; repository-level licence, data scope not stated separately")}
        if lic=="unknown": res["licence_source"]+="; text not recognised: "+pick[2][:50]
    else:
        rd=get(f"https://raw.githubusercontent.com/{o}/{r}/HEAD/README.md",60000) or get(f"https://raw.githubusercontent.com/{o}/{r}/HEAD/README.rst",60000)
        if rd is None:
            res={"licence":"unknown","licence_source":"repo unreachable or no README/LICENSE retrievable via raw.githubusercontent.com"}
        else:
            m=re.search(r"(?is)(#+\s*licen[sc]e[s]?\b.{0,400})|(licen[sc]e[ds]? under[^\n]{0,120})|(released under[^\n]{0,120})",rd)
            sp=spdx_from_text(m.group(0)) if m else None
            if sp: res={"licence":sp,"licence_source":"README licence statement (no LICENSE file in repo root)"}
            else: res={"licence":"none","licence_source":"no LICENSE file in repo root and no licence statement in README"}
    cache[k]=res; json.dump(cache,open(C,"w")); return res
def hf(did):
    k=f"hf:{did}"
    if k in cache: return cache[k]
    try: meta=json.load(urllib.request.urlopen(urllib.request.Request(f"https://huggingface.co/api/datasets/{did}",headers={"User-Agent":"agentprov-litsearch/0.1"}),timeout=30))
    except urllib.error.HTTPError as e:
        res={"licence":"unknown","licence_source":f"HF dataset API returned {e.code} (private, gated or removed)"}; cache[k]=res; return res
    except Exception as e:
        res={"licence":"unknown","licence_source":"HF API unreachable"}; return res
    lic=(meta.get("cardData") or {}).get("license")
    if isinstance(lic,list): lic=lic[0] if lic else None
    if lic:
        sp=HFMAP.get(lic.lower())
        if lic.lower()=="other":
            ln=(meta.get("cardData") or {}).get("license_name"); 
            lf=[s["rfilename"] for s in meta.get("siblings",[]) if s["rfilename"].upper().startswith("LICENSE")]
            txt=get(f"https://huggingface.co/datasets/{did}/resolve/main/{lf[0]}",5000) if lf else None
            sp=spdx_from_text(txt) if txt else None
            res={"licence":sp or "unknown","licence_source":f"HF dataset card license: other"+(f" ({ln})" if ln else "")+(f"; read {lf[0]}" if lf else "")}
        else: res={"licence":sp or lic,"licence_source":f"HF dataset card metadata license: {lic}"}
    else:
        tags=[t for t in meta.get("tags",[]) if t.startswith("license:")]
        if tags: res={"licence":HFMAP.get(tags[0].split(":",1)[1],tags[0].split(":",1)[1]),"licence_source":"HF dataset tag "+tags[0]}
        else: res={"licence":"none","licence_source":"HF dataset card has no license field or tag"}
    if meta.get("gated"): res["licence_source"]+="; dataset is gated ("+str(meta.get("gated"))+")"
    cache[k]=res; json.dump(cache,open(C,"w")); return res
ZMAP={"cc-by-4.0":"CC-BY-4.0","mit-license":"MIT","apache2.0":"Apache-2.0","cc-zero":"CC0-1.0","cc-by-nc-4.0":"CC-BY-NC-4.0","cc-by-sa-4.0":"CC-BY-SA-4.0","cc-by-nc-nd-4.0":"CC-BY-NC-ND-4.0","agpl-3.0-or-later":"AGPL-3.0","other-open":"unknown","gpl-3.0":"GPL-3.0"}
def zenodo(zid):
    k=f"zen:{zid}"
    if k in cache: return cache[k]
    try: d=json.load(urllib.request.urlopen(urllib.request.Request(f"https://zenodo.org/api/records/{zid}",headers={"User-Agent":"agentprov-litsearch/0.1"}),timeout=30))
    except Exception as e: return {"licence":"unknown","licence_source":"Zenodo API unreachable"}
    m=d["metadata"]; lid=(m.get("license") or {}).get("id")
    if lid: res={"licence":ZMAP.get(lid,lid),"licence_source":f"Zenodo record metadata licence: {lid}"}
    else: res={"licence":"none","licence_source":"Zenodo record has no licence field"}
    if m.get("access_right")!="open": res["licence_source"]+=f"; access_right={m.get('access_right')}"
    cache[k]=res; json.dump(cache,open(C,"w")); return res
def for_url(u):
    m=re.search(r"github\.com/([\w.-]+)/([\w.-]+)",u)
    if m: return github(m.group(1),re.sub(r"\.git$","",m.group(2)))
    m=re.search(r"huggingface\.co/datasets/([\w.-]+/[\w.-]+)",u)
    if m: return hf(m.group(1))
    m=re.search(r"zenodo\.(?:org/records?/)?(\d+)",u)
    if m: return zenodo(m.group(1))
    return {"licence":"unknown","licence_source":"host not covered by automatic licence check: "+u[:60]}
if __name__=="__main__":
    import sys
    for u in sys.argv[1:]: print(u,for_url(u))
