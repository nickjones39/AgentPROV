# ruff: noqa  (precheck examiner script for ast-survey-agentharm, committed as run; read-only analysis)
"""Tool error templates for file tools (counts; templates with quoted names/paths masked)."""
import json, re, sys
from collections import Counter
from pathlib import Path
from agentprov.ingest.archives import iter_zip_members, open_zip
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads
C = Path(sys.argv[1]).expanduser()
SH = {"ollama/gpt-oss:120b": "gptoss", "ollama/qwen3-coder:30b": "coder", "ollama/qwen3:14b": "qwen14"}
FN = {"read_file", "edit_txt", "convert_pdf_to_text"}
def tmpl(s):
    s = s[:200]
    s = re.sub(r"'[^']*'|\"[^\"]*\"", "<q>", s)
    s = re.sub(r"(/[^\s,:;)]+)+", "<path>", s)
    s = re.sub(r"\b[\w.-]+\.(txt|pdf|md|csv|json|docx|py|html|jpg|png|mp4|mp3)\b", "<file>", s)
    s = re.sub(r"\d+", "<n>", s)
    return s[:90]
out = Counter(); calls = Counter(); samp = Counter(); sampscore = {}
for line in (C / "raw/origins.jsonl").read_text().splitlines():
    r = json.loads(line)
    if r.get("origin", {}).get("kind") != "git": continue
    sha = r["sha256"].split(":", 1)[1]
    p = next((C / "raw/objects" / sha[:2]).glob(sha + "*"))
    with p.open("rb") as fp, open_zip(fp, IngestLimits(), release=False) as z:
        ms = list(iter_zip_members(z))
        h = strict_json_loads(z.read_member(next(m for m in ms if m.label == "header.json")))["eval"]
        arm = SH[h["model"]] + ("_benign" if h["task"].endswith("benign") else "_harmful")
        for m in ms:
            if not (m.label or "").startswith("samples/"): continue
            s = strict_json_loads(z.read_member(m)); att = s.get("attachments") or {}
            hit = False
            for e in s.get("events") or []:
                if e.get("event") == "tool" and e.get("function") in FN:
                    rr = e.get("result")
                    if isinstance(rr, str) and rr.startswith("attachment://"): rr = att.get(rr[13:], "")
                    if (e.get("error") or {}).get("type") == "file_not_found" or (isinstance(rr, str) and "File not found at" in rr): hit = True
                if e.get("event") != "tool" or e.get("function") not in FN: continue
                fn = e["function"]; calls[f"{arm}|{fn}"] += 1
                res = e.get("result")
                if isinstance(res, str) and res.startswith("attachment://"): res = att.get(res[13:], "")
                err = e.get("error")
                if err:
                    out[f"{arm}|{fn}|error:{err.get('type')}|{tmpl(err.get('message') or '')}"] += 1
                elif isinstance(res, str) and re.search(r"not found|no such|error|does not exist", res, re.I):
                    out[f"{arm}|{fn}|result|{tmpl(res)}"] += 1
            sc = float(s["scores"]["combined_scorer"]["value"]["score"]); key = f"{arm}|{'fnf' if hit else 'no_fnf'}"
            v = sampscore.setdefault(key, [0, 0.0]); v[0] += 1; v[1] += sc
            if hit: samp[arm] += 1
print(json.dumps({"samples_with_file_not_found": dict(sorted(samp.items())), "mean_score": {k: [v[0], round(v[1] / v[0], 4) if v[0] else None] for k, v in sorted(sampscore.items())}, "calls": dict(sorted(calls.items())), "error_templates": dict(sorted(out.items()))}, indent=1))
