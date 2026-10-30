"""Verifier: where else do the canary value, 'evil.test' and 'Secret asset' occur (counts per member class only)."""
import argparse, json, re, sys, os
from pathlib import Path
REPO = Path(sys.argv[1]); sys.path.insert(0, str(REPO / "tools" / "precheck"))
import l1_scan
from agentprov.ingest.limits import IngestLimits
profile, _ = l1_scan.resolve("ipi-defenses-agentdojo", "head", None)
ns = argparse.Namespace(git=None, use_pin=False, input=str(Path.home() / ".agentprov/staging/10c/zenodo-22011266/AgentSecurity-IPIDefenses-v4.0.zip"),
                        tree=None, whole_tree=False, no_verify_pin=False, nested_cap=768 << 20, commit=None, cache=None)
CH = "AgentSecurity-IPIDefenses-v4.0/docs/CHANGES.md"
src, _ = l1_scan.build_source(ns, profile, "head", IngestLimits())
rx = l1_scan.SECRET_PATTERNS["generic-credential-assignment"]
v = None; hdr = []
for label, _s, data in src.stream({CH}):
    t = data.decode("utf-8", "replace")
    m = next(rx.finditer(t)); v = re.search(r"[A-Za-z0-9_\-/+=.]{16,}$", m.group(0)).group(0).encode()
    # section headings above the match line (headings are not secret)
    hdr = [h for h in re.findall(r"(?m)^#{1,4} .*$", t[: m.start()])][-3:]
    ctx_lines = [l for l in t.splitlines() if "evil.test" in l or "canary" in l.lower() or "exfil" in l.lower()]
units = {json.loads(l)["label"] for l in open(os.path.expanduser("~/.agentprov/migration-work/precheck/ipi-defenses-agentdojo/l1-units-head.jsonl"))}
labels = [lab for lab in getattr(src, "labels", lambda: [])()] if hasattr(src, "labels") else []
res = {"logs": {"value": 0, "evil.test": 0, "secret_asset": 0}, "headings_above": hdr, "n_ctx_lines_canary_exfil_eviltest": len(ctx_lines)}
for label, _s, data in src.stream(units):
    res["logs"]["value"] += v in data; res["logs"]["evil.test"] += b"evil.test" in data; res["logs"]["secret_asset"] += b"Secret asset" in data
print(json.dumps(res, indent=1))
