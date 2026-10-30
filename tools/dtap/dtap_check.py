"""DTap corpus checks DT02-DT13 (read-only; counts and execution ids only): docs/reports/analysis/dtap-sample-check.md.

    uv run python -I tools/dtap/dtap_check.py scan --corpus DIR --out ROWS.jsonl [--jobs 4] [--limit N]
    uv run python -I tools/dtap/dtap_check.py summary ROWS.jsonl [--json OUT]
    uv run python -I tools/dtap/dtap_check.py inventory --corpus DIR --input TREE [--json OUT]

``scan`` reads, per row of ``executions.jsonl``, the AER, SEM and PROV files and the execution's raw objects (primary
trajectory, judge file, configuration) from the corpus raw store, and checks the corpus against the raw evidence and
the DTap specification (docs/architecture D.16), **independently of the adapter code**: the step mapping is re-derived
from the raw steps, the call-to-result pairing from the step order, the join relations from the raw ``task_info`` and
the configuration, and the payload markers with an own implementation of the D.16.6 normaliser. Checks:

* DT02 (R03 analogue): one message or harness record per step at its position, roles verbatim, tool names and
  parameters, result text or value, ``send_message_to_user`` text, no invented message; run time verbatim (DT08);
* DT03 (A05 analogue): marker status recomputed for every SEM marker; markers missing for a (part, payload) pair;
* DT04: exposure class recomputed per payload fixture; observed classes only where the own matcher finds the payload in
  logged content; ``ev`` of every class; the PROV statement of each exposure (bundle, evidence class); SA03, SA04;
* DT05 (SA08): links re-paired by a FIFO over the raw step order; harness shape; ``pairing_ambiguous_batch`` per batch;
* DT06: join relations and tier recomputed; configuration content only in tier-A runs;
* DT07: the D-29 quality decisions, SA01, SA02, SA05 and the applies-check of the DTap issue codes (R01n analogue);
* DT08: no ``prov:time``/``startTime``/``endTime`` in any PROV statement; ``t`` only on the run scope;
* DT09: role and integrity census of tool calls and results, fail-closed on ambiguous links;
* DT11: path-facet character screen (R01d), A02, A03 on role ``agent``; DT12: trajectory digest for R05 groups;
* DT13: ``endorser`` labels and their absence as taint subjects.

``inventory`` (DT10, IM04 analogue) accounts for every file of the sample input tree (an execution's primary, an
auxiliary artefact of one, or a register row). Text inside the data is untrusted and is never printed: the output
holds counts, normalised pointers, execution ids and truncated digests only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from multiprocessing import Pool
from pathlib import Path
from typing import Any

SPEC = "agentprov-prov/0.1"
MIN_NEEDLE = 24
WINDOW = 40
JUDGE_LINK_MIN = 40
TIME_KEYS = ("prov:time", "prov:startTime", "prov:endTime")
EV_IRI = {"apv:Observed": "O", "apv:Derived": "D", "apv:Inferred": "I"}
OBSERVED = {"observed_tool_output", "observed_description_log", "observed_user_step"}
I_CLASSES = {"configured_only", "partial_match"}
STRICT = {"openaisdk", "openclaw"}
#: issue codes the mapper raises from raw conditions (R01n applies-check); value = the predicate key computed below
APPLIES = {
    "dtap.harness_failure": "error_step",
    "dtap.empty_trajectory": "empty",
    "dtap.user_step_not_logged": "no_user_step",
    "dtap.goal_rewritten_at_eval": "goal_at_eval",
    "dtap.source_truncation_marker": "truncated_marker",
    "unattributed_additional_user_message": "later_user_step",
    "dtap.final_response_differs": "final_differs",
}
_ROOT: Path | None = None
_ESC = re.compile(r"\\[nrt]")


# ------------------------------------------------------------------------------------------------ own matcher (D.16.6)
def norm(text: str) -> str:
    """D.16.6 as written: literal ``\\n``/``\\r``/``\\t`` escapes removed, NFKC, lower case, alphanumerics only."""
    folded = unicodedata.normalize("NFKC", _ESC.sub("", text)).lower()
    return "".join(ch for ch in folded if ch.isalnum())


def as_text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def leaves(value: Any) -> list[str]:
    out: list[str] = []
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return out


def needles_of(content: Any) -> list[str]:
    return sorted({n for n in (norm(s) for s in leaves(content)) if len(n) >= MIN_NEEDLE})


def level(needles: list[str], hay: str) -> str:
    if not needles:
        return "gap"
    if any(n in hay for n in needles):
        return "present"
    for n in needles:
        if len(n) > WINDOW:
            mid = len(n) // 2 - WINDOW // 2
            if any(w in hay for w in (n[:WINDOW], n[mid:mid + WINDOW], n[-WINDOW:])):
                return "ambiguous"
    return "absent"


# ------------------------------------------------------------------------------------------------ helpers
def _strict(data: bytes) -> Any:
    from agentprov.ingest.loaders import strict_json_loads

    return strict_json_loads(data)


def _lines(path: Path) -> list[dict[str, Any]]:
    from agentprov.ingest.loaders import strict_json_loads

    return [strict_json_loads(x, record=True) for x in path.read_bytes().split(b"\n") if x]


def _raw(sha: str) -> bytes | None:
    assert _ROOT is not None
    h = sha.removeprefix("sha256:")
    for p in (_ROOT / "raw" / "objects" / h[:2]).glob(h + "*"):
        if p.is_file():
            return p.read_bytes()
    return None


def _ev(attrs: dict[str, Any]) -> str:
    v = attrs.get("apv:evidenceClass")
    v = v.get("$") if isinstance(v, dict) else v
    return EV_IRI.get(str(v), "-")


def _bundle_kind(iri: str) -> str:
    for k in ("core", "inf", "assess"):
        if f".{k}." in iri:
            return k
    return "other"


def _issue_set(seal: dict[str, Any]) -> Counter[str]:
    return Counter(str(i.get("code")) for i in seal.get("issues") or ())


def _wilson(k: int, n: int) -> list[float] | None:
    if n == 0:
        return None
    z = 1.959964
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return [round((c - r) / d, 4), round((c + r) / d, 4)]


class Row:
    """Per-execution result: counters and failures (check id -> short detail tokens)."""

    def __init__(self, ex: str) -> None:
        self.ex = ex
        self.c: Counter[str] = Counter()
        self.fail: dict[str, list[str]] = defaultdict(list)
        self.info: dict[str, Any] = {}

    def bad(self, check: str, detail: str) -> None:
        if len(self.fail[check]) < 20:
            self.fail[check].append(detail)
        self.c[f"{check}|fail"] += 1

    def to_json(self) -> dict[str, Any]:
        return {"ex": self.ex, "c": dict(self.c), "fail": dict(self.fail), "info": self.info}


# ------------------------------------------------------------------------------------------------ the raw run
def _as_redacted(value: Any, header: dict[str, Any]) -> Any:
    """The raw value as the mapper's D-607 redaction leaves it (the profile the header records), so that a redacted AER
    string compares equal to its raw source; identity when the profile declares no rule."""
    from agentprov.adapters.dtap.redact import Redactor, parse_redact_rules
    from agentprov.adapters.profiles import load_profile

    prof = header.get("profile") or {}
    profile = load_profile(str(prof.get("id")), prof.get("version"))
    red = Redactor(profile.id, profile.version, parse_redact_rules(profile.family_table().get("redact", ()), "check"))
    if not red.active:
        return value

    def walk(v: Any) -> Any:
        if isinstance(v, str):
            return red.label(v)
        if isinstance(v, dict):
            return {red.label(k) if isinstance(k, str) else k: walk(x) for k, x in v.items()}
        if isinstance(v, list):
            return [walk(x) for x in v]
        return v

    return walk(value)


class RawRun:
    """The raw trajectory read as data: step classes, the FIFO pairing and the batches."""

    def __init__(self, doc: dict[str, Any]) -> None:
        self.doc = doc
        self.steps: list[dict[str, Any]] = doc.get("trajectory") or []
        self.kind: list[str] = []
        for s in self.steps:
            md = s.get("metadata") or {}
            role = s.get("role")
            if role == "user":
                self.kind.append("user")
            elif role == "tool":
                self.kind.append("result")
            elif role == "agent" and s.get("action") == "send_message_to_user":
                self.kind.append("message")
            elif role == "agent" and "error" in md and not md.get("tool_name"):
                self.kind.append("error")
            elif role == "agent" and isinstance(md.get("tool_name"), str):
                self.kind.append("meta" if md["tool_name"].startswith("List MCP Tools") else "call")
            else:
                self.kind.append("other:" + str(role))
        self.pair: dict[int, int] = {}  # result step -> call step
        self.unanswered: list[int] = []
        self.orphans: list[int] = []
        self.batches: list[dict[str, Any]] = []
        queue: list[int] = []
        batch: dict[str, Any] | None = None
        for i, k in enumerate(self.kind):
            if k in ("call", "meta"):
                if batch is None:
                    batch = {"calls": [], "results": [], "pattern": ""}
                queue.append(i)
                batch["calls"].append(i)
                batch["pattern"] += "A"
            elif k == "result":
                if not queue:
                    self.orphans.append(i)
                    continue
                j = queue.pop(0)
                self.pair[i] = j
                assert batch is not None
                batch["results"].append(i)
                batch["pattern"] += "T"
                if not queue:
                    self.batches.append(batch)
                    batch = None
            elif k in ("user", "error") and batch is not None and queue:
                batch["pattern"] += "|"  # a non-agent step inside an open batch (recorded, never re-paired)
        if batch is not None:
            self.unanswered = list(queue)
            self.batches.append(batch)

    def name(self, i: int) -> Any:
        return (self.steps[i].get("metadata") or {}).get("tool_name")


# ------------------------------------------------------------------------------------------------ scan
def _init(root: str) -> None:
    global _ROOT
    _ROOT = Path(root)


def job(line: bytes) -> dict[str, Any]:
    assert _ROOT is not None
    row = json.loads(line)
    out = Row(row["ex"])
    try:
        _job(row, out)
    except Exception as exc:  # noqa: BLE001 - recorded, never hidden
        out.bad("DT00", "exception:" + type(exc).__name__)
    return out.to_json()


def _job(row: dict[str, Any], out: Row) -> None:
    assert _ROOT is not None
    paths = row.get("paths") or {}
    lines = _lines(_ROOT / paths["aer"])
    header, seal, recs = lines[0], lines[-1], lines[1:-1]
    by_id = {r.get("id"): r for r in recs}
    dtap = (header.get("ext") or {}).get("dtap") or {}
    facets = dtap.get("path_facets") or {}
    fw = str(facets.get("framework"))
    split = "benign" if facets.get("split") == "benign" else str(facets.get("threat"))
    unit = header.get("unit")
    issues = _issue_set(seal)
    out.info.update({"fw": fw, "model": facets.get("model"), "split": split, "unit": unit, "domain": facets.get("domain"),
                     "status": row.get("status"), "stages": row.get("stages"), "issues": sorted(issues)})
    arts = {a["id"]: a for a in header.get("artifacts") or ()}
    primary = next(a for a in arts.values() if a.get("role") == "primary")
    judge_art = next((a for a in arts.values() if str((a.get("origin") or {}).get("path", "")).endswith("judge_result.json")
                      and a.get("role") != "primary"), None)
    config_art = next((a for a in arts.values() if str((a.get("origin") or {}).get("path", "")).endswith("config.yaml")), None)
    pdata = _raw(primary["sha256"])
    if pdata is None:
        out.bad("DT02", "primary_not_stored")
        return
    pdoc = _as_redacted(_strict(pdata), header)
    judge = _as_redacted(_strict(_raw(judge_art["sha256"]) or b"null"), header) if judge_art else None
    if str((primary.get("origin") or {}).get("path", "")).endswith("judge_result.json"):
        judge, pdoc = pdoc, None  # a judge-only outcome unit
    sem: list[dict[str, Any]] = []
    for _ref, rel in sorted((paths.get("sem") or {}).items()):
        sem += [a for a in _lines(_ROOT / rel)[1:-1] if a.get("k") == "ann"]
    prov_rel = ((paths.get("prov") or {}).get(SPEC) or {}).get("json")
    prov = _strict((_ROOT / prov_rel).read_bytes()) if prov_rel else None
    out.c["executions"] += 1
    out.c[f"has_sem|{bool(sem)}"] += 1
    out.c[f"has_prov|{prov is not None}"] += 1
    raw = RawRun(pdoc) if isinstance(pdoc, dict) and "trajectory" in pdoc else None
    facts_check(out, header, recs, raw, facets)
    if raw is not None and unit == "agent_execution":
        step_check(out, header, recs, by_id, raw, fw)
        pairing_check(out, recs, by_id, seal, raw, fw)
    time_check(out, header, recs, pdoc, prov)
    join_check(out, header, recs, pdoc, config_art, split)
    quality_check(out, header, recs, seal, issues, pdoc, judge, raw, split, pdata)
    if sem:
        marker_check(out, recs, by_id, sem, prov, split, raw)
        semantics_check(out, recs, by_id, sem, prov, fw)


# ------------------------------------------------------------------------------------------------ DT11, DT12
def facts_check(out: Row, header: dict[str, Any], recs: list[dict[str, Any]], raw: RawRun | None, facets: dict[str, Any]) -> None:
    for key, value in facets.items():
        if isinstance(value, str):
            bad = [ch for ch in value if ord(ch) < 0x20 or 0x7F <= ord(ch) < 0xA0 or ord(ch) > 0x7E
                   or unicodedata.category(ch) in ("Cf", "Zl", "Zp")]
            if bad:
                out.bad("DT11", f"facet_chars:{key}")
    agents = [r for r in recs if r.get("k") == "message" and r.get("role") == "agent"]
    empties = 0
    for r in agents:
        parts = r.get("parts") or []
        has = any(p.get("t") == "tool_call" or (isinstance(p.get("text"), str) and p["text"].strip()) for p in parts)
        empties += not has
    out.c["a03|agent_messages"] += len(agents)
    out.c["a03|empty_agent_turn"] += empties
    if agents and not any(
            any(p.get("t") == "tool_call" or (isinstance(p.get("text"), str) and p["text"].strip()) for p in r.get("parts") or [])
            for r in agents):
        out.c["a03|all_agent_empty"] += 1
    for r in recs:
        if r.get("k") == "model_call":
            for key, reason in (r.get("unk") or {}).items():
                if "finish" in key:
                    out.c[f"a02|{key}|{reason}"] += 1
            if any("finish" in k for k in r):
                out.c["a02|finish_reason_present"] += 1
        if r.get("k") == "decision":
            out.c["sa06|decisions"] += 1
    traj = hashlib.sha256()
    n = 0
    for r in recs:
        if r.get("k") == "message":
            traj.update(json.dumps([r.get("role"), r.get("parts")], sort_keys=True, ensure_ascii=False).encode())
            n += 1
    out.info["traj_digest"] = traj.hexdigest()[:24] if n else None
    out.info["n_messages"] = n
    out.info["n_tool_calls"] = sum(1 for r in recs if r.get("k") == "message" for p in r.get("parts") or []
                                   if p.get("t") == "tool_call")
    out.info["task_dir"] = f"{facets.get('domain')}/{header.get('task', {}).get('task_id')}"
    out.info["file"] = facets.get("file")


# ------------------------------------------------------------------------------------------------ DT02
def _src_ptrs(r: dict[str, Any]) -> list[str]:
    return [str(loc.get("p")) for loc in r.get("src") or () if isinstance(loc, dict) and loc.get("a") == "a0" and "p" in loc]


def _num(v: Any) -> Any:
    """Integral floats as integers: JCS writes ``1.0`` as ``1`` and ``ext.lex.flt`` records the float form (C.11)."""
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, dict):
        return {k: _num(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_num(x) for x in v]
    return v


def _same(a: Any, b: Any) -> bool:
    return json.dumps(_num(a), sort_keys=True) == json.dumps(_num(b), sort_keys=True)


def step_check(out: Row, header: dict[str, Any], recs: list[dict[str, Any]], by_id: dict[Any, dict[str, Any]], raw: RawRun,
               fw: str) -> None:
    at_step: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for r in recs:
        for p in _src_ptrs(r):
            m = re.fullmatch(r"/trajectory/(\d+)(/.*)?", p)
            if m:
                at_step[int(m.group(1))].append(r)
    msg_ids = {r["id"] for r in recs if r.get("k") == "message"}
    expected_msgs: set[str] = set()
    meta_steps = {raw.pair[i] for i in raw.pair if raw.kind[raw.pair[i]] == "meta"} | {i for i, k in enumerate(raw.kind) if k == "meta"}
    meta_results = {i for i, j in raw.pair.items() if raw.kind[j] == "meta"}
    for i, (s, k) in enumerate(zip(raw.steps, raw.kind, strict=True)):
        md = s.get("metadata") or {}
        out.c[f"dt02|steps|{k}"] += 1
        mid = f"m{i}"
        if k == "user":
            expected_msgs.add(mid)
            m = by_id.get(mid)
            if m is None or m.get("role") != "user":
                out.bad("DT02", f"user_step_not_message:{i}")
                continue
            if not (m.get("parts") and m["parts"][0].get("text") == s.get("state")):
                out.bad("DT02", f"user_text:{i}")
        elif k == "message":
            expected_msgs.add(mid)
            m = by_id.get(mid)
            if m is None or m.get("role") != "agent":
                out.bad("DT02", f"agent_message_missing:{i}")
                continue
            if not (m.get("parts") and m["parts"][0].get("t") == "text" and m["parts"][0].get("text") == md.get("message")):
                out.bad("DT02", f"agent_message_text:{i}")
        elif k == "call":
            expected_msgs.add(mid)
            m = by_id.get(mid)
            if m is None or m.get("role") != "agent":
                out.bad("DT02", f"call_missing:{i}")
                continue
            part = (m.get("parts") or [{}])[0]
            if part.get("t") != "tool_call" or part.get("name") != md.get("tool_name"):
                out.bad("DT02", f"call_name:{i}")
            if "tool_params" in md:
                if not _same(part.get("args"), md.get("tool_params")):
                    out.bad("DT02", f"call_args:{i}")
            else:
                out.c[f"dt02|call_without_params|args={type(part.get('args')).__name__}"] += 1
        elif k == "meta":
            kinds = {(r.get("k"), r.get("type")) for r in at_step[i]}
            if ("activity", "dtap:list_mcp_tools") not in kinds:
                out.bad("DT02", f"meta_not_activity:{i}")
            if mid in msg_ids:
                out.bad("DT02", f"meta_as_message:{i}")
        elif k == "error":
            kinds = {(r.get("k"), r.get("type")) for r in at_step[i]}
            if ("activity", "dtap:harness_error") not in kinds:
                out.bad("DT02", f"error_not_activity:{i}")
        elif k == "result":
            if i in meta_results:
                arts = [r for r in at_step[i] if r.get("k") == "artefact" and r.get("type") == "dtap:tool_name_list"]
                if not arts:
                    out.bad("DT02", f"meta_result_not_artefact:{i}")
                elif not _same(arts[0].get("content"), s.get("state")):
                    out.bad("DT02", f"meta_result_content:{i}")
                continue
            expected_msgs.add(mid)
            m = by_id.get(mid)
            if m is None or m.get("role") != "tool":
                out.bad("DT02", f"result_missing:{i}")
                continue
            part = (m.get("parts") or [{}])[0]
            state = s.get("state")
            if isinstance(state, str):
                ok = part.get("text") == state and "value" not in part
                form = "text"
            else:
                ok = "value" in part and _same(part.get("value"), state)
                form = "value:" + type(state).__name__
            out.c[f"dt02|result_form|{form}"] += 1
            if not ok:
                out.bad("DT02", f"result_content:{i}")
            rname = md.get("tool_name")
            if rname == "unknown":
                if part.get("name") is not None:
                    out.bad("DT02", f"unknown_name_typed:{i}")
                out.c["dt02|result_name_unknown"] += 1
        else:
            out.c[f"dt02|unclassified_step|{k}"] += 1
    extra = msg_ids - expected_msgs
    for mid in sorted(extra):
        r = by_id[mid]
        # the echo after an error step is a message (D.16.3); anything else is invented
        step = int(mid[1:]) if mid[1:].isdigit() else -1
        if 0 < step < len(raw.kind) and raw.kind[step] == "message":
            continue
        if not (0 <= step < len(raw.kind) and raw.kind[step - 1] == "error"):
            out.bad("DT02", f"message_without_step:{mid}")
    for mid in sorted(expected_msgs - msg_ids):
        out.bad("DT02", f"step_without_message:{mid}")
    del meta_steps


# ------------------------------------------------------------------------------------------------ DT05 (SA08)
def pairing_check(out: Row, recs: list[dict[str, Any]], by_id: dict[Any, dict[str, Any]], seal: dict[str, Any], raw: RawRun,
                  fw: str) -> None:
    te_by_msg: dict[str, dict[str, Any]] = {}
    for r in recs:
        if r.get("k") == "message" and r.get("role") == "tool" and r.get("generated_by"):
            te_by_msg[r["id"]] = by_id.get(r["generated_by"]) or {}
    conflicts: set[int] = set()
    for b in raw.batches:
        calls = [c for c in b["calls"] if raw.kind[c] == "call"]
        names_ok = all(raw.name(r) == raw.name(raw.pair[r]) for r in b["results"])
        if fw in STRICT or fw == "googleadk":
            if not names_ok:
                conflicts.update(b["calls"])
                out.c[f"dt05|{fw}|name_check_fails_batches"] += 1
        shape = "single" if len(b["calls"]) == 1 else ("contiguous" if re.fullmatch(r"A+T+", b["pattern"]) else "interleaved")
        out.c[f"dt05|{fw}|batches|{shape}"] += 1
        if fw in STRICT and len(b["calls"]) > 1:
            out.c[f"dt05|{fw}|strict_harness_multi_call_batch"] += 1
        if fw == "googleadk" and shape == "interleaved":
            out.c["dt05|googleadk|non_contiguous_batch"] += 1
        multi = len(b["calls"]) > 1
        out.c[f"dt05|{fw}|results"] += len(b["results"])
        if multi:
            out.c[f"dt05|{fw}|results_in_multi_call_batches"] += len(b["results"])
            out.c[f"dt05|{fw}|calls_in_multi_call_batches"] += len(b["calls"])
        b["shape"], b["multi"], b["tool_calls"] = shape, multi, calls
    # links
    for res, call in raw.pair.items():
        if raw.kind[call] == "meta":
            continue
        mid = f"m{res}"
        msg = by_id.get(mid)
        if msg is None:
            continue
        part = (msg.get("parts") or [{}])[0]
        te = te_by_msg.get(mid, {})
        expect = f"m{call}#0"
        if call in conflicts:
            if "responds_to" in part or "call" in te:
                out.bad("DT05", f"linked_despite_name_conflict:{res}")
            continue
        if part.get("responds_to") != expect or te.get("call") != expect:
            out.bad("DT05", f"link:{res}")
        evf_m, evf_t = msg.get("evf") or {}, te.get("evf") or {}
        if evf_m.get("/parts/0/responds_to") != "I" or evf_t.get("/call") != "I":
            out.bad("DT05", f"link_not_I:{res}")
        out.c[f"dt05|{fw}|links_checked"] += 1
    # issues
    amb = [i for i in seal.get("issues") or () if i.get("code") == "dtap.pairing_ambiguous_batch"]
    amb_calls = {x for i in amb for x in i.get("ids") or () if isinstance(x, str) and "#" in x}
    multi_batches = [b for b in raw.batches if b["multi"]]
    for b in multi_batches:
        want = {f"m{c}#0" for c in b["tool_calls"]}
        hit = [i for i in amb if want and want <= set(i.get("ids") or ())]
        if want and len(hit) != 1:
            out.bad("DT05", f"ambiguous_issue_missing:{min(b['calls'])}")
        for i in hit:
            out.c[f"dt05|{fw}|issue_detail|{i.get('detail')}|shape={b['shape']}"] += 1
    single_calls = {f"m{c}#0" for b in raw.batches if not b["multi"] for c in b["tool_calls"]}
    if amb_calls & single_calls:
        out.bad("DT05", "ambiguous_issue_on_single_batch")
    out.c["dt05|ambiguous_issues"] += len(amb)
    out.c["dt05|multi_call_batches"] += len(multi_batches)
    codes = _issue_set(seal)
    if raw.unanswered:
        out.c[f"dt05|{fw}|unanswered_calls"] += len(raw.unanswered)
        if not codes.get("unexecuted_tool_call"):
            out.bad("DT05", "unanswered_without_issue")
    if raw.orphans:
        out.c[f"dt05|{fw}|orphan_results"] += len(raw.orphans)
        if not codes.get("orphan_tool_result"):
            out.bad("DT05", "orphan_without_issue")
    if conflicts and not codes.get("call_result_link_conflict"):
        out.bad("DT05", "conflict_without_issue")


# ------------------------------------------------------------------------------------------------ DT08
def time_check(out: Row, header: dict[str, Any], recs: list[dict[str, Any]], pdoc: Any, prov: Any) -> None:
    for r in [header, *recs]:
        if "t" in r and not (r.get("k") == "scope" and r.get("id") == "run"):
            out.bad("DT08", f"t_on:{r.get('k')}")
    run = next((r for r in recs if r.get("k") == "scope" and r.get("id") == "run"), None)
    if run is not None and isinstance(pdoc, dict) and "traj_info" in pdoc:
        t = run.get("t") or {}
        ts = (pdoc.get("traj_info") or {}).get("timestamp")
        for key in ("start", "end", "start_naive", "end_naive", "dur_s"):
            if key in t:
                out.bad("DT08", f"typed_time:{key}")
        if ts is None:
            if "raw" in t:
                out.bad("DT08", "raw_time_without_source")
        elif (t.get("raw") or {}).get("end") != ts:
            out.bad("DT08", "raw_end_not_verbatim")
        zone = ((run.get("ext") or {}).get("dtap") or {}).get("timestamp_zone")
        if isinstance(ts, str):
            own = "utc" if re.search(r"(Z|[+-]00:00)$", ts) else ("none" if re.fullmatch(r"[0-9T:.\- ]+", ts) else "other")
            out.c[f"dt08|zone|{zone}|own={own}"] += 1
    if prov is not None:
        n = 0
        stack = [prov]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                n += sum(1 for k in TIME_KEYS if k in node)
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
        out.c["dt08|prov_time_attributes"] += n
        if n:
            out.bad("DT08", "prov_time")


# ------------------------------------------------------------------------------------------------ DT06
def _nws(s: str) -> str:
    return " ".join(s.split())


def rel(run: Any, cfg: Any, *, instruction: bool) -> str:
    """D.16.5 as written: exact; whitespace; (instruction) the 500-character prefix; (goal) the configuration goal is a
    prefix of the run text."""
    if not isinstance(run, str) or not isinstance(cfg, str):
        return "absent"
    if run == cfg:
        return "exact"
    if _nws(run) == _nws(cfg):
        return "whitespace"
    if instruction and len(run) == 500 and (cfg.startswith(run) or _nws(cfg).startswith(_nws(run))):
        return "prefix_500"
    if not instruction and cfg and _nws(run).startswith(_nws(cfg)):
        return "prefix"
    return "differs"


def join_check(out: Row, header: dict[str, Any], recs: list[dict[str, Any]], pdoc: Any, config_art: dict[str, Any] | None,
               split: str) -> None:
    from agentprov.ingest.yamlsafe import safe_load

    join = ((header.get("ext") or {}).get("dtap") or {}).get("join")
    status = join.get("status") if isinstance(join, dict) else None
    tier = join.get("tier") if isinstance(join, dict) else None
    out.c[f"dt06|status|{status}|tier={tier}"] += 1
    out.info["join"] = [status, tier]
    cfg_fx = [r for r in recs if r.get("k") == "fixture" and any(
        isinstance(s, dict) and config_art is not None and s.get("a") == config_art.get("id") for s in r.get("src") or ())]
    if tier != "A" and cfg_fx:
        out.bad("DT06", f"config_content_outside_tier_a:{len(cfg_fx)}")
    if status != "joined" or config_art is None or not isinstance(pdoc, dict):
        return
    data = _raw(config_art["sha256"])
    if data is None:
        out.bad("DT06", "config_not_stored")
        return
    cfg = safe_load(data.decode("utf-8"))
    task = (cfg.get("Task") if isinstance(cfg, dict) else None) or {}
    attack = (cfg.get("Attack") if isinstance(cfg, dict) else None) or {}
    ti = pdoc.get("task_info") or {}
    goal = attack.get("malicious_goal")
    orig = ti.get("original_instruction")
    if split in ("benign", "indirect"):
        ins = rel(orig, task.get("task_instruction"), instruction=True)
    elif split == "direct":
        cands = [st.get("content") for turn in attack.get("attack_turns") or [] for st in (turn or {}).get("attack_steps") or []
                 if isinstance(st, dict) and st.get("type") == "prompt"] + [goal]
        order = ("exact", "whitespace", "prefix_500", "differs", "absent")
        ins = min((rel(orig, c, instruction=True) for c in cands), key=order.index)
    elif split == "direct_prompt":
        ins = rel(orig, goal, instruction=True)
    else:
        ins = "not_applicable"
    mal = ti.get("malicious_instruction")
    if split in ("benign", "direct_no_attack"):
        gl = "exact" if mal in ("", None) else "differs"
    else:
        gl = rel(mal, goal, instruction=False)
    ok_i = ins in ("exact", "whitespace", "prefix_500", "not_applicable")
    ok_g = gl in ("exact", "whitespace", "prefix")
    own = "A" if ok_i and ok_g else ("B" if ok_i or ok_g else "C")
    out.c[f"dt06|own_tier|{own}|aer={tier}"] += 1
    out.c[f"dt06|instruction|own={ins}|aer={join.get('instruction')}"] += 1
    out.c[f"dt06|goal|own={gl}|aer={join.get('goal')}"] += 1
    if own != tier:
        out.bad("DT06", f"tier:{own}!={tier}")
    if tier == "A" and split in ("direct", "indirect"):
        n_steps = sum(len((turn or {}).get("attack_steps") or []) for turn in attack.get("attack_turns") or [])
        n_fx = sum(1 for r in recs if r.get("k") == "fixture" and r.get("kind") == "injection_payload")
        if n_fx != n_steps:
            out.bad("DT06", f"payload_fixtures:{n_fx}!={n_steps}")
    if split in ("direct_prompt", "direct_no_attack", "benign"):
        if any(r.get("k") == "fixture" and r.get("kind") == "injection_payload" for r in recs):
            out.bad("DT06", f"payload_fixture_in_{split}")


# ------------------------------------------------------------------------------------------------ DT07 (SA01, SA02, SA05, R01n)
def quality_check(out: Row, header: dict[str, Any], recs: list[dict[str, Any]], seal: dict[str, Any], issues: Counter[str],
                  pdoc: Any, judge: Any, raw: RawRun | None, split: str, pdata: bytes) -> None:
    unit = header.get("unit")
    js = {r["id"]: r for r in recs if r.get("k") == "judgement"}
    run = next((r for r in recs if r.get("k") == "scope" and r.get("id") == "run"), {})
    link = ((header.get("ext") or {}).get("dtap") or {}).get("judge_link")
    method = link.get("method") if isinstance(link, dict) else None
    resolved = link.get("resolved") if isinstance(link, dict) else None
    out.c[f"dt07|judge_link|{method}|resolved={resolved}|judgements={len(js)}"] += 1
    out.info["judge_link"] = [method, resolved, (link or {}).get("group_size"), (link or {}).get("judge_sha256", "")[:16]]
    # synthetic must never be an execution
    if isinstance(pdoc, dict) and ((pdoc.get("task_info") or {}).get("synthetic") is True
                                   or ((pdoc.get("traj_info") or {}).get("metadata") or {}).get("synthetic") is True):
        out.bad("DT07", "synthetic_imported")
    pred: dict[str, bool] = {}
    if raw is not None:
        ti = pdoc.get("task_info") or {}
        tr = pdoc.get("traj_info") or {}
        users = [i for i, k in enumerate(raw.kind) if k == "user"]
        msgs = [s for s, k in zip(raw.steps, raw.kind, strict=True) if k == "message"]
        last = (msgs[-1].get("metadata") or {}).get("message") if msgs else None
        final = tr.get("agent_final_response")
        pred = {
            "error_step": "error" in raw.kind,
            "empty": not raw.steps,
            "no_user_step": bool(raw.steps) and not users,
            "goal_at_eval": "malicious_instruction_at_eval" in ti,
            "truncated_marker": b"[truncated" in pdata,
            "later_user_step": len(users) > 1,
            "final_differs": final is not None and last is not None and final != last,
        }
        out.info["pred"] = sorted(k for k, v in pred.items() if v)
        for code, key in APPLIES.items():
            has, want = issues.get(code, 0) > 0, pred[key]
            out.c[f"r01n|{code}|issue={has}|raw={want}"] += 1
            if has != want:
                out.bad("DT07", f"applies:{code}:{has}!={want}")
        if pred["error_step"]:
            if run.get("status") != "error":
                out.bad("DT07", "harness_failure_status")
            if not js or not issues.get("dtap.judgement_on_failed_run"):
                out.bad("DT07", "harness_failure_judgements")
        if pred["empty"]:
            if unit != "outcome_only" or not issues.get("no_execution_observed"):
                out.bad("DT07", "empty_not_outcome_only")
            if not js:
                out.bad("DT07", "empty_without_judgements")
        n_calls = sum(1 for k in raw.kind if k == "call")
        out.info["n_raw_calls"] = n_calls
    # judgements against the judge file
    if isinstance(judge, dict) and js:
        by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in js.values():
            by_name[str(r.get("name"))].append(r)
        ts = by_name.get("task_success", [])
        if len(ts) != 1 or ts[0].get("value") != judge.get("task_success"):
            out.bad("DT07", "task_success_value")
        att = by_name.get("attack_success", [])
        audit = judge.get("audit_correction")
        if isinstance(audit, dict):
            out.c["dt07|audit_corrected"] += 1
            orig = [r for r in att if not r.get("revises")]
            corr = [r for r in att if r.get("revises")]
            if len(orig) != 1 or len(corr) != 1:
                out.bad("DT07", "audit_pair_missing")
            else:
                if orig[0].get("value") != audit.get("original_attack_success") or corr[0].get("value") != judge.get("attack_success"):
                    out.bad("DT07", "audit_values")
                if corr[0].get("revises") != orig[0].get("id") or corr[0].get("origin") != "recomputed":
                    out.bad("DT07", "audit_revises")
                out.c[f"dt07|audit|orig={orig[0].get('value')}|corr={corr[0].get('value')}"] += 1
        elif len(att) != 1 or att[0].get("value") != judge.get("attack_success"):
            out.bad("DT07", "attack_success_value")
        # SA01 harness constants
        for r in js.values():
            out.c[f"sa01|{split}|{r.get('name')}|{json.dumps(r.get('value'))}|{r.get('origin')}"] += 1
        if split == "direct_prompt" and ts and ts[0].get("origin") != "harness_default":
            out.bad("DT07", "direct_prompt_task_success_origin")
        if split == "benign" and att and any(r.get("value") is None and r.get("origin") != "harness_default" for r in att):
            out.bad("DT07", "benign_attack_null_origin")
        eff = next((r.get("value") for r in att if r.get("revises")), None) if any(r.get("revises") for r in att) else \
            (att[0].get("value") if att else None)
        out.info["attack_success_effective"] = eff
        out.info["task_success"] = ts[0].get("value") if ts else None
        out.info["task_success_origin"] = ts[0].get("origin") if ts else None
        if raw is not None and ts and ts[0].get("value") is True and ts[0].get("origin") == "checker":
            out.c[f"sa05|{split}|task_true"] += 1
            if out.info.get("n_raw_calls", 0) == 0:
                out.c[f"sa05|{split}|task_true_zero_calls"] += 1
    # judge-to-attempt linkage (D.16.8) recomputed: a judge string (>= 40 normalised characters) found in exactly one
    # attempt links the judge to it; otherwise a single attempt is linked by co-location; otherwise unresolved
    if isinstance(judge, dict) and isinstance(link, dict) and isinstance(pdoc, dict):
        jneedles = sorted({n for key in ("task_message", "task_metadata", "attack_message", "attack_metadata")
                           for n in (norm(s) for s in leaves(judge.get(key))) if len(n) >= JUDGE_LINK_MIN})
        own = _logged(pdoc)
        sibs = []
        for a in header.get("artifacts") or ():
            path = str((a.get("origin") or {}).get("path", ""))
            if a.get("role") != "primary" and path.endswith(".json") and not path.endswith("judge_result.json"):
                data = _raw(a["sha256"])
                if data is not None:
                    sibs.append(_logged(_strict(data)))
        hays = [own, *sibs]

        def found(n: str, h: list[str]) -> bool:
            return any(n in x for x in h)

        unique = [any(found(n, h) and not any(found(n, o) for j, o in enumerate(hays) if j != i) for n in jneedles)
                  for i, h in enumerate(hays)]
        own_link = "content" if unique[0] else ("other_attempt" if any(unique[1:]) else
                                                ("colocation" if not sibs else "unresolved"))
        aer_link = "other_attempt" if method == "content" and not js else method
        out.c[f"dt07|link_recomputed|own={own_link}|aer={aer_link}"] += 1
        if own_link != aer_link:
            out.bad("DT07", f"judge_link:{aer_link}!={own_link}")
    # re-run linkage
    if isinstance(link, dict) and (link.get("group_size") or 1) > 1:
        if method == "content" and resolved and not js and not issues.get("dtap.unjudged_attempt"):
            out.bad("DT07", "content_link_no_judgement_no_issue")
        if resolved is False and (js or not issues.get("dtap.judge_attempt_unresolved")):
            out.bad("DT07", "unresolved_with_judgements_or_no_issue")
    out.c[f"sa02|unexecuted_tool_call|{bool(issues.get('unexecuted_tool_call'))}"] += 1


def _logged(doc: Any) -> list[str]:
    """The logged content of one attempt as D.16.8 reads it: each step, and the final response (not ``task_info``,
    which is configuration text shared by every attempt). One normalised haystack per item."""
    out = [norm(as_text(step)) for step in (doc.get("trajectory") or [])] if isinstance(doc, dict) else []
    final = ((doc.get("traj_info") or {}) if isinstance(doc, dict) else {}).get("agent_final_response")
    if isinstance(final, str):
        out.append(norm(final))
    return out


# ------------------------------------------------------------------------------------------------ DT03, DT04 (SA03, SA04)
def _haystacks(recs: list[dict[str, Any]], by_id: dict[Any, dict[str, Any]]) -> dict[str, list[tuple[str, str]]]:
    out: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for r in recs:
        if r.get("k") == "message":
            for k, p in enumerate(r.get("parts") or []):
                pid = f"{r['id']}#{k}"
                if p.get("t") == "tool_result":
                    out["tool_output"].append((pid, norm(as_text(p["text"] if "text" in p else p.get("value")))))
                elif r.get("role") == "user" and isinstance(p.get("text"), str):
                    out["user"].append((pid, norm(p["text"])))
                elif r.get("role") == "agent" and r.get("actor") == "agent":
                    if isinstance(p.get("text"), str):
                        out["agent"].append((pid, norm(p["text"])))
                    elif p.get("t") == "tool_call":
                        out["agent"].append((pid, norm(as_text(p.get("args")))))
        elif r.get("k") == "fixture" and r.get("kind") == "tool_definitions":
            out["description"].append((r["id"], norm(as_text(r.get("content")))))
    return out


def marker_check(out: Row, recs: list[dict[str, Any]], by_id: dict[Any, dict[str, Any]], sem: list[dict[str, Any]], prov: Any,
                 split: str, raw: RawRun | None) -> None:
    payloads = {r["id"]: r for r in recs if r.get("k") == "fixture" and r.get("kind") == "injection_payload"}
    hay = _haystacks(recs, by_id)
    if not payloads:
        if any(a.get("type") == "dtap.exposure" for a in sem):
            out.bad("DT04", "exposure_without_payload")
        if split in ("direct", "indirect"):
            out.c["dt04|attacked_runs_without_payload_fixtures"] += 1
        return
    needles = {fid: needles_of(r.get("content")) for fid, r in payloads.items()}
    channel = {fid: str(r.get("vector", "")).split(":", 1)[0] for fid, r in payloads.items()}
    hay_by = {pid: h for rows in hay.values() for pid, h in rows}
    # DT03: every marker's status recomputed
    seen_pairs: set[tuple[str, str]] = set()
    for a in sem:
        t = a.get("type")
        if t not in ("injection_marker", "dtap.description_marker", "dtap.prompt_marker", "dtap.agent_output_marker"):
            continue
        v = a.get("value") or {}
        fid, status, target = v.get("fixture"), v.get("status"), a.get("target")
        if fid not in payloads:
            continue
        seen_pairs.add((str(target), fid))
        if t == "dtap.agent_output_marker" and target == "exec":
            continue  # the final response is not an AER part; counted, not recomputed
        h = hay_by.get(str(target))
        if h is None:
            out.c[f"dt03|{t}|target_not_found"] += 1
            continue
        own = level(needles[fid], h)
        out.c[f"dt03|{t}|sem={status}|own={own}"] += 1
        if own != status:
            out.bad("DT03", f"{t}:{target}:{fid}:{status}!={own}")
    for pid, _h in hay["tool_output"]:
        for fid in payloads:
            if channel[fid] in ("environment", "skill") and (pid, fid) not in seen_pairs:
                out.bad("DT03", f"injection_marker_missing:{pid}:{fid}")
    for pid, _h in hay["user"]:
        for fid in payloads:
            if channel[fid] == "prompt" and (pid, fid) not in seen_pairs:
                out.bad("DT03", f"prompt_marker_missing:{pid}:{fid}")
    # DT04: exposure class per payload fixture
    exposures = [a for a in sem if a.get("type") == "dtap.exposure"]
    by_fx: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for a in exposures:
        by_fx[str((a.get("value") or {}).get("fixture"))].append(a)
    assess = _assess_index(prov)
    for fid in payloads:
        anns = by_fx.get(fid, [])
        if len(anns) != 1:
            out.bad("DT04", f"exposure_count:{fid}:{len(anns)}")
            continue
        a = anns[0]
        cls = (a.get("value") or {}).get("class")
        ch = channel[fid]
        out.c[f"dt04|{split}|{ch}|{cls}"] += 1
        located = {"environment": ("tool_output",), "skill": ("tool_output", "description"), "tool": ("description",),
                   "prompt": ("user",)}.get(ch, ())
        found = {loc: [level(needles[fid], h) for _p, h in hay[loc]] for loc in located}
        agent_lv = [level(needles[fid], h) for _p, h in hay["agent"]]
        if not needles[fid]:
            own = "unmatchable"
        elif loc_hit := next((loc for loc in located if "present" in found[loc]), None):
            own = {"tool_output": "observed_tool_output", "description": "observed_description_log",
                   "user": "observed_user_step"}[loc_hit]
        elif any("ambiguous" in found[loc] for loc in located):
            own = "partial_match"
        elif "present" in agent_lv:
            own = "agent_output_only"
        elif "ambiguous" in agent_lv:
            own = "partial_match"
        elif any(hay[loc] for loc in located):
            own = "logged_absent"
        else:
            own = "configured_only"
        out.c[f"dt04|own={own}|sem={cls}"] += 1
        if own != cls:
            out.bad("DT04", f"class:{fid}:{cls}!={own}")
        if cls in OBSERVED and own not in OBSERVED:
            out.bad("DT04", f"observed_without_logged_match:{fid}")
        if cls == "configured_only" and ch == "environment":
            out.c["dt04|configured_only_on_environment_channel"] += 1
        want = "I" if cls in I_CLASSES else "D"
        if a.get("ev") != want:
            out.bad("DT04", f"sem_ev:{cls}:{a.get('ev')}")
        stmt = assess.get(str(a.get("id")))
        if prov is not None:
            if stmt is None:
                out.bad("DT04", f"no_prov_statement:{cls}")
            else:
                kinds = sorted({k for k, _e in stmt})
                evs = sorted({e for _k, e in stmt})
                out.c[f"dt04|prov|{cls}|bundles={','.join(kinds)}|ev={','.join(evs)}"] += 1
                if kinds != ["assess"] or evs != [want]:
                    out.bad("DT04", f"prov_statement:{cls}:{kinds}:{evs}")
    # SA03, SA04 per execution
    classes = [(channel[f], (by_fx.get(f) or [{}])[0].get("value", {}).get("class")) for f in payloads]
    out.info["exposure"] = sorted({f"{c}|{k}" for c, k in classes})
    observed = any(k in OBSERVED for _c, k in classes)
    unobservable = any(k == "configured_only" for _c, k in classes)
    three = "observed" if observed else ("unobservable_channel" if unobservable else
                                         ("logged_absent" if any(k == "logged_absent" for _c, k in classes) else "other"))
    out.c[f"sa03|{split}|{three}"] += 1
    out.info["sa03"] = three


def _assess_index(prov: Any) -> dict[str, list[tuple[str, str]]]:
    """SEM annotation id -> [(bundle kind, evidence class)] of every PROV entity that carries it."""
    out: dict[str, list[tuple[str, str]]] = defaultdict(list)
    if not isinstance(prov, dict):
        return out
    for iri, body in (prov.get("bundle") or {}).items():
        for _key, attrs in ((body or {}).get("entity") or {}).items():
            if isinstance(attrs, dict) and "apv:annotationId" in attrs:
                out[str(attrs["apv:annotationId"])].append((_bundle_kind(iri), _ev(attrs)))
    for _key, attrs in (prov.get("entity") or {}).items():
        if isinstance(attrs, dict) and "apv:annotationId" in attrs:
            out[str(attrs["apv:annotationId"])].append(("top", _ev(attrs)))
    return out


# ------------------------------------------------------------------------------------------------ DT09, DT13
def semantics_check(out: Row, recs: list[dict[str, Any]], by_id: dict[Any, dict[str, Any]], sem: list[dict[str, Any]], prov: Any,
                    fw: str) -> None:
    roles_by_target: dict[str, list[str]] = {}
    integ: dict[str, str] = {}
    for a in sem:
        if a.get("type") == "role" and isinstance(a.get("value"), list):
            roles_by_target[str(a.get("target"))] = [str(x) for x in a["value"]]
        elif a.get("type") == "integrity":
            integ[str(a.get("target"))] = str(a.get("value"))
    calls: list[tuple[str, str]] = []
    for r in recs:
        if r.get("k") == "message" and r.get("role") == "agent" and r.get("actor") == "agent":
            for k, p in enumerate(r.get("parts") or []):
                if p.get("t") == "tool_call":
                    calls.append((f"{r['id']}#{k}", str(p.get("name"))))
    endorser_parts: set[str] = set()
    for pid, name in calls:
        roles = roles_by_target.get(pid)
        if roles is None:
            out.bad("DT09", f"call_without_role:{pid}")
            continue
        out.c[f"dt09|{fw}|calls"] += 1
        if roles == ["unknown"]:
            out.c[f"dt09|{fw}|unknown_role_calls"] += 1
            out.c[f"dt09|unknown_tool|{fw}|{name[:60]}"] += 1
        for role in roles:
            out.c[f"dt09|role|{role}"] += 1
        if "endorser" in roles:
            endorser_parts.add(pid)
            out.c[f"dt13|endorser|{name[:60]}|{'+'.join(sorted(roles))}"] += 1
            if set(roles) & {"write_sink", "send_sink", "execute_sink"}:
                out.bad("DT13", f"endorser_with_sink:{pid}")
    for r in recs:
        if r.get("k") == "message" and r.get("role") == "tool":
            for k, p in enumerate(r.get("parts") or []):
                if p.get("t") != "tool_result":
                    continue
                pid = f"{r['id']}#{k}"
                v = integ.get(pid)
                out.c[f"dt09|result_integrity|{v}"] += 1
                if (r.get("unk") or {}).get("/parts/0/responds_to") == "ambiguous" and v != "unknown":
                    out.bad("DT09", f"ambiguous_link_not_fail_closed:{pid}")
                if v == "trusted":
                    out.bad("DT09", f"trusted_tool_output:{pid}")
    # DT13: an endorser-only request is never a taint subject
    if prov is not None and endorser_parts:
        subjects: Counter[str] = Counter()
        for iri, body in (prov.get("bundle") or {}).items():
            if _bundle_kind(iri) != "assess":
                continue
            for _k, attrs in ((body or {}).get("entity") or {}).items():
                claim = attrs.get("apv:claim")
                claim = claim.get("$") if isinstance(claim, dict) else claim
                if claim != "apv:PotentiallyInfluencedBy":
                    continue
                subj = attrs.get("apv:subject")
                subj = subj.get("$") if isinstance(subj, dict) else subj
                subjects[str(subj)] += 1
        for pid in endorser_parts:
            roles = roles_by_target.get(pid, [])
            if set(roles) <= {"endorser", "content_source", "neutral", "egress_read"}:
                keys = {f"x:{pid.replace('#', '-')}", f"x:{pid.split('#')[0]}"}
                te = next((r["id"] for r in recs if r.get("k") == "tool_execution" and r.get("call") == pid), None)
                if te:
                    keys.add(f"x:{te}")
                if any(subjects.get(k) for k in keys):
                    out.bad("DT13", f"endorser_taint_subject:{pid}")
                out.c["dt13|endorser_requests_checked"] += 1


# ------------------------------------------------------------------------------------------------ summary
def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    c: Counter[str] = Counter()
    fails: dict[str, Counter[str]] = defaultdict(Counter)
    fail_ex: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        c.update(r["c"])
        for check, details in r["fail"].items():
            for d in details:
                fails[check][re.sub(r"\d+", "N", d.split(":")[0] + ":" + (d.split(":")[1] if ":" in d else ""))[:80]] += 1
            if len(fail_ex[check]) < 10:
                fail_ex[check].append(r["ex"])
    out: dict[str, Any] = {"executions": len(rows), "counters": dict(sorted(c.items())),
                           "failures": {k: dict(v) for k, v in sorted(fails.items())},
                           "failure_examples": dict(sorted(fail_ex.items()))}
    # pairing shares per harness (DT05) against the census
    census = {"claudesdk": 0.295, "googleadk": 0.449}
    share = {}
    for fw in ("openaisdk", "claudesdk", "googleadk", "openclaw"):
        n = c.get(f"dt05|{fw}|results", 0)
        k = c.get(f"dt05|{fw}|results_in_multi_call_batches", 0)
        share[fw] = {"results": n, "in_multi_call_batches": k, "share": round(k / n, 4) if n else None,
                     "wilson95": _wilson(k, n), "census": census.get(fw, 0.0)}
    n = sum(v["results"] for v in share.values())
    k = sum(v["in_multi_call_batches"] for v in share.values())
    share["all"] = {"results": n, "in_multi_call_batches": k, "share": round(k / n, 4) if n else None, "wilson95": _wilson(k, n),
                    "census": 0.086}
    out["dt05_pairing_shares"] = share
    # join tiers (DT06)
    tiers: Counter[str] = Counter()
    for r in rows:
        st, t = (r["info"].get("join") or [None, None])
        if r["info"].get("unit") == "agent_execution":
            tiers[str(t) if st == "joined" else str(st)] += 1
    tot = sum(tiers.values())
    out["dt06_tiers"] = {k: {"n": v, "share": round(v / tot, 4), "wilson95": _wilson(v, tot)} for k, v in sorted(tiers.items())}
    out["dt06_tiers_census"] = {"A": 62419 / 67806, "B": 2899 / 67806, "C": 1693 / 67806, "missing": 786 / 67806,
                                "unparseable": 9 / 67806}
    # semantics (DT09)
    sem_cov = {}
    for fw in ("openaisdk", "claudesdk", "googleadk", "openclaw", "all"):
        if fw == "all":
            n = sum(c.get(f"dt09|{f}|calls", 0) for f in ("openaisdk", "claudesdk", "googleadk", "openclaw"))
            k = sum(c.get(f"dt09|{f}|unknown_role_calls", 0) for f in ("openaisdk", "claudesdk", "googleadk", "openclaw"))
        else:
            n, k = c.get(f"dt09|{fw}|calls", 0), c.get(f"dt09|{fw}|unknown_role_calls", 0)
        sem_cov[fw] = {"calls": n, "unknown": k, "share": round(k / n, 4) if n else None, "wilson95": _wilson(k, n)}
    sem_cov["census_unknown_share"] = 585 / 501228
    out["dt09_unknown_role"] = sem_cov
    # SA04: effective attack success without an observed exposure
    sa04: Counter[str] = Counter()
    for r in rows:
        i = r["info"]
        if i.get("split") in ("direct", "indirect") and i.get("attack_success_effective") is True:
            sa04[f"{i['split']}|{i.get('sa03', 'no_payload_fixtures')}"] += 1
    out["sa04_successes_by_exposure"] = dict(sorted(sa04.items()))
    # R05 (DT12): identical message lists across executions
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        if r["info"].get("traj_digest"):
            groups[r["info"]["traj_digest"]].append(r)
    dup = [g for g in groups.values() if len(g) > 1]
    labels: Counter[str] = Counter()
    for g in dup:
        diff = [k for k in ("fw", "model", "split", "domain", "task_dir", "file")
                if len({str(x["info"].get(k)) for x in g}) > 1]
        labels["differ:" + ",".join(diff)] += 1
        if len({str(x["info"].get("task_success")) for x in g}) > 1:
            labels["task_success_differs"] += 1
    out["dt12_identical_groups"] = {"groups": len(dup), "executions": sum(len(g) for g in dup), "labels": dict(labels),
                                    "examples": [sorted(x["ex"] for x in g)[:3] for g in dup[:5]]}
    return out


# ------------------------------------------------------------------------------------------------ DT01
def env_values(tasks: Path) -> tuple[dict[str, int], set[str], set[str]]:
    """Counts, and the sets of ``env_vars`` keys and string values, of every configuration of the tasks tree (values
    are held in memory only; never printed)."""
    from agentprov.ingest.yamlsafe import safe_load

    c: Counter[str] = Counter()
    keys: set[str] = set()
    values: set[str] = set()
    for dirpath, dirs, files in os.walk(tasks):
        dirs[:] = [d for d in dirs if d != ".git"]
        if "config.yaml" not in files:
            continue
        c["configs"] += 1
        try:
            doc = safe_load(Path(dirpath, "config.yaml").read_bytes().decode("utf-8"))
        except Exception:  # noqa: BLE001 - counted (the duplicate-key file)
            c["configs_unparsed"] += 1
            continue
        found = False
        stack = [doc]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                for k, v in node.items():
                    if k == "env_vars" and isinstance(v, dict):
                        found = True
                        for ek, ev in v.items():
                            keys.add(str(ek))
                            c["entries"] += 1
                            if ev is not None and not isinstance(ev, (dict, list)):
                                values.add(str(ev))
                    else:
                        stack.append(v)
            elif isinstance(node, list):
                stack.extend(node)
        c["configs_with_env_vars"] += found
    return dict(c), keys, values


_TOKEN = re.compile(rb"[A-Za-z0-9_\-.@:/+=%~]+")
_K = 6


def _grep_files(patterns: list[bytes], files: list[Path], work: Path) -> dict[Path, Counter[bytes]]:
    """Occurrences of each fixed byte string of ``patterns`` in each file (in memory; never printed). Token-like
    patterns are found through an index of their first six bytes over the distinct token runs of a file (a substring of
    a token run is found wherever it starts); any other pattern by ``bytes.count``. ``work`` is unused (kept for the
    call signature)."""
    del work
    tokenish = sorted({p for p in patterns if len(p) >= _K and _TOKEN.fullmatch(p)})
    other = sorted(set(patterns) - set(tokenish))
    index: dict[bytes, list[bytes]] = defaultdict(list)
    for p in tokenish:
        index[p[:_K]].append(p)
    out: dict[Path, Counter[bytes]] = {}
    for path in files:
        data = path.read_bytes()
        present: set[bytes] = set()
        for tok in set(_TOKEN.findall(data)):
            for i in range(len(tok) - _K + 1):
                for p in index.get(tok[i:i + _K], ()):
                    if tok.startswith(p, i):
                        present.add(p)
        present.update(p for p in other if p and p in data)
        if present:
            out[path] = Counter({p: data.count(p) for p in present})
    return out


def envvars(corpus: Path, tasks: Path, extra: list[Path], work: Path, min_len: int) -> dict[str, Any]:
    """DT01: ``env_vars`` keys and values in derived output; every hit attributed (run content or not)."""
    root = corpus if (corpus / "executions.jsonl").exists() else corpus.with_name(corpus.name + ".partial")
    counts, keys, values = env_values(tasks)
    long_values = sorted(v for v in values if len(v) >= min_len)
    forms: dict[bytes, str] = {}
    for v in long_values:
        forms[v.encode("utf-8")] = v
        esc = json.dumps(v, ensure_ascii=False)[1:-1].encode("utf-8")
        forms.setdefault(esc, v)
    key_forms = sorted({b'"env_vars"', b"env_vars"})
    rows = [json.loads(x) for x in (root / "executions.jsonl").read_bytes().splitlines() if x]
    owner: dict[Path, str] = {}
    raws: dict[str, list[str]] = {}
    for r in rows:
        head = json.loads((root / r["paths"]["aer"]).read_bytes().split(b"\n", 1)[0])
        raws[r["ex"]] = [a["sha256"] for a in head.get("artifacts") or () if not str((a.get("origin") or {}).get("path", "")).endswith(".yaml")]
        owner[root / r["paths"]["aer"]] = r["ex"]
        for rel in (r["paths"].get("sem") or {}).values():
            owner[root / rel] = r["ex"]
        for forms_ in (r["paths"].get("prov") or {}).values():
            for rel in (forms_ or {}).values():
                owner[root / rel] = r["ex"]
    corpus_files = [p for p in (root / "executions.jsonl", root / "register.jsonl", root / "corpus.json",
                                root / "raw" / "origins.jsonl") if p.exists()]
    corpus_files += sorted((root / "validation").glob("*")) if (root / "validation").exists() else []
    derived = sorted(owner) + corpus_files
    extra_files = [p for e in extra for p in ([e] if e.is_file() else sorted(e.rglob("*"))) if p.is_file()]
    res: dict[str, Any] = {"tasks": counts, "distinct_keys": len(keys), "distinct_values": len(values),
                           "values_searched": len(long_values), "min_len": min_len, "derived_files": len(derived),
                           "extra_files": len(extra_files)}
    _ROOT_SET(root)
    for label, patterns in (("values", sorted(forms)), ("key_literal", key_forms), ("key_names", sorted(k.encode() for k in keys if len(k) >= 6))):
        hits = _grep_files(patterns, derived + extra_files, work)
        c: Counter[str] = Counter()
        unexplained: list[str] = []
        for path, found in hits.items():
            where = owner.get(path)
            kind = ("extra" if path in extra_files else ("corpus_file:" + path.name if where is None else
                                                          ("aer" if "/aer/" in str(path) else "sem" if "/sem/" in str(path) else "prov")))
            c[f"files|{kind}"] += 1
            raw_blobs = [_raw(s) or b"" for s in raws.get(where, [])] if where else []
            for value_bytes, n in found.items():
                if any(value_bytes in b for b in raw_blobs):
                    c[f"occurrences|{kind}|in_own_raw_run_or_judge"] += n
                else:
                    c[f"occurrences|{kind}|not_in_own_raw"] += n
                    if len(unexplained) < 20:
                        unexplained.append(f"{where or path.name}|{kind}|{hashlib.sha256(value_bytes).hexdigest()[:12]}")
        res[label] = {"counts": dict(sorted(c.items())), "not_in_own_raw_examples": unexplained}
    return res


def _ROOT_SET(root: Path) -> None:  # noqa: N802 - sets the module root for _raw outside the pool
    global _ROOT
    _ROOT = root


# ------------------------------------------------------------------------------------------------ DT13 (staging runs)
def endorser_runs(runs: Path, tasks: Path, limit: int) -> dict[str, Any]:
    """DT13 on runs that call an ``endorser`` tool: the runs of the pinned tree whose agent steps call a
    ``verify_*`` tool are mapped, annotated and derived in memory through the product pipeline (the reader's auxiliary
    plan; nothing is written), and :func:`semantics_check` runs on them. Up to ``limit`` runs per harness."""
    from agentprov.adapters.dtap.dialect import DtapTrajectoryReader
    from agentprov.adapters.runner import aer_bytes, map_artefact_total
    from agentprov.adapters.profiles import load_profile
    from agentprov.adapters.runner.importer import _AuxListing, git_blob_sha1  # noqa: PLC2701
    from agentprov.adapters.semantics_profiles import load_semantics_profile
    from agentprov.adapters.types import Origin
    from agentprov.aer.reader import load_aer_bytes
    from agentprov.prov.engine import derive
    from agentprov.sem.engine import annotate

    profile = load_semantics_profile("dtap.tools", 1)
    pins = {p["role"]: p for p in load_profile("dtap-bench").data["source"]["pins"]}

    def origin(role: str, path: str, raw: bytes) -> Any:
        return Origin.git(str(pins[role]["repo"]), str(pins[role]["commit"]), path, git_blob_sha1(raw))

    chosen: dict[str, list[str]] = defaultdict(list)
    for dirpath, dirs, files in os.walk(runs):
        dirs[:] = sorted(d for d in dirs if d != ".git")
        rel_dir = Path(dirpath).relative_to(runs).as_posix()
        if "/travel/" not in f"/{rel_dir}/":
            continue
        fw = rel_dir.split("/", 1)[0]
        for name in sorted(files):
            if not name.endswith(".json") or name == "judge_result.json" or len(chosen[fw]) >= limit:
                continue
            data = Path(dirpath, name).read_bytes()
            if b"verify_" not in data:
                continue
            try:
                doc = _strict(data)
            except Exception:  # noqa: BLE001 - not a trajectory (LFS pointer): skipped
                continue
            steps = doc.get("trajectory") if isinstance(doc, dict) else None
            if any(isinstance(s, dict) and s.get("role") == "agent" and re.search(r"verify_(manager_access|promo_eligibility|refund_eligibility)$",
                                 str((s.get("metadata") or {}).get("tool_name", ""))) for s in steps or []):
                chosen[fw].append(f"{rel_dir}/{name}")
    labels = [x for fw in sorted(chosen) for x in chosen[fw]]
    run_labels = []
    for dirpath, _dirs, files in os.walk(runs):
        rel_dir = Path(dirpath).relative_to(runs).as_posix()
        if "/travel/" in f"/{rel_dir}/":
            run_labels += [f"{rel_dir}/{f}" for f in files]
    task_labels = [Path(dp, "config.yaml").relative_to(tasks).as_posix() for dp, _d, fs in os.walk(tasks)
                   if "config.yaml" in fs and "/travel/" in f"/{Path(dp).relative_to(tasks).as_posix()}/"]
    listing = _AuxListing(run_labels, {"tasks": task_labels})
    reader = DtapTrajectoryReader()
    rows: list[dict[str, Any]] = []
    for label in labels:
        out = Row(label)
        plan = reader.auxiliary_for(label, listing)
        aux: list[dict[str, Any]] = []
        blobs: dict[str, bytes] = {}
        for role, ref in sorted(plan.items()):
            if role.startswith("copy:"):
                continue
            path = (tasks / ref.removeprefix("tasks:")) if ref.startswith("tasks:") else (runs / ref)
            raw = path.read_bytes()
            aux.append({"role": role, "label": ref, "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw),
                        "origin": origin("tasks" if ref.startswith("tasks:") else "runs", ref.removeprefix("tasks:"), raw).to_json()})
            blobs[role] = raw
        data = (runs / label).read_bytes()
        outcome, _unit = map_artefact_total(data, origin("runs", label, data), profile_id="dtap-bench",
                                            auxiliary=aux, auxiliary_bytes=blobs)
        doc = load_aer_bytes(aer_bytes(outcome)[0])
        sem = annotate(doc, profile)
        prov = json.loads(derive(doc, [sem], sem_profiles={(profile.id, profile.version): profile}).prov_json)
        recs = list(doc.records)
        semantics_check(out, recs, {r.get("id"): r for r in recs}, list(sem.annotations), prov, label.split("/", 1)[0])
        rows.append(out.to_json())
    c: Counter[str] = Counter()
    for r in rows:
        c.update({k: v for k, v in r["c"].items() if k.startswith(("dt13", "dt09|role|endorser")) or "|fail" in k})
    return {"runs": len(rows), "by_harness": {k: len(v) for k, v in sorted(chosen.items())}, "counters": dict(sorted(c.items())),
            "failures": [r["fail"] for r in rows if r["fail"]]}


# ------------------------------------------------------------------------------------------------ DT10
def inventory(corpus: Path, tree: Path) -> dict[str, Any]:
    """Every file of the input tree: the primary of an execution, an auxiliary artefact, or a register row."""
    root = corpus if (corpus / "executions.jsonl").exists() else corpus.with_name(corpus.name + ".partial")
    rows = [json.loads(x) for x in (root / "executions.jsonl").read_bytes().splitlines() if x]
    primary: set[str] = set()
    aux: set[str] = set()
    for r in rows:
        head = json.loads((root / r["paths"]["aer"]).read_bytes().split(b"\n", 1)[0])
        for a in head.get("artifacts") or ():
            path = (a.get("origin") or {}).get("path")
            (primary if a.get("role") == "primary" else aux).add(str(path))
    reg: dict[str, str] = {}
    for x in (root / "register.jsonl").read_bytes().splitlines():
        if x:
            g = json.loads(x)
            path = (g.get("subject") or {}).get("path")
            if path:
                reg.setdefault(str(path), f"{g.get('code')}|{g.get('detail', '')[:40]}")
    c: Counter[str] = Counter()
    unaccounted: list[str] = []
    for dirpath, _dirs, files in os.walk(tree):
        for name in files:
            rel = Path(dirpath, name).relative_to(tree).as_posix()
            if rel in primary:
                c["primary"] += 1
                if rel in reg:
                    c["primary_and_register:" + reg[rel].split("|")[0]] += 1
            elif rel in aux:
                c["auxiliary:" + ("judge" if name == "judge_result.json" else "other")] += 1
            elif rel in reg:
                code, detail = reg[rel].split("|", 1)
                c[f"register:{code}:{re.sub(r'[^a-z_.]', '', detail.split(' ')[0])[:30]}"] += 1
            else:
                c["unaccounted"] += 1
                unaccounted.append(hashlib.sha256(rel.encode()).hexdigest()[:16])
    return {"executions": len(rows), "files": dict(sorted(c.items())), "unaccounted_path_digests": unaccounted[:50]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="mode", required=True)
    s = sub.add_parser("scan")
    s.add_argument("--corpus", required=True, type=Path)
    s.add_argument("--out", required=True, type=Path)
    s.add_argument("--jobs", type=int, default=4)
    s.add_argument("--limit", type=int, default=0)
    m = sub.add_parser("summary")
    m.add_argument("rows", type=Path)
    m.add_argument("--json", type=Path)
    v = sub.add_parser("inventory")
    v.add_argument("--corpus", required=True, type=Path)
    v.add_argument("--input", required=True, type=Path)
    v.add_argument("--json", type=Path)
    e = sub.add_parser("envvars")
    e.add_argument("--corpus", required=True, type=Path)
    e.add_argument("--tasks", required=True, type=Path)
    e.add_argument("--extra", type=Path, nargs="*", default=[])
    e.add_argument("--work", type=Path, required=True, help="scratch directory for the pattern file (outside the repository)")
    e.add_argument("--min-len", type=int, default=8)
    e.add_argument("--json", type=Path)
    n = sub.add_parser("endorser")
    n.add_argument("--runs", required=True, type=Path)
    n.add_argument("--tasks", required=True, type=Path)
    n.add_argument("--limit", type=int, default=10, help="runs per harness")
    n.add_argument("--json", type=Path)
    a = ap.parse_args(argv)
    if a.mode == "endorser":
        data = endorser_runs(a.runs, a.tasks, a.limit)
        text = json.dumps(data, indent=1, sort_keys=True)
        if a.json:
            a.json.write_text(text + "\n", encoding="utf-8")
        print(text)
        return 0
    if a.mode == "envvars":
        data = envvars(a.corpus, a.tasks, a.extra, a.work, a.min_len)
        text = json.dumps(data, indent=1, sort_keys=True)
        if a.json:
            a.json.write_text(text + "\n", encoding="utf-8")
        print(text)
        return 0
    if a.mode == "scan":
        root = a.corpus if (a.corpus / "executions.jsonl").exists() else a.corpus.with_name(a.corpus.name + ".partial")
        lines = [x for x in (root / "executions.jsonl").read_bytes().split(b"\n") if x]
        if a.limit:
            lines = lines[: a.limit]
        a.out.parent.mkdir(parents=True, exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as fh, Pool(a.jobs, initializer=_init, initargs=(str(root),)) as pool:
            for res in pool.imap(job, lines, chunksize=4):
                fh.write(json.dumps(res, sort_keys=True) + "\n")
        print(f"scanned {len(lines)}", file=sys.stderr)
        return 0
    if a.mode == "summary":
        rows = [json.loads(x) for x in a.rows.read_text(encoding="utf-8").splitlines() if x]
        data = summary(rows)
    else:
        data = inventory(a.corpus, a.input)
    text = json.dumps(data, indent=1, sort_keys=True)
    if a.json:
        a.json.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
