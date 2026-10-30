"""Shape of C0-bearing channel args: length, position of the control chars, and a quote_untrusted rendering (<=60 chars) of 4."""
import collections, json, re, sys
from pathlib import Path
REPO = Path.cwd()  # run from the repository root
sys.path.insert(0, str(REPO / "tools" / "precheck"))
import l1_scan as s
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.quote import quote_untrusted
bare, commit = sys.argv[1], sys.argv[2]
src = s.GitSource(Path(bare), commit); rd = s.GitBlobReader(bare); L = IngestLimits()
isc = lambda ch: (ord(ch) < 0x20 and ch not in "\n\t\r") or ch == "\x7f"
shapes = collections.Counter(); shown = 0
for e in src.entries():
    if not e.label.startswith("data/traces/e2e/") or e.disposition == "absent_blob": continue
    v = s.parse_json(rd.read(e.sha1), L).value
    for m in v["messages"]:
        for tc in m.get("tool_calls") or []:
            ch = (tc.get("args") or {}).get("channel")
            if isinstance(ch, str) and any(isc(c) for c in ch):
                pos = "leading" if isc(ch[0]) else ("trailing" if isc(ch[-1]) else "inner")
                stripped = "".join(c for c in ch if not isc(c))
                shapes[f"{pos}|len={len(ch)}|stripped_is_word={bool(re.fullmatch(r'[A-Za-z_ -]+', stripped))}"] += 1
                if shown < 4:
                    print(quote_untrusted(ch[:60], "args.channel", max_chars=60)); shown += 1
print(dict(shapes))
