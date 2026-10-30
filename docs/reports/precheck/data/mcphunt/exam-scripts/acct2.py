"""Context of the one named home-dir account seen only in /events/*/result_full (digest fc5669b5): per hit the trace
label, canary flag, event server/tool, whether the hit lies beyond the 12,000-char message truncation, the result's
mapped-to-message status, and booleans for nearby context words. Name printed only if it is in the generic word list.
usage: uv run python -I acct2.py <staging-root> <out.json>
"""
import hashlib, json, os, re, sys
from agentprov.ingest.jsonstream import open_json_stream
from agentprov.ingest.limits import IngestLimits, MIB
root, outp = os.path.expanduser(sys.argv[1]), sys.argv[2]
TARGET = "fc5669b5"
WORDS = "node dave mark mike paul alex anna john test temp work data repo code dev1 ops1 null none john user root ftp sync halt mail news uucp man lp bin sys games list irc".split()
WD = {hashlib.sha256(w.encode()).hexdigest()[:8]: w for w in WORDS}
RX = re.compile(r"/home/([^/\s\"'<>\\]{1,64})/")
CTX = ("passwd", "Author", "git", "docker", "Dockerfile", "README", "config", "ssh", ".env", "pip", "site-packages", "Traceback")
LIM = IngestLimits().replace(max_json_element_bytes=64 * MIB, max_jsonl_line_bytes=64 * MIB)
out = {"word": WD.get(TARGET), "hits": []}
for sp in ("main", "mitigation"):
    for f in sorted(os.listdir(os.path.join(root, sp))):
        lab = f"{sp}/{f}"
        with open(os.path.join(root, lab), "rb") as fh:
            for it in open_json_stream(fh, LIM, arrays=("/traces",)):
                t = it.value
                fl = any(e.get("canary_in_result") or e.get("canary_in_args") for e in t.get("events") or [] if isinstance(e, dict))
                for e in t.get("events") or []:
                    rf = str(e.get("result_full"))
                    for mm in RX.finditer(rf):
                        if hashlib.sha256(mm.group(1).encode()).hexdigest()[:8] != TARGET: continue
                        win = rf[max(0, mm.start() - 300): mm.end() + 300]
                        out["hits"].append({"trace": f"{lab}#/traces/{it.index}", "canary_flagged": fl, "server": e.get("server"),
                            "tool": e.get("tool"), "offset": mm.start(), "beyond_12000": mm.start() >= 12000,
                            "result_truncated": e.get("result_truncated"), "ctx": [w for w in CTX if w in win],
                            "in_task_prompt": mm.group(1) in str(t.get("task_prompt")), "name_len": len(mm.group(1))})
json.dump(out, open(outp, "w"), indent=1); print(json.dumps(out, indent=0))
