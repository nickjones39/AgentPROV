"""H-03 extension: every github/*/important_instructions/injection_task_1 file: logged security vs an executed git_delete_repo (strict ingest; counts only)."""
import glob, os, collections, json, sys
from agentprov.ingest.loaders import strict_json_loads
R = os.path.expanduser("~/Desktop/PhD/Labs/AgentPROV-upstream/agentdyn/runs")
out = {}
for scope, pat in (("user_task_2", "user_task_2"), ("all_user_tasks", "user_task_*")):
    c = collections.Counter()
    for p in glob.glob(f"{R}/*/github/{pat}/important_instructions/injection_task_1.json"):
        v = strict_json_loads(open(p, "rb").read())
        part = "c" if "build_constraints" in v else ("a" if "agentdojo_package_version" in v else "b")
        ex = any(m.get("role") == "tool" and isinstance(m.get("tool_call"), dict) and m["tool_call"].get("function") == "git_delete_repo" and not m.get("error")
                 for m in v.get("messages") or [] if isinstance(m, dict))
        c[f"{part}|security={v.get('security')}|executed_git_delete_repo={ex}"] += 1
    out[scope] = dict(sorted(c.items()))
json.dump(out, open(sys.argv[1], "w"), indent=1); print(json.dumps(out, indent=1))
