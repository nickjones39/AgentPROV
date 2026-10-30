"""Key skeleton of the cell JSON (key names and value types only)."""
import sys, json, collections
sys.path.insert(0, sys.argv[1]); from rawlib import cells
top=collections.Counter(); run=collections.Counter(); turn=collections.Counter(); tc=collections.Counter(); cfg=collections.Counter()
for i,(l,d) in enumerate(cells()):
    for k,v in d.items(): top[(k,type(v).__name__)]+=1
    for k,v in (d.get("config") or {}).items() if isinstance(d.get("config"),dict) else []: cfg[(k,type(v).__name__)]+=1
    for r in d.get("runs",[]):
        for k,v in r.items(): run[(k,type(v).__name__)]+=1
        for t in r.get("turns",[]):
            for k,v in t.items(): turn[(k,type(v).__name__)]+=1
            for c in t.get("toolCalls") or []:
                for k,v in c.items(): tc[(k,type(v).__name__)]+=1
for n,c in [("top",top),("config",cfg),("run",run),("turn",turn),("toolcall",tc)]:
    print(n, sorted(c.items()))
