import hashlib, json, os, re, sys, collections
from agentprov.ingest.jsonstream import open_json_stream
from agentprov.ingest.limits import IngestLimits, MIB
root = os.path.expanduser(sys.argv[1]); LIM = IngestLimits().replace(max_json_element_bytes=64*MIB, max_jsonl_line_bytes=64*MIB)
RX = re.compile(r"/home/([^/\s\"'<>\\]{1,64})")
H = lambda s: hashlib.sha256(s.encode()).hexdigest()[:8]
GEN = set("node user root test demo home kali mint arch pi app dev www data mysql nobody admin guest ubuntu debian centos fedora vagrant jovyan coder gitpod vscode runner ec2-user azureuser opc alpine docker git jenkins build appuser postgres redis nginx agent claude codex sandbox worker linuxbrew username yourname you me foo bar".split())
words = set()
for p in ("/usr/share/dict/words",):
    words |= {w.strip().lower() for w in open(p)}
out = {}
with open(os.path.join(root, "main/gpt_5_4.json"), "rb") as fh:
    for it in open_json_stream(fh, LIM, arrays=("/traces",)):
        if it.index != 370: continue
        rf = str(it.value["events"][20]["result_full"])
        lines = rf.splitlines()
        out["line_head_kinds"] = collections.Counter(("path:" if re.match(r"^[\w./-]+:", l) else "other") for l in lines).most_common()
        out["first_seg_kinds"] = collections.Counter((l.split("/")[0] if re.match(r"^[\w.-]+/", l) else "-")[:20] for l in lines).most_common(6)
        for m in RX.finditer(rf):
            n = m.group(1)
            if H(n) == "fc5669b5":
                w = rf[max(0, m.start()-400): m.end()+300]
                l = next(x for x in lines if m.group(0) + "/.ssh" in x or m.group(0) in x)
                pre = l.split(":", 1)[0]
                out["hit"] = {"line_file_prefix_ext": os.path.splitext(pre)[1], "line_file_prefix_first_seg": pre.split("/")[0][:20],
                    "line_file_prefix_depth": pre.count("/"),
                    "ctx": [t for t in ("useradd", "chown", "COPY", "RUN", "Dockerfile", "authorized_keys", "ssh-keygen", "mkdir", "echo", "cloud-init", "ansible", "#", "\\n", "PermitRootLogin", "test", "example", "fixture") if t in w]}
        out["names"] = {H(n): ("generic" if n in GEN else "dict" if n.lower() in words else "other") + f"/len{len(n)}" for n in {m.group(1) for m in RX.finditer(rf)}}
        break
print(json.dumps(out, indent=0))
