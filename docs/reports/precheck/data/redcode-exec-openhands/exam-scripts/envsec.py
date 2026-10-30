"""Pre-check examiner, redcode-exec-openhands: characterise strict token-shaped strings in the supp zip's environment/
tree and the context of two unresolved /home/<name>/ accounts. Never prints a token, an account name or a full label:
labels are reduced to segment classes (allowlisted common names kept), tokens to shape statistics.
Usage: uv run python -I envsec.py OUT.json
"""
import hashlib, json, re, sys
from collections import Counter, defaultdict
from pathlib import Path
from agentprov.ingest.archives import iter_zip_members, open_zip

Z = Path.home() / ".agentprov/staging/10g/zenodo_23168099"
STRICT = {"anthropic": r"sk-ant-[A-Za-z0-9_\-]{20,}", "openai": r"(?<![A-Za-z0-9])sk-(?:proj-)?[A-Za-z0-9_\-]{20,}",
          "aws": r"(?:AKIA|ASIA)[0-9A-Z]{16}", "hf": r"hf_[A-Za-z0-9]{34,}"}
KEEP = {"environment", "OpenHands", "openhands", "tests", "test", "unit", "frontend", "src", "docs", "runtime", "llm",
        "core", "utils", "server", "integrations", "enterprise", "__tests__", "evaluation", "containers", "app", "sandbox"}
PLACE = re.compile(r"(?i)fake|dummy|example|test|xxxx|your|placeholder|mock|sample|redacted|1234|abcd")
HOME = re.compile(r"/home/([^/\s\"'<>\\]{1,64})/([^/\s\"'<>\\]{0,40})")
WATCH = {"<account-B>", "03924d78", "12ed0620"}
d8 = lambda s: hashlib.sha256(s.encode()).hexdigest()[:8]


def seg(p):
    return p if p in KEEP else ("<dot-file>" if p.startswith(".") else "<seg>")


def main(out):
    R = {"env_tokens": [], "watch_next_segment": defaultdict(Counter), "watch_where": defaultdict(Counter)}
    with open(Z / "agent-execution-decisions-supp.zip", "rb") as fp, open_zip(fp, release=False) as oz:
        for m in iter_zip_members(oz):
            lab = m.label or ""
            try:
                t = oz.read_member(m).decode("utf-8")
            except UnicodeDecodeError:
                continue
            for n, nxt in HOME.findall(t):
                if d8(n) in WATCH:
                    R["watch_next_segment"][d8(n)][nxt if re.fullmatch(r"\.?[a-z_]{1,20}", nxt or "") else "<other>"] += 1
                    R["watch_where"][d8(n)][lab.split("/")[0] + "/" + lab.split("/")[-2]] += 1
            if not lab.startswith("environment/"):
                continue
            parts = lab.split("/")
            for k, rx in STRICT.items():
                for mt in re.finditer(rx, t):
                    v = mt.group(0)
                    ctx = t[max(0, mt.start() - 60): mt.end() + 60]
                    R["env_tokens"].append({"kind": k, "path_shape": "/".join(seg(p) for p in parts[:-1]) + "/" + ("<dot-file:" + parts[-1][1:5] + "...>" if parts[-1].startswith(".") else "<file>." + parts[-1].rsplit(".", 1)[-1][:6]),
                                            "len": len(v), "distinct_chars": len(set(v)), "placeholder_word_in_token_or_context": bool(PLACE.search(ctx)),
                                            "d8": d8(v), "depth": len(parts)})
    R["watch_next_segment"] = {k: dict(v) for k, v in R["watch_next_segment"].items()}
    R["watch_where"] = {k: dict(v) for k, v in R["watch_where"].items()}
    Path(out).write_text(json.dumps(R, indent=1, sort_keys=True))
    print(json.dumps(R, sort_keys=True)[:5000])


if __name__ == "__main__":
    main(sys.argv[1])
