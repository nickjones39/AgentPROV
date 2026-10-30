import urllib.error, sys, json, time, urllib.request, urllib.parse, datetime
qs = json.load(open(sys.argv[1]))
out = open(sys.argv[2], 'a')
log = open(sys.argv[3], 'a')
def get(url):
    err=''
    for i in range(4):
        try:
            req = urllib.request.Request(url, headers={'User-Agent':'agentprov-research/1.0'})
            return json.load(urllib.request.urlopen(req, timeout=60))
        except urllib.error.HTTPError as e:
            err=str(e)
            if e.code==400: return {'error':err}
            time.sleep(10*(i+1))
        except Exception as e:
            err = str(e); time.sleep(5*(i+1))
    return {'error': err}
for q in qs:
    ts = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')
    total=None; n=0
    for page in range(1,5):
        url = 'https://zenodo.org/api/records?'+urllib.parse.urlencode({'q':q,'size':25,'page':page})
        d = get(url)
        if 'error' in d: log.write(f"{ts}\t{q}\tERROR {d['error']}\n"); break
        total = d['hits']['total']
        for h in d['hits']['hits']:
            m=h['metadata']
            out.write(json.dumps({'q':q,'id':h['id'],'conceptrecid':h.get('conceptrecid'),'doi':h.get('doi'),'title':m.get('title'),'date':m.get('publication_date'),'rt':m.get('resource_type',{}).get('type'),'lic':(m.get('license') or {}).get('id'),'creators':[c.get('name') for c in m.get('creators',[])][:6],'files':[(f['key'],f['size']) for f in h.get('files',[])][:30],'nfiles':len(h.get('files',[])),'desc':(m.get('description') or '')[:600],'rel':[(r.get('relation'),r.get('identifier')) for r in m.get('related_identifiers',[])][:10],'access':m.get('access_right')})+'\n')
            n+=1
        if n>=total or n>=100: break
        time.sleep(1.5)
    log.write(f"{ts}\t{q}\ttotal={total}\tfetched={n}\n"); log.flush()
    out.flush()
    time.sleep(1.5)
