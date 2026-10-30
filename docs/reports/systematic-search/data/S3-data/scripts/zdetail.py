import urllib.parse, sys, json, time, urllib.request, urllib.error, re, datetime
ids=[l.split()[0] for l in open(sys.argv[1]) if l.strip()]; out=open(sys.argv[2],'a')
def get(url,tries=3):
    for i in range(tries):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'agentprov-research/1.0'}),timeout=60))
        except urllib.error.HTTPError as e:
            if e.code in (404,403): return {'__error':e.code}
            time.sleep(4*(i+1))
        except Exception as e: time.sleep(4*(i+1))
    return {'__error':'fail'}
for id in ids:
    d=get(f'https://zenodo.org/api/records/{id}')
    ts=datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')
    if '__error' in d: out.write(json.dumps({'id':id,'error':d['__error'],'ts':ts})+'\n'); continue
    m=d['metadata']
    rec={'id':id,'ts':ts,'doi':d.get('doi'),'conceptdoi':d.get('conceptdoi'),'title':m['title'],'date':m['publication_date'],'access':m.get('access_right'),'lic':(m.get('license') or {}).get('id'),'rt':m.get('resource_type',{}).get('type'),'creators':[c['name'] for c in m['creators']][:8],'desc':re.sub(r'\s+',' ',re.sub('<[^>]+>',' ',m.get('description','')))[:1800],'rel':[(r['relation'],r['identifier']) for r in m.get('related_identifiers',[])],'files':[(f['key'],f['size']) for f in d.get('files',[])],'version':m.get('version'),'stats':d.get('stats',{}).get('unique_downloads'),'zip':{}}
    for f in d.get('files',[]):
        if f['key'].lower().endswith('.zip') and f['size']<3_000_000_000:
            c=get('https://zenodo.org/api/records/%s/files/%s/container'%(id,urllib.request.quote(f['key'])),1)
            if '__error' not in c:
                ent=c.get('entries') or c.get('hits') or c
                if isinstance(ent,dict): ent=ent.get('entries',ent)
                try:
                    rec['zip'][f['key']]=[ (e.get('key') or e.get('path') or str(e))[:100] for e in (ent if isinstance(ent,list) else [])][:60]
                    rec['zip'][f['key']+'#n']=len(ent) if isinstance(ent,list) else str(c)[:200]
                except Exception as e: rec['zip'][f['key']]=str(c)[:300]
            else: rec['zip'][f['key']]='container-error-%s'%c['__error']
            time.sleep(1)
    out.write(json.dumps(rec)+'\n'); out.flush(); time.sleep(1.2)
