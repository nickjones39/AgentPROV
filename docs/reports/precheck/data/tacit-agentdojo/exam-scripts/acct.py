"""Characterise /home/<name>/ matches in given labels. Prints counts/roles/digests only, never the name."""
import hashlib, json, os, re, subprocess, sys
from agentprov.ingest.loaders import strict_json_loads
BARE = os.path.expanduser("~/.agentprov/staging/10c/tacit/Tacit.git"); C = "995692d3cd42c32e08cf0db8a5fae55fec272f1a"
ENV = {"PATH": os.environ["PATH"], "HOME": os.environ["HOME"], "GIT_NO_LAZY_FETCH": "1", "GIT_ALLOW_PROTOCOL": "file"}
RX = re.compile(r"/home/([^/\s\"'<>\\]{1,64})/")
def blob(label): return subprocess.run(["git", "-C", BARE, "show", f"{C}:{label}"], capture_output=True, env=ENV, check=True).stdout
def walk(v, ptr, out):
    if isinstance(v, dict):
        for k, x in v.items(): walk(x, ptr + "/" + str(k), out)
    elif isinstance(v, list):
        for i, x in enumerate(v): walk(x, ptr + "/" + str(i), out)
    elif isinstance(v, str): out.append((ptr, v))
for label in sys.argv[1:]:
    d = strict_json_loads(blob(label)); strs = []; walk(d, "", strs)
    names = {}; first = {}
    for ptr, s in strs:
        for m in RX.finditer(s):
            n = m.group(1); h = hashlib.sha256(n.encode()).hexdigest()[:16]
            mi = int(ptr.split("/")[2]) if ptr.startswith("/messages/") else None
            role = d["messages"][mi]["role"] if mi is not None else None
            names.setdefault(h, {"len": len(n), "isalpha": n.isalpha(), "lower": n.islower(), "roles": {}, "msgs": set()})
            names[h]["roles"][role] = names[h]["roles"].get(role, 0) + 1; names[h]["msgs"].add(mi)
            first.setdefault(h, (mi, role))
    for h, info in names.items():
        n_any = None
        # does the name (case-insensitive) occur in any system/user message, or any tool output before first use?
        fm = first[h][0]
        nm = [m.group(1) for ptr, s in strs for m in RX.finditer(s) if hashlib.sha256(m.group(1).encode()).hexdigest()[:16] == h][0]
        pre = [i for i, msg in enumerate(d["messages"][:fm]) if nm.lower() in json.dumps(msg).lower()]
        roles_any = sorted({d["messages"][i]["role"] for i, msg in enumerate(d["messages"]) if nm.lower() in json.dumps(msg).lower()})
        print(label.split("/", 2)[2], h, {"len": info["len"], "isalpha": info["isalpha"], "lower": info["lower"], "roles": info["roles"],
              "n_msgs": len(info["msgs"]), "first_use": first[h], "occurs_before_first_use_in_msgs": pre, "roles_with_name_anywhere": roles_any,
              "n_messages": len(d["messages"])})
