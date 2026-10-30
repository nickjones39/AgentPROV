"""Read pinned blobs of menelaus29-ipi-multidomain (copied from interbolt exam-scripts) through agentprov.ingest (bounded strict parse); counts only."""
import json, os, subprocess, sys
from agentprov.ingest.loaders import strict_json_loads
from agentprov.adapters.runner.importer import git_blob_sha1
BARE=os.path.expanduser('~/.agentprov/staging/10c/menelaus29/ipi-multidomain-agent-study.git')
COMMIT='ec9c9287889ebec339c4304f01a4a4a99500c491'
ENV={k:v for k,v in os.environ.items() if k in ('PATH','TMPDIR','HOME')}|{"GIT_NO_LAZY_FETCH":"1","GIT_ALLOW_PROTOCOL":"file","GIT_CONFIG_NOSYSTEM":"1","GIT_CONFIG_GLOBAL":os.devnull,"GIT_TERMINAL_PROMPT":"0","LC_ALL":"C"}
H=["-c",f"core.hooksPath={os.devnull}","-c","protocol.allow=never","-c","protocol.file.allow=always"]
def tree():
    out=subprocess.run(["git",*H,"-C",BARE,"ls-tree","-r","-z",COMMIT],capture_output=True,env=ENV,check=True).stdout
    res={}
    for rec in out.split(b"\0"):
        if not rec: continue
        meta,path=rec.split(b"\t",1); m=meta.split()
        if m[1]==b"blob": res[path.decode()]=m[2].decode()
    return res
class Reader:
    def __init__(self):
        self.p=subprocess.Popen(["git",*H,"-C",BARE,"cat-file","--batch"],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=ENV)
    def read(self,oid):
        self.p.stdin.write(oid.encode()+b"\n"); self.p.stdin.flush()
        h=self.p.stdout.readline().split()
        assert len(h)>=3 and h[1]==b"blob", "absent"
        d=self.p.stdout.read(int(h[2])); self.p.stdout.read(1)
        assert git_blob_sha1(d)==oid
        return d
    def json(self,oid): return strict_json_loads(self.read(oid))
