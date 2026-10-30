import json,urllib.request,urllib.parse,datetime,time
out=open('kg.jsonl','a'); log=open('kglog.tsv','a')
qs=['agentdojo','injecagent','agentharm','agent security bench','prompt injection agent','indirect prompt injection','llm agent trajectories','agent trajectories','llm agent logs','agent traces','tool calling agent','tool use benchmark','swe-bench trajectories','tau-bench','webarena','osworld','gaia agent','inspect ai logs','agent benchmark runs','mcp tool poisoning','agentic ai security','llm agent execution logs','agent execution traces','function calling traces','ai agent logs']
for q in qs:
    ts=datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ'); n=0
    for p in (1,2):
        u='https://www.kaggle.com/api/v1/datasets/list?'+urllib.parse.urlencode({'search':q,'pageSize':20,'page':p})
        try: d=json.load(urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'agentprov-research/1.0'}),timeout=60))
        except Exception as e: log.write(f"{ts}\t{q}\tERROR {e}\n"); break
        for x in d:
            out.write(json.dumps({'q':q,'ref':x.get('refNullable') or x.get('urlNullable'),'url':x.get('urlNullable'),'title':x.get('titleNullable'),'sub':x.get('subtitleNullable'),'size':x.get('totalBytesNullable'),'lic':x.get('licenseNameNullable'),'updated':x.get('lastUpdatedNullable'),'dl':x.get('downloadCountNullable'),'owner':x.get('creatorNameNullable')})+'\n'); n+=1
        if len(d)<20: break
        time.sleep(1)
    log.write(f"{ts}\t{q}\thits={n}\n"); log.flush(); time.sleep(1)
