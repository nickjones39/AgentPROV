# ruff: noqa: B007, B905, UP031  (analysis script, committed as run; style-only)
"""Examination 2, per-execution census scanner (read-only).

For every row of ``executions.jsonl`` of one corpus it reads the AER, SEM and PROV files and runs, independently of the
code under test (see ``exam2_lib``):

* X01 strict re-parse, X02 second-JCS byte comparison, X03 number/key-order census, X05 JSONL framing;
* U01-U14 string-content screens (byte prefilter, then a decoded walk with normalised pointers);
* A01 tool-call argument census, A02 finish-reason census, A03 empty assistant turns (role ``assistant`` or DTap's
  ``agent``: ``tools/analysis/message_roles.py``), A05 payload-form histogram against the SEM injection markers;
* P01-P11 PROV checks: event-ordering (strict cycles, Constraint 42), dependency/communication/derivation/specialisation
  cycles, C51, C26/C24, normal-form generator expansion and lints, dangling references, shared top-level statements for
  the cross-document consistency check, mentionOf, graph metrics, PN_LOCAL, multi-valued keys.

Output: one JSON line per execution (counts, normalised pointers, ids, sha256 prefixes; never corpus text) to
``--out``. ``exam2_merge.py`` aggregates the lines.

Usage: ``python tools/analysis2/exam2_scan.py --corpus DIR --out OUT.jsonl [--jobs 4] [--limit N]``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from multiprocessing import Pool
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))
from exam2_lib import (  # noqa: E402
    B, ELEMENTS, FORMALS, G, NODE_ARGS, P, JcsError, StrictError, classify_json_string, jcs, looks_json,
    nontrivial_cycles, norm_tokens, scc, sha16, strict_parse, union_find_components,
)
from message_roles import is_assistant  # noqa: E402  (assistant + DTap agent: one shared grouping)

_ROOT: Path | None = None
_YAML: Any = None
_YESC: Any = None
EXEMPLARS = 3


def _init(root: str) -> None:
    global _ROOT, _YAML, _YESC
    _ROOT = Path(root)
    from agentprov.adapters.agentdojo.hooks.autodojo import yaml_escape
    from agentprov.ingest.yamlsafe import safe_load

    _YAML = safe_load
    _YESC = yaml_escape


class Acc:
    """Per-execution accumulator."""

    def __init__(self, ex: str) -> None:
        self.ex = ex
        self.c: Counter = Counter()  # flat counters "group|key"
        self.hits: Counter = Counter()  # (pattern, kind, pointer) -> strings
        self.ex_ptr: dict[str, list] = {}

    def hit(self, pattern: str, kind: str, ptr: str, s: str) -> None:
        key = f"{pattern}|{kind}|{ptr}"
        self.hits[key] += 1
        lst = self.ex_ptr.setdefault(key, [])
        if len(lst) < 1:
            lst.append(sha16(s))


# ------------------------------------------------------------------------------------------------ bytes-level
def byte_checks(acc: Acc, kind: str, data: bytes) -> set[str]:
    for name, rx in B.items():
        n = len(rx.findall(data))
        if n:
            acc.c[f"bytes|{kind}|{name}"] += n
            acc.c[f"bytesfiles|{kind}|{name}"] += 1
    active: set[str] = set()
    for gname, (rx, pats) in G.items():
        if rx.search(data):
            active.update(pats)
            acc.c[f"prefilter|{kind}|{gname}"] += 1
    return active


def walk_strings(acc: Acc, kind: str, node: Any, base: list[str], active: set[str]) -> None:
    """Decoded walk of keys and values; applies only the patterns the byte prefilter activated."""
    pats = [(n, P[n]) for n in sorted(active) if n in P]
    want_json = "@JSON_IN_STRING" in active
    if not pats and not want_json:
        return
    stack: list[tuple[Any, list[str]]] = [(node, base)]
    while stack:
        n, toks = stack.pop()
        if isinstance(n, str):
            _apply(acc, kind, toks, n, pats, want_json)
        elif isinstance(n, dict):
            for k, v in n.items():
                _apply(acc, kind, toks + [k, "#key"], k, pats, False)
                stack.append((v, toks + [k]))
        elif isinstance(n, list):
            for i, v in enumerate(n):
                stack.append((v, toks + [str(i)]))


def _apply(acc: Acc, kind: str, toks: list[str], s: str, pats: list, want_json: bool) -> None:
    ptr = None
    for name, rx in pats:
        if rx.search(s):
            if ptr is None:
                ptr = norm_tokens(toks)
            acc.hit(name, kind, ptr, s)
            if name == "LIT_ESC" and "\\n" in s and "\n" not in s:
                acc.hit("WHOLLY_ESCAPED", kind, ptr, s)
    if want_json and looks_json(s):
        if ptr is None:
            ptr = norm_tokens(toks)
        cls, sub = classify_json_string(s, _YAML)
        acc.hit(f"JSONSTR:{cls}:{sub}", kind, ptr, s)


# ------------------------------------------------------------------------------------------------ JSONL files
def check_jsonl(acc: Acc, kind: str, data: bytes) -> list[Any]:
    """X01/X02/X05 on a JSONL file; returns the parsed records (None for an unparseable line)."""
    acc.c[f"files|{kind}"] += 1
    if not data.endswith(b"\n"):
        acc.c[f"framing|{kind}|no_final_lf"] += 1
    if b"\r" in data:
        acc.c[f"framing|{kind}|raw_cr"] += 1
    lines = data.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    out: list[Any] = []
    stats: Counter = Counter()
    for line in lines:
        acc.c[f"records|{kind}"] += 1
        if not line:
            acc.c[f"framing|{kind}|blank_line"] += 1
            out.append(None)
            continue
        flags: Counter = Counter()
        try:
            obj = strict_parse(line, flags)
        except StrictError as exc:
            acc.c[f"strict|{kind}|{exc.code}"] += 1
            out.append(None)
            continue
        for f, n in flags.items():
            acc.c[f"strictflag|{kind}|{f}"] += n
        try:
            canon = jcs(obj, stats)
            if canon != line:
                acc.c[f"jcs|{kind}|mismatch"] += 1
        except JcsError as exc:
            acc.c[f"jcs|{kind}|error_{exc.code}"] += 1
        out.append(obj)
    for f, n in stats.items():
        acc.c[f"num|{kind}|{f}"] += n
    return out


# ------------------------------------------------------------------------------------------------ pointers (U12)
def ptr_check(acc: Acc, kind: str, field: str, value: Any) -> None:
    vals = value if isinstance(value, list) else [value]
    for v in vals:
        if not isinstance(v, str):
            continue
        p = v.split("#", 1)[1] if "#" in v else v
        for tok in p.split("/"):
            if not tok:
                continue
            if tok.isdigit() and not tok.isascii():
                acc.c[f"ptr|{kind}|{field}|nonascii_digit"] += 1
            elif tok.isascii() and tok.isdigit() and len(tok) > 1 and tok[0] == "0":
                acc.c[f"ptr|{kind}|{field}|leading_zero"] += 1
            elif not tok.isascii():
                acc.c[f"ptr|{kind}|{field}|nonascii_token"] += 1
        acc.c[f"ptr|{kind}|{field}|checked"] += 1


_SCRIPT_WORD = re.compile(r"[A-Z]+")


def name_check(acc: Acc, field: str, s: Any) -> None:
    if not isinstance(s, str):
        return
    acc.c[f"names|{field}|checked"] += 1
    if not s.isascii():
        acc.c[f"names|{field}|non_ascii"] += 1
        if unicodedata.normalize("NFC", s) != s:
            acc.c[f"names|{field}|not_nfc"] += 1
        scripts = {unicodedata.name(ch, "?").split(" ")[0] for ch in s if ch.isalpha()}
        if len(scripts) > 1:
            acc.c[f"names|{field}|mixed_script"] += 1
    if s != s.strip() or any(ord(ch) < 0x20 for ch in s):
        acc.c[f"names|{field}|ws_or_control"] += 1


# ------------------------------------------------------------------------------------------------ AER
def aer_semantics(acc: Acc, recs: list[Any], out: dict[str, Any]) -> dict[str, Any]:
    """A01-A03, U01/U12/U13 targeted fields. Returns fixtures and tool texts for A05."""
    fixtures: dict[str, Any] = {}
    texts: dict[str, Any] = {}
    model = None
    assistants: list[tuple[str, bool]] = []
    for r in recs:
        if not isinstance(r, dict):
            continue
        k = r.get("k")
        for key in (r.get("unk") or {}):
            ptr_check(acc, "aer", "unk_key", key)
        for key in (r.get("evf") or {}):
            ptr_check(acc, "aer", "evf_key", key)
        for loc in r.get("src") or ():
            if isinstance(loc, dict) and "p" in loc:
                ptr_check(acc, "aer", "src_p", loc["p"])
        lex = (r.get("ext") or {}).get("lex") if isinstance(r.get("ext"), dict) else None
        if isinstance(lex, dict):
            for key in (lex.get("ord") or {}):
                ptr_check(acc, "aer", "lex_ord", key)
            for item in lex.get("flt") or ():
                ptr_check(acc, "aer", "lex_flt", item)
            acc.c["x03|lex_flt_pointers"] += len(lex.get("flt") or ())
            acc.c["x03|lex_ord_objects"] += len(lex.get("ord") or {})
        if k == "execution":
            task = r.get("task") or {}
            for f in ("suite", "task_id", "attack_id", "attack_target_id", "defense_id", "benchmark"):
                name_check(acc, f"task.{f}", task.get(f))
            out["profile"] = f"{(r.get('profile') or {}).get('id')}@{(r.get('profile') or {}).get('version')}"
        elif k == "actor":
            m = r.get("model")
            if isinstance(m, dict):
                for f in ("requested", "served", "provider"):
                    name_check(acc, f"model.{f}", m.get(f))
                if r.get("kind") == "llm_agent" and model is None:
                    model = m.get("served") or m.get("requested")
            name_check(acc, f"actor_name.{r.get('kind')}", r.get("name"))
        elif k == "fixture":
            fixtures[r.get("id")] = r.get("content")
        elif k == "model_call":
            for key in r:
                if "finish" in key or "stop" in key:
                    v = r[key]
                    acc.c[f"a02|finish|{key}|{v if isinstance(v, str) and len(v) < 40 else type(v).__name__}"] += 1
            unk = r.get("unk") or {}
            for key, reason in unk.items():
                if "finish" in key or "stop" in key:
                    acc.c[f"a02|finish_unk|{key}|{reason}"] += 1
        elif k == "tool_execution":
            name_check(acc, "tool_execution.name", r.get("name"))
        elif k == "message":
            role = r.get("role")
            parts = r.get("parts") or []
            if is_assistant(role):  # A01/A03 read model output: role assistant, or DTap's verbatim agent
                has_call = False
                nonempty = False
                for i, p in enumerate(parts):
                    if not isinstance(p, dict):
                        continue
                    t = p.get("t")
                    if t == "tool_call":
                        has_call = True
                        _args(acc, p)
                    elif isinstance(p.get("text"), str) and p.get("text").strip():
                        nonempty = True
                    elif isinstance(p.get("text"), dict):
                        nonempty = True
                    elif t not in ("text",):
                        nonempty = True
                assistants.append((r.get("id"), has_call or nonempty))
                if not has_call and not nonempty:
                    acc.c["a03|empty_assistant_turn"] += 1
            for i, p in enumerate(parts):
                if isinstance(p, dict) and p.get("t") == "tool_result":
                    texts[f"{r.get('id')}#{i}"] = p.get("text")
    if assistants:
        acc.c["a03|executions_with_assistant"] += 1
        if not assistants[-1][1]:
            acc.c["a03|empty_final_assistant"] += 1
        if not any(x[1] for x in assistants):
            acc.c["a03|all_assistant_empty"] += 1
    out["model"] = model if isinstance(model, str) and len(model) < 120 else None
    return {"fixtures": fixtures, "texts": texts}


_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_.\-]{0,127}")


def _args(acc: Acc, p: dict[str, Any]) -> None:
    name = p.get("name")
    name_check(acc, "tool_call.name", name)
    tool = name if isinstance(name, str) and _IDENT.fullmatch(name) else "<nonident>"
    if tool == "<nonident>":
        acc.c["a01|name_nonident"] += 1
    args = p.get("args")
    if isinstance(args, dict) and set(args) == {"$lit"}:
        args = args["$lit"]
        acc.c["a01|args_lit_wrapped"] += 1
    if isinstance(args, dict) and set(args) == {"$utf16"}:
        acc.c["a01|args_utf16"] += 1
    t = type(args).__name__
    acc.c[f"a01|args_type|{t}"] += 1
    if isinstance(args, dict):
        acc.c[f"a01k|{tool}|{','.join(sorted(args))}"] += 1
        for key, v in args.items():
            vt = type(v).__name__
            if isinstance(v, dict) and len(v) == 1 and next(iter(v)).startswith("$"):
                vt = "wrap" + next(iter(v))
            acc.c[f"a01t|{tool}|{key if _IDENT.fullmatch(key) else '~'}|{vt}"] += 1
            if isinstance(v, str) and looks_json(v) and v.strip()[:1] in "{[":
                cls, _sub = classify_json_string(v, _YAML)
                acc.c[f"a01|arg_value_jsonlike|{cls}"] += 1
    elif isinstance(args, str):
        cls, sub = classify_json_string(args, _YAML) if looks_json(args) else ("not_jsonlike", "")
        acc.c[f"a01|args_string|{cls}"] += 1
    raw = p.get("args_raw")
    if isinstance(raw, str):
        acc.c["a01|args_raw_present"] += 1
        try:
            fl: Counter = Counter()
            same = jcs(strict_parse(raw.encode(), fl)) == jcs(args)
            acc.c[f"a01|args_raw_vs_args|{'equal' if same else 'differs'}"] += 1
        except (StrictError, JcsError):
            acc.c["a01|args_raw_vs_args|raw_unparsed"] += 1


def marker_forms(acc: Acc, sem_recs: list[Any], ctx: dict[str, Any], out: dict[str, Any]) -> None:
    """A05: which spellings of each fixture payload occur in the marked tool text, against the SEM marker status."""
    fixtures, texts = ctx["fixtures"], ctx["texts"]
    if not fixtures:
        return
    any_present = False
    any_found = False
    yaml_cache: dict[Any, str | None] = {}
    for r in sem_recs:
        if not isinstance(r, dict) or r.get("type") != "injection_marker":
            continue
        v = r.get("value") or {}
        status, norm, fx = v.get("status"), v.get("normaliser"), v.get("fixture")
        payload = fixtures.get(fx)
        text = texts.get(r.get("target"))
        if not isinstance(payload, str) or not isinstance(text, str):
            acc.c[f"a05|{status}|{norm}|payload_or_text_not_string"] += 1
            continue
        forms = _forms(payload)
        found = sorted(name for name, f in forms.items() if f and f in text)
        ws_p = " ".join(payload.split())
        if not found:
            ws_t = " ".join(text.split())
            if ws_p and ws_p in ws_t:
                found = ["ws_collapsed"]
        if not found:
            target = r.get("target")
            if target not in yaml_cache:
                yaml_cache[target] = _yaml_strings(text)
            ytext = yaml_cache[target]
            if ytext is not None and ws_p and ws_p in " ".join(ytext.split()):
                found = ["yaml_decoded"]
            elif ytext is None:
                found = ["none_yaml_unparsable"]
        if found == ["none_yaml_unparsable"]:
            found_flag = False
        else:
            found_flag = bool(found)
        key = "+".join(found) if found else "none"
        acc.c[f"a05|{status}|{norm}|{key}"] += 1
        if status == "present":
            any_present = True
        if found_flag:
            any_found = True
        if status == "present" and not found_flag:
            out.setdefault("a05_present_nofound", []).append(r.get("target"))
        if status != "present" and found_flag:
            out.setdefault("a05_found_notpresent", []).append(r.get("target"))
    acc.c[f"a05x|present={any_present}|found={any_found}"] += 1


def _yaml_strings(text: str) -> str | None:
    """All string scalars of ``text`` read as YAML (the project's safe loader), joined; None if it is not YAML."""
    try:
        v = _YAML(text)
    except Exception:  # noqa: BLE001 - not YAML (or over a limit): recorded as such
        return None
    parts: list[str] = []
    stack = [v]
    while stack:
        n = stack.pop()
        if isinstance(n, str):
            parts.append(n)
        elif isinstance(n, dict):
            stack.extend(n.keys())
            stack.extend(n.values())
        elif isinstance(n, list):
            stack.extend(n)
        elif n is not None:
            parts.append(str(n))
    return "\n".join(parts)


def _forms(p: str) -> dict[str, str]:
    j = json.dumps(p)[1:-1]
    return {"verbatim": p, "yaml_escape": _YESC(p), "json_ascii": j, "json_utf8": json.dumps(p, ensure_ascii=False)[1:-1],
            "py_repr": repr(p)[1:-1], "json_json": json.dumps(j)[1:-1]}


# ------------------------------------------------------------------------------------------------ PROV
def bundle_kind(name: str) -> str:
    m = re.match(r"[a-z]+:bundle\.([a-z]+)\.", name)
    return m.group(1) if m else "other"


def statements(container: dict[str, Any], acc: Acc, where: str) -> list[tuple[str, str, dict[str, Any]]]:
    out = []
    for sec, items in container.items():
        if sec in ("prefix", "bundle") or not isinstance(items, dict):
            continue
        for key, attrs in items.items():
            if isinstance(attrs, list):
                acc.c[f"p11|multi_valued|{where}|{sec}"] += 1
                for a in attrs:
                    if isinstance(a, dict):
                        out.append((sec, key, a))
            elif isinstance(attrs, dict):
                out.append((sec, key, attrs))
    return out


def _qn(v: Any) -> list[str]:
    if isinstance(v, str):
        return [v]
    if isinstance(v, list):
        return [x for x in v if isinstance(x, str)]
    return []


def _types(attrs: dict[str, Any]) -> list[str]:
    t = attrs.get("prov:type")
    vals = t if isinstance(t, list) else [t]
    return sorted(x.get("$") for x in vals if isinstance(x, dict) and isinstance(x.get("$"), str))


def node_class(sec: str, attrs: dict[str, Any]) -> str:
    ts = _types(attrs)
    apv = [t for t in ts if t.startswith("apv:")]
    if apv:
        return apv[0]
    return ts[0] if ts else sec


def event_graph_violations(sts: list[tuple[str, str, dict[str, Any]]], acts: set[str]) -> tuple[int, int]:
    """(strict_cycle_sccs, nonstrict_cycle_sccs) of the PROV event graph built from the relations (no times needed)."""
    edges: list[tuple[Any, Any, bool]] = []
    act_seen = set(acts)
    for sec, _k, a in sts:
        if sec == "used":
            act, ent = a.get("prov:activity"), a.get("prov:entity")
            if act and ent:
                u = ("u", act, ent)
                edges += [(("s", act), u, False), (u, ("e", act), False), (("g", ent), u, False)]
                act_seen.add(act)
        elif sec == "wasGeneratedBy":
            act, ent = a.get("prov:activity"), a.get("prov:entity")
            if act and ent:
                edges += [(("s", act), ("g", ent), False), (("g", ent), ("e", act), False)]
                act_seen.add(act)
        elif sec == "wasInformedBy":
            a2, a1 = a.get("prov:informed"), a.get("prov:informant")
            if a1 and a2:
                edges.append((("s", a1), ("e", a2), False))
                act_seen.update((a1, a2))
        elif sec == "wasStartedBy":
            act, trig, starter = a.get("prov:activity"), a.get("prov:trigger"), a.get("prov:starter")
            if act and trig:
                edges.append((("g", trig), ("s", act), False))
                act_seen.add(act)
            if trig and starter:  # Inference 9: the trigger was generated by the starter
                edges += [(("s", starter), ("g", trig), False), (("g", trig), ("e", starter), False)]
                act_seen.add(starter)
        elif sec == "wasDerivedFrom":
            e2, e1, act = a.get("prov:generatedEntity"), a.get("prov:usedEntity"), a.get("prov:activity")
            if e2 and e1:
                edges.append((("g", e1), ("g", e2), True))  # Constraint 42: strict
                if act:  # Inference 11: generation of e2 by act, usage of e1 by act
                    u = ("u", act, e1)
                    edges += [(("s", act), u, False), (u, ("e", act), False), (("g", e1), u, False),
                              (("s", act), ("g", e2), False), (("g", e2), ("e", act), False), (u, ("g", e2), False)]
                    act_seen.add(act)
        elif sec in ("specializationOf", "mentionOf"):
            spec, gen = a.get("prov:specificEntity"), a.get("prov:generalEntity")
            if spec and gen:
                edges.append((("g", gen), ("g", spec), False))
    for act in act_seen:
        edges.append((("s", act), ("e", act), False))
    adj: dict[Any, list[Any]] = defaultdict(list)
    nodes: set[Any] = set()
    strict_self = 0
    for x, y, st in edges:
        if x == y:
            if st:
                strict_self += 1
            continue
        adj[x].append(y)
        nodes.update((x, y))
    comps = scc(sorted(nodes, key=str), adj)
    member = {}
    for i, c in enumerate(comps):
        for v in c:
            member[v] = i
    strict = set()
    nonstrict = 0
    for i, c in enumerate(comps):
        if len(c) > 1:
            nonstrict += 1
    for x, y, st in edges:
        if st and x != y and member.get(x) == member.get(y):
            strict.add(member[x])
    return len(strict) + strict_self, nonstrict


def prov_checks(acc: Acc, doc: dict[str, Any], out: dict[str, Any]) -> None:
    top = {k: v for k, v in doc.items() if k not in ("bundle", "prefix")}
    prefixes = doc.get("prefix") or {}
    for p, iri in prefixes.items():
        if isinstance(iri, str) and not iri.endswith(("#", "/")):
            acc.c["p10|prefix_iri_not_hash_or_slash"] += 1
    containers: dict[str, tuple[str, list]] = {"top": ("top", statements(top, acc, "top"))}
    for bname, bd in (doc.get("bundle") or {}).items():
        if isinstance(bd, dict):
            for p, iri in (bd.get("prefix") or {}).items():
                acc.c["p10|bundle_level_prefix"] += 1
            containers[bname] = (bundle_kind(bname), statements(bd, acc, bundle_kind(bname)))
    kinds = Counter(k for k, _ in containers.values())
    for k, n in kinds.items():
        acc.c[f"p09|containers|{k}"] += n
    declared: dict[str, dict[str, str]] = {}  # container -> node -> section
    relids: dict[str, set[str]] = {}
    for cname, (_kind, sts) in containers.items():
        d = {}
        r = set()
        for sec, key, _a in sts:
            if sec in ELEMENTS:
                d[key] = sec
            else:
                r.add(key)
        declared[cname] = d
        relids[cname] = r
    core_names = [c for c, (k, _s) in containers.items() if k == "core"]
    core = core_names[0] if core_names else None
    alldecl: dict[str, str] = {}
    for d in declared.values():
        alldecl.update(d)
    allrel = set().union(*relids.values()) if relids else set()

    # P10 / U11: keys and QName values
    for cname, (kind, sts) in containers.items():
        for sec, key, a in sts:
            if not key.startswith("_:"):
                local = key.split(":", 1)[1] if ":" in key else key
                if local.endswith("."):
                    acc.c["p10|local_trailing_dot"] += 1
                if re.search(r"[^A-Za-z0-9_.:\-]", key):
                    acc.c[f"u11|prov_key_unusual_chars|{kind}"] += 1
                if local.lower() in ("node", "edge", "graph", "digraph", "subgraph", "strict"):
                    acc.c["u11|prov_local_dot_keyword"] += 1
            for attr, v in a.items():
                vals = v if isinstance(v, list) else [v]
                for x in vals:
                    if isinstance(x, dict) and x.get("type") == "prov:QUALIFIED_NAME" and isinstance(x.get("$"), str):
                        q = x["$"]
                        if q.split(":", 1)[-1].endswith("."):
                            acc.c["p10|qname_value_trailing_dot"] += 1
                if attr in ("apv:sourcePointer", "apv:rulePointer"):
                    ptr_check(acc, "prov", attr, v)

    # P06 dangling references; P08 mentionOf
    for cname, (kind, sts) in containers.items():
        scope = dict(declared[cname])
        if core:
            scope.update(declared[core])
        scope.update(declared["top"])
        for sec, key, a in sts:
            if sec in ELEMENTS:
                continue
            for arg, v in a.items():
                if arg in NODE_ARGS:
                    for x in _qn(v):
                        if x not in scope:
                            where = "elsewhere" if x in alldecl else "nowhere"
                            acc.c[f"p06|unresolved_{where}|{kind}|{sec}|{arg}"] += 1
                elif arg in ("prov:generation", "prov:usage"):
                    for x in _qn(v):
                        if x not in allrel:
                            acc.c[f"p06|relid_unresolved|{kind}|{sec}|{arg}"] += 1
                elif arg == "prov:bundle":
                    for x in _qn(v):
                        if x not in containers:
                            acc.c[f"p08|mention_bundle_missing|{kind}"] += 1
            if sec == "mentionOf":
                acc.c[f"p08|mentionOf|{kind}"] += 1
                b = a.get("prov:bundle")
                gen, spec = a.get("prov:generalEntity"), a.get("prov:specificEntity")
                if isinstance(b, str) and b in declared and gen not in declared[b]:
                    acc.c[f"p08|general_not_in_named_bundle|{kind}"] += 1
                if spec not in declared[cname]:
                    acc.c[f"p08|specific_not_declared_here|{kind}"] += 1

    # P03 C51, P04 C26/C24 per container
    for cname, (kind, sts) in containers.items():
        starts: dict[tuple, str] = {}
        gens: dict[tuple, str] = {}
        for sec, key, a in sts:
            if sec == "wasDerivedFrom":
                acc.c[f"p03|wasDerivedFrom|{kind}"] += 1
                if (a.get("prov:generation") or a.get("prov:usage")) and not a.get("prov:activity"):
                    acc.c[f"p03|c51_violation|{kind}"] += 1
                    out.setdefault("p03_c51", []).append(key)
            elif sec == "wasStartedBy":
                t = (a.get("prov:activity"), a.get("prov:trigger"), a.get("prov:starter"))
                if t in starts and starts[t] != key:
                    acc.c[f"p04|c26_duplicate_start|{kind}"] += 1
                starts.setdefault(t, key)
            elif sec == "wasGeneratedBy":
                t = (a.get("prov:entity"), a.get("prov:activity"))
                if t in gens and gens[t] != key:
                    acc.c[f"p04|c24_duplicate_generation|{kind}"] += 1
                gens.setdefault(t, key)

    # views
    infs =[sts for c, (k, sts) in containers.items() if k == "inf"]
    core_sts = containers[core][1] if core else []
    sm = core_sts + [s for b in infs for s in b]
    assess = [s for c, (k, sts) in containers.items() if k == "assess" for s in sts]
    view_sets = [("container", c, k, sts) for c, (k, sts) in containers.items()]
    view_sets.append(("view", "core+inf", "S(M)", sm))
    if assess:
        view_sets.append(("view", "core+assess", "core+assess", core_sts + assess))
    for vtype, _name, label, sts in view_sets:
        acts = {key for sec, key, _a in sts if sec == "activity"}
        strict, nonstrict = event_graph_violations(sts, acts)
        lab = label if vtype == "view" else f"container:{label}"
        acc.c[f"p01|views|{lab}"] += 1
        if strict:
            acc.c[f"p01|strict_cycle|{lab}"] += strict
            out.setdefault("p01_strict", []).append(lab)
        if nonstrict:
            acc.c[f"p01|nonstrict_scc|{lab}"] += nonstrict
        # P02 cycles
        dep, inf_e, der, spe = [], [], [], []
        genby: dict[str, set[str]] = defaultdict(set)
        for sec, _k, a in sts:
            if sec == "wasGeneratedBy" and a.get("prov:entity") and a.get("prov:activity"):
                genby[a["prov:entity"]].add(a["prov:activity"])
        for sec, _k, a in sts:
            if sec == "used" and a.get("prov:activity") and a.get("prov:entity"):
                for g in genby.get(a["prov:entity"], ()):
                    dep.append((a["prov:activity"], g))
            elif sec == "wasInformedBy" and a.get("prov:informed") and a.get("prov:informant"):
                inf_e.append((a["prov:informed"], a["prov:informant"]))
            elif sec == "wasDerivedFrom" and a.get("prov:generatedEntity") and a.get("prov:usedEntity"):
                der.append((a["prov:generatedEntity"], a["prov:usedEntity"]))
            elif sec in ("specializationOf", "mentionOf") and a.get("prov:specificEntity") and a.get("prov:generalEntity"):
                spe.append((a["prov:specificEntity"], a["prov:generalEntity"]))
        for name, e in (("dependency", dep), ("informed", inf_e), ("derivation", der), ("specialization", spe)):
            n = nontrivial_cycles(e)
            if n:
                acc.c[f"p02|{name}_cycle|{lab}"] += n
                out.setdefault("p02", []).append(f"{name}:{lab}")

    # P05 normal-form expansion on S(M)
    gens_e: dict[str, set[str]] = defaultdict(set)
    assoc: dict[str, set[str]] = defaultdict(set)
    for sec, _k, a in sm:
        if sec == "wasGeneratedBy" and a.get("prov:entity") and a.get("prov:activity"):
            gens_e[a["prov:entity"]].add(a["prov:activity"])
        elif sec == "wasAssociatedWith" and a.get("prov:activity") and a.get("prov:agent"):
            assoc[a["prov:activity"]].add(a["prov:agent"])
    expanded: dict[str, set[str]] = defaultdict(set, {e: set(v) for e, v in gens_e.items()})
    for sec, _k, a in sm:
        if sec == "wasStartedBy":
            trig, starter = a.get("prov:trigger"), a.get("prov:starter")
            if trig and starter:
                explicit = gens_e.get(trig, set())
                if not explicit:
                    acc.c["p05|trigger_generator_implied_only"] += 1
                elif starter in explicit and len(explicit) == 1:
                    acc.c["p05|trigger_generator_is_starter"] += 1
                else:
                    acc.c["p05|trigger_generator_differs_from_starter"] += 1
                    out.setdefault("p05_trigger", []).append(trig)
                expanded[trig].add(starter)
            elif trig:
                acc.c["p05|start_without_starter"] += 1
        elif sec == "wasDerivedFrom" and a.get("prov:activity") and a.get("prov:generatedEntity"):
            expanded[a["prov:generatedEntity"]].add(a["prov:activity"])
        elif sec == "wasAttributedTo" and a.get("prov:entity") and a.get("prov:agent"):
            g = gens_e.get(a["prov:entity"], set())
            if not g:
                acc.c["p05|attribution_generator_implied_only"] += 1
            elif any(a["prov:agent"] in assoc.get(x, ()) for x in g):
                acc.c["p05|attribution_supported"] += 1
            else:
                acc.c["p05|attribution_generator_not_associated"] += 1
                out.setdefault("p05_attr", []).append(a["prov:entity"])
        elif sec == "actedOnBehalfOf":
            act, dl, rs = a.get("prov:activity"), a.get("prov:delegate"), a.get("prov:responsible")
            if not act:
                acc.c["p05|delegation_without_activity"] += 1
            else:
                have = assoc.get(act, set())
                acc.c[f"p05|delegation_assoc|delegate={'explicit' if dl in have else 'implied'}|responsible={'explicit' if rs in have else 'implied'}"] += 1
    acc.c["p05|entities_multi_generator_explicit"] += sum(1 for v in gens_e.values() if len(v) > 1)
    acc.c["p05|entities_multi_generator_expanded"] += sum(1 for v in expanded.values() if len(v) > 1)

    # P09 graph metrics on core, S(M), S(M)+attribute links
    def elems(names: list[str]) -> dict[str, tuple[str, str]]:
        d = {}
        for c in names:
            for sec, key, a in containers[c][1]:
                if sec in ELEMENTS:
                    d[key] = (sec, node_class(sec, a))
        return d

    def rel_edges(sts: list) -> list[tuple[str, str]]:
        e = []
        for sec, _k, a in sts:
            if sec in ELEMENTS:
                continue
            args = [x for arg in FORMALS.get(sec, ()) if arg in NODE_ARGS for x in _qn(a.get(arg))]
            if len(args) >= 2:
                for x in args[1:]:
                    e.append((args[0], x))
        return e

    inf_names = [c for c, (k, _s) in containers.items() if k == "inf"]
    core_el = elems([core]) if core else {}
    sm_el = elems(([core] if core else []) + inf_names)
    e_core = rel_edges(core_sts)
    e_sm = rel_edges(sm)
    attr_links = []
    for c in ([core] if core else []) + inf_names:
        for sec, key, a in containers[c][1]:
            if sec in ELEMENTS:
                for attr in ("apv:partOf", "apv:about"):
                    for x in (a.get(attr) if isinstance(a.get(attr), list) else [a.get(attr)]):
                        if isinstance(x, dict) and isinstance(x.get("$"), str):
                            attr_links.append((key, x["$"]))
    out["p09_components"] = [
        union_find_components(set(core_el), e_core) if core_el else 0,
        union_find_components(set(sm_el), e_sm) if sm_el else 0,
        union_find_components(set(sm_el), e_sm + attr_links) if sm_el else 0,
    ]
    deg: Counter = Counter()
    indeg: Counter = Counter()
    outdeg: Counter = Counter()
    for x, y in e_sm:
        deg[x] += 1
        deg[y] += 1
        outdeg[x] += 1
        indeg[y] += 1
    deg_attr = Counter(deg)
    for x, y in attr_links:
        deg_attr[x] += 1
        deg_attr[y] += 1
    dh: dict[str, Counter] = defaultdict(Counter)
    for node, (sec, cls) in sm_el.items():
        d = deg.get(node, 0)
        dh[cls][min(d, 1000)] += 1
        acc.c[f"p09deg|{sec}|in|{min(indeg.get(node, 0), 1000)}"] += 1
        acc.c[f"p09deg|{sec}|out|{min(outdeg.get(node, 0), 1000)}"] += 1
        if d == 0:
            acc.c[f"p09|orphan|{cls}"] += 1
            if deg_attr.get(node, 0) == 0:
                acc.c[f"p09|orphan_even_with_attr|{cls}"] += 1
        acc.c[f"p09|nodes|{cls}"] += 1
    out["p09_deghist"] = {cls: dict(c) for cls, c in dh.items()}
    # Gap share, times
    for cname, (kind, sts) in containers.items():
        for sec, key, a in sts:
            if sec == "entity" and kind in ("core", "inf"):
                acc.c["p09|entities_core_inf"] += 1
                if "apv:Gap" in _types(a):
                    acc.c["p09|gap_entities"] += 1
            if sec == "activity":
                acc.c[f"p09|activities|{kind}"] += 1
                if "prov:startTime" in a:
                    acc.c[f"p09|activities_with_startTime|{kind}"] += 1
                if "prov:endTime" in a:
                    acc.c[f"p09|activities_with_endTime|{kind}"] += 1
            if sec not in ELEMENTS and "prov:time" in a:
                acc.c[f"p09|relations_with_time|{kind}|{sec}"] += 1
            if sec == "entity" and ("prov:generatedAtTime" in a or "prov:invalidatedAtTime" in a):
                acc.c[f"p09|entity_time|{kind}"] += 1
            if sec not in ELEMENTS:
                acc.c[f"p09|relations|{kind}|{sec}"] += 1
    # P07 shared top-level statements
    shared = []
    for sec, key, a in containers["top"][1]:
        if key.split(":", 1)[0] in ("raw", "sw", "rules"):
            shared.append([sec, key, sha16(jcs(a).decode("utf-8"))])
    out["p07_shared"] = shared
    out["p07_prefix"] = sorted([p, iri] for p, iri in prefixes.items() if p != "x")


# ------------------------------------------------------------------------------------------------ one execution
def scan_one(row: dict[str, Any]) -> dict[str, Any]:
    assert _ROOT is not None
    ex = row["ex"]
    acc = Acc(ex)
    out: dict[str, Any] = {"ex": ex, "status": row.get("status"), "unit": row.get("unit")}
    paths = row.get("paths") or {}
    ctx: dict[str, Any] = {"fixtures": {}, "texts": {}}
    sem_all: list[Any] = []
    aer_path = paths.get("aer")
    if aer_path:
        data = (_ROOT / aer_path).read_bytes()
        acc.c["bytes_total|aer"] += len(data)
        active = byte_checks(acc, "aer", data)
        recs = check_jsonl(acc, "aer", data)
        ctx = aer_semantics(acc, recs, out)
        if active:
            for r in recs:
                if isinstance(r, dict):
                    walk_strings(acc, "aer", r, [f"{r.get('k')}:{r.get('kind') or r.get('role') or ''}"], active)
    for ref, p in (paths.get("sem") or {}).items():
        data = (_ROOT / p).read_bytes()
        acc.c["bytes_total|sem"] += len(data)
        active = byte_checks(acc, "sem", data)
        recs = check_jsonl(acc, "sem", data)
        sem_all += recs
        for r in recs:
            if isinstance(r, dict):
                for prem in r.get("premises") or ():
                    if isinstance(prem, dict) and "p" in prem:
                        ptr_check(acc, "sem", "premise_p", prem["p"])
                if "at" in r:
                    ptr_check(acc, "sem", "at", r["at"])
                if active:
                    walk_strings(acc, "sem", r, [f"{r.get('k')}:{r.get('type') or ''}"], active)
    marker_forms(acc, sem_all, ctx, out)
    for spec, forms in (paths.get("prov") or {}).items():
        p = forms.get("json") if isinstance(forms, dict) else None
        if not p:
            continue
        data = (_ROOT / p).read_bytes()
        acc.c["bytes_total|prov"] += len(data)
        acc.c["files|prov"] += 1
        active = byte_checks(acc, "prov", data)
        flags: Counter = Counter()
        try:
            doc = strict_parse(data, flags)
        except StrictError as exc:
            acc.c[f"strict|prov|{exc.code}"] += 1
            continue
        for f, n in flags.items():
            acc.c[f"strictflag|prov|{f}"] += n
        stats: Counter = Counter()
        try:
            if jcs(doc, stats) != data:
                acc.c["jcs|prov|mismatch"] += 1
        except JcsError as exc:
            acc.c[f"jcs|prov|error_{exc.code}"] += 1
        for f, n in stats.items():
            acc.c[f"num|prov|{f}"] += n
        if active:
            _walk_prov(acc, doc, active)
        if isinstance(doc, dict):
            prov_checks(acc, doc, out)
    out["c"] = dict(acc.c)
    out["hits"] = dict(acc.hits)
    out["exh"] = acc.ex_ptr
    return out


def _walk_prov(acc: Acc, doc: dict[str, Any], active: set[str]) -> None:
    for sec, items in doc.items():
        if sec == "bundle" and isinstance(items, dict):
            for bname, bd in items.items():
                k = bundle_kind(bname)
                for s2, it2 in (bd or {}).items():
                    if isinstance(it2, dict):
                        for key, attrs in it2.items():
                            walk_strings(acc, "prov", key, [f"bundle.{k}", s2, "*", "#key"], active)
                            walk_strings(acc, "prov", attrs, [f"bundle.{k}", s2, "*"], active)
        elif isinstance(items, dict):
            for key, attrs in items.items():
                walk_strings(acc, "prov", key, ["top", sec, "*", "#key"], active)
                walk_strings(acc, "prov", attrs, ["top", sec, "*"], active)


def _safe(row: dict[str, Any]) -> dict[str, Any]:
    try:
        return scan_one(row)
    except Exception as exc:  # noqa: BLE001 - an analysis failure is recorded, never hidden
        return {"ex": row.get("ex"), "error": type(exc).__name__, "c": {}, "hits": {}, "exh": {}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    root = Path(a.corpus).expanduser()
    rows = [json.loads(line) for line in (root / "executions.jsonl").read_bytes().splitlines() if line]
    rows.sort(key=lambda r: r["ex"])
    if a.limit:
        rows = rows[: a.limit]
    n = 0
    with open(a.out, "w", encoding="utf-8") as fh, Pool(a.jobs, initializer=_init, initargs=(str(root),)) as pool:
        for res in pool.imap(_safe, rows, chunksize=16):
            fh.write(json.dumps(res, sort_keys=True) + "\n")
            n += 1
            if n % 2000 == 0:
                print(f"{root.name}: {n}/{len(rows)}", file=sys.stderr, flush=True)
    print(f"{root.name}: done {n}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
