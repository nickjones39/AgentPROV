import json,urllib.request,re,time,sys
ids=sys.argv[1:]
out=open('fs_detail.jsonl','a')
for i in ids:
    try:
        d=json.load(urllib.request.urlopen(urllib.request.Request('https://api.figshare.com/v2/articles/'+i,headers={'User-Agent':'agentprov-research/1.0'}),timeout=60))
    except Exception as e:
        out.write(json.dumps({'id':i,'error':str(e)})+'\n'); continue
    out.write(json.dumps({'id':i,'doi':d.get('doi'),'title':d.get('title'),'date':d.get('published_date'),'lic':(d.get('license') or {}).get('name'),'type':d.get('defined_type_name'),'authors':[a['full_name'] for a in d.get('authors',[])][:6],'desc':re.sub(r'\s+',' ',re.sub('<[^>]+>',' ',d.get('description','')))[:900],'files':[(f['name'],f['size']) for f in d.get('files',[])][:25],'nfiles':len(d.get('files',[])),'refs':d.get('references',[])[:5],'url':d.get('figshare_url'),'is_public':d.get('is_public'),'embargo':d.get('is_embargoed'),'confidential':d.get('is_confidential')})+'\n'); out.flush(); time.sleep(0.5)
