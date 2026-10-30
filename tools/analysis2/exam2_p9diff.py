# ruff: noqa: B007, B905, UP031  (analysis script, committed as run; style-only)
"""Examination 2: phase-9 vs phase-10 comparison of a re-derived corpus (read-only).

AGENTS.md expects, for the corpora re-derived on the phase-10 code (agentdojo 2024-06, adprov v1 release, survey
AgentHarm): AER differs only in ``execution.profile.sha256`` (and, with the history index, the two history fields), PROV
in the catalogue digest. This tool matches executions by id and reports, per artefact kind, the normalised JSON pointers
that differ (difference signatures), with counts and example ids; executions present in only one corpus are counted.

Usage: ``python tools/analysis2/exam2_p9diff.py --old DIR --new DIR --out REPORT.json [--jobs 4]``.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from multiprocessing import Pool
from pathlib import Path
from typing import Any

_OLD: Path | None = None
_NEW: Path | None = None
_H = re.compile(r"\.[a-z2-7]{16,}$|\.[0-9a-f]{64}$")


def _init(old: str, new: str) -> None:
    global _OLD, _NEW, _OLD_INDEX
    _OLD, _NEW = Path(old), Path(new)
    _OLD_INDEX = {r["ex"]: r for r in (json.loads(x) for x in (_OLD / "executions.jsonl").read_bytes().splitlines() if x)}


def norm_key(k: str, parent: str) -> str:
    if k.isdigit():
        return "*"
    if parent in ("bundle",):
        return re.sub(r"\.[a-z2-7]{16,}$", ".<h>", k)
    if parent in ("entity", "activity", "agent", "used", "wasGeneratedBy", "wasDerivedFrom", "wasInformedBy",
                  "wasAssociatedWith", "wasAttributedTo", "actedOnBehalfOf", "hadMember", "specializationOf", "mentionOf",
                  "wasStartedBy", "ord", "args", "args_effective", "content", "value"):
        return "*"
    return k


def diff(a: Any, b: Any, path: str, parent: str, out: set[str], depth: int = 0) -> None:
    if a == b:
        return
    if isinstance(a, dict) and isinstance(b, dict) and depth < 12:
        for k in set(a) | set(b):
            nk = norm_key(k, parent)
            if k not in a:
                out.add(f"{path}/{nk}:added")
            elif k not in b:
                out.add(f"{path}/{nk}:removed")
            else:
                diff(a[k], b[k], f"{path}/{nk}", k, out, depth + 1)
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b) and depth < 12:
        for x, y in zip(a, b, strict=True):
            diff(x, y, f"{path}/*", parent, out, depth + 1)
    else:
        out.add(f"{path}:changed")


def one(row: dict[str, Any]) -> dict[str, Any]:
    assert _OLD and _NEW
    res: dict[str, Any] = {"ex": row["ex"]}
    old_rows = _OLD_INDEX.get(row["ex"])
    if old_rows is None:
        res["only_new"] = True
        return res
    sigs: dict[str, list[str]] = {}
    pn, po = row["paths"], old_rows["paths"]
    a = (_OLD / po["aer"]).read_bytes()
    b = (_NEW / pn["aer"]).read_bytes()
    if a != b:
        la, lb = a.split(b"\n"), b.split(b"\n")
        s: set[str] = set()
        if len(la) != len(lb):
            s.add("line_count")
        for x, y in zip(la, lb):
            if x != y and x and y:
                rx, ry = json.loads(x), json.loads(y)
                diff(rx, ry, f"{ry.get('k')}", "", s)
        sigs["aer"] = sorted(s)
    for ref in set(pn.get("sem") or {}) | set(po.get("sem") or {}):
        if ref not in (po.get("sem") or {}) or ref not in (pn.get("sem") or {}):
            sigs.setdefault("sem", []).append(f"profile_ref_only_in_one:{ref}")
            continue
        a = (_OLD / po["sem"][ref]).read_bytes()
        b = (_NEW / pn["sem"][ref]).read_bytes()
        if a != b:
            s = set()
            la, lb = a.split(b"\n"), b.split(b"\n")
            if len(la) != len(lb):
                s.add("line_count")
            for x, y in zip(la, lb):
                if x != y and x and y:
                    rx, ry = json.loads(x), json.loads(y)
                    diff(rx, ry, f"{ry.get('k')}:{ry.get('type', '')}", "", s)
            sigs["sem"] = sorted(s)
    for spec in pn.get("prov") or {}:
        a = (_OLD / po["prov"][spec]["json"]).read_bytes()
        b = (_NEW / pn["prov"][spec]["json"]).read_bytes()
        if a != b:
            s = set()
            da, db = json.loads(a), json.loads(b)
            for sec in set(da) | set(db):  # shared top-level statements, unmasked, by key
                if sec in ("bundle", "prefix"):
                    continue
                xa, xb = da.get(sec) or {}, db.get(sec) or {}
                for k in set(xa) & set(xb):
                    if k.split(":", 1)[0] in ("raw", "sw", "rules"):
                        diff(xa[k], xb[k], f"/top/{sec}/{'raw:*' if k.startswith('raw:') else k}", "", s)
            la, lb = _leaves(da), _leaves(db)
            if la == lb:
                s.add("equal_after_masking_ids_and_digests")
            else:
                for path, _v in (la - lb) + (lb - la):
                    s.add(f"{path}:differs")
            sigs["prov"] = sorted(s)[:40]
    res["sigs"] = sigs
    res["index_digest_equal"] = {k: row["digests"].get(k) == old_rows["digests"].get(k) for k in ("aer", "sem", "prov", "validation")}
    return res


_OLD_INDEX: dict[str, dict] = {}
_MASKS = [(re.compile(rb"[0-9a-f]{64}"), b"<sha>"), (re.compile(rb"\.[a-z2-7]{26}(?=[\"./]|$)"), b".<dk>"),
          (re.compile(rb"(?<=[.-])[a-z2-7]{12,25}(?=[\"./]|$)"), b"<h>")]


def _mask(b: bytes) -> bytes:
    for rx, rep in _MASKS:
        b = rx.sub(rep, b)
    return b


def _m(text: str) -> str:
    return _mask(text.encode("utf-8", "surrogatepass")).decode("utf-8", "surrogatepass")


def _leaves(doc: Any) -> Counter:
    """Multiset of (normalised path, masked leaf value): ids, derivation keys and digests masked; list positions kept."""
    out: Counter = Counter()
    stack = [(doc, "")]
    while stack:
        n, path = stack.pop()
        if isinstance(n, dict):
            for k, v in n.items():
                stack.append((v, path + "/" + re.sub(r"^(x|xd|_):[a-z_]+\.<h>$", r"\1:<stmt>", _m(k))))
        elif isinstance(n, list):
            for v in n:
                stack.append((v, path + "/*"))
        else:
            out[(path, _m(json.dumps(n, sort_keys=True)))] += 1
    return out


def main() -> int:
    global _OLD_INDEX
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True, type=Path)
    ap.add_argument("--new", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args()
    old, new = a.old.expanduser(), a.new.expanduser()
    _OLD_INDEX = {r["ex"]: r for r in (json.loads(x) for x in (old / "executions.jsonl").read_bytes().splitlines() if x)}
    rows = sorted((json.loads(x) for x in (new / "executions.jsonl").read_bytes().splitlines() if x), key=lambda r: r["ex"])
    only_old = len(set(_OLD_INDEX) - {r["ex"] for r in rows})
    sig_counts: dict[str, Counter] = {"aer": Counter(), "sem": Counter(), "prov": Counter()}
    sig_ex: dict[str, str] = {}
    files_differ: Counter = Counter()
    digest_eq: Counter = Counter()
    only_new = 0
    with Pool(a.jobs, initializer=_init, initargs=(str(old), str(new))) as pool:
        for res in pool.imap(one, rows, chunksize=32):
            if res.get("only_new"):
                only_new += 1
                continue
            for k, v in res.get("index_digest_equal", {}).items():
                digest_eq[f"{k}={v}"] += 1
            for kind, sigs in res["sigs"].items():
                files_differ[kind] += 1
                key = " | ".join(sigs)
                sig_counts[kind][key] += 1
                sig_ex.setdefault(f"{kind}:{key}", res["ex"])
    rep = {"old": old.name, "new": new.name, "executions_new": len(rows), "only_in_new": only_new, "only_in_old": only_old,
           "files_differ": dict(files_differ), "index_digests_equal": dict(digest_eq),
           "signatures": {k: [[n, s, sig_ex[f"{k}:{s}"]] for s, n in v.most_common(15)] for k, v in sig_counts.items()}}
    a.out.write_text(json.dumps(rep, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
