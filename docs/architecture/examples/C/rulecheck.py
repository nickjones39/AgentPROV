"""Check C.6.4 rule-coverage and class-compatibility semantics on the generated examples (r2 rule names, D.5.4)."""
import glob
import json
from pathlib import Path

HERE = Path(__file__).parent
I_RULES = {
    # adapter catalogues (D.5.4; class I)
    "agentdojo.pipeline_dir_is_model_identity@1", "agentdojo.defence_suffix@1", "agentdojo.context_is_prefix@1",
    "agentdojo.pi_detector_sentinel@1", "agentdojo.naive_local_timestamp_unverified@1",
    "agentdojo.payload_attributed_to_attacker@1", "agentdojo.auto_execution_unverified@1", "agentdojo.checker_inputs_unverified@1", "adprov.v1_capture_code_semantics@1", "adprov.context_is_prefix@1",
    "rope.guard_active_in_main_tree@1", "rope.model_dir_identity@1", "rope.harness_is_vendored_autodojo@1",
    "rope.denial_error_pattern@1",
    # planned stac catalogue (D.8.2; class I)
    "stac.assistant_turns_scripted@1", "stac.prefix_user_turns_by_prompt_writer@1",
    "stac.prompt_written_after_execution@1", "stac.planning_after_prefix@1", "stac.tool_status_from_content@1",
    # agentdojo.suites semantics-profile rules (class I: baseline tables)
    "agentdojo.integrity_external_content@1", "agentdojo.channel_table@1", "agentdojo.read_tools@1",
    "agentdojo.sink_tools@1"}
SKIP = {"k", "id", "ev", "by", "evf", "rule", "src", "unk", "ext", "aer", "ex", "mode", "unit", "source_key", "artifacts",
        "adapter", "dialect", "profile", "rules", "ns", "canon", "hash", "capture", "related"}


def tagged(rec):
    """Effective tags for top-level asserted fields (record default) and evf pointers."""
    out = {"/" + f: rec["ev"] for f in rec if f not in SKIP}
    out.update(rec.get("evf") or {})
    return out


def applicable(rec, ptr):
    refs = rec.get("rule") or []
    scoped = [(r.split("#", 1)[0], r.split("#", 1)[1]) for r in refs if "#" in r]
    best = [(rid, p) for rid, p in scoped if ptr == p or ptr.startswith(p + "/")]
    if best:
        n = max(len(p) for _, p in best)
        return [rid for rid, p in best if len(p) == n]
    return [r for r in refs if "#" not in r]


errs = 0
files = sorted(glob.glob(str(HERE / "*.aer.jsonl"))) + sorted(glob.glob(str(HERE / "*.sem.jsonl")))
for f in files:
    for ln in open(f, encoding="utf-8"):
        rec = json.loads(ln)
        if rec["k"] in ("seal", "sem"):
            continue
        if rec["k"] == "ann":
            cls = "I" if any(r in I_RULES for r in rec["rule"]) else "D"
            if rec["ev"] == "D" and cls == "I":
                print(f, rec["id"], "SEM D with I rule"); errs += 1
            if rec["ev"] == "I" and cls != "I":
                print(f, rec["id"], "SEM I without I rule"); errs += 1
            continue
        tags = tagged(rec)
        has_i = False
        for p, t in tags.items():
            if t not in ("D", "I"):
                continue
            app = applicable(rec, p)
            if not app:
                print(f, rec["id"], p, "no applicable rule"); errs += 1
            if t == "D" and any(r in I_RULES for r in app):
                print(f, rec["id"], p, "D covered by I rule", app); errs += 1
            has_i |= t == "I"
        if has_i and not any(r.split("#")[0] in I_RULES for r in rec.get("rule", [])):
            print(f, rec["id"], "I assertion but no I-class rule cited"); errs += 1
        for r in rec.get("rule", []):
            if "#" in r:
                p = r.split("#", 1)[1]
                eff = tags.get(p)
                if eff is None:
                    cands = [q for q in tags if p.startswith(q + "/")]
                    eff = tags[max(cands, key=len)] if cands else rec["ev"]
                if eff.startswith("O") and p not in (rec.get("unk") or {}):
                    print(f, rec["id"], "scoped rule on O field", r); errs += 1
print("files:", len(files), "errors:", errs)
