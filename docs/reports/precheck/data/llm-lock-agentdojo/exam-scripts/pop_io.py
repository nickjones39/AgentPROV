"""Shared raw access for the llm-lock exam scripts: pinned blobs from the staged bare clone, lazy fetch off, blob id checked."""
import os, subprocess
from agentprov.adapters.runner.importer import git_blob_sha1
ENV = {k: v for k, v in os.environ.items() if k in ("PATH", "TMPDIR", "HOME")} | {
    "GIT_NO_LAZY_FETCH": "1", "GIT_ALLOW_PROTOCOL": "file", "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}
H = ["-c", f"core.hooksPath={os.devnull}", "-c", "protocol.allow=never", "-c", "protocol.file.allow=always"]
def text(c):
    if c is None: return ""
    if isinstance(c, str): return c
    return "\n".join((b.get("content") or b.get("text") or "") for b in c if isinstance(b, dict))
def tree(bare, commit):
    out = subprocess.run(["git", *H, "-C", os.path.expanduser(bare), "ls-tree", "-r", "-z", commit], capture_output=True, env=ENV, check=True).stdout
    res = {}
    for rec in out.split(b"\0"):
        if rec:
            meta, path = rec.split(b"\t", 1); m = meta.split()
            if m[1] == b"blob": res[path.decode()] = m[2].decode()
    return res
class Reader:
    def __init__(self, bare):
        self.p = subprocess.Popen(["git", *H, "-C", os.path.expanduser(bare), "cat-file", "--batch"], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=ENV)
    def read(self, oid):
        self.p.stdin.write(oid.encode() + b"\n"); self.p.stdin.flush()
        h = self.p.stdout.readline().split()
        assert len(h) >= 3 and h[1] == b"blob", "absent"
        d = self.p.stdout.read(int(h[2])); self.p.stdout.read(1)
        assert git_blob_sha1(d) == oid
        return d
    def close(self):
        self.p.stdin.close(); self.p.wait()
