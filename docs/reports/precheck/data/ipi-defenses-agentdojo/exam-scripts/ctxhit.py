"""L1-10 follow-up: which context artefact holds the generic-credential-assignment match and its shape class (never the
value): key word, value length, character classes, and whether the value looks like an identifier/placeholder (only
[A-Za-z_] and dots, as in a variable or attribute name) or a high-entropy literal. Reads through l1_scan.ArchiveSource.
Usage (repo root): uv run python -I .../ctxhit.py"""
import argparse, json, math, sys
from collections import Counter
from pathlib import Path
REPO = Path(__file__).resolve().parents[6]
sys.path.insert(0, str(REPO / "tools" / "precheck"))
import l1_scan  # noqa: E402
from agentprov.ingest.limits import IngestLimits  # noqa: E402
CTX = ["AgentSecurity-IPIDefenses-v4.0/README.md", "AgentSecurity-IPIDefenses-v4.0/data/RUN_MAP.md",
       "AgentSecurity-IPIDefenses-v4.0/docs/CHANGES.md", "AgentSecurity-IPIDefenses-v4.0/docs/CHANGES_ADDENDUM_2026-07-16.md",
       "AgentSecurity-IPIDefenses-v4.0/code/agentdojo_banking.py"]
profile, _ = l1_scan.resolve("ipi-defenses-agentdojo", "head", None)
ns = argparse.Namespace(git=None, use_pin=False, input=str(Path.home() / ".agentprov/staging/10c/zenodo-22011266/AgentSecurity-IPIDefenses-v4.0.zip"),
                        tree=None, whole_tree=False, no_verify_pin=False, nested_cap=768 << 20, commit=None, cache=None)
src, _ = l1_scan.build_source(ns, profile, "head", IngestLimits())
rx = l1_scan.SECRET_PATTERNS["generic-credential-assignment"]
out = {}
for label, _s, data in src.stream(set(CTX)):
    text = data.decode("utf-8", "replace"); hits = []
    for m in rx.finditer(text):
        s = m.group(0); key = s.split("=")[0].split(":")[0].strip("\"' ").lower()
        val = s[len(s.rstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-/+=.")):]
        c = Counter(val); ent = -sum(n / len(val) * math.log2(n / len(val)) for n in c.values())
        hits.append({"key_word": next(k for k in ("api_key", "api-key", "apikey", "secret", "token", "password", "passwd") if k in key) if any(k in key for k in ("api", "secret", "token", "pass")) else "other",
                     "value_len": len(val), "has_digit": any(ch.isdigit() for ch in val),
                     "identifier_like": all(ch.isalpha() or ch in "_." for ch in val), "entropy_bits_per_char": round(ent, 2),
                     "line_no": text.count("\n", 0, m.start()) + 1, "equals_agentdojo_attacker_iban": val.lower() == "us133000000121212121212", "is_iban_shape": len(val) >= 15 and val[:2].isalpha() and val[2:4].isdigit()})
    out[label.rsplit("/", 1)[-1]] = hits
print(json.dumps(out))
