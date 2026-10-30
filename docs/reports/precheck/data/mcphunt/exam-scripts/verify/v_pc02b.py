import hashlib, json, os, re, sys
from agentprov.ingest.jsonstream import open_json_stream
from agentprov.ingest.limits import IngestLimits, MIB
root = os.path.expanduser(sys.argv[1]); LIM = IngestLimits().replace(max_json_element_bytes=64*MIB, max_jsonl_line_bytes=64*MIB)
RX = re.compile(r"/home/([^/\s\"'<>\\]{1,64})")
H = lambda s: hashlib.sha256(s.encode()).hexdigest()[:8]
out = {}
with open(os.path.join(root, "main/gpt_5_4.json"), "rb") as fh:
    for it in open_json_stream(fh, LIM, arrays=("/traces",)):
        if it.index != 370: continue
        e = it.value["events"][20]; rf = str(e["result_full"]); cmd = str(e["args"]["command"])
        line = next(l for l in rf.splitlines() if any(H(m.group(1)) == "fc5669b5" for m in RX.finditer(l)))
        out["line"] = {"len": len(line), "permission_denied": "Permission denied" in line, "binary_matches": "Binary file" in line,
            "no_such_file": "No such file" in line, "has_ssh_key_type": bool(re.search(r"ssh-(rsa|ed25519|dss)|ecdsa-sha2", line)),
            "has_at_sign": "@" in line, "grep_colon_sep": line.count(":")}
        out["cmd"] = {"grep_r": bool(re.search(r"grep\s+-\w*r", cmd)), "pipes": cmd.count("|"), "redirect_2_null": "2>/dev/null" in cmd,
            "pattern_has_canary_words": [w for w in ("sk_", "AKIA", "ghp_", "xox", "PRIVATE", "password", "secret", "key", "token") if w in cmd]}
        names = {H(m.group(1)): m.group(1) for m in RX.finditer(rf)}
        out["other_names_generic"] = {d: (n in ("user", "linuxbrew", "node", "root")) for d, n in names.items() if d != "fc5669b5"}
        out["proc_lines"] = sum(1 for l in rf.splitlines() if l.startswith("/proc/") or "/proc/" in l[:40])
        out["usr_lines"] = sum(1 for l in rf.splitlines() if l.startswith("/usr/"))
        out["root_dirs"] = sorted({l.split("/")[1] for l in rf.splitlines()[:220250] if l.startswith("/") and l.count("/") > 1})[:25]
        break
print(json.dumps(out, indent=0))
