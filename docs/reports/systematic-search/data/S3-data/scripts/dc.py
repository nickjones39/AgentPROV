import sys, json, time, urllib.request, urllib.parse, datetime
qs=json.load(open(sys.argv[1])); out=open(sys.argv[2],'a'); log=open(sys.argv[3],'a')
for q in qs:
    ts=datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')
    n=0; total=None
    for page in range(1,4):
        url='https://api.datacite.org/dois?'+urllib.parse.urlencode({'query':q,'page[size]':100,'page[number]':page})
        try: d=json.load(urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'agentprov-research/1.0'}),timeout=90))
        except Exception as e: log.write(f"{ts}\t{q}\tERROR {e}\n"); break
        total=d['meta']['total']
        for x in d['data']:
            a=x['attributes']
            out.write(json.dumps({'q':q,'doi':a['doi'],'client':x['relationships']['client']['data']['id'],'title':(a.get('titles') or [{}])[0].get('title'),'year':a.get('publicationYear'),'types':a.get('types',{}).get('resourceTypeGeneral'),'creators':[c.get('name') for c in a.get('creators',[])][:5],'lic':[r.get('rightsIdentifier') or r.get('rights') for r in a.get('rightsList',[])],'desc':' '.join(dd.get('description','') for dd in a.get('descriptions',[]))[:500],'rel':[(r.get('relationType'),r.get('relatedIdentifier')) for r in a.get('relatedIdentifiers',[])][:8],'url':a.get('url'),'size':a.get('sizes'),'formats':a.get('formats')})+'\n'); n+=1
        if n>=total or n>=300: break
        time.sleep(1)
    log.write(f"{ts}\t{q}\ttotal={total}\tfetched={n}\n"); log.flush(); out.flush(); time.sleep(1)
