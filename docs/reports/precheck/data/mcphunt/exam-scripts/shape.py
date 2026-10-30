"""Shape booleans (no value) for the two openai-key-shaped strings in mitigation/minimax_m3_rv1 #/traces/106 and the
fc5669b5 home path in main/gpt_5_4 #/traces/370: character classes, hyphen-word structure, the next path segment class,
sanitizer placeholders in the same result, and count of other /home/<x>/ names in that result.
usage: uv run python -I shape.py <staging-root> <out.json>
"""
import hashlib, json, os, re, sys
from agentprov.ingest.jsonstream import open_json_stream
from agentprov.ingest.limits import IngestLimits, MIB
root, outp = os.path.expanduser(sys.argv[1]), sys.argv[2]
LIM = IngestLimits().replace(max_json_element_bytes=64 * MIB, max_jsonl_line_bytes=64 * MIB)
KEY = re.compile(r"(?<![A-Za-z0-9])sk-(?!ant-)(?:proj-|svcacct-)?[A-Za-z0-9_\-]{20,}")
HOME = re.compile(r"/home/([^/\s\"'<>\\]{1,64})/([^/\s\"'<>\\]{0,64})")
PL = ("/home/user/", "/mcphunt/", "<HOME>", "MCPHUNT-HOST", "<redacted>", "<internal-gateway>")
def item(lab, idx):
    with open(os.path.join(root, lab), "rb") as fh:
        for it in open_json_stream(fh, LIM, arrays=("/traces",)):
            if it.index == idx: return it.value
out = {"keys": [], "home": []}
t = item("mitigation/minimax_m3_rv1.json", 106)
for e in t["events"]:
    rf = str(e.get("result_full"))
    for mm in KEY.finditer(rf):
        s = mm.group(0); body = s[3:]
        out["keys"].append({"d8": hashlib.sha256(s.encode()).hexdigest()[:8], "len": len(s), "hyphens": body.count("-"),
            "underscores": body.count("_"), "lower_alpha_and_hyphen_only": bool(re.fullmatch(r"[a-z\-]+", body)),
            "digits": sum(c.isdigit() for c in body), "upper": sum(c.isupper() for c in body),
            "result_len": len(rf), "path_context": bool(re.search(r"[/\\][^\s]*$", rf[max(0, mm.start() - 80):mm.start()]))})
t = item("main/gpt_5_4.json", 370)
for e in t["events"]:
    rf = str(e.get("result_full"))
    names = {hashlib.sha256(m.group(1).encode()).hexdigest()[:8] for m in HOME.finditer(rf)}
    for mm in HOME.finditer(rf):
        if hashlib.sha256(mm.group(1).encode()).hexdigest()[:8] != "fc5669b5": continue
        nxt = mm.group(2)
        out["home"].append({"next_is_dot_ssh": nxt == ".ssh", "next_dotfile": nxt.startswith("."), "next_len": len(nxt),
            "placeholders_in_result": [p for p in PL if p in rf], "distinct_home_names_in_result": len(names),
            "result_len": len(rf), "args_keys": sorted((e.get("args") or {}).keys())})
json.dump(out, open(outp, "w"), indent=1); print(json.dumps(out))
