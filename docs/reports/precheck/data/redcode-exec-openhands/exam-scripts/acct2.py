"""Pre-check examiner, redcode-exec-openhands: context classes of the unresolved /home/<name>/ hits (booleans and
counts only) and the home-path names of the environment/ dot-file history. Usage: uv run python -I acct2.py OUT.json"""
import hashlib, json, re, sys
from collections import Counter, defaultdict
from pathlib import Path
from agentprov.ingest.archives import iter_zip_members, open_zip
from agentprov.ingest.loaders import strict_json_loads

Z = Path.home() / ".agentprov/staging/10g/zenodo_23168099"
HOME = re.compile(r"/home/([^/\s\"'<>\\]{1,64})/")
WATCH = {"<account-B>", "03924d78", "<account-A>"}
d8 = lambda s: hashlib.sha256(s.encode()).hexdigest()[:8]
PATHLIST = re.compile(r"(?:/[^:\s]+:){2,}")


def main(out):
    R = defaultdict(Counter)
    for z in sorted(Z.glob("trajectories_OH-*.zip")):
        with open(z, "rb") as fp, open_zip(fp, release=False) as oz:
            for m in iter_zip_members(oz):
                if m.disposition != "selected" or "/trajectory/" not in (m.label or ""):
                    continue
                for e in strict_json_loads(oz.read_member(m)):
                    s = json.dumps(e, ensure_ascii=False)
                    for n in set(HOME.findall(s)):
                        k = d8(n)
                        if k not in WATCH: continue
                        for mt in re.finditer(re.escape("/home/" + n + "/"), s):
                            ctx = s[max(0, mt.start() - 200): mt.end() + 200]
                            R[k][f"pathlist={bool(PATHLIST.search(ctx))}"] += 1
                            R[k][f"PATH_word={'PATH' in ctx}"] += 1
                            R[k][f"pip_or_site={'site-packages' in ctx or 'pip' in ctx}"] += 1
                            R[k][f"cmd={str((e.get('args') or {}).get('command', ''))[:24].split(' ')[0] if 'action' in e else 'obs:' + str(e.get('observation'))}"] += 1
    with open(Z / "agent-execution-decisions-supp.zip", "rb") as fp, open_zip(fp, release=False) as oz:
        for m in iter_zip_members(oz):
            parts = (m.label or "").split("/")
            if parts[0] == "environment" and len(parts) == 3 and parts[-1].startswith(".bash"):
                t = oz.read_member(m).decode("utf-8", "replace")
                R["bash_history"]["lines"] = t.count("\n")
                for n in HOME.findall(t): R["bash_history"]["home:" + d8(n)] += 1
                R["bash_history"]["users_dir_hits"] = len(re.findall(r"/Users/[^/\s]+/", t))
                R["bash_history"]["hf_token_shapes"] = len(re.findall(r"hf_[A-Za-z0-9]{34,}", t))
                R["bash_history"]["huggingface_word"] = len(re.findall(r"(?i)hugging|hf auth|HF_TOKEN|huggingface-cli", t))
                R["bash_history"]["files"] += 1
    Path(out).write_text(json.dumps(R, indent=1, sort_keys=True))
    print(json.dumps(R, sort_keys=True))


if __name__ == "__main__":
    main(sys.argv[1])
