"""Verifier: structure of the CHANGES.md match without the value (value masked, segments described)."""
import argparse, json, re, sys
from pathlib import Path
REPO = Path(sys.argv[1])
sys.path.insert(0, str(REPO / "tools" / "precheck"))
import l1_scan
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.quote import quote_untrusted
profile, _ = l1_scan.resolve("ipi-defenses-agentdojo", "head", None)
ns = argparse.Namespace(git=None, use_pin=False, input=str(Path.home() / ".agentprov/staging/10c/zenodo-22011266/AgentSecurity-IPIDefenses-v4.0.zip"),
                        tree=None, whole_tree=False, no_verify_pin=False, nested_cap=768 << 20, commit=None, cache=None)
CH = "AgentSecurity-IPIDefenses-v4.0/docs/CHANGES.md"
src, _ = l1_scan.build_source(ns, profile, "head", IngestLimits())
rx = l1_scan.SECRET_PATTERNS["generic-credential-assignment"]
words = set()
try: words = {w.strip().lower() for w in open("/usr/share/dict/words")}
except OSError: pass
out = []
for label, _s, data in src.stream({CH}):
    text = data.decode("utf-8", "replace")
    for m in rx.finditer(text):
        v = re.search(r"[A-Za-z0-9_\-/+=.]{16,}$", m.group(0)).group(0)
        ls = text.rfind("\n", 0, m.start()) + 1; le = text.find("\n", m.end())
        line = text[ls:le]
        masked = line.replace(v, "<VALUE>")
        segs = re.split(r"([-=])", v)
        out.append({"masked_line": quote_untrusted(masked[:400], "CHANGES.md"),
                    "match_prefix_before_value": quote_untrusted(m.group(0)[: len(m.group(0)) - len(v)], "CHANGES.md"),
                    "segments": [{"sep": s} if s in "-=" else {"len": len(s), "alpha": s.isalpha(), "lower": s.islower(), "dict_word": s.lower() in words, "digits": sum(c.isdigit() for c in s)} for s in segs if s != ""],
                    "prev_line_masked": quote_untrusted(text[text.rfind("\n", 0, ls - 1) + 1: ls - 1][:300], "CHANGES.md"),
                    "value_count_in_file": text.count(v)})
print(json.dumps(out, indent=1))
