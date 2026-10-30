"""Examination 2: corpus-level files and the raw store (read-only).

* X01/X02/X05/U14 on ``executions.jsonl``, ``register.jsonl``, ``validation/results.jsonl``, ``raw/origins.jsonl``,
  ``raw/members.jsonl`` (JCS lines) and on ``corpus.json``, ``derivation.json``, ``validation/summary.json`` (H.1.4(2):
  sorted keys, 2-space indent, ``ensure_ascii=False``; re-serialised with that rule and compared; floats counted;
  objects whose code-point key order differs from UTF-16 order counted);
* A04: degenerate executions and failure codes from the index and register; the source-side population in the raw
  JSON objects: strict-parse failures by class (duplicate keys, non-finite constants, float overflow, invalid UTF-8,
  BOM), integers beyond I-JSON, and decoded strings or keys holding lone surrogates.

Prints/writes a JSON report of counts and ids only.

Usage: ``python tools/analysis2/exam2_corpusfiles.py --corpus DIR [...] --out REPORT.json``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from exam2_lib import JcsError, P, StrictError, jcs, strict_parse  # noqa: E402

JSONL = ("executions.jsonl", "register.jsonl", "validation/results.jsonl", "raw/origins.jsonl", "raw/members.jsonl")
DOCS = ("corpus.json", "derivation.json", "validation/summary.json")
_DEGEN = re.compile(r"adapter_defect|aer\.write\.invalid|unparseable|lone_surrogate|degenerate|unsupported_variant")


def _walk(node: Any, stats: Counter) -> None:
    stack = [node]
    while stack:
        n = stack.pop()
        if isinstance(n, str):
            try:
                n.encode("utf-8")
            except UnicodeEncodeError:
                stats["lone_surrogate_strings"] += 1
            if P["ABS_PATH"].search(n):
                stats["abs_path_strings"] += 1
        elif isinstance(n, dict):
            keys = list(n)
            if not all(k.isascii() for k in keys) and sorted(keys) != sorted(keys, key=lambda k: k.encode("utf-16-be", "surrogatepass")):
                stats["codepoint_vs_utf16_order_differs"] += 1
            for k in keys:
                try:
                    k.encode("utf-8")
                except UnicodeEncodeError:
                    stats["lone_surrogate_keys"] += 1
            stack.extend(n.values())
        elif isinstance(n, list):
            stack.extend(n)
        elif isinstance(n, float):
            stats["floats"] += 1


def corpus_files(root: Path) -> dict[str, Any]:
    rep: dict[str, Any] = {}
    for name in JSONL:
        p = root / name
        if not p.exists():
            rep[name] = "absent"
            continue
        data = p.read_bytes()
        c: Counter = Counter()
        c["final_lf"] = int(data.endswith(b"\n"))
        c["raw_cr"] = data.count(b"\r")
        lines = data.split(b"\n")
        if lines and lines[-1] == b"":
            lines.pop()
        for line in lines:
            c["lines"] += 1
            if not line:
                c["blank"] += 1
                continue
            fl: Counter = Counter()
            try:
                obj = strict_parse(line, fl)
            except StrictError as exc:
                c[f"strict_{exc.code}"] += 1
                continue
            c.update({f"flag_{k}": v for k, v in fl.items()})
            try:
                if jcs(obj) != line:
                    c["jcs_mismatch"] += 1
            except JcsError as exc:
                c[f"jcs_error_{exc.code}"] += 1
            st: Counter = Counter()
            _walk(obj, st)
            c.update(st)
        rep[name] = dict(c)
    for name in DOCS:
        p = root / name
        if not p.exists():
            rep[name] = "absent"
            continue
        data = p.read_bytes()
        c = Counter()
        try:
            obj = strict_parse(data, c)
            again = (json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
            c["h142_reserialise_equal"] = int(again == data)
            st = Counter()
            _walk(obj, st)
            c.update(st)
        except StrictError as exc:
            c[f"strict_{exc.code}"] += 1
        rep[name] = dict(c)
    return rep


def degenerate(root: Path) -> dict[str, Any]:
    rows = [json.loads(x) for x in (root / "executions.jsonl").read_bytes().splitlines() if x]
    c: Counter = Counter()
    ex: dict[str, list[str]] = {}
    for r in rows:
        c[f"status|{r.get('status')}"] += 1
        c[f"unit|{r.get('unit')}"] += 1
        for code in r.get("issues") or ():
            if _DEGEN.search(code):
                c[f"issue|{code}"] += 1
                ex.setdefault(code, []).append(r["ex"])
        st = r.get("stages") or {}
        for stage, v in st.items():
            vals = v.values() if isinstance(v, dict) else [v]
            for x in vals:
                if x != "ok":
                    c[f"stage_not_ok|{stage}|{x}"] += 1
    reg: Counter = Counter()
    for x in (root / "register.jsonl").read_bytes().splitlines():
        if not x:
            continue
        r = json.loads(x)
        code = str(r.get("code"))
        reg[f"{code}|{r.get('disposition')}"] += 1
        det = str(r.get("detail") or "")
        if _DEGEN.search(code) or _DEGEN.search(det):
            reg[f"degenerate_like|{code}|{det[:60] if re.fullmatch(r'[A-Za-z0-9_.:, ()-]*', det[:60]) else '<detail>'}"] += 1
    return {"index": dict(c), "register_codes": dict(reg), "examples": {k: v[:5] for k, v in ex.items()}}


_ESC_SURR = re.compile(rb"(?<!\\)(?:\\\\)*\\u[dD][89a-fA-F][0-9a-fA-F]{2}")


def raw_store(root: Path) -> dict[str, Any]:
    c: Counter = Counter()
    examples: dict[str, list[str]] = {}
    objs = root / "raw" / "objects"
    for p in sorted(objs.rglob("*")):
        if not p.is_file():
            continue
        ext = p.suffix.lstrip(".")
        c[f"objects|{ext}"] += 1
        if ext != "json":
            continue
        data = p.read_bytes()
        if _ESC_SURR.search(data):
            c["files_with_escaped_surrogate_escapes"] += 1  # pairs and lone ones; decoded check below
        fl: Counter = Counter()
        try:
            obj = strict_parse(data, fl)
        except StrictError as exc:
            c[f"strict_fail|{exc.code}"] += 1
            examples.setdefault(exc.code, []).append(p.name[:20])
            continue
        if fl:
            c.update({f"flag|{k}": v for k, v in fl.items()})
            for k in fl:
                examples.setdefault(k, []).append(p.name[:20])
        st: Counter = Counter()
        _walk(obj, st)
        for k in ("lone_surrogate_strings", "lone_surrogate_keys"):
            if st.get(k):
                c[f"files_with|{k}"] += 1
                c[k] += st[k]
                examples.setdefault(k, []).append(p.name[:20])
    return {"counts": dict(c), "examples": {k: v[:5] for k, v in examples.items()}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rep = {}
    for c in a.corpus:
        root = Path(c).expanduser()
        rep[root.name] = {"files": corpus_files(root), "degenerate": degenerate(root), "raw": raw_store(root)}
        print(root.name, "done", file=sys.stderr)
    Path(a.out).write_text(json.dumps(rep, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
