"""Aggregate the per-execution feature rows of ``phase10_extract.py`` into per-corpus and cross-corpus tables.

Reads ``<indir>/<corpus>.jsonl`` (written by the extractor: ids, counts and safe tokens only) and writes
``<indir>/summary.json``; prints a plain-text digest. No corpus file is read here.

Usage: ``python tools/analysis/phase10_aggregate.py --in OUTDIR``.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from message_roles import group_counts, is_assistant  # noqa: E402  (assistant + DTap agent: one shared grouping)

CORPORA = ["rope-p10", "agentdyn-a-p10", "agentdojo-upstream-head-p10", "mandate-agentdojo-eval-p10", "ast-survey-agentdojo-p10"]


def q(values: list[float]) -> dict[str, Any]:
    if not values:
        return {}
    v = sorted(values)
    n = len(v)
    return {"n": n, "min": v[0], "p50": v[n // 2], "p95": v[min(n - 1, int(n * 0.95))], "p99": v[min(n - 1, int(n * 0.99))],
            "max": v[-1], "mean": round(statistics.fmean(v), 3)}


def judg(row: dict[str, Any], name: str, recorded: bool = True) -> Any:
    for j in row.get("judgements") or ():
        if j["name"] == name and (j["revises"] is not recorded):
            return j
    return None


def top(counter: Counter[Any], n: int = 25) -> list[tuple[Any, int]]:
    return counter.most_common(n)


def ex_examples(rows: list[dict[str, Any]], k: int = 3) -> list[str]:
    return sorted(r["ex"] for r in rows)[:k]


def analyse(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"n": len(rows)}
    # ---- integrity
    integ = Counter(e for r in rows for e in r["integrity"])
    out["integrity_errors"] = dict(integ)
    out["integrity_examples"] = {code: ex_examples([r for r in rows if code in r["integrity"]]) for code in integ}
    out["dup_ex"] = sum(c - 1 for c in Counter(r["ex"] for r in rows).values() if c > 1)
    out["dup_source_sha"] = sum(c - 1 for c in Counter(r["source_sha"] for r in rows).values() if c > 1)
    out["n_origins"] = dict(Counter(r.get("n_origins") for r in rows))
    out["multi_origin_examples"] = ex_examples([r for r in rows if (r.get("n_origins") or 1) > 1])
    out["raw_bytes"] = q([r.get("raw_bytes", 0) for r in rows])
    out["status"] = dict(Counter(r["status"] for r in rows))
    out["completeness"] = dict(Counter(r["completeness"] for r in rows))
    vc = [r for r in rows if r["completeness"] == "verified_complete"]
    out["verified_complete_composition"] = dict(Counter(
        f"unit={r['unit']}|run_error={r['run_error']}|n_msgs={'0' if not r['n_messages'] else '>0'}|assistant={r['roles'].get('assistant', 0) > 0}"
        for r in vc))
    out["verified_complete_examples"] = ex_examples(vc)
    out["unit"] = dict(Counter(r["unit"] for r in rows))
    out["variant"] = dict(Counter(r["variant"] for r in rows))
    out["profile"] = dict(Counter(r["profile"] for r in rows))
    # ---- facets
    for key in ("model", "provider", "suite", "benchmark", "attack", "defence", "task_kind", "bench_version", "dist_version",
                "sys_prompt_variant", "rope_arm", "final_role", "run_error_head", "benchmark_era"):
        out[f"facet_{key}"] = dict(Counter(str(r.get(key)) for r in rows))
    out["pipeline_name_safe_distinct"] = len({r.get("pipeline_name_digest") for r in rows})
    # ---- issues
    issues = Counter(c for r in rows for c in r["seal_issues"])
    out["seal_issues"] = dict(issues)
    out["seal_issue_examples"] = {c: ex_examples([r for r in rows if c in r["seal_issues"]]) for c in issues}
    out["seal_issue_details"] = dict(Counter(d for r in rows for d in r.get("seal_issue_details", ())))
    by_model: dict[str, Counter[str]] = defaultdict(Counter)
    n_model: Counter[str] = Counter()
    for r in rows:
        m = str(r.get("model"))
        n_model[m] += 1
        for c in r["seal_issues"]:
            by_model[m][c] += 1
    out["issues_by_model"] = {m: {"n": n_model[m], **dict(by_model[m])} for m in sorted(n_model)}
    by_suite: dict[str, Counter[str]] = defaultdict(Counter)
    for r in rows:
        for c in r["seal_issues"]:
            by_suite[str(r.get("suite"))][c] += 1
    out["issues_by_suite"] = {s: dict(c) for s, c in sorted(by_suite.items())}
    by_attack: dict[str, Counter[str]] = defaultdict(Counter)
    for r in rows:
        for c in r["seal_issues"]:
            by_attack[str(r.get("attack"))][c] += 1
    out["issues_by_attack"] = {s: dict(c) for s, c in sorted(by_attack.items())}
    # ---- accounting
    out["acc_status"] = dict(Counter(r.get("acc_status") for r in rows))
    out["acc_checks"] = dict(Counter(f"{k}:{v}" for r in rows for k, v in (r.get("acc_checks") or {}).items()))
    disp = Counter()
    for r in rows:
        for k, v in (r.get("acc_dispatch") or {}).items():
            disp[k] += v
    out["acc_dispatch_sum"] = dict(disp)
    # ---- unknowns and evidence classes
    unk = Counter()
    for r in rows:
        unk.update(r.get("unk") or {})
    out["unk_top"] = top(unk, 60)
    unk_reason = Counter()
    for k, v in unk.items():
        unk_reason[k.rsplit(":", 1)[1]] += v
    out["unk_by_reason"] = dict(unk_reason)
    ev = Counter()
    for r in rows:
        ev.update(r.get("ev") or {})
    out["aer_record_ev"] = dict(ev)
    evf = Counter()
    for r in rows:
        evf.update(r.get("evf") or {})
    out["aer_evf_by_class"] = dict(Counter({c: 0 for c in "ODI"}) + Counter({k.rsplit(":", 1)[1]: v for k, v in evf.items()}))
    evf_c = Counter()
    for k, v in evf.items():
        evf_c[k.rsplit(":", 1)[1]] += v
    out["aer_evf_by_class"] = dict(evf_c)
    pc = Counter()
    for r in rows:
        pc.update(r.get("prov_classes") or {})
    out["prov_classes"] = dict(pc)
    ps = Counter()
    for r in rows:
        ps.update(r.get("prov_sections") or {})
    out["prov_sections"] = dict(ps)
    pr = Counter()
    for r in rows:
        pr.update(r.get("prov_rules") or {})
    out["prov_rules"] = dict(pr)
    out["prov_bundles"] = q([sum((r.get("prov_bundles") or {}).values()) for r in rows])
    out["prov_inference_bundles"] = q([(r.get("prov_bundles") or {}).get("inference", 0) for r in rows])
    # ---- graph
    for key in ("prov_nodes", "prov_edges", "prov_core_nodes", "prov_core_edges", "prov_components", "prov_core_components",
                "prov_aug_components", "prov_bytes", "n_messages", "n_tool_call_parts", "duration"):
        vals = [r.get(key) for r in rows if isinstance(r.get(key), int | float)]
        out[f"dist_{key}"] = q(vals)
    out["aug_minor"] = dict(Counter(k for r in rows for k in (r.get("prov_aug_minor") or {})))
    out["aug_isolated"] = dict(sum((Counter(r.get("prov_aug_isolated") or {}) for r in rows), Counter()))
    out["union_isolated"] = dict(sum((Counter(r.get("prov_isolated") or {}) for r in rows), Counter()))
    out["core_isolated"] = dict(sum((Counter(r.get("prov_core_isolated") or {}) for r in rows), Counter()))
    out["prov_forbidden"] = dict(sum((Counter(r.get("prov_forbidden") or {}) for r in rows), Counter()))
    out["prov_times"] = sum(r.get("prov_times", 0) for r in rows)
    out["prov_xcheck"] = dict(sum((Counter(r.get("prov_xcheck") or {}) for r in rows), Counter()))
    out["prov_xcheck_examples"] = {k: ex_examples([r for r in rows if (r.get("prov_xcheck") or {}).get(k)]) for k in out["prov_xcheck"]}
    out["te_used_kinds"] = dict(sum((Counter(r.get("te_used_kinds") or {}) for r in rows), Counter()))
    biggest = sorted(rows, key=lambda r: r.get("prov_nodes", 0), reverse=True)[:3]
    smallest = sorted(rows, key=lambda r: r.get("prov_nodes", 0))[:3]
    out["largest_graphs"] = [(r["ex"], r.get("prov_nodes"), r.get("n_messages"), r.get("model"), r.get("suite"), r.get("attack")) for r in biggest]
    out["smallest_graphs"] = [(r["ex"], r.get("prov_nodes"), r.get("n_messages"), r.get("unit"), r.get("model")) for r in smallest]
    # ---- records
    out["record_kinds"] = dict(sum((Counter(r.get("record_kinds") or {}) for r in rows), Counter()))
    out["roles"] = dict(sum((Counter(r.get("roles") or {}) for r in rows), Counter()))
    out["msg_actors"] = dict(sum((Counter(r.get("msg_actors") or {}) for r in rows), Counter()))
    out["te_status"] = dict(sum((Counter(r.get("te_status") or {}) for r in rows), Counter()))
    out["decisions"] = dict(sum((Counter(r.get("decisions") or {}) for r in rows), Counter()))
    out["mc_roles"] = dict(sum((Counter(r.get("mc_roles") or {}) for r in rows), Counter()))
    out["link_ev"] = dict(sum((Counter(r.get("link_ev") or {}) for r in rows), Counter()))
    out["mc_input_nonmonotone"] = sum(r.get("mc_input_nonmonotone", 0) for r in rows)
    out["after_issues"] = sum(r.get("after_issues", 0) for r in rows)
    out["n_empty_text_assistant"] = sum(r.get("n_empty_text_assistant", 0) for r in rows)
    out["n_null_text_nocall_assistant"] = sum(r.get("n_null_text_nocall_assistant", 0) for r in rows)
    out["null_nocall_exec"] = sum(1 for r in rows if r.get("n_null_text_nocall_assistant", 0))
    out["n_reasoning_parts"] = sum(r.get("n_reasoning_parts", 0) for r in rows)
    out["n_other_parts"] = sum(r.get("n_other_parts", 0) for r in rows)
    out["n_multi_value_results"] = sum(r.get("n_multi_value_results", 0) for r in rows)
    out["final_assistant_with_calls"] = sum(1 for r in rows if (r.get("final_assistant_calls") or 0) > 0)
    # ---- ids
    idf: dict[str, Counter[str]] = defaultdict(Counter)
    for r in rows:
        idf[str(r.get("model"))].update(r.get("id_forms") or {})
    out["id_forms_by_model"] = {m: dict(c.most_common(6)) for m, c in sorted(idf.items())}
    out["dup_provider_ids_exec"] = dict(Counter(str(r.get("model")) for r in rows if r.get("dup_provider_ids")))
    # ---- text
    out["textchars"] = dict(sum((Counter(r.get("textchars") or {}) for r in rows), Counter()))
    out["textchars_exec"] = {k: sum(1 for r in rows if (r.get("textchars") or {}).get(k)) for k in out["textchars"]}
    fmt_m: dict[str, Counter[str]] = defaultdict(Counter)
    for r in rows:
        fmt_m[str(r.get("model"))].update({k: v for k, v in (r.get("fmt") or {}).items()})
    out["fmt_by_model"] = {m: dict(c) for m, c in sorted(fmt_m.items())}
    out["bad_ident"] = dict(sum((Counter(r.get("bad_ident") or {}) for r in rows), Counter()))
    out["leak"] = dict(sum((Counter(r.get("leak") or {}) for r in rows), Counter()))
    out["leak_exec"] = {k: sum(1 for r in rows if (r.get("leak") or {}).get(k)) for k in out["leak"]}
    out["leak_examples"] = {k: ex_examples([r for r in rows if (r.get("leak") or {}).get(k)]) for k in out["leak"]}
    # ---- judgements and scoring consistency
    jd = Counter()
    for r in rows:
        for j in r.get("judgements") or ():
            jd[f"{j['name']}|{j['value']}|{j['origin']}|{'recomputed' if j['revises'] else 'recorded'}"] += 1
    out["judgements"] = dict(jd)
    benign = [r for r in rows if r.get("attack") is None]
    attacked = [r for r in rows if r.get("attack") is not None and r.get("task_kind") != "dos"]
    out["benign_n"] = len(benign)
    out["benign_with_fixtures"] = sum(1 for r in benign if r.get("n_fixtures"))
    out["benign_with_nonempty_fixtures"] = sum(1 for r in benign if r.get("n_fixtures_nonempty"))
    out["attacked_n"] = len(attacked)
    out["attacked_without_fixtures"] = sum(1 for r in attacked if not r.get("n_fixtures"))
    out["attacked_with_empty_fixture"] = sum(1 for r in attacked if r.get("n_fixtures") and r.get("n_fixtures_nonempty", 0) < r.get("n_fixtures", 0))

    def sec(r: dict[str, Any]) -> Any:
        j = judg(r, "security")
        return j["value"] if j else None

    def sec_c(r: dict[str, Any]) -> Any:  # the recorded security value only when its origin is the checker
        j = judg(r, "security")
        return j["value"] if j and j["origin"] == "checker" else None

    def uti(r: dict[str, Any]) -> Any:
        j = judg(r, "utility")
        return j["value"] if j else None

    has_marker = [r for r in attacked if r.get("sem_marker_present_msgs", 0) > 0]
    out["attacked_with_marker_present"] = len(has_marker)
    out["attacked_no_marker_security_true"] = sum(1 for r in attacked if r.get("sem_marker_present_msgs", 0) == 0 and sec_c(r) is True and r["unit"] == "agent_execution")
    out["attacked_no_marker_security_true_examples"] = ex_examples([r for r in attacked if r.get("sem_marker_present_msgs", 0) == 0 and sec_c(r) is True and r["unit"] == "agent_execution"], 5)
    nm_by = Counter((r.get("suite"), r.get("target")) for r in attacked if r.get("sem_marker_present_msgs", 0) == 0 and sec_c(r) is True and r["unit"] == "agent_execution")
    out["attacked_no_marker_security_true_by_cell"] = [(f"{a}/{b}", c) for (a, b), c in nm_by.most_common(15)]
    out["attacked_no_marker"] = sum(1 for r in attacked if r.get("sem_marker_present_msgs", 0) == 0 and r["unit"] == "agent_execution")
    nm_s = Counter(str(r.get("suite")) for r in attacked if r.get("sem_marker_present_msgs", 0) == 0 and r["unit"] == "agent_execution")
    out["attacked_no_marker_by_suite"] = dict(nm_s)
    out["attacked_by_suite"] = dict(Counter(str(r.get("suite")) for r in attacked))
    out["benign_marker_present"] = sum(1 for r in benign if r.get("sem_marker_present_msgs", 0) > 0)
    out["security_true_attacked"] = sum(1 for r in attacked if sec(r) is True)
    out["security_true_attacked_checker"] = sum(1 for r in attacked if sec_c(r) is True)
    out["utility_true_no_tool_calls_by_cell"] = Counter(f"{r.get('suite')}/{r.get('task_id')}" for r in rows if uti(r) is True and r.get("n_tool_call_parts", 0) == 0 and r["unit"] == "agent_execution").most_common(10)
    out["utility_true_run_error"] = sum(1 for r in rows if r.get("run_error") and uti(r) is True)
    out["security_true_run_error"] = sum(1 for r in rows if r.get("run_error") and sec(r) is True)
    out["utility_true_final_not_assistant"] = sum(1 for r in rows if uti(r) is True and r.get("final_role") is not None
                                                  and not is_assistant(r.get("final_role")))
    out["utility_true_null_final"] = sum(1 for r in rows if uti(r) is True and "retry_passes_inferred" in r["seal_issues"])
    out["utility_true_no_tool_calls"] = sum(1 for r in rows if uti(r) is True and r.get("n_tool_call_parts", 0) == 0 and r["unit"] == "agent_execution")
    out["security_true_no_tool_calls_attacked"] = sum(1 for r in attacked if sec_c(r) is True and r.get("n_tool_call_parts", 0) == 0 and r["unit"] == "agent_execution")
    out["security_true_no_tool_calls_attacked_examples"] = ex_examples([r for r in attacked if sec_c(r) is True and r.get("n_tool_call_parts", 0) == 0 and r["unit"] == "agent_execution"], 5)
    out["security_true_attacked_by_target"] = dict(Counter(f"{r.get('suite')}/{r.get('target')}" for r in attacked if sec(r) is True).most_common(12))
    out["utility_true_by_model"] = {m: f"{sum(1 for r in rows if r.get('model') == m and uti(r) is True)}/{sum(1 for r in rows if r.get('model') == m)}" for m in sorted({str(r.get('model')) for r in rows})}
    # defence decisions in benign runs
    out["benign_with_deny"] = sum(1 for r in benign if any(k.startswith("deny") for k in (r.get("decisions") or {})))
    out["benign_with_redact"] = sum(1 for r in benign if any(k.startswith("redact") for k in (r.get("decisions") or {})))
    out["benign_deny_examples"] = ex_examples([r for r in benign if any(k.startswith("deny") for k in (r.get("decisions") or {}))])
    out["attacked_with_deny"] = sum(1 for r in attacked if any(k.startswith("deny") for k in (r.get("decisions") or {})))
    # SEM
    st = Counter()
    for r in rows:
        st.update(r.get("sem_types") or {})
    out["sem_types"] = dict(st)
    unk_suite = Counter()
    tot_suite = Counter()
    for r in rows:
        unk_suite[str(r.get("suite"))] += r.get("sem_unknown_role", 0)
        tot_suite[str(r.get("suite"))] += sum(v for k, v in (r.get("sem_types") or {}).items() if k.startswith("role:"))
    out["sem_unknown_role_by_suite"] = {s: f"{unk_suite[s]}/{tot_suite[s]}" for s in sorted(tot_suite)}
    out["sem_unknown_exec_by_suite"] = dict(Counter(str(r.get("suite")) for r in rows if r.get("sem_unknown_role", 0)))
    # artefact safety net
    art = Counter()
    art_cls = Counter()
    art_ex: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        for a in r.get("artefacts") or ():
            ids = a["entries"] or ["artefact.unclassified." + a["detector"].removeprefix("artefact.generic.")]
            for i in ids:
                key = f"{i}#{a['variant']}"
                art[key] += 1
                if len(art_ex[key]) < 3:
                    art_ex[key].append(r["ex"])
            art_cls["classified" if a["classified"] else "unclassified"] += 1
    out["artefact_findings"] = dict(sorted(art.items()))
    out["artefact_examples"] = dict(art_ex)
    out["artefact_classified"] = dict(art_cls)
    # timestamps
    starts = [r.get("start_naive") for r in rows if r.get("start_naive")]
    out["start_naive_range"] = (min(starts), max(starts)) if starts else None
    out["start_present"] = len(starts)
    sc = Counter(starts)
    out["start_identical_max"] = sc.most_common(3)
    out["start_shared_by_ge_10"] = sum(c for c in sc.values() if c >= 10)
    by_m_range = {}
    for m in sorted({str(r.get("model")) for r in rows}):
        s = [r["start_naive"] for r in rows if str(r.get("model")) == m and r.get("start_naive")]
        if s:
            by_m_range[m] = (min(s), max(s), len(s))
    out["start_range_by_model"] = by_m_range
    out["duration_nonpositive"] = sum(1 for r in rows if isinstance(r.get("duration"), int | float) and r["duration"] <= 0)
    out["duration_missing"] = sum(1 for r in rows if r.get("duration") is None)
    out["duration_lt_1s_with_calls"] = sum(1 for r in rows if isinstance(r.get("duration"), int | float) and r["duration"] < 1 and group_counts(r.get("roles", {})).get("assistant", 0) >= 2)
    out["duration_lt_1s_examples"] = ex_examples([r for r in rows if isinstance(r.get("duration"), int | float) and r["duration"] < 1 and group_counts(r.get("roles", {})).get("assistant", 0) >= 2])
    viol = []
    for r in rows:
        c, s = r.get("committed_no_later_than"), r.get("start_naive")
        if c and s and s[:10] > c[:10]:
            viol.append(r)
    out["start_after_commit_date"] = len(viol)
    out["commit_date_present"] = sum(1 for r in rows if r.get("committed_no_later_than"))
    out["start_after_commit_examples"] = ex_examples(viol)
    # duplicates (identical trajectories under different files)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        if r.get("traj_digest"):
            groups[r["traj_digest"]].append(r)
    dupg = [g for g in groups.values() if len(g) > 1]
    out["traj_dup_groups"] = len(dupg)
    out["traj_dup_execs"] = sum(len(g) for g in dupg)
    diff_label = Counter()
    for g in dupg:
        for key in ("model", "attack", "target", "task_id", "suite", "defence", "rope_arm"):
            if len({str(r.get(key)) for r in g}) > 1:
                diff_label[key] += 1
    out["traj_dup_label_differs"] = dict(diff_label)
    out["traj_dup_examples"] = [sorted(r["ex"] for r in g)[:3] for g in sorted(dupg, key=lambda g: -len(g))[:5]]
    out["traj_dup_sizes"] = dict(Counter(len(g) for g in dupg))
    out["traj_dup_model_differs"] = [(sorted({str(r.get("model")) for r in g}), g[0].get("n_messages"), sorted(r["ex"] for r in g)[:2])
                                     for g in dupg if len({str(r.get("model")) for r in g}) > 1][:15]
    out["traj_dup_defence_differs"] = [(sorted({str(r.get("defence")) for r in g}), g[0].get("n_messages"), sorted(r["ex"] for r in g)[:2])
                                       for g in dupg if len({str(r.get("defence")) for r in g}) > 1][:8]
    # judgement differs within identical trajectories (same messages, different outcome)
    jdiff = 0
    jdiff_ex = []
    for g in dupg:
        vals = {(str(judg(r, 'utility') and judg(r, 'utility')['value']), str(judg(r, 'security') and judg(r, 'security')['value'])) for r in g}
        if len(vals) > 1:
            jdiff += 1
            if len(jdiff_ex) < 3:
                jdiff_ex.append(sorted(r["ex"] for r in g)[:2])
    out["traj_dup_outcome_differs"] = jdiff
    out["traj_dup_outcome_differs_examples"] = jdiff_ex
    # identity
    out["identity_conflict_by_model"] = dict(Counter(str(r.get("model")) for r in rows if "identity_conflict" in r["seal_issues"]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="indir", required=True, type=Path)
    args = ap.parse_args()
    summary = {}
    for c in CORPORA:
        p = args.indir / f"{c}.jsonl"
        if not p.exists():
            continue
        rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line]
        summary[c] = analyse(rows)
    (args.indir / "summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps({c: {"n": s["n"], "integrity": s["integrity_errors"]} for c, s in summary.items()}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
