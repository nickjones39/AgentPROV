"""Per-execution feature extraction over a sealed AgentPROV corpus (read-only; phase-10 corpus analysis).

For every row of ``executions.jsonl`` this tool

* re-checks the integrity chain: the index paths resolve; every raw object re-hashes to its name; the AER parses strictly
  (JCS lines) and its seal digest equals ``digests.aer``; the SEM file parses, its seal equals ``digests.sem`` and its
  ``aer_digest`` equals the AER digest; the PROV-JSON bytes hash to ``digests.prov`` and parse with the strict ingest
  loader; the validation row's JCS digest equals ``digests.validation``;
* extracts AER facts (task facets, record counts, issues, accounting, unknowns, evidence classes, provider call ids,
  call/result linkage, judgements, a trajectory digest for duplicate detection, text-shape counters); the model-output
  screens read role ``assistant`` and DTap's verbatim ``agent`` (``message_roles.py``), while ``roles`` and
  ``final_role`` stay verbatim;
* extracts SEM facts (annotation types/values, unknown-tool roles, injection-marker statuses);
* extracts PROV graph facts (bundles, statements by section/rule/evidence class, connectivity of the core+inference
  union graph, AER-to-PROV cross-checks, statements that must never appear);
* runs the shared artefact safety net (``agentprov.artefacts.scan``) with the shipped catalogues, passing the
  execution's verified SEM records so that ``payload_not_reaching_agent`` runs.

Output: one JSON line per execution on ``--out`` (no source text, only ids, counts and short safe tokens). Source text
is never printed. Corpus content is untrusted data; every file is parsed with the project's strict readers.

Usage: ``python tools/analysis/phase10_extract.py --corpus ~/.agentprov/corpora/<id> --out OUT.jsonl [--jobs 4]
[--limit N]``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from multiprocessing import Pool
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from message_roles import is_assistant  # noqa: E402  (assistant + DTap agent: one shared grouping)

from agentprov.aer.reader import load_aer
from agentprov.artefacts import discover_catalogues, scan
from agentprov.ingest.loaders import strict_json_loads
from agentprov.ingest.limits import IngestLimits
from agentprov.io.canonical import jcs_bytes
from agentprov.sem.reader import load_sem

SPEC = "agentprov-prov/0.1"
_DIGITS = re.compile(r"\d+")
_SAFE_TOKEN = re.compile(r"[A-Za-z0-9_.:\-/@]{1,80}")
_CATALOGUES: Any = None
_ROOT: Path | None = None
_LIMITS = IngestLimits()

#: assistant-text markers of model-output formatting (counted, never quoted)
_FORMAT_MARKERS = {
    "think_open": "<think>",
    "think_close": "</think>",
    "function_tag": "<function=",
    "tool_call_tag": "<tool_call>",
    "harmony_channel": "<|channel|>",
    "special_token": "<|",
    "json_fence": "```json",
    "action_prefix": "Action:",
}
_MOJIBAKE = ("Ã©", "â€", "Ã¨", "Â ")


def _norm_ptr(ptr: str) -> str:
    return _DIGITS.sub("N", ptr)


def _safe(value: Any) -> str | None:
    if isinstance(value, str) and _SAFE_TOKEN.fullmatch(value):
        return value
    if value is None:
        return None
    return "<unsafe>"


def _char_classes(text: str) -> Counter[str]:
    """Counts of characters a display or an ASCII-safe field should not hold (never the characters themselves)."""
    out: Counter[str] = Counter()
    for ch in text:
        o = ord(ch)
        if o < 0x20 and ch not in "\n\t\r":
            out["c0_control"] += 1
        elif 0x7F <= o < 0xA0:
            out["c1_control"] += 1
        elif ch == "�":
            out["replacement_char"] += 1
        elif unicodedata.bidirectional(ch) in ("RLE", "LRE", "RLO", "LRO", "PDF", "RLI", "LRI", "FSI", "PDI"):
            out["bidi_control"] += 1
        elif o in (0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF):
            out["zero_width"] += 1
        elif 0xE0000 <= o <= 0xE007F:
            out["tag_char"] += 1
        elif 0xD800 <= o <= 0xDFFF:
            out["surrogate"] += 1
    return out


def _non_ascii(text: str) -> bool:
    return any(ord(c) > 0x7E or ord(c) < 0x20 for c in text)


def _texts(parts: Any) -> list[str]:
    out = []
    for p in parts if isinstance(parts, list) else ():
        if isinstance(p, dict) and isinstance(p.get("text"), str):
            out.append(p["text"])
    return out


def _init(root: str) -> None:
    global _CATALOGUES, _ROOT
    _CATALOGUES = tuple(discover_catalogues())
    _ROOT = Path(root)


# --------------------------------------------------------------------------------------------------------------- AER
def aer_facts(doc: Any, f: dict[str, Any]) -> dict[str, Any]:
    h = doc.header
    task = h.get("task") or {}
    ext = h.get("ext") or {}
    adx = ext.get("agentdojo") or {}
    f["profile"] = f"{h['profile']['id']}@{h['profile']['version']}"
    f["variant"] = (h.get("dialect") or {}).get("variant")
    f["unit"] = h.get("unit")
    f["benchmark"] = _safe(task.get("benchmark"))
    f["suite"] = _safe(task.get("suite"))
    f["task_id"] = _safe(task.get("task_id"))
    f["attack"] = _safe(task.get("attack_id"))
    f["target"] = _safe(task.get("attack_target_id"))
    f["defence"] = _safe(task.get("defense_id")) if "defense_id" in task else "<unk>"
    f["task_kind"] = adx.get("task_kind")
    f["run_error"] = adx.get("error") is not None
    f["run_error_head"] = None
    if isinstance(adx.get("error"), str):  # first token of the error class only (e.g. "JSONDecodeError"), never text
        tok = re.match(r"[A-Za-z_][A-Za-z0-9_.]{0,60}", adx["error"])
        f["run_error_head"] = tok.group(0) if tok else "<other>"
    f["pipeline_name_safe"] = _safe(adx.get("pipeline_name"))
    f["pipeline_name_digest"] = hashlib.sha256(str(adx.get("pipeline_name")).encode()).hexdigest()[:12]
    f["committed_no_later_than"] = adx.get("committed_no_later_than")
    f["benchmark_era"] = (adx.get("benchmark_era") or {}).get("candidate") if isinstance(adx.get("benchmark_era"), dict) else None
    f["header_ext_keys"] = sorted(f"{ns}.{k}" for ns, v in ext.items() if isinstance(v, dict) for k in v)
    f["rope_arm"] = json.dumps(ext.get("rope", {}).get("arm"), sort_keys=True) if "rope" in ext else None
    f["autodojo_cells"] = len(ext.get("autodojo", {}).get("cache_cells", ())) if "autodojo" in ext else None
    f["header_unk"] = sorted(f"{k}={v}" for k, v in (h.get("unk") or {}).items())
    f["origin_path"] = (h.get("artifacts") or [{}])[0].get("origin", {}).get("path")
    f["origin_intro_commit"] = (h.get("artifacts") or [{}])[0].get("origin", {}).get("introduced_in_commit")
    f["n_artifacts"] = len(h.get("artifacts") or [])
    # ASCII-safety of fields that are identifiers
    bad_ident: Counter[str] = Counter()
    for key in ("suite", "task_id", "attack_id", "attack_target_id", "defense_id", "benchmark"):
        v = task.get(key)
        if isinstance(v, str) and (_non_ascii(v) or not _SAFE_TOKEN.fullmatch(v)):
            bad_ident[f"task.{key}"] += 1
    kinds: Counter[str] = Counter()
    ev: Counter[str] = Counter()
    evf: Counter[str] = Counter()
    unk: Counter[str] = Counter()
    roles: Counter[str] = Counter()
    actors_msg: Counter[str] = Counter()
    te_status: Counter[str] = Counter()
    dc: Counter[str] = Counter()
    mc_roles: Counter[str] = Counter()
    id_forms: Counter[str] = Counter()
    link_ev: Counter[str] = Counter()
    rules_used: Counter[str] = Counter()
    textchars: Counter[str] = Counter()
    fmt: Counter[str] = Counter()
    judg: list[dict[str, Any]] = []
    tool_names: set[str] = set()
    actor_info: dict[str, Any] = {}
    fixtures: list[str] = []
    traj = hashlib.sha256()
    msgs: list[dict[str, Any]] = []
    provider_ids: list[str] = []
    n_tool_call_parts = 0
    n_empty_text_assistant = 0
    n_null_text_nocall_assistant = 0
    n_reasoning_parts = 0
    n_other_parts = 0
    n_multi_value_results = 0
    sys_prompt_variant = None
    after_issues = 0
    for r in doc.records:
        k = r.get("k")
        kinds[k] += 1
        ev[f"{k}:{r.get('ev')}"] += 1
        for p, c in (r.get("evf") or {}).items():
            evf[f"{k}:{_norm_ptr(p)}:{c}"] += 1
        for p, reason in (r.get("unk") or {}).items():
            unk[f"{k}:{_norm_ptr(p)}:{reason}"] += 1
        for ref in r.get("rule") or ():
            rules_used[str(ref).split("#", 1)[0]] += 1
        if k == "actor":
            info = {"kind": r.get("kind"), "name": _safe(r.get("name"))}
            if isinstance(r.get("model"), dict):
                info["model"] = _safe(r["model"].get("requested"))
                info["provider"] = _safe(r["model"].get("provider"))
            if r.get("id") == "bench":
                info["version"] = _safe(r.get("version"))
                info["dist_version"] = _safe((r.get("code") or {}).get("dist_version"))
            actor_info[str(r.get("id"))] = info
            for key in ("name",):
                v = r.get(key)
                if isinstance(v, str) and _non_ascii(v):
                    bad_ident[f"actor.{key}"] += 1
        elif k == "scope" and r.get("id") == "run":
            t = r.get("t") or {}
            f["duration"] = t.get("dur_s")
            f["start_naive"] = t.get("start_naive")
            f["start_raw_present"] = "raw" in t
        elif k == "scope" and r.get("id") == "att0":
            f["att0_index"] = r.get("index")
        elif k == "fixture":
            c = r.get("content")
            if isinstance(c, str):
                fixtures.append(c)
            f.setdefault("fixture_vectors", []).append(_safe(r.get("vector")))
            for key in ("autodojo",):
                if key in (r.get("ext") or {}):
                    f.setdefault("fixture_cache_match", []).append(_safe((r["ext"][key] or {}).get("cache_match")))
        elif k == "message":
            role = r.get("role")
            roles[str(role)] += 1
            actors_msg[f"{role}:{r.get('actor')}"] += 1
            parts = r.get("parts") or []
            texts = _texts(parts)
            traj.update(jcs_bytes([role, parts]))
            for t in texts:
                textchars.update(_char_classes(t))
                if any(m in t for m in _MOJIBAKE):
                    textchars["mojibake_seq"] += 1
            if role == "system" and (r.get("ext") or {}).get("agentdojo", {}).get("system_prompt_variant"):
                sys_prompt_variant = r["ext"]["agentdojo"]["system_prompt_variant"]
            calls = [p for p in parts if isinstance(p, dict) and p.get("t") == "tool_call"]
            if is_assistant(role):  # SA07 and the empty-turn counters: role assistant, or DTap's verbatim agent
                for t in texts:
                    for name, marker in _FORMAT_MARKERS.items():
                        if marker in t:
                            fmt[name] += 1
                if any(p.get("t") == "text" and p.get("text") == "" for p in parts if isinstance(p, dict)):
                    n_empty_text_assistant += 1
                if not calls and all(p.get("t") == "text" and p.get("text") is None for p in parts if isinstance(p, dict)):
                    n_null_text_nocall_assistant += 1
                n_reasoning_parts += sum(1 for p in parts if isinstance(p, dict) and p.get("t") == "reasoning")
                fmt["calls_form:" + str((r.get("ext") or {}).get("agentdojo", {}).get("calls_form", "list_or_null"))] += 1
            n_other_parts += sum(1 for p in parts if isinstance(p, dict) and p.get("t") == "other")
            for p in calls:
                n_tool_call_parts += 1
                if isinstance(p.get("name"), str):
                    tool_names.add(p["name"])
                    if _non_ascii(p["name"]):
                        bad_ident["tool_call.name"] += 1
                if "provider_call_id" not in p:
                    id_forms["absent"] += 1
                elif p["provider_call_id"] is None:
                    id_forms["null"] += 1
                elif p["provider_call_id"] == "":
                    id_forms["empty"] += 1
                else:
                    pid = str(p["provider_call_id"])
                    provider_ids.append(pid)
                    # id style as a shape token (letters/digits abstracted), never the id itself
                    id_forms["prefix:" + re.sub(r"[0-9]", "9", re.sub(r"[a-z]", "a", re.sub(r"[A-Z]", "A", pid[:5])))] += 1
            for p in parts:
                if isinstance(p, dict) and p.get("t") == "tool_result":
                    if "value" in p:
                        n_multi_value_results += 1
            if role == "tool":
                link_ev[str((r.get("evf") or {}).get("/parts/0/responds_to", "unk:" + str((r.get("unk") or {}).get("/parts/0/responds_to"))))] += 1
            msgs.append({"id": r.get("id"), "role": role, "actor": r.get("actor"), "texts": texts, "n_calls": len(calls)})
        elif k == "model_call":
            mc_roles[f"{r.get('role')}:{r.get('actor')}"] += 1
            # input is the full prefix of earlier messages by construction; check it
            f.setdefault("_mc_inputs", []).append(len(r.get("input") or []))
        elif k == "tool_execution":
            te_status[str(r.get("status"))] += 1
            if r.get("name") and isinstance(r["name"], str):
                tool_names.add(r["name"])
            if "requested_by" in r:
                te_status["requested_by_defence"] += 1
            if "call" not in r and "requested_by" not in r:
                te_status["no_call_link"] += 1
        elif k == "decision":
            dc[f"{r.get('verdict')}:{(actor_info.get(str(r.get('actor'))) or {}).get('name')}"] += 1
        elif k == "judgement":
            judg.append({"name": r.get("name"), "value": r.get("value"), "origin": r.get("origin"),
                         "revises": r.get("revises") is not None, "actor": r.get("actor"),
                         "corr": _safe(((r.get("ext") or {}).get("rope") or {}).get("correction"))})
        for a in r.get("after") or ():
            if not isinstance(a, dict) or not isinstance(a.get("id"), str):
                after_issues += 1
    f["record_kinds"] = dict(kinds)
    f["ev"] = dict(ev)
    f["evf"] = dict(evf)
    f["unk"] = dict(unk)
    f["roles"] = dict(roles)
    f["msg_actors"] = dict(actors_msg)
    f["te_status"] = dict(te_status)
    f["decisions"] = dict(dc)
    f["mc_roles"] = dict(mc_roles)
    f["id_forms"] = {k: v for k, v in id_forms.items() if v}
    f["link_ev"] = dict(link_ev)
    f["rules_used"] = dict(rules_used)
    f["textchars"] = dict(textchars)
    f["fmt"] = dict(fmt)
    f["bad_ident"] = dict(bad_ident)
    f["judgements"] = judg
    f["actors"] = actor_info
    f["model"] = (actor_info.get("agent") or {}).get("model")
    f["provider"] = (actor_info.get("agent") or {}).get("provider")
    f["bench_version"] = (actor_info.get("bench") or {}).get("version")
    f["dist_version"] = (actor_info.get("bench") or {}).get("dist_version")
    f["n_tool_call_parts"] = n_tool_call_parts
    f["n_empty_text_assistant"] = n_empty_text_assistant
    f["n_null_text_nocall_assistant"] = n_null_text_nocall_assistant
    f["n_reasoning_parts"] = n_reasoning_parts
    f["n_other_parts"] = n_other_parts
    f["n_multi_value_results"] = n_multi_value_results
    f["n_tool_names"] = len(tool_names)
    f["sys_prompt_variant"] = sys_prompt_variant
    f["after_issues"] = after_issues
    f["traj_digest"] = traj.hexdigest()[:24] if msgs else None
    f["n_messages"] = len(msgs)
    f["final_role"] = msgs[-1]["role"] if msgs else None
    f["final_actor"] = msgs[-1]["actor"] if msgs else None
    f["final_assistant_calls"] = msgs[-1]["n_calls"] if msgs and is_assistant(msgs[-1]["role"]) else None
    dup = Counter(provider_ids)
    f["dup_provider_ids"] = sum(c for c in dup.values() if c > 1)
    f["n_provider_ids"] = len(provider_ids)
    # mc input prefix check: the i-th model call's input length must be non-decreasing
    inputs = f.pop("_mc_inputs", [])
    f["mc_input_nonmonotone"] = sum(1 for a, b in zip(inputs, inputs[1:], strict=False) if b < a)
    # payload leakage: fixture text inside system / first-user message, or in assistant text / args
    leak: Counter[str] = Counter()
    first_user = next((m for m in msgs if m["role"] == "user"), None)
    system = next((m for m in msgs if m["role"] == "system"), None)
    payload_lines = []
    for c in fixtures:
        core = c.strip()
        if len(core) >= 40:
            payload_lines.append(core)
    for c in payload_lines:
        probe = c[:120]
        if system and any(probe in t for t in system["texts"]):
            leak["payload_in_system"] += 1
        if first_user and any(probe in t for t in first_user["texts"]):
            leak["payload_in_task_prompt"] += 1
        if any(probe in t for m in msgs if m["role"] == "tool" for t in m["texts"]):
            leak["payload_verbatim_in_tool_output"] += 1
        if any(probe in t for m in msgs if is_assistant(m["role"]) for t in m["texts"]):
            leak["payload_verbatim_in_assistant_text"] += 1
    f["leak"] = dict(leak)
    f["n_fixtures"] = len(fixtures)
    f["n_fixtures_nonempty"] = sum(1 for c in fixtures if c.strip())
    seal = doc.seal
    acc = seal.get("accounting") or {}
    f["acc_status"] = acc.get("status")
    f["acc_checks"] = {str(c.get("id")).split("@")[0].removeprefix("aer.acc."): c.get("verdict") for c in acc.get("checks") or ()}
    obs = {}
    for c in acc.get("checks") or ():
        if str(c.get("id")).startswith("aer.acc.tool_calls_dispatched"):
            obs = c.get("observed") or {}
    f["acc_dispatch"] = obs
    f["seal_issues"] = sorted({str(i.get("code")) for i in seal.get("issues") or ()})
    f["seal_issue_counts"] = dict(Counter(str(i.get("code")) for i in seal.get("issues") or ()))
    f["seal_issue_details"] = sorted({f"{i.get('code')}|{_safe(i.get('detail'))}" for i in seal.get("issues") or () if i.get("detail")})
    return f


# --------------------------------------------------------------------------------------------------------------- SEM
def sem_facts(sem: Any, f: dict[str, Any]) -> None:
    types: Counter[str] = Counter()
    unknown_tools = 0
    markers: Counter[str] = Counter()
    present_targets: set[str] = set()
    outcome: list[str] = []
    for r in sem.records[1:]:
        t = str(r.get("type"))
        v = r.get("value")
        if t == "injection_marker" and isinstance(v, dict):
            markers[str(v.get("status"))] += 1
            if v.get("status") == "present":
                present_targets.add(str(r.get("target")).split("#")[0])
            types[f"{t}:{v.get('status')}"] += 1
        elif t in ("role",) and isinstance(v, list):
            types[f"{t}:{'|'.join(map(str, v))}"] += 1
            if "unknown" in v:
                unknown_tools += 1
        elif isinstance(v, str | bool | int) or v is None:
            types[f"{t}:{v}"] += 1
        else:
            types[f"{t}:<{type(v).__name__}>"] += 1
        if t == "outcome":
            outcome.append(json.dumps(v, sort_keys=True)[:200])
        for ref in r.get("rule") or ():
            if str(ref).startswith("agentdojo.unknown_tool"):
                pass
    f["sem_types"] = dict(types)
    f["sem_unknown_role"] = unknown_tools
    f["sem_markers"] = dict(markers)
    f["sem_marker_present_msgs"] = len(present_targets)
    f["sem_outcome"] = outcome


# --------------------------------------------------------------------------------------------------------------- PROV
_REL_SECTIONS = {"wasGeneratedBy", "used", "wasInformedBy", "wasStartedBy", "wasEndedBy", "wasInvalidatedBy", "wasDerivedFrom",
                 "wasAttributedTo", "wasAssociatedWith", "actedOnBehalfOf", "wasInfluencedBy", "alternateOf",
                 "specializationOf", "mentionOf", "hadMember"}
_ARGS = {
    "wasGeneratedBy": ("prov:entity", "prov:activity"), "used": ("prov:activity", "prov:entity"),
    "wasInformedBy": ("prov:informed", "prov:informant"), "wasStartedBy": ("prov:activity", "prov:trigger", "prov:starter"),
    "wasEndedBy": ("prov:activity", "prov:trigger", "prov:ender"), "wasInvalidatedBy": ("prov:entity", "prov:activity"),
    "wasDerivedFrom": ("prov:generatedEntity", "prov:usedEntity", "prov:activity"),
    "wasAttributedTo": ("prov:entity", "prov:agent"), "wasAssociatedWith": ("prov:activity", "prov:agent"),
    "actedOnBehalfOf": ("prov:delegate", "prov:responsible"), "wasInfluencedBy": ("prov:influencee", "prov:influencer"),
    "alternateOf": ("prov:alternate1", "prov:alternate2"), "specializationOf": ("prov:specificEntity", "prov:generalEntity"),
    "mentionOf": ("prov:specificEntity", "prov:generalEntity"), "hadMember": ("prov:collection", "prov:entity"),
}
_TIME_KEYS = ("prov:time", "prov:startTime", "prov:endTime")


def _cls(attrs: dict[str, Any]) -> str:
    v = attrs.get("apv:evidenceClass")
    if isinstance(v, dict):
        v = v.get("$")
    return {"apv:Observed": "O", "apv:Derived": "D", "apv:Inferred": "I"}.get(str(v), "-")


def _node_kind(key: str) -> str:
    k = key.removeprefix("x:")
    if ".mn-" in k:
        return "mention"
    if ".gap-" in k:
        return "gap"
    if re.fullmatch(r"m\d+", k):
        return "message"
    if re.fullmatch(r"m\d+-\d+", k):
        return "part"
    if re.fullmatch(r"(mc|te|dc)\d+", k):
        return k[:2]
    if re.fullmatch(r"j\d+(\.check|\.rule|\.\w+)?", k):
        return "judgement"
    if re.fullmatch(r"fx\d+", k):
        return "fixture"
    return re.sub(r"\d+", "N", k)[:24]


def prov_facts(doc: dict[str, Any], aer: Any, f: dict[str, Any]) -> None:
    bundles = doc.get("bundle") or {}
    kinds: Counter[str] = Counter()
    sec_by_kind: Counter[str] = Counter()
    cls_by_kind: Counter[str] = Counter()
    rule_by_kind: Counter[str] = Counter()
    forbidden: Counter[str] = Counter()
    times = 0
    gen: dict[str, set[str]] = {}
    assoc: set[str] = set()
    used_by: dict[str, set[str]] = {}
    members: set[tuple[str, str]] = set()
    attributed: set[str] = set()
    nodes: dict[str, str] = {}
    adj: dict[str, set[str]] = {}
    core_nodes: dict[str, str] = {}
    core_adj: dict[str, set[str]] = {}
    attr_links: list[tuple[str, str]] = []

    def link(a: str, b: str, core: bool) -> None:
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
        if core:
            core_adj.setdefault(a, set()).add(b)
            core_adj.setdefault(b, set()).add(a)

    for iri, body in bundles.items():
        if ".core." in iri:
            bk = "core"
        elif ".inf." in iri:
            bk = "inference"
        elif ".assess." in iri:
            bk = "assessment"
        else:
            bk = "unknown"
        kinds[bk] += 1
        if not isinstance(body, dict):
            continue
        for sec, items in body.items():
            if not isinstance(items, dict):
                continue
            for key, attrs in items.items():
                if not isinstance(attrs, dict):
                    continue
                sec_by_kind[f"{bk}:{sec}"] += 1
                cls_by_kind[f"{bk}:{_cls(attrs)}"] += 1
                r = attrs.get("apv:rule")
                if isinstance(r, str):
                    rule_by_kind[f"{bk}:{r}"] += 1
                if any(t in attrs for t in _TIME_KEYS):
                    times += 1
                if bk in ("core", "inference"):
                    if sec in ("entity", "activity", "agent"):
                        nodes.setdefault(key, sec)
                        adj.setdefault(key, set())
                        for attr in ("apv:partOf", "apv:about"):  # attribute links (E: non-request parts, gap entities)
                            v = attrs.get(attr)
                            v = v.get("$") if isinstance(v, dict) else v
                            if isinstance(v, str):
                                attr_links.append((key, v))
                        if bk == "core":
                            core_nodes.setdefault(key, sec)
                            core_adj.setdefault(key, set())
                    elif sec in _ARGS:
                        ends = [attrs.get(a) for a in _ARGS[sec] if isinstance(attrs.get(a), str)]
                        for a in ends:
                            adj.setdefault(a, set())
                            if bk == "core":
                                core_adj.setdefault(a, set())
                        for a, b in zip(ends, ends[1:], strict=False):
                            link(a, b, bk == "core")
                        if sec == "wasGeneratedBy" and len(ends) >= 2:
                            gen.setdefault(ends[0], set()).add(ends[1])
                        elif sec == "wasAssociatedWith" and ends:
                            assoc.add(ends[0])
                        elif sec == "used" and len(ends) >= 2:
                            used_by.setdefault(ends[0], set()).add(ends[1])
                        elif sec == "hadMember" and len(ends) >= 2:
                            members.add((ends[0], ends[1]))
                        elif sec == "wasAttributedTo" and ends:
                            attributed.add(ends[0])
                    if sec == "wasInfluencedBy":
                        forbidden["wasInfluencedBy"] += 1
                    if sec == "wasInformedBy" and bk == "core":
                        forbidden["wasInformedBy_in_core"] += 1
                    if sec == "wasDerivedFrom":
                        forbidden[f"wasDerivedFrom_in_{bk}"] += 1
                    if sec in ("used", "wasDerivedFrom", "wasInformedBy") and bk == "core" and _cls(attrs) == "I":
                        forbidden["inferred_in_core"] += 1
                if bk == "core" and _cls(attrs) == "I":
                    forbidden["I_statement_in_core"] += 1
                if bk == "assessment" and sec in ("used", "wasDerivedFrom", "wasInformedBy"):
                    forbidden[f"assessment_{sec}"] += 1
    # tool-execution usage of anything except its request: list what each te uses
    te_used_kinds: Counter[str] = Counter()
    for act, ents in used_by.items():
        if _node_kind(act) == "te":
            for e in ents:
                te_used_kinds[_node_kind(e)] += 1
    # connectivity (core+inference union), components excluding gap entities (connected by attribute by design)
    minor: Counter[str] = Counter()

    def components(a: dict[str, set[str]], skip: set[str], record_minor: bool = False) -> tuple[int, Counter[str]]:
        seen: set[str] = set()
        n = 0
        isolated: Counter[str] = Counter()
        comps: list[list[str]] = []
        for start in a:
            if start in seen or start in skip:
                continue
            n += 1
            stack = [start]
            comp = []
            seen.add(start)
            while stack:
                x = stack.pop()
                comp.append(x)
                for y in a[x]:
                    if y not in seen and y not in skip:
                        seen.add(y)
                        stack.append(y)
            if len(comp) == 1:
                isolated[_node_kind(comp[0])] += 1
            comps.append(comp)
        if record_minor and comps:
            comps.sort(key=len, reverse=True)
            for comp in comps[1:]:
                minor["+".join(sorted({_node_kind(x) for x in comp}))[:80]] += 1
        return n, isolated

    gaps = {k for k in adj if ".gap-" in k}
    n_comp, isolated = components(adj, gaps)
    core_gaps = {k for k in core_adj if ".gap-" in k}
    n_core_comp, core_isolated = components(core_adj, core_gaps)
    aug = {k: set(v) for k, v in adj.items()}
    for a, b in attr_links:
        aug.setdefault(a, set()).add(b)
        aug.setdefault(b, set()).add(a)
    n_aug_comp, aug_isolated = components(aug, set(), record_minor=True)
    f["prov_aug_minor"] = dict(minor)
    f["prov_aug_components"] = n_aug_comp
    f["prov_aug_isolated"] = dict(aug_isolated)
    # AER cross-checks
    xc: Counter[str] = Counter()
    for r in aer.records:
        k = r.get("k")
        rid = r.get("id")
        if k == "message":
            key = f"x:{rid}"
            g = r.get("generated_by")
            if g is not None:
                if f"x:{g}" not in gen.get(key, set()):
                    xc["message_generated_by_missing"] += 1
            elif key not in attributed:
                xc["message_without_generation_or_attribution"] += 1
            for n_, p in enumerate(r.get("parts") or ()):
                if isinstance(p, dict) and p.get("t") == "tool_call" and (key, f"x:{rid}-{n_}") not in members:
                    xc["tool_call_part_not_member"] += 1
        elif k in ("model_call", "tool_execution", "decision"):
            if f"x:{rid}" not in assoc:
                xc[f"{k}_without_association"] += 1
            if k == "tool_execution" and isinstance(r.get("call"), str):
                part = "x:" + r["call"].replace("#", "-")
                if part not in used_by.get(f"x:{rid}", set()):
                    xc["tool_execution_without_used_request"] += 1
            if k == "model_call":
                n_inputs = len(r.get("input") or [])
                n_used = sum(1 for e in used_by.get(f"x:{rid}", set()) if _node_kind(e) == "message")
                if n_used != n_inputs:
                    xc["model_call_used_ne_input"] += 1
    f["prov_bundles"] = dict(kinds)
    f["prov_sections"] = dict(sec_by_kind)
    f["prov_classes"] = dict(cls_by_kind)
    f["prov_rules"] = dict(rule_by_kind)
    f["prov_forbidden"] = dict(forbidden)
    f["prov_times"] = times
    f["prov_nodes"] = len([k for k in nodes if ".mn-" not in k])
    f["prov_core_nodes"] = len(core_nodes)
    f["prov_edges"] = sum(v for k, v in sec_by_kind.items() if k.split(":")[0] in ("core", "inference") and k.split(":")[1] in _REL_SECTIONS)
    f["prov_core_edges"] = sum(v for k, v in sec_by_kind.items() if k.startswith("core:") and k.split(":")[1] in _REL_SECTIONS)
    f["prov_components"] = n_comp
    f["prov_isolated"] = dict(isolated)
    f["prov_core_components"] = n_core_comp
    f["prov_core_isolated"] = dict(core_isolated)
    f["prov_xcheck"] = dict(xc)
    f["te_used_kinds"] = dict(te_used_kinds)
    top = doc.get("entity") or {}
    aer_ent = [k for k in top if k.startswith("xd:aer.")]
    f["prov_aer_digest_ok"] = bool(aer_ent) and aer_ent[0] == f"xd:aer.{aer.execution_digest}"


# --------------------------------------------------------------------------------------------------------------- job
def job(row_line: bytes) -> dict[str, Any]:
    assert _ROOT is not None
    row = strict_json_loads(row_line, record=True)
    f: dict[str, Any] = {"ex": row["ex"], "status": row["status"], "completeness": row["completeness"],
                         "issues": row["issues"], "index_unit": row["unit"], "execution_observed": row["execution_observed"],
                         "n_origins": row.get("n_origins"), "source_sha": row["raw"][0]["sha256"] if row.get("raw") else None,
                         "integrity": []}
    errs: list[str] = f["integrity"]
    # raw objects re-hash
    for rr in row.get("raw") or ():
        h = rr["sha256"].removeprefix("sha256:")
        cands = list((_ROOT / "raw" / "objects" / h[:2]).glob(h + ".*")) + list((_ROOT / "raw" / "objects" / h[:2]).glob(h))
        if not cands:
            if rr.get("included"):
                errs.append("raw.missing")
            continue
        data = cands[0].read_bytes()
        if hashlib.sha256(data).hexdigest() != h:
            errs.append("raw.hash_mismatch")
        f.setdefault("raw_bytes", len(data))
        if data.startswith(b"\xef\xbb\xbf"):
            errs.append("raw.bom")
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            errs.append("raw.not_utf8")
    paths = row.get("paths") or {}
    digests = row.get("digests") or {}
    try:
        aer = load_aer(_ROOT / paths["aer"], verify=True)
    except Exception as exc:  # noqa: BLE001 - report, do not crash
        errs.append("aer.unreadable:" + type(exc).__name__)
        return f
    if "sha256:" + aer.execution_digest != digests.get("aer"):
        errs.append("aer.digest_mismatch")
    if aer.ex != row["ex"]:
        errs.append("aer.ex_mismatch")
    if aer.header.get("source_key", {}).get("sha256") != (f["source_sha"] or "").removeprefix("sha256:"):
        errs.append("aer.source_key_mismatch")
    aer_facts(aer, f)
    verified_sem: list[Any] = []  # SEM files that passed the digest checks, in sorted ref order
    for ref, rel in sorted((paths.get("sem") or {}).items()):
        try:
            sem = load_sem(_ROOT / rel, verify=True)
        except Exception as exc:  # noqa: BLE001
            errs.append("sem.unreadable:" + type(exc).__name__)
            continue
        if "sha256:" + sem.digest != (digests.get("sem") or {}).get(ref):
            errs.append("sem.digest_mismatch")
        if sem.header.get("aer_digest") != "sha256:" + aer.execution_digest:
            errs.append("sem.aer_digest_mismatch")
        else:
            verified_sem.append(sem)
        sem_facts(sem, f)
    # The safety net runs after SEM is loaded: payload_not_reaching_agent reads the SEM records and is skipped without
    # them (artefacts.scan). Only a SEM file bound to this AER is passed; the first in ref order if several.
    try:
        sem_records = verified_sem[0].records if verified_sem else None
        f["artefacts_sem_used"] = sem_records is not None
        f["artefacts"] = [x.to_json() for x in scan([*aer.records, aer.seal], _CATALOGUES, sem_records=sem_records)]
        for a in f["artefacts"]:
            a.pop("ids", None)
            a.pop("rules", None)
    except Exception as exc:  # noqa: BLE001
        errs.append("artefacts.scan_error:" + type(exc).__name__)
    prov_rel = (paths.get("prov") or {}).get(SPEC, {}).get("json")
    if prov_rel is None:
        errs.append("prov.missing")
        return f
    data = (_ROOT / prov_rel).read_bytes()
    if "sha256:" + hashlib.sha256(data).hexdigest() != digests.get("prov", {}).get(SPEC, {}).get("json"):
        errs.append("prov.digest_mismatch")
    try:
        doc = strict_json_loads(data, _LIMITS)
    except Exception as exc:  # noqa: BLE001
        errs.append("prov.unparseable:" + type(exc).__name__)
        return f
    f["prov_bytes"] = len(data)
    prov_facts(doc, aer, f)
    if not f["prov_aer_digest_ok"]:
        errs.append("prov.aer_entity_mismatch")
    return f


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--corpus", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    root: Path = args.corpus.expanduser()
    lines = [ln for ln in (root / "executions.jsonl").read_bytes().split(b"\n") if ln]
    if args.limit:
        lines = lines[: args.limit]
    # validation digests (H.2.11: sha256 of the JCS bytes of the results row)
    vdig: dict[str, str] = {}
    for ln in (root / "validation" / "results.jsonl").read_bytes().split(b"\n"):
        if ln:
            v = strict_json_loads(ln, record=True)
            vdig[v["ex"]] = "sha256:" + hashlib.sha256(jcs_bytes(v)).hexdigest()
    index_vdig = {}
    for ln in lines:
        r = strict_json_loads(ln, record=True)
        index_vdig[r["ex"]] = r.get("digests", {}).get("validation")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(args.out, "w", encoding="utf-8") as out, Pool(args.jobs, initializer=_init, initargs=(str(root),)) as pool:
        for f in pool.imap(job, lines, chunksize=8):
            if vdig.get(f["ex"]) != index_vdig.get(f["ex"]):
                f["integrity"].append("validation.digest_mismatch")
            out.write(json.dumps(f, sort_keys=True, separators=(",", ":")) + "\n")
            n += 1
            if n % 2000 == 0:
                print(f"{root.name}: {n}/{len(lines)}", file=sys.stderr, flush=True)
    print(f"{root.name}: done {n}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
