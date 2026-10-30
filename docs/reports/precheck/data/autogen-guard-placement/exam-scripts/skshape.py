# ruff: noqa  (precheck examiner script for autogen-guard-placement, committed as run; read-only analysis)
"""Shape of the sk- secret-like strings in results/phase7/capture.json: JSON pointer, segment lengths, known-word
segments, Shannon entropy, digest prefix. Never prints a value.  Usage: python -I skshape.py <zip> <out.json>"""
import hashlib, json, math, re, sys
from collections import Counter
from pathlib import Path
from agentprov.ingest.archives import iter_zip_members, open_zip
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads
PAT = re.compile(r"sk-[A-Za-z0-9_-]{20,}")
WORDS = {"proj", "ant", "api", "or", "v1", "local", "test", "dummy", "fake", "example", "lm", "studio", "lmstudio", "admin", "svcacct", "none", "placeholder"}
res = []
def walk(v, p):
    if isinstance(v, dict):
        for k, x in v.items(): yield from walk(x, p + "/" + str(k))
    elif isinstance(v, list):
        for x in v: yield from walk(x, p + "/*")
    elif isinstance(v, str):
        for h in PAT.finditer(v): yield p, h.group(0), v
with Path(sys.argv[1]).expanduser().open("rb") as fp, open_zip(fp, IngestLimits(), release=False) as z:
    for m in iter_zip_members(z):
        if not m.label.endswith("results/phase7/capture.json"):
            continue
        doc = strict_json_loads(z.read_member(m))
        for p, s, whole in walk(doc, ""):
            segs = s.split("-")
            cnt = Counter(s); ent = -sum(c / len(s) * math.log2(c / len(s)) for c in cnt.values())
            ctx = whole.lower()
            res.append({"pointer": p, "len": len(s), "segment_lengths": [len(x) for x in segs],
                        "known_word_segments": [x.lower() for x in segs if x.lower() in WORDS],
                        "entropy_bits_per_char": round(ent, 2), "sha256_8": hashlib.sha256(s.encode()).hexdigest()[:8],
                        "whole_string_len": len(whole), "string_is_the_token": whole == s,
                        "context_words": sorted(w for w in ("key", "api", "secret", "token", "redact", "detect", "leak", "fake", "example", "canary", "probe") if w in ctx)})
Path(sys.argv[2]).write_text(json.dumps(res, indent=1) + "\n")
print(json.dumps(res))
