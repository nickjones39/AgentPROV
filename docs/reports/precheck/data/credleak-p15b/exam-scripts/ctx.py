"""credleak-p15b: named account-path digests in the 39 not-selected members (bytes through agentprov.ingest, decoded
as UTF-8 with replacement for the regex only), and redaction-marker counts. Digests and counts only.
Usage: python -I ctx.py <exam-scripts dir> <worktree root> <out.json>
"""
import sys, re, json, hashlib, collections
sys.path.insert(0, sys.argv[1]); from rawlib import members, is_cell
sys.path.insert(0, f"{sys.argv[2]}/tools/precheck"); from l1_scan import GENERIC_ACCOUNTS
ACC = {"users-dir": re.compile(r"/Users/([^/\s\"'<>\\]{1,64})/"), "home-dir": re.compile(r"/home/([^/\s\"'<>\\]{1,64})/")}
RED = re.compile(r"(?i)redacted|<redacted|\[redacted")
out = collections.defaultdict(lambda: collections.Counter()); files = 0; red = collections.Counter()
for label, data in members(lambda l: not is_cell(l)):
    files += 1; s = data.decode("utf-8", "replace"); kind = label.rsplit(".", 1)[-1]
    red[kind] += len(RED.findall(s))
    for k, rx in ACC.items():
        for m in rx.finditer(s):
            n = m.group(1)
            g = "generic" if n.lower() in GENERIC_ACCOUNTS else hashlib.sha256(n.encode("utf-8", "surrogatepass")).hexdigest()[:12]
            out[f"{k}:{g}"][label.split("/")[1] + "/*." + kind] += 1
res = dict(files=files, accounts={k: dict(v) for k, v in out.items()}, redaction_markers_by_ext=dict(red))
json.dump(res, open(sys.argv[3], "w"), indent=1, sort_keys=True); print(json.dumps(res, sort_keys=True))
