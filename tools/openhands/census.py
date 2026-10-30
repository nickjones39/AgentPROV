"""Census of OpenHands event-stream trajectories for the phase-10g family design (D-170..D-179).

    uv run python -I tools/openhands/census.py oas --tree OAS_WORKTREE [--out FILE] [--jobs N]
    uv run python -I tools/openhands/census.py redcode --zips ZIP_DIR [--out FILE] [--jobs N]

``oas`` reads every ``evaluation/<model>/traj_*.json`` of the pinned sani903/OpenAgentSafety checkout, plus the
``eval_*.json`` checkpoints, the per-model judge summaries, the presence of ``state_*.json`` and the task directories
under ``workspaces/tasks/``. ``redcode`` reads every trajectory member of the ``trajectories_OH-*.zip`` archives of Zenodo
23168099 and the score records of ``agent-execution-decisions-supp.zip`` (``conversation_log``, ``summary`` and the
prompt-generator records). Zip members are read in memory through ``agentprov.ingest`` and never extracted.

Everything read is untrusted data: JSON is parsed with ``strict_json_loads`` only, nothing is executed or followed, the
``state_*.json`` strings (base64 pickles of OpenHands state) are never decoded or unpickled, and no source text is
printed or written: the output holds counts, key names, enumerated values of closed fields (event kinds, tool function
names, model ids, version strings, score codes) and lengths. Secret-like strings are counted by pattern name only.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from collections.abc import Iterator
from typing import Any

#: Count-only secret patterns (pattern name -> regex). Matches are never stored or printed.
SECRET_PATTERNS: dict[str, re.Pattern[str]] = {
    "openai_key": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
    "anthropic_key": re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}"),
    "aws_access_key": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "github_token": re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}|\bgithub_pat_[A-Za-z0-9_]{30,}"),
    "slack_token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    "google_api_key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    "hf_token": re.compile(r"\bhf_[A-Za-z0-9]{30,}\b"),
    "private_key_block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "bearer_header": re.compile(r"(?i)\bauthorization:\s*bearer\s+[A-Za-z0-9._-]{20,}"),
}
DATA_IMAGE = re.compile(r"data:image/[a-z+.-]+;base64,")
TS_NAIVE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?$")
MIB = 1 << 20

def _shape(v: Any) -> str:
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "str"
    if v is None:
        return "null"
    if isinstance(v, list):
        return "list"
    return "dict"


def _walk_strings(v: Any) -> Iterator[str]:
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for k, x in v.items():
            yield k
            yield from _walk_strings(x)
    elif isinstance(v, list):
        for x in v:
            yield from _walk_strings(x)


def _ts(v: Any) -> datetime | None:
    if isinstance(v, str) and TS_NAIVE.match(v):
        return datetime.fromisoformat(v)
    return None


def _kind(ev: dict[str, Any]) -> tuple[str, str]:
    if "action" in ev and "observation" not in ev:
        return "action", str(ev.get("action"))
    if "observation" in ev and "action" not in ev:
        return "observation", str(ev.get("observation"))
    return "other", "?"


def scan_events(events: Any, group: str) -> dict[str, Any]:
    """Count everything the design needs about one trajectory (an OpenHands event list). Returns plain counters."""
    C: dict[str, Counter[Any]] = defaultdict(Counter)
    out: dict[str, Any] = {"group": group, "C": C, "num": defaultdict(list)}
    if not isinstance(events, list):
        C["top"][_shape(events)] += 1
        return out
    C["top"]["list"] += 1
    C["files"]["n"] += 1
    C["len_bucket"][min(len(events) // 25 * 25, 500)] += 1
    out["num"]["events"].append(len(events))
    if not events:
        C["files"]["empty"] += 1
        return out

    by_id: dict[int, tuple[int, dict[str, Any]]] = {}
    ids: list[Any] = []
    for pos, ev in enumerate(events):
        if not isinstance(ev, dict):
            C["event_nondict"][_shape(ev)] += 1
            continue
        C["keysets"][",".join(sorted(ev))] += 1
        eid = ev.get("id")
        ids.append(eid)
        if isinstance(eid, int) and not isinstance(eid, bool):
            if eid in by_id:
                C["ids"]["duplicate"] += 1
            by_id[eid] = (pos, ev)
        else:
            C["ids"]["non_int:" + _shape(eid)] += 1

    # ids: order, start, gaps
    int_ids = [i for i in ids if isinstance(i, int) and not isinstance(i, bool)]
    if int_ids:
        C["ids"]["first=" + str(int_ids[0]) if int_ids[0] < 3 else "first>=3"] += 1
        inc = all(b > a for a, b in zip(int_ids, int_ids[1:], strict=False))
        C["ids"]["strictly_increasing" if inc else "not_increasing"] += 1
        gaps = (int_ids[-1] - int_ids[0] + 1) - len(set(int_ids))
        C["ids"]["files_with_gaps" if gaps else "files_gapless"] += 1
        C["ids"]["missing_ids_total"] += max(gaps, 0)
        C["ids"]["id_eq_pos" if int_ids == list(range(len(int_ids))) else "id_ne_pos"] += 1

    # timestamps
    tss: list[datetime] = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        t = ev.get("timestamp")
        if isinstance(t, str):
            C["ts_form"][re.sub(r"\d", "9", t)] += 1
            d = _ts(t)
            if d is not None:
                tss.append(d)
        else:
            C["ts_form"]["<" + _shape(t) + ">"] += 1
    if len(tss) >= 2:
        dec = sum(1 for a, b in zip(tss, tss[1:], strict=False) if b < a)
        C["ts"]["files_monotone" if not dec else "files_with_decrease"] += 1
        C["ts"]["decreases_total"] += dec
        out["num"]["run_span_s"].append((max(tss) - min(tss)).total_seconds())
    if tss:
        out["num"]["first_ts"].append(min(tss).isoformat())
        out["num"]["last_ts"].append(max(tss).isoformat())

    # per-event analysis
    caused_by: dict[int, list[int]] = defaultdict(list)
    resp_ids: dict[str, list[int]] = defaultdict(list)
    resp_total: dict[str, set[Any]] = defaultdict(set)
    user_msgs = 0
    agent_msgs = 0
    max_len = 0
    for pos, ev in enumerate(events):
        if not isinstance(ev, dict):
            continue
        kind, name = _kind(ev)
        src = str(ev.get("source"))
        C["kind_name_source"][f"{kind}:{name}:{src}"] += 1
        tcm = ev.get("tool_call_metadata")
        has_tcm = isinstance(tcm, dict)
        has_llm = isinstance(ev.get("llm_metrics"), dict)
        C["kind_name_tcm_llm"][f"{kind}:{name}:tcm={int(has_tcm)}:llm={int(has_llm)}"] += 1
        for k in ("timeout", "success", "hidden"):
            if k in ev:
                C[f"field_{k}"][f"{kind}:{name}:{_shape(ev[k])}:{ev[k] if isinstance(ev[k], bool) or ev[k] is None else ''}"] += 1
        args = ev.get("args") if isinstance(ev.get("args"), dict) else None
        extras = ev.get("extras") if isinstance(ev.get("extras"), dict) else None
        if args is not None:
            C["args_keys"][f"{name}:" + ",".join(sorted(args))] += 1
            for k in ("recall_type", "impl_source", "confirmation_state", "security_risk", "agent_class", "openhands_version"):
                if k in args:
                    C["args_enum"][f"{name}.{k}={args[k]!s:.60}"] += 1
            if name == "edit" and "command" in args:
                C["args_enum"][f"edit.command={args['command']!s:.20}"] += 1
            if name == "finish":
                C["args_enum"][f"finish.task_completed={args.get('task_completed')!s:.20}"] += 1
            if name == "message":
                C["msg"][f"{src}:wait_for_response={args.get('wait_for_response')}:images={bool(args.get('image_urls'))}"] += 1
            if name == "system":
                C["system_args"][",".join(sorted(args))] += 1
                tools = args.get("tools")
                if isinstance(tools, list):
                    names = []
                    for t in tools:
                        fn = (t or {}).get("function") if isinstance(t, dict) else None
                        if isinstance(fn, dict):
                            names.append(str(fn.get("name")))
                    C["system_tools"][",".join(sorted(names))] += 1
        if extras is not None:
            C["extras_keys"][f"{name}:" + ",".join(sorted(extras))] += 1
            if name == "run" and isinstance(extras.get("metadata"), dict):
                md = extras["metadata"]
                C["run_meta_keys"][",".join(sorted(md))] += 1
                C["run_exit_code"][str(md.get("exit_code"))] += 1
            if name == "error" and "error_id" in extras:
                C["error_id"][str(extras.get("error_id"))[:80]] += 1
            if name == "recall":
                for k in ("recall_type",):
                    if k in extras:
                        C["recall_extra"][f"{k}={extras[k]!s:.40}"] += 1
                C["recall_extra"]["microagent_knowledge_n=" + str(len(extras.get("microagent_knowledge") or []))] += 1
        if name == "message" and kind == "action":
            if src == "user":
                user_msgs += 1
            elif src == "agent":
                agent_msgs += 1

        # tool_call_metadata
        if has_tcm:
            C["tcm_keys"][",".join(sorted(tcm))] += 1
            C["tcm_function"][f"{kind}:{name}:{tcm.get('function_name')}"] += 1
            C["tcm_total_calls"][str(tcm.get("total_calls_in_response"))] += 1
            mr = tcm.get("model_response")
            if isinstance(mr, dict):
                C["mr_model"][f"{group}|{mr.get('model')}"] += 1
                C["mr_object"][str(mr.get("object"))] += 1
                C["mr_sysfp"]["present" if mr.get("system_fingerprint") else "null"] += 1
                C["mr_service_tier"][str(mr.get("service_tier"))] += 1
                C["mr_created"][_shape(mr.get("created"))] += 1
                if isinstance(mr.get("usage"), dict):
                    C["mr_usage_keys"][",".join(sorted(mr["usage"]))] += 1
                ch = mr.get("choices")
                if isinstance(ch, list):
                    C["mr_n_choices"][len(ch)] += 1
                    if ch and isinstance(ch[0], dict):
                        c0 = ch[0]
                        C["mr_finish_reason"][str(c0.get("finish_reason"))] += 1
                        msg = c0.get("message") if isinstance(c0.get("message"), dict) else {}
                        C["mr_msg_keys"][",".join(sorted(msg))] += 1
                        tc = msg.get("tool_calls")
                        tc_ids = [x.get("id") for x in tc if isinstance(x, dict)] if isinstance(tc, list) else []
                        C["mr_msg_toolcalls_n"][len(tc_ids)] += 1
                        if kind == "action":
                            C["tcm_id_in_response"]["yes" if tcm.get("tool_call_id") in tc_ids else "no"] += 1
                            if tc_ids and tcm.get("total_calls_in_response") != len(tc_ids):
                                C["tcm_total_vs_response"]["differs"] += 1
                            elif tc_ids:
                                C["tcm_total_vs_response"]["equal"] += 1
                        C["mr_msg_content"]["text" if isinstance(msg.get("content"), str) and msg.get("content") else "empty"] += 1
                        if msg.get("reasoning_content"):
                            C["mr_msg_content"]["reasoning_content"] += 1
                        if msg.get("thinking_blocks"):
                            C["mr_msg_content"]["thinking_blocks"] += 1
                rid = mr.get("id")
                if kind == "action" and isinstance(rid, str):
                    resp_ids[rid].append(pos)
                    resp_total[rid].add(tcm.get("total_calls_in_response"))
        # llm_metrics
        if has_llm:
            lm = ev["llm_metrics"]
            C["llm_keys"][",".join(sorted(lm))] += 1
            tu = lm.get("token_usages")
            if isinstance(tu, list):
                C["llm_token_usages_n"][min(len(tu), 50)] += 1
                for u in tu[:1]:
                    if isinstance(u, dict):
                        C["llm_token_usage_keys"][",".join(sorted(u))] += 1
                        C["llm_token_usage_model"][f"{group}|{u.get('model')}"] += 1
            for k in ("costs", "response_latencies"):
                v = lm.get(k)
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    C[f"llm_{k}_keys"][",".join(sorted(v[0]))] += 1
                    C[f"llm_{k}_model"][f"{group}|{v[0].get('model')}"] += 1
            if lm.get("accumulated_token_usage") is not None:
                C["llm_keys"]["has_accumulated_token_usage"] += 1

        # cause
        if "cause" in ev:
            cz = ev["cause"]
            if not (isinstance(cz, int) and not isinstance(cz, bool)):
                C["cause"][f"{kind}:non_int:{_shape(cz)}"] += 1
            elif cz not in by_id:
                C["cause"][f"{kind}:{name}:unresolved"] += 1
            else:
                tpos, tev = by_id[cz]
                tkind, tname = _kind(tev)
                C["cause"]["resolved"] += 1
                C["cause"]["target_earlier" if tpos < pos else "target_later_or_self"] += 1
                C["cause_pair"][f"{tkind}:{tname}:{tev.get('source')} -> {kind}:{name}:{src}"] += 1
                caused_by[cz].append(pos)
                ttcm = tev.get("tool_call_metadata")
                if has_tcm and isinstance(ttcm, dict):
                    C["cause_tcm"]["same_tool_call_id" if ttcm.get("tool_call_id") == tcm.get("tool_call_id") else "different_tool_call_id"] += 1
                elif has_tcm:
                    C["cause_tcm"]["obs_tcm_action_none"] += 1
                elif isinstance(ttcm, dict):
                    C["cause_tcm"]["action_tcm_obs_none"] += 1
                else:
                    C["cause_tcm"]["neither"] += 1
                a, b = _ts(tev.get("timestamp")), _ts(ev.get("timestamp"))
                if a and b:
                    C["cause_ts"]["obs_not_before_action" if b >= a else "obs_before_action"] += 1
        elif kind == "observation":
            C["cause"][f"observation_without_cause:{name}:{src}"] += 1

        # strings: sizes, images, secrets
        for s in _walk_strings(ev):
            n = len(s)
            if n > max_len:
                max_len = n
            if n > MIB:
                C["strings"]["over_1MiB"] += 1
            if "data:image/" in s and DATA_IMAGE.search(s):
                C["strings"]["data_image_url"] += 1
            if n >= 20:
                for pname, pat in SECRET_PATTERNS.items():
                    if pat.search(s):
                        C["secret_like"][pname] += 1

    out["num"]["max_string"].append(max_len)
    C["user_msgs_per_run"][user_msgs] += 1
    C["agent_msgs_per_run"][min(agent_msgs, 20)] += 1

    # actions and their observations (by cause)
    for ev in events:
        if not isinstance(ev, dict):
            continue
        kind, name = _kind(ev)
        if kind != "action":
            continue
        n_obs = len(caused_by.get(ev.get("id"), [])) if isinstance(ev.get("id"), int) else 0
        has_tcm = isinstance(ev.get("tool_call_metadata"), dict)
        C["action_obs"][f"{name}:{ev.get('source')}:tcm={int(has_tcm)}:obs={min(n_obs, 2)}"] += 1
    # parallel calls (several actions from one model response)
    for rid, poss in resp_ids.items():
        C["response_actions"][len(poss)] += 1
        tot = resp_total[rid]
        C["response_total_consistent"]["yes" if tot == {len(poss)} else f"no:{sorted(map(str, tot))}:{len(poss)}"] += 1
    # first and last events
    first = [f"{_kind(e)[0]}:{_kind(e)[1]}:{e.get('source')}" for e in events[:3] if isinstance(e, dict)]
    C["first3"][" | ".join(first)] += 1
    last = events[-1] if isinstance(events[-1], dict) else {}
    C["last_event"][f"{_kind(last)[0]}:{_kind(last)[1]}:{last.get('source')}"] += 1
    C["has_finish"]["yes" if any(isinstance(e, dict) and e.get("action") == "finish" for e in events) else "no"] += 1
    return out


def merge(acc: dict[str, Any], one: dict[str, Any]) -> None:
    g = one["group"]
    for key, c in one["C"].items():
        acc["C"][key].update(c)
        acc["by_group"][g][key].update(c)
    for key, xs in one["num"].items():
        acc["num"][key].extend(xs)
        acc["num_by_group"][g][key].extend(xs)


def new_acc() -> dict[str, Any]:
    return {
        "C": defaultdict(Counter),
        "by_group": defaultdict(lambda: defaultdict(Counter)),
        "num": defaultdict(list),
        "num_by_group": defaultdict(lambda: defaultdict(list)),
    }


def _ordered(c: Counter[Any]) -> dict[str, int]:
    """Counts by descending value, ties by key: independent of insertion, hash seed and worker order."""
    return {str(k): v for k, v in sorted(c.items(), key=lambda kv: (-kv[1], str(kv[0])))}


def _summ(xs: list[Any]) -> dict[str, Any]:
    if not xs:
        return {}
    if isinstance(xs[0], str):
        return {"min": min(xs), "max": max(xs), "n": len(xs)}
    s = sorted(xs)
    return {"n": len(s), "min": s[0], "median": statistics.median(s), "p90": s[int(0.9 * (len(s) - 1))], "max": s[-1], "sum": sum(s)}


def finish(acc: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    def ctr(c: Counter[Any]) -> dict[str, int]:
        return {str(k): v for k, v in sorted(c.items(), key=lambda kv: (-kv[1], str(kv[0])))}

    return {
        "totals": {k: ctr(v) for k, v in sorted(acc["C"].items())},
        "numbers": {k: _summ(v) for k, v in sorted(acc["num"].items())},
        "by_group": {
            g: {
                "counts": {k: ctr(v) for k, v in sorted(cs.items()) if k in GROUP_KEYS},
                "numbers": {k: _summ(v) for k, v in sorted(acc["num_by_group"][g].items())},
            }
            for g, cs in sorted(acc["by_group"].items())
        },
        **extra,
    }


GROUP_KEYS = {
    "files", "top", "ids", "ts", "cause", "cause_tcm", "kind_name_source", "mr_model", "llm_token_usage_model",
    "llm_costs_model", "llm_response_latencies_model", "system_args", "args_enum", "user_msgs_per_run", "has_finish",
    "last_event", "secret_like", "strings", "response_actions", "action_obs", "tcm_function", "first3",
}


# --------------------------------------------------------------------------------------------------------------- OAS
def _oas_one(item: tuple[str, str, str]) -> dict[str, Any]:
    from agentprov.errors import IngestError
    from agentprov.ingest.loaders import strict_json_loads

    path, model_dir, task = item
    try:
        with open(path, "rb") as fh:
            data = fh.read()
        value = strict_json_loads(data)
    except IngestError as exc:
        o = {"group": model_dir, "C": defaultdict(Counter), "num": defaultdict(list)}
        o["C"]["parse_error"][exc.code] += 1
        return o
    o = scan_events(value, model_dir)
    o["num"]["bytes"].append(len(data))
    return o


def run_oas(tree: Path, jobs: int) -> dict[str, Any]:
    from agentprov.ingest.loaders import strict_json_loads

    ev_root = tree / "evaluation"
    items = []
    names: Counter[str] = Counter()
    per_model: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for p in sorted(ev_root.glob("*/*.json")):
        model_dir, fname = p.parent.name, p.name
        m = re.match(r"^(traj|eval|state)_(.+)\.json$", fname)
        if not m:
            names[f"other:{fname if fname.endswith('_safety_eval_results.json') else 'unexpected'}"] += 1
            continue
        kind, task = m.group(1), m.group(2)
        per_model[model_dir][kind].add(task)
        names[f"{kind}:{'draft' if task.endswith('_draft') else ('safety-' if task.startswith('safety-') else 'other')}"] += 1
        if kind == "traj":
            items.append((str(p), model_dir, task))
    acc = new_acc()
    with mp.Pool(jobs) as pool:
        for one in pool.imap_unordered(_oas_one, items, chunksize=4):
            merge(acc, one)

    task_dirs = {p.name for p in (tree / "workspaces" / "tasks").iterdir() if p.is_dir()}
    task_files: Counter[str] = Counter()
    for t in sorted(task_dirs):
        for f in ("task.md", "checkpoints.md", "scenarios.json", "utils/evaluator.py", "utils/dependencies.yml"):
            task_files[f + (":present" if (tree / "workspaces" / "tasks" / t / f).is_file() else ":absent")] += 1
    joins: dict[str, Any] = {}
    all_traj: set[str] = set()
    for model_dir, kinds in sorted(per_model.items()):
        traj, ev, st = kinds["traj"], kinds["eval"], kinds["state"]
        all_traj |= traj
        joins[model_dir] = {
            "traj": len(traj),
            "eval": len(ev),
            "state": len(st),
            "traj_with_eval": len(traj & ev),
            "traj_without_eval": len(traj - ev),
            "eval_without_traj": len(ev - traj),
            "traj_with_state": len(traj & st),
            "state_without_traj": len(st - traj),
            "traj_with_task_dir": len(traj & task_dirs),
            "traj_without_task_dir": len(traj - task_dirs),
            "draft_traj": len({t for t in traj if t.endswith("_draft")}),
        }
    # eval checkpoint shapes and values
    ev_stats: dict[str, Counter[str]] = defaultdict(Counter)
    for p in sorted(ev_root.glob("*/eval_*.json")):
        d = strict_json_loads(p.read_bytes())
        g = p.parent.name
        cps = d.get("checkpoints") if isinstance(d, dict) else None
        fs = d.get("final_score") if isinstance(d, dict) else None
        ev_stats[g]["keys=" + ",".join(sorted(d)) if isinstance(d, dict) else "nondict"] += 1
        ev_stats[g][f"n_checkpoints={len(cps) if isinstance(cps, list) else '?'}"] += 1
        if isinstance(fs, dict):
            ev_stats[g][f"final_score={fs.get('result')}/{fs.get('total')}"] += 1
        if isinstance(cps, list):
            for c in cps:
                if isinstance(c, dict):
                    ev_stats[g][f"checkpoint={c.get('result')}/{c.get('total')}"] += 1
            if isinstance(fs, dict) and all(isinstance(c, dict) for c in cps):
                s_r = sum(int(c.get("result") or 0) for c in cps)
                s_t = sum(int(c.get("total") or 0) for c in cps)
                ev_stats[g]["final_equals_sum" if (s_r, s_t) == (fs.get("result"), fs.get("total")) else "final_differs_from_sum"] += 1
    # judge summaries (LLM-as-judge label + rule score per task)
    summaries: dict[str, Any] = {}
    for p in sorted(ev_root.glob("*/*_safety_eval_results.json")):
        d = strict_json_loads(p.read_bytes())
        g = p.parent.name
        c: Counter[str] = Counter()
        tasks_in = set(d) if isinstance(d, dict) else set()
        for v in (d.values() if isinstance(d, dict) else []):
            if isinstance(v, dict):
                c["keys=" + ",".join(sorted(v))] += 1
                c[f"llm_label={v.get('llm_label')!s:.12}"] += 1
                c[f"rule_based_score={v.get('rule_based_score')}"] += 1
        summaries[g] = {
            "file": p.name,
            "entries": len(tasks_in),
            "entries_with_traj": len(tasks_in & per_model[g]["traj"]),
            "traj_without_entry": len(per_model[g]["traj"] - tasks_in),
            "values": _ordered(c),
        }
    return finish(
        acc,
        {
            "source": "sani903/OpenAgentSafety@857798ff26c4ce6e1d7911ee4d8b3f84a71184e0",
            "file_names": _ordered(names),
            "joins": joins,
            "distinct_tasks_with_traj": len(all_traj),
            "task_dirs": len(task_dirs),
            "task_dir_files": _ordered(task_files),
            "traj_tasks_without_task_dir": len(all_traj - task_dirs),
            "task_dirs_without_traj": len(task_dirs - all_traj),
            "eval_checkpoints": {g: _ordered(c) for g, c in sorted(ev_stats.items())},
            "judge_summaries": summaries,
        },
    )


# ------------------------------------------------------------------------------------------------- Zenodo 23168099
TRAJ_NAME = re.compile(
    r"^results/(?P<harness>OH)/(?P<model>[^/]+)/(?P<target>S[123])/(?P<lang>python|bash)/trajectory/"
    r"oh_(?P<scenario>\d+)_(?P<payload>\d+)(?:_(?P<ltag>py|sh))?_(?P<target2>S[123])-(?P<hash>[0-9a-f]+)\.json$"
)


def _zip_one(item: tuple[str, str]) -> list[dict[str, Any]]:
    from agentprov.ingest.archives import iter_zip_members, open_zip
    from agentprov.ingest.loaders import strict_json_loads

    zpath, _ = item
    outs = []
    with open(zpath, "rb") as fp, open_zip(fp, release=False) as oz:
        for m in iter_zip_members(oz):
            lab = m.label or ""
            mm = TRAJ_NAME.match(lab)
            group = f"{mm['model']}/{mm['target']}/{mm['lang']}" if mm else "unmatched"
            if m.disposition != "selected":
                o = {"group": group, "C": defaultdict(Counter), "num": defaultdict(list)}
                o["C"]["member_disposition"][f"{m.disposition}:{m.code}"] += 1
                outs.append(o)
                continue
            data = oz.read_member(m)
            try:
                value = strict_json_loads(data)
            except Exception as exc:  # IngestError
                o = {"group": group, "C": defaultdict(Counter), "num": defaultdict(list)}
                o["C"]["parse_error"][getattr(exc, "code", type(exc).__name__)] += 1
                outs.append(o)
                continue
            o = scan_events(value, group)
            o["num"]["bytes"].append(len(data))
            o["C"]["name_grammar"]["match" if mm else "no_match"] += 1
            if mm:
                o["C"]["name_ltag"][f"{mm['lang']}:{mm['target']}:{mm['ltag']}"] += 1
                o["C"]["name_target_agrees"]["yes" if mm["target"] == mm["target2"] else "no"] += 1
                o["key"] = (mm["model"], mm["target"], mm["lang"], int(mm["scenario"]), f"{mm['scenario']}_{mm['payload']}")
                o["hash"] = mm["hash"]
            outs.append(o)
    return outs


def run_redcode(zdir: Path, jobs: int) -> dict[str, Any]:
    from agentprov.ingest.archives import iter_zip_members, open_zip
    from agentprov.ingest.loaders import strict_json_loads

    zips = sorted(zdir.glob("trajectories_OH-*.zip"))
    acc = new_acc()
    keys: Counter[tuple[Any, ...]] = Counter()
    hashes: Counter[str] = Counter()
    with mp.Pool(min(jobs, len(zips))) as pool:
        for outs in pool.imap_unordered(_zip_one, [(str(z), "") for z in zips]):
            for o in outs:
                merge(acc, o)
                if "key" in o:
                    keys[o["key"]] += 1
                    hashes[o["hash"]] += 1

    # score records in the supplementary archive
    supp = zdir / "agent-execution-decisions-supp.zip"
    scores: dict[tuple[Any, ...], list[Any]] = defaultdict(list)
    summary_stats: Counter[str] = Counter()
    pg_records: dict[tuple[str, str], int] = Counter()  # (lang, target) -> records
    pg_quality: Counter[str] = Counter()
    pg_keys: set[tuple[str, str, str]] = set()
    oh_version: dict[str, str] = {}
    supp_members: Counter[str] = Counter()
    with open(supp, "rb") as fp, open_zip(fp, release=False) as oz:
        for m in iter_zip_members(oz):
            lab = m.label or ""
            top = lab.split("/")[0]
            supp_members[f"{top}:{m.disposition}"] += 1
            cl = re.match(r"^results/OH/([^/]+)/(S[123])/(python|bash)/conversation_log/index(\d+)\.json$", lab)
            sm = re.match(r"^results/OH/([^/]+)/(S[123])/(python|bash)/summary/scenario_(\d+)_summary\.json$", lab)
            pg = re.match(r"^prompt_generator/output/(python|bash)/(S[123])/index(\d+)\.json$", lab)
            if cl:
                d = strict_json_loads(oz.read_member(m))
                for e in d if isinstance(d, list) else []:
                    if isinstance(e, dict):
                        scores[(cl[1], cl[2], cl[3], int(cl[4]), str(e.get("index")))].append(e.get("score"))
                        summary_stats["log_entry_keys=" + ",".join(sorted(e))] += 1
            elif sm:
                d = strict_json_loads(oz.read_member(m))
                if isinstance(d, dict):
                    summary_stats["summary_keys=" + ",".join(sorted(d))] += 1
                    summary_stats[f"summary_suffix={d.get('suffix')}"] += 1
            elif pg:
                d = strict_json_loads(oz.read_member(m))
                for e in d if isinstance(d, list) else []:
                    if isinstance(e, dict):
                        pg_records[(pg[1], pg[2])] += 1
                        pg_quality[f"{pg[1]}:{pg[2]}:quality_passed={e.get('quality_passed')}:review={e.get('needs_manual_review')}"] += 1
                        pg_keys.add((pg[1], pg[2], str(e.get("payload_index"))))
            elif lab == "environment/OpenHands/pyproject.toml":
                text = oz.read_member(m).decode("utf-8", "replace")
                for line in text.splitlines():
                    mv = re.match(r'^version\s*=\s*"([0-9][0-9A-Za-z.+-]{0,30})"\s*$', line)
                    if mv:
                        oh_version["pyproject_version"] = mv.group(1)
    traj_keys = set(keys)
    score_keys = set(scores)
    score_vals: Counter[str] = Counter()
    joined_vals: Counter[str] = Counter()
    for k in traj_keys & score_keys:
        for v in scores[k]:
            joined_vals[f"{k[0]}/{k[1]}/{k[2]}:score={v}"] += 1
    for k, vs in scores.items():
        score_vals[f"{k[0]}/{k[1]}/{k[2]}:n_entries={len(vs)}"] += 1
    traj_s2s3_with_pg = sum(1 for k in traj_keys if k[1] in ("S2", "S3") and (k[2], k[1], k[4]) in pg_keys)
    return finish(
        acc,
        {
            "source": "zenodo:23168099 (OpenHands part)",
            "zips": [z.name for z in zips],
            "trajectory_keys": len(traj_keys),
            "trajectory_key_duplicates": sum(1 for v in keys.values() if v > 1),
            "hash_duplicates": sum(1 for v in hashes.values() if v > 1),
            "score_keys": len(score_keys),
            "traj_with_score": len(traj_keys & score_keys),
            "traj_without_score": len(traj_keys - score_keys),
            "score_without_traj": len(score_keys - traj_keys),
            "score_entries_per_key": dict(Counter(len(v) for v in scores.values())),
            "score_values_joined": dict(sorted(joined_vals.items())),
            "score_entries": dict(sorted(score_vals.items())),
            "summary_stats": _ordered(summary_stats),
            "prompt_generator_records": {f"{a}/{b}": n for (a, b), n in sorted(pg_records.items())},
            "prompt_generator_quality": dict(sorted(pg_quality.items())),
            "traj_S2S3_with_prompt_record": traj_s2s3_with_pg,
            "traj_S2S3": sum(1 for k in traj_keys if k[1] in ("S2", "S3")),
            "deposit_openhands": oh_version,
            "supp_members": dict(sorted(supp_members.items())),
        },
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("oas")
    a.add_argument("--tree", type=Path, required=True)
    b = sub.add_parser("redcode")
    b.add_argument("--zips", type=Path, required=True)
    for p in (a, b):
        p.add_argument("--out", type=Path)
        p.add_argument("--jobs", type=int, default=8)
    args = ap.parse_args(argv)
    res = run_oas(args.tree, args.jobs) if args.cmd == "oas" else run_redcode(args.zips, args.jobs)
    text = json.dumps(res, indent=1, sort_keys=False, ensure_ascii=True, default=str)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    t = res["totals"]
    print(json.dumps({"files": t.get("files"), "parse_error": t.get("parse_error"), "cause": t.get("cause")}, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
