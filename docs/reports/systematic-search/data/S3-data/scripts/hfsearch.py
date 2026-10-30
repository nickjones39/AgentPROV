import sys, json, time, urllib.request, urllib.parse, datetime
terms=json.load(open(sys.argv[1])); out=open(sys.argv[2],'a'); log=open(sys.argv[3],'a')
for t in terms:
    ts=datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')
    url='https://huggingface.co/api/datasets?'+urllib.parse.urlencode({'search':t,'full':'true','limit':200})
    try:
        d=json.load(urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'agentprov-research/1.0'}),timeout=60))
    except Exception as e:
        log.write(f"{ts}\t{t}\tERROR {e}\n"); continue
    for x in d:
        out.write(json.dumps({'q':t,'id':x['id'],'gated':x.get('gated'),'downloads':x.get('downloads'),'likes':x.get('likes'),'tags':x.get('tags',[]),'last':x.get('lastModified'),'created':x.get('createdAt')})+'\n')
    log.write(f"{ts}\t{t}\thits={len(d)}\n"); log.flush(); time.sleep(0.5)
