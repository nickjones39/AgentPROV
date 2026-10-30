import json,urllib.request,urllib.parse,datetime,time
out=open('hf2.jsonl','a'); log=open('hflog2.tsv','a')
qs=[('filter','prompt-injection'),('filter','indirect-prompt-injection'),('filter','agent-traces'),('filter','agent-trajectories'),('filter','trajectories'),('filter','trajectory'),('filter','agentdojo'),('filter','inspect-ai'),('filter','inspect'),('filter','agentic-safety'),('filter','agent-safety'),('filter','agent-security'),('filter','tool-use'),('filter','tool-calling'),('filter','function-calling'),('filter','agent-evaluation'),('filter','agent-benchmark'),('filter','red-teaming'),('filter','mcp'),('filter','swe-bench'),('filter','tau-bench'),('filter','agentharm'),('filter','injecagent'),('filter','asb'),('filter','traces'),('filter','agent-logs'),('filter','llm-agents')]
extra=[('search','injection trajectories'),('search','agentdojo-'),('search','asb'),('search','agent-security-bench'),('search','agentic safety'),('search','ipi'),('search','agentdyn'),('search','mcptox'),('search','agent hijacking'),('search','tool hijacking'),('search','agent attack trajectories'),('search','honeypot agent'),('search','llm agent logs'),('search','tool call logs'),('search','eval logs'),('search','.eval'),('search','swe-bench runs'),('search','terminal agent traces')]
for k,v in qs+extra:
    ts=datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')
    n=0
    url='https://huggingface.co/api/datasets?'+urllib.parse.urlencode({k:v,'limit':1000,'full':'true'})
    try: d=json.load(urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'agentprov-research/1.0'}),timeout=120))
    except Exception as e: log.write(f"{ts}\t{k}={v}\tERROR {e}\n"); continue
    for x in d:
        out.write(json.dumps({'q':f'{k}={v}','id':x['id'],'gated':x.get('gated'),'downloads':x.get('downloads'),'tags':x.get('tags',[]),'last':x.get('lastModified'),'created':x.get('createdAt')})+'\n'); n+=1
    log.write(f"{ts}\t{k}={v}\thits={n}\n"); log.flush(); time.sleep(0.7)
