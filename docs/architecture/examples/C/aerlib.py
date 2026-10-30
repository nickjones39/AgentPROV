"""Scratch prototype for spec section C (AER 0.1). Not production code.

Builds AER records, serialises them with RFC 8785 (rfc8785 0.1.4), computes
execution ids over the mapping id (C.4.1) and seals, re-resolves source locators
against the raw artefact bytes, and checks a subset of the C.17 validator
invariants. r2 contract (2026-10-08): mapping-id execution ids, `unit`, integer
profile and catalogue versions, `prov_primary`, no as-sent message copies.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import rfc8785

PARTIES = {"capture", "source", "provider", "benchmark", "config", "replay"}
UNK = {"not_recorded", "lost", "overwritten", "withheld", "ambiguous", "not_captured", "not_applicable"}
RULE_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+@[1-9][0-9]*(#(/.*)?)?$")
TAG_RE = re.compile(r"^(O|D|I|O:(capture|source|provider|benchmark|config|replay))$")
UNITS = {"agent_execution", "outcome_only", "scenario"}
PROV_PRIMARY = {"native", "byte_derived", "secondary", "unknown"}
RESERVED_IDS = {"as"}            # EF E.4.2; `exec`, `seal`, `run` only for their kinds (C.4.2)
ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


def jcs(obj: Any) -> bytes:
    return rfc8785.dumps(obj)


def sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def ex_preimage(mapping_id: str, artefact_sha256_hex: str, loc: dict) -> bytes:
    return ("aer-ex/1\n" + mapping_id + "\n" + artefact_sha256_hex + "\n").encode("utf-8") + jcs(loc)


def ex_id(mapping_id: str, artefact_sha256_hex: str, loc: dict) -> str:
    """C.4.1: mapping_id = "<adapter id>/<profile id>" (AD-04)."""
    pre = ex_preimage(mapping_id, artefact_sha256_hex, loc)
    return "ex_" + base64.b32encode(hashlib.sha256(pre).digest()).decode("ascii").lower().rstrip("=")[:26]


# ---------------------------------------------------------------- JSON pointers
def ptr_escape(tok: str) -> str:
    return tok.replace("~", "~0").replace("/", "~1")


def ptr_get(doc: Any, ptr: str) -> Any:
    if ptr == "":
        return doc
    if not ptr.startswith("/"):
        raise KeyError(ptr)
    cur = doc
    for raw in ptr[1:].split("/"):
        tok = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(cur, list):
            if not re.fullmatch(r"0|[1-9][0-9]*", tok):
                raise KeyError(ptr)
            cur = cur[int(tok)]
        elif isinstance(cur, dict):
            cur = cur[tok]
        else:
            raise KeyError(ptr)
    return cur


def ptr_exists(doc: Any, ptr: str) -> bool:
    try:
        ptr_get(doc, ptr)
        return True
    except (KeyError, IndexError, TypeError):
        return False


# ---------------------------------------------------------------- lexical hints
class Pairs(list):
    """Object parsed with member order kept (object_pairs_hook)."""


def parse_ordered(b: bytes) -> Any:
    def hook(pairs):
        keys = [k for k, _ in pairs]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate member name")
        return Pairs(pairs)
    return json.loads(b.decode("utf-8"), object_pairs_hook=hook)


def plain(v: Any) -> Any:
    if isinstance(v, Pairs):
        return {k: plain(x) for k, x in v}
    if isinstance(v, list):
        return [plain(x) for x in v]
    return v


def lex_hints(v: Any, at: str, ord_: dict, flt: list) -> None:
    """Record member order differing from JCS order, and integral floats, under pointer `at`."""
    if isinstance(v, Pairs):
        keys = [k for k, _ in v]
        if keys != sorted(keys, key=lambda s: s.encode("utf-16-be")):
            ord_[at] = keys
        for k, x in v:
            lex_hints(x, at + "/" + ptr_escape(k), ord_, flt)
    elif isinstance(v, list):
        for i, x in enumerate(v):
            lex_hints(x, f"{at}/{i}", ord_, flt)
    elif isinstance(v, float) and v.is_integer():
        flt.append(at)


def add_lex(rec: dict, pairs_by_ptr: list[tuple[str, Any]]) -> None:
    ord_: dict = {}
    flt: list = []
    for at, v in pairs_by_ptr:
        lex_hints(v, at, ord_, flt)
    if ord_ or flt:
        lex = {}
        if ord_:
            lex["ord"] = ord_
        if flt:
            lex["flt"] = sorted(flt)
        rec.setdefault("ext", {})["lex"] = lex


# ---------------------------------------------------------------- writer
def seal_and_serialise(records: list[dict], seal_body: dict) -> tuple[bytes, str]:
    lines = [jcs(r) + b"\n" for r in records]
    body = b"".join(lines)
    seal = {"k": "seal", "id": "seal", "n_records": len(records) + 1,
            "records_sha256": sha256_hex(body)}
    seal.update(seal_body)
    out = body + jcs(seal) + b"\n"
    return out, seal["records_sha256"]


# ---------------------------------------------------------------- validator subset
REF_FIELDS = {
    # field -> allowed target kinds ("part" = message part id)
    "on_behalf_of": {"actor"},
    "parent": {"scope"},
    "spawned_by": {"tool_execution", "model_call"},
    "scope": {"scope"},
    "actor": {"actor"},
    "generated_by": {"model_call", "tool_execution", "decision"},
    "call": {"part:tool_call"},
    "subject": {"execution", "scope", "message", "part", "model_call", "tool_execution", "state_change", "fixture"},
    "cause": {"tool_execution", "scope", "decision", "model_call"},
    "revises": {"judgement"},
    "retry_of": {"model_call"},
    "tools": {"fixture"},
}


def validate(data: bytes, artefacts: dict[str, bytes], catalogue: set[str]) -> list[str]:
    errs: list[str] = []
    if not data.endswith(b"\n"):
        errs.append("no final LF")
    raw_lines = data.split(b"\n")[:-1]
    recs = []
    for i, ln in enumerate(raw_lines):
        r = json.loads(ln)
        if jcs(r) != ln:
            errs.append(f"line {i}: not JCS")
        recs.append(r)
    if recs[0]["k"] != "execution" or recs[-1]["k"] != "seal":
        errs.append("execution/seal position")
    seal = recs[-1]
    if seal["n_records"] != len(recs):
        errs.append("n_records")
    body = b"".join(ln + b"\n" for ln in raw_lines[:-1])
    if sha256_hex(body) != seal["records_sha256"]:
        errs.append("seal hash")
    seen: dict[str, dict] = {}
    parts: dict[str, dict] = {}
    hdr = recs[0]
    # header checks of the r2 contract (AER-V22, AER-V26, AER-V20 prov_primary)
    if hdr.get("unit") not in UNITS:
        errs.append("header: unit")
    if not isinstance(hdr["profile"].get("version"), int) or not re.fullmatch(r"[0-9a-f]{64}", hdr["profile"].get("sha256", "")):
        errs.append("header: profile {id, version: int, sha256}")
    if not all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in hdr["rules"].values()):
        errs.append("header: rules values must be positive integers")
    if hdr["mode"] == "import":
        mid = hdr["adapter"]["id"] + "/" + hdr["profile"]["id"]
        if hdr["ex"] != ex_id(mid, hdr["source_key"]["sha256"], hdr["source_key"]["loc"]):
            errs.append("header: ex is not import_execution_id(mapping id, sha256, loc)")
    for a in hdr["artifacts"]:
        if a.get("prov_primary") not in PROV_PRIMARY:
            errs.append(f"artefact {a['id']}: prov_primary")
    for r in recs[1:-1]:
        for ru in r.get("rule") or []:
            if ru.split(".")[0] not in hdr["rules"]:
                errs.append(f"{r['id']}: catalogue of {ru} not declared in header rules")
    for iss in seal.get("issues", []):
        if iss["rule"].split(".")[0] not in hdr["rules"]:
            errs.append(f"seal issue {iss['code']}: catalogue of {iss['rule']} not declared")
    arts = {a["id"]: a for a in hdr["artifacts"]}
    parsed = {}
    for aid, a in arts.items():
        b = artefacts[aid]
        if sha256_hex(b) != a["sha256"] or len(b) != a["bytes"]:
            errs.append(f"artefact {aid} digest/size")
        parsed[aid] = plain(parse_ordered(b))
    for r in recs[:-1]:
        rid = r["id"]
        if rid in seen:
            errs.append(f"dup id {rid}")
        if not ID_RE.match(rid) or rid in RESERVED_IDS:
            errs.append(f"{rid}: local id grammar or reserved name")
        if (rid == "exec") != (r["k"] == "execution") or (rid == "run") != (r["k"] == "scope" and r.get("kind") == "run"):
            errs.append(f"{rid}: fixed id used for the wrong kind")
        # evidence tags
        tags = [r.get("ev")] + list((r.get("evf") or {}).values())
        for t in tags:
            if t is None or not TAG_RE.match(t):
                errs.append(f"{rid}: bad tag {t}")
        bare_o = any(t == "O" for t in tags)
        if bare_o and r.get("by") not in PARTIES:
            errs.append(f"{rid}: O without by")
        has_o = any(t and t.startswith("O") for t in tags)
        if has_o and not r.get("src"):
            errs.append(f"{rid}: O without src")
        di = any(t in ("D", "I") for t in tags)
        rules = r.get("rule") or []
        if di and not rules:
            errs.append(f"{rid}: D/I without rule")
        for ru in rules:
            if not RULE_RE.match(ru):
                errs.append(f"{rid}: bad rule {ru}")
            if ru.split("#")[0] not in catalogue:
                errs.append(f"{rid}: undeclared rule {ru}")
        for p, why in (r.get("unk") or {}).items():
            if why not in UNK:
                errs.append(f"{rid}: unk reason {why}")
            if why != "ambiguous" and ptr_exists(r, p):
                errs.append(f"{rid}: unk {p} but value present")
            if why == "ambiguous" and not ptr_exists(r, p) and not p.startswith("/t/"):
                pass
        # locators
        for loc in r.get("src") or []:
            a = loc["a"]
            try:
                if "o" in loc:
                    ptr_get(arts[a]["origin"], loc["o"])
                elif "bytes" in loc:
                    s, e = loc["bytes"]
                    sl = plain(parse_ordered(artefacts[a][s:e]))
                    ptr_get(sl, loc.get("p", ""))
                else:
                    ptr_get(parsed[a], loc["p"])
            except Exception as ex:  # noqa: BLE001
                errs.append(f"{rid}: locator {loc} does not resolve ({ex!r})")
        # references (backward only, kind-typed)
        def check_ref(field, target):
            allowed = REF_FIELDS[field]
            if "#" in target:
                if target not in parts:
                    errs.append(f"{rid}.{field} -> {target}: not earlier")
                    return
                pk = "part:" + parts[target]["t"]
                if not ({"part", pk} & allowed):
                    errs.append(f"{rid}.{field} -> {target}: kind {pk}")
                return
            if target not in seen:
                errs.append(f"{rid}.{field} -> {target}: not earlier")
                return
            if seen[target]["k"] not in allowed:
                errs.append(f"{rid}.{field} -> {target}: kind {seen[target]['k']}")
        for f in REF_FIELDS:
            if f in r and isinstance(r[f], str) and r["k"] != "execution":
                if f == "tools" and r["k"] != "model_call":
                    continue
                check_ref(f, r[f])
        if r["k"] == "model_call" and isinstance(r.get("input"), list):
            for m in r["input"]:
                if m not in seen or seen[m]["k"] != "message":
                    errs.append(f"{rid}.input -> {m}")
        for a in r.get("after") or []:
            if a["id"] not in seen and a["id"] not in parts:
                errs.append(f"{rid}.after -> {a['id']}: not earlier")
        if r["k"] == "message":
            for k, p in enumerate(r["parts"]):
                if p["t"] == "tool_result" and "responds_to" in p:
                    if p["responds_to"] not in parts or parts[p["responds_to"]]["t"] != "tool_call":
                        errs.append(f"{rid}#{k}.responds_to")
        seen[rid] = r
        if r["k"] == "message":
            for k, p in enumerate(r["parts"]):
                parts[f"{rid}#{k}"] = p
        # ext namespaces
        for ns in (r.get("ext") or {}):
            if ns != "lex" and ns not in hdr["ns"]:
                errs.append(f"{rid}: undeclared ns {ns}")
    return errs


def pget(v, ptr: str):
    """JSON Pointer over an order-preserving parse (Pairs)."""
    if ptr == "":
        return v
    for raw in ptr[1:].split("/"):
        tok = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(v, Pairs):
            v = dict(v)[tok]
        else:
            v = v[int(tok)]
    return v
