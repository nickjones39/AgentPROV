"""Read pinned blobs of whistlebench from the staged bare clone (no fetch); blob sha verified."""
import io, os, subprocess
from agentprov.adapters.runner.importer import git_blob_sha1
BARE=os.path.expanduser('~/.agentprov/staging/10f/whistlebench/whistlebench.git')
COMMIT='9c27637c3cf6dfb2c0d5801c7f3d91358cb587bc'
ENV={k:v for k,v in os.environ.items() if k in ('PATH','TMPDIR','HOME')}|{"GIT_NO_LAZY_FETCH":"1","GIT_ALLOW_PROTOCOL":"file","GIT_CONFIG_NOSYSTEM":"1","GIT_CONFIG_GLOBAL":os.devnull,"GIT_TERMINAL_PROMPT":"0","LC_ALL":"C"}
H=["-c",f"core.hooksPath={os.devnull}","-c","protocol.allow=never","-c","protocol.file.allow=always"]
def tree(prefix='final_runs/'):
    out=subprocess.run(["git",*H,"-C",BARE,"ls-tree","-r","-z",COMMIT,"--",prefix],capture_output=True,env=ENV,check=True).stdout
    res={}
    for rec in out.split(b"\0"):
        if not rec: continue
        meta,path=rec.split(b"\t",1); m=meta.split()
        if m[1]==b"blob": res[path.decode()]=m[2].decode()
    return res
def read(oid):
    d=subprocess.run(["git",*H,"-C",BARE,"cat-file","blob",oid],capture_output=True,env=ENV,check=True).stdout
    assert git_blob_sha1(d)==oid
    return d
