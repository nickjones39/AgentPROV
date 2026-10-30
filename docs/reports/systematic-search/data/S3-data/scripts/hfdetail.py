import sys, json, time, urllib.request, urllib.parse, datetime, urllib.error
ids=[l.strip() for l in open(sys.argv[1]) if l.strip()]; out=open(sys.argv[2],'a')
def get(url, raw=False):
    for i in range(3):
        try:
            r=urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'agentprov-research/1.0'}),timeout=60).read()
            return r.decode('utf8','replace') if raw else json.loads(r)
        except urllib.error.HTTPError as e:
            if e.code in (401,403,404): return {'error':e.code}
            time.sleep(3*(i+1))
        except Exception as e: time.sleep(3*(i+1))
    return {'error':'fail'}
for id in ids:
    ts=datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')
    d=get(f'https://huggingface.co/api/datasets/{id}?blobs=true')
    rec={'id':id,'ts':ts}
    if 'error' in d: rec['error']=d['error']
    else:
        sib=d.get('siblings',[])
        rec.update({'gated':d.get('gated'),'private':d.get('private'),'downloads':d.get('downloads'),'likes':d.get('likes'),'created':d.get('createdAt'),'last':d.get('lastModified'),'sha':d.get('sha'),'author':d.get('author'),'usedStorage':d.get('usedStorage'),'tags':d.get('tags',[]),'nfiles':len(sib),'files':[(s['rfilename'],s.get('size')) for s in sib[:25]],'sumsize':sum((s.get('size') or 0) for s in sib),'license':(d.get('cardData') or {}).get('license')})
        exts={}
        for s in sib:
            e=s['rfilename'].rsplit('.',1)[-1] if '.' in s['rfilename'] else ''
            exts[e]=exts.get(e,0)+1
        rec['exts']=exts
        if d.get('gated') in (False,None):
            card=get(f'https://huggingface.co/datasets/{id}/raw/main/README.md',raw=True)
            rec['card']=card[:1800] if isinstance(card,str) else None
    out.write(json.dumps(rec)+'\n'); out.flush(); time.sleep(0.3)
