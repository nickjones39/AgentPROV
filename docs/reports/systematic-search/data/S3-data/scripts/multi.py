import sys, json, time, urllib.request, urllib.parse, datetime
terms=json.load(open(sys.argv[1])); out=open('multi.jsonl','a'); log=open('multilog.tsv','a')
H={'User-Agent':'agentprov-research/1.0'}
def get(url,data=None):
    for i in range(3):
        try:
            req=urllib.request.Request(url,headers=dict(H,**({'Content-Type':'application/json'} if data else {})),data=data)
            return json.load(urllib.request.urlopen(req,timeout=60))
        except Exception as e: err=str(e); time.sleep(3)
    return {'__error':err}
def now(): return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')
for t in terms:
    # Figshare
    ts=now(); n=0; d=get('https://api.figshare.com/v2/articles/search',json.dumps({'search_for':t,'page_size':100,'page':1}).encode())
    if isinstance(d,list):
        for x in d: out.write(json.dumps({'repo':'figshare','q':t,'id':x['id'],'doi':x.get('doi'),'title':x.get('title'),'date':x.get('published_date'),'type':x.get('defined_type_name'),'url':x.get('url_public_html')})+'\n'); n+=1
        log.write(f"{ts}\tfigshare\t{t}\thits={n}\n")
    else: log.write(f"{ts}\tfigshare\t{t}\tERROR {d}\n")
    # Dryad
    ts=now(); d=get('https://datadryad.org/api/v2/search?'+urllib.parse.urlencode({'q':t,'per_page':100}))
    if '__error' not in d:
        for x in d['_embedded']['stash:datasets']: out.write(json.dumps({'repo':'dryad','q':t,'doi':x.get('identifier'),'title':x.get('title'),'date':x.get('publicationDate'),'abstract':(x.get('abstract') or '')[:400]})+'\n')
        log.write(f"{ts}\tdryad\t{t}\ttotal={d.get('total')}\n")
    else: log.write(f"{ts}\tdryad\t{t}\tERROR {d}\n")
    # OSF (title / description / tags)
    for fld in ('title','description'):
        ts=now(); d=get('https://api.osf.io/v2/nodes/?'+urllib.parse.urlencode({f'filter[{fld}][icontains]':t,'page[size]':100}))
        if '__error' not in d:
            for x in d['data']:
                a=x['attributes']; out.write(json.dumps({'repo':'osf','q':t,'field':fld,'id':x['id'],'title':a.get('title'),'date':a.get('date_created'),'public':a.get('public'),'desc':(a.get('description') or '')[:400],'tags':a.get('tags'),'url':x['links'].get('html')})+'\n')
            log.write(f"{ts}\tosf-nodes-{fld}\t{t}\ttotal={d['links']['meta']['total']}\n")
        else: log.write(f"{ts}\tosf-nodes-{fld}\t{t}\tERROR {d}\n")
    # OSF registrations? skip; SWH origin search (url substring)
    ts=now(); d=get('https://archive.softwareheritage.org/api/1/origin/search/'+urllib.parse.quote(t.replace(' ','-'))+'/?limit=100&with_visit=true')
    if isinstance(d,list):
        for x in d: out.write(json.dumps({'repo':'swh','q':t,'url':x['url'],'visits':x.get('nb_visits'),'last':x.get('last_visit_date')})+'\n')
        log.write(f"{ts}\tswh\t{t}\thits={len(d)}\n")
    else: log.write(f"{ts}\tswh\t{t}\tERROR {str(d)[:100]}\n")
    log.flush(); out.flush(); time.sleep(1)
