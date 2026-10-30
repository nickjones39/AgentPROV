"""L1-10 follow-up 2: context of the CHANGES.md match (never the value): the matched key token, whether the key word is
inside a longer identifier, the line's markdown kind, and in how many of the 3,211 selected logs the same value occurs
(benchmark content if > 0). Usage (repo root): uv run python -I .../ctxhit2.py"""
import argparse, json, os, re, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[6]
sys.path.insert(0, str(REPO / "tools" / "precheck"))
import l1_scan  # noqa: E402
from agentprov.ingest.limits import IngestLimits  # noqa: E402
profile, _ = l1_scan.resolve("ipi-defenses-agentdojo", "head", None)
ns = argparse.Namespace(git=None, use_pin=False, input=str(Path.home() / ".agentprov/staging/10c/zenodo-22011266/AgentSecurity-IPIDefenses-v4.0.zip"),
                        tree=None, whole_tree=False, no_verify_pin=False, nested_cap=768 << 20, commit=None, cache=None)
rows = [json.loads(l)["label"] for l in open(os.path.expanduser("~/.agentprov/migration-work/precheck/ipi-defenses-agentdojo/l1-units-head.jsonl"))]
CH = "AgentSecurity-IPIDefenses-v4.0/docs/CHANGES.md"
src, _ = l1_scan.build_source(ns, profile, "head", IngestLimits())
rx = l1_scan.SECRET_PATTERNS["generic-credential-assignment"]
vals = []; info = []
for label, _s, data in src.stream({CH}):
    text = data.decode("utf-8", "replace")
    for m in rx.finditer(text):
        s = m.group(0); v = re.search(r"[A-Za-z0-9_\-/+=.]{16,}$", s).group(0); vals.append(v)
        line = text[text.rfind("\n", 0, m.start()) + 1: text.find("\n", m.end())]
        pre = text[max(0, m.start() - 1): m.start()]
        info.append({"key_token": re.match(r"(?i)[a-z_\-]+", s).group(0).lower(), "key_inside_identifier": bool(re.match(r"[A-Za-z0-9_]", pre)),
                     "line_kind": "table" if line.lstrip().startswith("|") else "code" if line.startswith(("    ", "\t", "`")) else "list" if line.lstrip().startswith(("-", "*")) else "text",
                     "value_has_upper": any(c.isupper() for c in v), "value_has_lower": any(c.islower() for c in v), "value_has_symbol": any(not c.isalnum() for c in v),
                     "value_placeholder_word": any(w in v.lower() for w in ("your", "example", "placeholder", "redact", "xxxx", "dummy", "changeme", "env", "os.environ", "getenv")),
                     "value_provider_prefix": bool(re.match(r"(?i)(sk-|sk_|rk_|ghp_|gho_|xox|AIza|hf_|AKIA|ASIA|eyJ)", v)),
                     "value_symbols": sorted({c for c in v if not c.isalnum()}), "value_is_path_like": v.count("/") >= 1, "value_dotted_identifier": bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)+", v))})
logs_with = 0
for label, _s, data in src.stream(set(rows)):
    logs_with += any(v.encode() in data for v in vals)
print(json.dumps({"matches": info, "selected_logs_containing_the_value": logs_with, "logs_scanned": len(rows)}))
