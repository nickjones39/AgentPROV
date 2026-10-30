"""Verifier PC-02: booleans/counts only about the fc5669b5 home name. Never prints the name."""
import hashlib, json, os, re, sys, collections
from agentprov.ingest.jsonstream import open_json_stream
from agentprov.ingest.limits import IngestLimits, MIB
root = os.path.expanduser(sys.argv[1])
LIM = IngestLimits().replace(max_json_element_bytes=64 * MIB, max_jsonl_line_bytes=64 * MIB)
T = "fc5669b5"
H = lambda s: hashlib.sha256(s.encode()).hexdigest()[:8]
GEN = set("node user root test demo home kali mint arch pi app dev www data mysql nobody admin guest ubuntu debian centos fedora vagrant jovyan coder gitpod vscode runner ec2-user azureuser opc alpine docker git jenkins build appuser postgres redis nginx agent claude codex sandbox worker".split())
words = set()
for p in ("/usr/share/dict/words", "/usr/share/dict/propernames"):
    try: words |= {w.strip() for w in open(p)}
    except OSError: pass
cand = {H(w): ("generic" if w in GEN else "dict") for w in words | GEN}
cand.update({H(w.lower()): "dict-lower" for w in words if H(w.lower()) not in cand})
out = {"class_of_name": cand.get(T, "not-in-generic-or-dictionary")}
RX = re.compile(r"/home/([^/\s\"'<>\\]{1,64})")
name = None
docs = collections.Counter(); fields = collections.Counter()
for sp in sorted(os.listdir(root)):
    d = os.path.join(root, sp)
    if not os.path.isdir(d): continue
    for f in sorted(os.listdir(d)):
        if not f.endswith(".json"): continue
        lab = f"{sp}/{f}"
        with open(os.path.join(d, f), "rb") as fh:
            try:
                for it in open_json_stream(fh, LIM, arrays=("/traces",)):
                    s = json.dumps(it.value)
                    for m in RX.finditer(s):
                        if H(m.group(1)) == T:
                            name = m.group(1); docs[f"{lab}#/traces/{it.index}"] += 1
                    if name and name in s and not docs.get(f"{lab}#/traces/{it.index}"):
                        docs[f"{lab}#/traces/{it.index} (bare-name only)"] += 1
            except Exception as ex:
                out.setdefault("not_trace_docs", []).append(lab)
out["traces_with_home_name"] = dict(docs)
if name:
    out["name_shape"] = {"len": len(name), "lower": name.islower(), "alpha": name.isalpha(), "digits": sum(c.isdigit() for c in name)}
# context in the target trace
with open(os.path.join(root, "main/gpt_5_4.json"), "rb") as fh:
    for it in open_json_stream(fh, LIM, arrays=("/traces",)):
        if it.index != 370: continue
        t = it.value
        for i, e in enumerate(t.get("events") or []):
            rf = str(e.get("result_full"))
            if name and f"/home/{name}" in rf:
                cmd = str((e.get("args") or {}).get("command"))
                lines = rf.splitlines()
                pref = collections.Counter("/" + l.lstrip("./").split("/")[0] if l.startswith("/") else "other" for l in lines)
                out["event"] = {"idx": i, "server": e.get("server"), "tool": e.get("tool"),
                    "cmd_words": [w for w in ("find", "ls", "grep", "cat", "tree", "du", "-R", "-r", "/", "~", "sudo", "docker", "ssh") if w in cmd.split() or w in cmd],
                    "cmd_len": len(cmd), "n_lines": len(lines), "top_line_prefixes": pref.most_common(8),
                    "home_lines": sum(1 for l in lines if f"/home/{name}" in l),
                    "has_macos_Users": "/Users/" in rf, "has_proc": "/proc/" in rf, "has_dockerenv": ".dockerenv" in rf,
                    "other_home_names": len({H(m.group(1)) for m in RX.finditer(rf)}) - 1,
                    "ssh_child_names_kind": collections.Counter(("id_" in l, "known_hosts" in l, "authorized_keys" in l) for l in lines if f"/home/{name}/.ssh" in l).most_common()}
        out["trace_placeholders"] = [p for p in ("/home/user/", "/mcphunt/", "<HOME>", "MCPHUNT-HOST", "<redacted>") if p in json.dumps(t)]
        out["env_type"] = t.get("env_type"); out["task_id_hash"] = H(str(t.get("task_id")))
        break
print(json.dumps(out, indent=0, default=str))
