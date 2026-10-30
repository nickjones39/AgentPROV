"""Examination 2: X04 (second JCS against RFC 8785 vectors and the project's canonicaliser) and C00 (fault injection).

Reads one execution of a corpus (read-only), mutates copies in memory and checks that each examination check fires.
Prints a JSON report; no corpus text.

Usage: ``python tools/analysis2/exam2_selftest.py --corpus DIR [--out REPORT.json]``.
"""

from __future__ import annotations

import argparse
import copy
import json
import random
import struct
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from exam2_lib import JcsError, StrictError, es_number, jcs, strict_parse  # noqa: E402

import exam2_scan  # noqa: E402

from agentprov.io.canonical import jcs_bytes  # noqa: E402  (the code under test, used only as the comparison side)


def x04() -> dict:
    res: dict = {}
    vectors = [0.0, -0.0, 1.0, -1.0, 1e21, 1e20, 1e-7, 1e-6, 5e-324, 1.7976931348623157e308, 1e23, 333333333.3333333,
               100000000000000000000.0, 0.000001, 123e-20, 4.35, 0.1 + 0.2, 2**53 - 1.0, 9007199254740991.0, 1e300,
               -1e-300, 1.5e-07, 295147905179352830000.0, 4.940656458412465e-324, 2.2250738585072014e-308, 0.5, 1e16]
    mism = []
    for v in vectors:
        mine = es_number(v)
        theirs = jcs_bytes(v).decode()
        if mine != theirs:
            mism.append([repr(v), mine, theirs])
    res["vectors"] = len(vectors)
    res["vector_mismatches"] = mism
    rnd = random.Random(20261011)
    n = 200_000
    bad = 0
    examples = []
    for _ in range(n):
        bits = rnd.getrandbits(64)
        v = struct.unpack("<d", struct.pack("<Q", bits))[0]
        if v != v or v in (float("inf"), float("-inf")):
            continue
        a, b = es_number(v), jcs_bytes(v).decode()
        if a != b:
            bad += 1
            if len(examples) < 5:
                examples.append([repr(v), a, b])
    res["random_doubles"] = n
    res["random_mismatches"] = bad
    res["random_examples"] = examples
    # integers near the I-JSON bound
    for x in (2**53 - 1, -(2**53 - 1)):
        assert jcs(x) == jcs_bytes(x)
    try:
        jcs(2**53)
        res["int_2_53"] = "accepted"
    except JcsError:
        res["int_2_53"] = "rejected (as rfc8785)"
    # key order: astral vs BMP-high vs ASCII
    obj = {"\U0001f600": 1, "\uffff": 2, "\ue000": 3, "a": 4, "é": 5, "\U00010000": 6}
    res["key_order_equal"] = jcs(obj) == jcs_bytes(obj)
    res["key_order_mine"] = [k.encode("unicode_escape").decode() for k in json.loads(jcs(obj))]
    # strings: controls, DEL, separators, quotes
    s = "".join(chr(i) for i in range(0x20)) + '"\\\x7f\u2028\u2029\u0085\U0001f600'
    res["string_escape_equal"] = jcs(s) == jcs_bytes(s)
    try:
        jcs("a\ud800")
        res["lone_surrogate"] = "accepted"
    except JcsError:
        res["lone_surrogate"] = "rejected"
    return res


def c00(corpus: Path) -> dict:
    rows = [json.loads(x) for x in (corpus / "executions.jsonl").read_bytes().splitlines() if x]
    row = sorted(rows, key=lambda r: r["ex"])[0]
    aer = (corpus / row["paths"]["aer"]).read_bytes()
    prov_path = next(iter(row["paths"]["prov"].values()))["json"]
    prov = json.loads((corpus / prov_path).read_bytes())
    line = aer.split(b"\n")[1]
    out: dict = {}

    def parse_code(b: bytes) -> str:
        try:
            obj = strict_parse(b, Counter())
        except StrictError as exc:
            return f"strict:{exc.code}"
        try:
            return "ok" if jcs(obj) == b else "jcs_mismatch"
        except JcsError as exc:
            return f"jcs:{exc.code}"

    d = json.loads(line)
    k0 = sorted(d)[0]
    out["baseline_line"] = parse_code(line)
    out["duplicate_key"] = parse_code(line[:-1] + b',"' + k0.encode() + b'":1}')
    out["nan"] = parse_code(line[:-1] + b',"zz":NaN}')
    out["overflow_1e400"] = parse_code(line[:-1] + b',"zz":1e400}')
    out["whitespace"] = parse_code(line.replace(b":", b": ", 1))
    out["key_reordered"] = parse_code(json.dumps(dict(reversed(list(d.items()))), separators=(",", ":"), ensure_ascii=False).encode())
    out["float_1_0"] = parse_code(line[:-1] + b',"zz":1.0}')
    out["escaped_lone_surrogate"] = parse_code(line[:-1] + b',"zz":"\\ud800"}')
    out["uppercase_hex_escape"] = parse_code(line[:-1] + b',"zz":"\\u001F"}')
    out["bom"] = parse_code(b"\xef\xbb\xbf" + line)
    out["trailing_data"] = parse_code(line + b" 1")
    out["big_int_flag"] = (lambda f: (strict_parse(line[:-1] + b',"zz":9007199254740993}', f), dict(f))[1])(Counter())

    exam2_scan._init(str(corpus))

    def prov_counts(doc: dict) -> dict:
        acc = exam2_scan.Acc("x")
        o: dict = {}
        exam2_scan.prov_checks(acc, doc, o)
        return {k: v for k, v in acc.c.items() if k.startswith(("p01|strict", "p02|", "p03|c51", "p04|", "p06|", "p11|"))}

    out["prov_baseline"] = prov_counts(prov)
    core = next(b for n, b in prov["bundle"].items() if ".core." in n)
    ents = sorted(core["entity"])
    m = copy.deepcopy(prov)
    mc = next(b for n, b in m["bundle"].items() if ".core." in n)
    mc.setdefault("wasDerivedFrom", {})["x:t1.aaaaaaaaaaaaaaaa"] = {"prov:generatedEntity": ents[0], "prov:usedEntity": ents[1]}
    mc["wasDerivedFrom"]["x:t2.aaaaaaaaaaaaaaaa"] = {"prov:generatedEntity": ents[1], "prov:usedEntity": ents[0]}
    out["derivation_cycle"] = prov_counts(m)
    m = copy.deepcopy(prov)
    mc = next(b for n, b in m["bundle"].items() if ".core." in n)
    gen_id = next(iter(mc["wasGeneratedBy"]))
    mc.setdefault("wasDerivedFrom", {})["x:t3.aaaaaaaaaaaaaaaa"] = {"prov:generatedEntity": ents[0], "prov:usedEntity": ents[1], "prov:generation": gen_id}
    out["c51_no_activity"] = prov_counts(m)
    m = copy.deepcopy(prov)
    inf = next((b for n, b in m["bundle"].items() if "wasStartedBy" in b), None)
    if inf is not None:
        k, v = next(iter(inf["wasStartedBy"].items()))
        inf["wasStartedBy"]["x:start_tool.bbbbbbbbbbbbbbbb"] = dict(v)
        out["c26_duplicate_start"] = prov_counts(m)
    m = copy.deepcopy(prov)
    mc = next(b for n, b in m["bundle"].items() if ".core." in n)
    k = next(iter(mc["used"]))
    mc["used"][k] = dict(mc["used"][k], **{"prov:entity": "x:does-not-exist"})
    out["dangling_argument"] = prov_counts(m)
    m = copy.deepcopy(prov)
    mc = next(b for n, b in m["bundle"].items() if ".core." in n)
    act = next(iter(mc["activity"]))
    e_new = "x:loop-entity"
    mc["entity"][e_new] = {}
    mc["wasGeneratedBy"]["x:g.cccccccccccccccc"] = {"prov:entity": e_new, "prov:activity": act}
    mc["used"]["x:u.cccccccccccccccc"] = {"prov:activity": act, "prov:entity": e_new}
    out["dependency_self_loop"] = prov_counts(m)
    return {"source_ex": row["ex"], "results": out}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out")
    a = ap.parse_args()
    rep = {"x04": x04(), "c00": c00(Path(a.corpus).expanduser())}
    text = json.dumps(rep, indent=1, sort_keys=True)
    if a.out:
        Path(a.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
