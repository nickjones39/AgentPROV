"""L1-10 follow-through: which members hold the named home-dir accounts, PEM and JWT shapes of l1-10 (counts, digests,
diff-line class and model only; never a name or value). Read-only, streamed through l1_scan.ArchiveSource.

    uv run python -I S/patches.py OUT.json
"""
from __future__ import annotations
import hashlib, json, re, sys
from collections import Counter, defaultdict
from pathlib import Path
REPO = Path(__file__).resolve().parents[6]
sys.path.insert(0, str(REPO / "tools" / "precheck"))
import l1_scan  # noqa: E402
ARCHIVE = str(Path.home() / ".agentprov/staging/10e/zenodo_20404563/RESULTS_raw.tar.zst")
ROLL = re.compile(r"^RESULTS_build/cells/gemini_cli__([^/]+)/(SK-[A-Z]+)__(m\d\d)/(.+)$")
def d12(s): return hashlib.sha256(s.encode("utf-8", "surrogatepass")).hexdigest()[:12]
def main(out):
    a = l1_scan.parser().parse_args(["--source", "code-agent-misalignment-geminicli", "--part", "results-raw", "--input", ARCHIVE])
    prof, _ = l1_scan.resolve(a.source, a.part, None)
    src, _ = l1_scan.build_source(a, prof, a.part, l1_scan.IngestLimits())
    ents = src.entries()
    disp = l1_scan.classify(ents, prof)
    roles_screened = Counter()
    want = set()
    for e in ents:
        d = disp.get(e.label, e.disposition).split(":", 1)[0]
        if d in ("context", "blob", "auxiliary") and not e.own.lower().endswith((".json", ".jsonl")):
            want.add(e.label)
            m = ROLL.match(e.own)
            roles_screened[m.group(4) if m else e.own] += 1
    r = {"screened": len(want), "roles_screened": dict(roles_screened)}
    acc = defaultdict(Counter)
    for label, _s, data in src.stream(want):
        if not isinstance(data, bytes):
            continue
        m = ROLL.match(label)
        role, model, sk = (m.group(4), m.group(1), m.group(2)) if m else (label, "-", "-")
        text = data.decode("utf-8", "replace")
        seen = set()
        for line in text.split("\n"):
            lc = line[:1] if line[:1] in "+- " and not line.startswith(("+++", "---")) else "other"
            for name, rx in l1_scan.ACCOUNT_PATTERNS.items():
                for mm in rx.finditer(line):
                    n = mm.group(1)
                    if n.lower() in l1_scan.GENERIC_ACCOUNTS:
                        continue
                    k = f"{name}:{d12(n)}"
                    acc[k + ":role"][role] += 1
                    acc[k + ":line"][lc] += 1
                    acc[k + ":model"][model] += 1
                    acc[k + ":skeleton"][sk] += 1
                    acc[k + ":line_has_jss_agent_work"][str("jss_agent_work" in line)] += 1
                    nxt = line[mm.end():].split("/", 1)[0] if name == "home-dir" else ""
                    acc[k + ":next_segment"][d12(nxt) if nxt != "jss_agent_work" else "jss_agent_work"] += 1
                    seen.add(k)
            for sname in ("private-key-block", "jwt"):
                if l1_scan.SECRET_PATTERNS[sname].search(line):
                    acc[f"secret:{sname}:role"][role] += 1
                    acc[f"secret:{sname}:line"][lc] += 1
                    acc[f"secret:{sname}:model"][model] += 1
                    acc[f"secret:{sname}:skeleton"][sk] += 1
        for k in seen:
            acc[k + ":files"]["n"] += 1
        if "jss_agent_work" in text:
            acc["jss_agent_work"][role] += 1
    r["by"] = {k: dict(v) for k, v in sorted(acc.items())}
    Path(out).write_text(json.dumps(r, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print("ok", len(want))
if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
