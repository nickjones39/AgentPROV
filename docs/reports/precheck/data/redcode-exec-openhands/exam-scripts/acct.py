"""Pre-check examiner, redcode-exec-openhands head: account-path, secret-like and aggregate-row characterisation.

Counts only; account names appear only as 8-hex sha256 prefixes; no matched secret-like text is printed.
Usage: uv run python -I acct.py OUT.json
"""
import csv, hashlib, io, json, re, sys
from collections import Counter, defaultdict
from pathlib import Path
from agentprov.ingest.archives import iter_zip_members, open_zip
from agentprov.ingest.loaders import strict_json_loads

Z = Path.home() / ".agentprov/staging/10g/zenodo_23168099"
HOME = re.compile(r"/home/([^/\s\"'<>\\]{1,64})/")
GENERIC = {"ubuntu", "user", "root", "runner", "app", "node", "admin", "agent", "dev", "test", "guest", "vscode", "jovyan",
           "circleci", "ec2-user", "sandbox", "username", "you", "yourname", "name", "me", "shared", "default", "docker",
           "work", "coder", "jenkins", "alice", "bob", "john", "jane", "example", "demo", "<user>", "user1", "myuser"}
CANDIDATES = ["openhands", "enduser", "pn", "linuxbrew", "kali", "pi", "vagrant", "ftp", "www-data", "nobody", "daemon",
              "postgres", "mysql", "git", "ubuntu", "testuser", "victim", "attacker", "student", "researcher", "redcode",
              "codeact", "oh", "openhands-user", "appuser", "dockeruser", "devuser", "lab", "server", "anonymous"]
CRED = re.compile(r"(?i)(?:api[_-]?key|secret|token|passw(?:or)?d)[\"']?\s{0,3}[:=]\s{0,3}[\"']?[A-Za-z0-9_\-/+=.]{16,}")
STRICT = {"anthropic": r"sk-ant-[A-Za-z0-9_\-]{20,}", "openai": r"(?<![A-Za-z0-9])sk-(?:proj-)?[A-Za-z0-9_\-]{20,}",
          "aws": r"(?:AKIA|ASIA)[0-9A-Z]{16}", "github": r"gh[pousr]_[A-Za-z0-9]{30,}", "google": r"AIza[0-9A-Za-z_\-]{35}",
          "hf": r"hf_[A-Za-z0-9]{34,}", "private_key": r"-----BEGIN[A-Z ]{0,20} PRIVATE KEY-----"}
d8 = lambda s: hashlib.sha256(s.encode()).hexdigest()[:8]


def main(out):
    R = {"candidate_d8": {d8(c): c for c in CANDIDATES}}
    names = defaultdict(lambda: Counter())
    cred = Counter()
    cred_texts = []
    for z in sorted(Z.glob("trajectories_OH-*.zip")):
        with open(z, "rb") as fp, open_zip(fp, release=False) as oz:
            for m in iter_zip_members(oz):
                if m.disposition != "selected" or "/trajectory/" not in (m.label or ""):
                    continue
                ev = strict_json_loads(oz.read_member(m))
                first_user = next((e for e in ev if e.get("source") == "user" and e.get("action") == "message"), {})
                prompt = json.dumps(first_user, ensure_ascii=False)
                seen = set()
                for i, e in enumerate(ev):
                    s = json.dumps(e, ensure_ascii=False)
                    who = "obs" if "observation" in e else f"act:{e.get('source')}"
                    for n in HOME.findall(s):
                        if n.lower() in GENERIC or n in seen: continue
                        seen.add(n)
                        names[d8(n)][f"first_in={who}:{e.get('observation') or e.get('action')}"] += 1
                        names[d8(n)][f"in_task_prompt={n in prompt}"] += 1
                    for mt in CRED.finditer(s):
                        cred_texts.append(mt.group(0))
                        cred[f"{who}:in_task_prompt={mt.group(0) in prompt}"] += 1
    ds, pg = [], []
    supp_names = defaultdict(Counter); strict_files = []; csv_rows = []; summary_arms = set(); log_arms = set()
    with open(Z / "agent-execution-decisions-supp.zip", "rb") as fp, open_zip(fp, release=False) as oz:
        for m in iter_zip_members(oz):
            lab = m.label or ""
            b = oz.read_member(m)
            try:
                t = b.decode("utf-8")
            except UnicodeDecodeError:
                continue
            if lab.startswith("dataset/RedCode-Exec/"): ds.append(t)
            if lab.startswith("prompt_generator/output/"): pg.append(t)
            top = lab.split("/")[0]
            for n in HOME.findall(t):
                if n.lower() not in GENERIC:
                    supp_names[top][d8(n)] += 1
            if top == "environment":
                kinds = sorted(k for k, rx in STRICT.items() if re.search(rx, t))
                if kinds:
                    parts = lab.split("/")
                    strict_files.append({"kinds": kinds, "dir_class": "test" if any("test" in p.lower() for p in parts) else
                                         ("docs" if any(p.lower() in ("docs", "doc") for p in parts) else "other"),
                                         "ext": parts[-1].rsplit(".", 1)[-1][:8] if "." in parts[-1] else ""})
            mm = re.match(r"^results/OH/([^/]+)/(S[123])/(python|bash)/", lab)
            if mm and lab.endswith("_summary.json") and "/summary/S" in lab: summary_arms.add("/".join(mm.groups()))
            if mm and "/conversation_log/" in lab: log_arms.add("/".join(mm.groups()))
            if mm and lab.endswith("per_scenario.csv"):
                for row in csv.DictReader(io.StringIO(t)):
                    if not (row.get("scenario") or "").strip().isdigit():
                        csv_rows.append({"arm": "/".join(mm.groups()), "scenario": (row.get("scenario") or "")[:20],
                                         "internal_id": (row.get("internal_id") or "")[:20], "risky_level": (row.get("risky_level") or "")[:20],
                                         "success": row.get("success"), "reject": row.get("reject"), "fail": row.get("fail"), "total": row.get("total")})
    dst, pgt = "\n".join(ds), "\n".join(pg)
    R["traj_names"] = {k: dict(v) for k, v in names.items()}
    R["supp_names_by_top"] = {k: dict(v) for k, v in supp_names.items()}
    R["traj_names_also_in_supp_results"] = sorted(set(names) & set(supp_names.get("results", {})))
    R["traj_names_also_in_environment"] = sorted(set(names) & set(supp_names.get("environment", {})))
    R["cred_matches"] = {"total": len(cred_texts), "by_place": dict(cred), "in_redcode_dataset": sum(t in dst for t in cred_texts),
                         "in_prompt_generator": sum(t in pgt for t in cred_texts), "distinct_d8": len({d8(t) for t in cred_texts})}
    R["environment_strict_secret_files"] = strict_files
    R["csv_non_scenario_rows"] = csv_rows
    R["arms_with_summary_json"] = sorted(summary_arms); R["arms_with_logs"] = sorted(log_arms)
    Path(out).write_text(json.dumps(R, indent=1, sort_keys=True))
    print(json.dumps({k: R[k] for k in R if k != "candidate_d8"}, sort_keys=True)[:6000])


if __name__ == "__main__":
    main(sys.argv[1])
