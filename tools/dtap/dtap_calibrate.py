"""Fault-injection calibration of ``tools/dtap/dtap_check.py`` (protocol section 2.1 step 2; C00 analogue for DT01-DT13).

    uv run python -I tools/dtap/dtap_calibrate.py --corpus DIR --rows ROWS.jsonl --tasks TASKS_TREE --work SCRATCH --out OUT.json

For each fault, one execution with the needed feature is chosen from a baseline ``dtap_check.py scan`` (``--rows``; the
first by id), its index row, AER, SEM, PROV and raw objects are **copied** into a one-execution scratch corpus under
``--work``, the copy is mutated, and the check is re-run on the copy. A fault is *detected* when the named check fails on
the mutated copy and did not fail on the original. The corpus itself is never written. Prints counts and ids only; the
``env_vars`` sentinel is a value of the pinned configurations and is never printed.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dtap_check as dc  # noqa: E402

Lines = list[dict[str, Any]]


def _read(path: Path) -> Lines:
    return [json.loads(x) for x in path.read_bytes().split(b"\n") if x]


def _write(path: Path, lines: Lines) -> None:
    path.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines), encoding="utf-8")


def copy_execution(root: Path, row: dict[str, Any], work: Path) -> Path:
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    rels = [row["paths"]["aer"], *(row["paths"].get("sem") or {}).values()]
    rels += [v for forms in (row["paths"].get("prov") or {}).values() for v in (forms or {}).values()]
    for rel in rels:
        (work / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / rel, work / rel)
    head = json.loads((root / row["paths"]["aer"]).read_bytes().split(b"\n", 1)[0])
    for a in head.get("artifacts") or ():
        h = str(a["sha256"]).removeprefix("sha256:")
        for p in (root / "raw" / "objects" / h[:2]).glob(h + "*"):
            (work / "raw" / "objects" / h[:2]).mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, work / "raw" / "objects" / h[:2] / p.name)
    (work / "executions.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    (work / "register.jsonl").write_text("", encoding="utf-8")
    return work


def run_check(work: Path, row: dict[str, Any]) -> dict[str, Any]:
    dc._init(str(work))  # noqa: SLF001 - the scan's own per-process setup
    return dc.job(json.dumps(row).encode())


# ------------------------------------------------------------------------------------------------ mutations
def m_sem(pred: Callable[[dict[str, Any]], bool], change: Callable[[dict[str, Any]], None]) -> Callable[[Path, dict[str, Any]], bool]:
    def apply(work: Path, row: dict[str, Any]) -> bool:
        for rel in (row["paths"].get("sem") or {}).values():
            lines = _read(work / rel)
            for a in lines:
                if a.get("k") == "ann" and pred(a):
                    change(a)
                    _write(work / rel, lines)
                    return True
        return False
    return apply


def m_aer(pred: Callable[[dict[str, Any]], bool], change: Callable[[dict[str, Any]], None]) -> Callable[[Path, dict[str, Any]], bool]:
    def apply(work: Path, row: dict[str, Any]) -> bool:
        lines = _read(work / row["paths"]["aer"])
        for r in lines:
            if pred(r):
                change(r)
                _write(work / row["paths"]["aer"], lines)
                return True
        return False
    return apply


def m_prov(change: Callable[[dict[str, Any]], bool]) -> Callable[[Path, dict[str, Any]], bool]:
    def apply(work: Path, row: dict[str, Any]) -> bool:
        rel = row["paths"]["prov"][dc.SPEC]["json"]
        doc = json.loads((work / rel).read_bytes())
        ok = change(doc)
        (work / rel).write_text(json.dumps(doc), encoding="utf-8")
        return ok
    return apply


def _exposure_cls(cls: str) -> Callable[[dict[str, Any]], bool]:
    return lambda a: a.get("type") == "dtap.exposure" and (a.get("value") or {}).get("class") == cls


def _set_class(a: dict[str, Any]) -> None:
    a["value"]["class"] = "logged_absent" if a["value"]["class"] != "logged_absent" else "configured_only"


def _assess_ev(cls_ids: set[str], to: str) -> Callable[[dict[str, Any]], bool]:
    def change(doc: dict[str, Any]) -> bool:
        for iri, body in doc.get("bundle", {}).items():
            if ".assess." not in iri:
                continue
            for attrs in (body.get("entity") or {}).values():
                if str(attrs.get("apv:annotationId")) in cls_ids:
                    attrs["apv:evidenceClass"] = {"$": to, "type": "prov:QUALIFIED_NAME"}
                    return True
        return False
    return change


def _add_time(doc: dict[str, Any]) -> bool:
    for iri, body in doc.get("bundle", {}).items():
        if ".core." in iri and body.get("activity"):
            next(iter(body["activity"].values()))["prov:endTime"] = "2026-01-01T00:00:00Z"
            return True
    return False


def _move_link(r: dict[str, Any]) -> None:
    part = r["parts"][0]
    part["responds_to"] = "m0#0" if part.get("responds_to") != "m0#0" else "m1#0"


def _drop_issue(code: str) -> Callable[[dict[str, Any]], None]:
    def change(seal: dict[str, Any]) -> None:
        seal["issues"] = [i for i in seal["issues"] if i.get("code") != code]
    return change


def _bump_arg(r: dict[str, Any]) -> None:
    part = r["parts"][0]
    part["args"] = {**(part.get("args") or {}), "__calibration__": 1} if isinstance(part.get("args"), dict) else {"__calibration__": 1}


def _tier_b(r: dict[str, Any]) -> None:
    r["ext"]["dtap"]["join"]["tier"] = "B"


def _flip_marker(a: dict[str, Any]) -> None:
    a["value"]["status"] = "absent" if a["value"]["status"] == "present" else "present"


def _add_endorser(a: dict[str, Any]) -> None:
    a["value"] = sorted({*a["value"], "endorser"})


def _subject_to_endorser(work: Path, row: dict[str, Any]) -> bool:
    """Relabel, as ``endorser`` only, a request that is an ``apv:PotentiallyInfluencedBy`` subject in the PROV."""
    doc = json.loads((work / row["paths"]["prov"][dc.SPEC]["json"]).read_bytes())
    subjects = set()
    for iri, body in doc.get("bundle", {}).items():
        for attrs in (body.get("entity") or {}).values() if ".assess." in iri else ():
            claim = attrs.get("apv:claim")
            if (claim.get("$") if isinstance(claim, dict) else claim) == "apv:PotentiallyInfluencedBy":
                subj = attrs.get("apv:subject")
                subjects.add(str(subj.get("$") if isinstance(subj, dict) else subj))
    return m_sem(lambda x: x.get("type") == "role" and f"x:{str(x.get('target')).replace('#', '-')}" in subjects,
                 lambda x: x.update(value=["endorser"]))(work, row)


def _env_sentinel(value: str) -> Callable[[Path, dict[str, Any]], bool]:
    def apply(work: Path, row: dict[str, Any]) -> bool:
        lines = _read(work / row["paths"]["aer"])
        for r in lines:
            if r.get("k") == "message" and r.get("role") == "agent":
                for p in r.get("parts") or []:
                    if isinstance(p.get("text"), str):
                        p["text"] += " " + value
                        _write(work / row["paths"]["aer"], lines)
                        return True
        return False
    return apply


def _env_key_in_sem(work: Path, row: dict[str, Any]) -> bool:
    rel = next(iter((row["paths"].get("sem") or {}).values()))
    lines = _read(work / rel)
    lines[1].setdefault("value", {})
    lines[1]["env_vars"] = {"X": "calibration"}
    _write(work / rel, lines)
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--corpus", required=True, type=Path)
    ap.add_argument("--rows", required=True, type=Path)
    ap.add_argument("--tasks", required=True, type=Path)
    ap.add_argument("--work", required=True, type=Path)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    root = a.corpus if (a.corpus / "executions.jsonl").exists() else a.corpus.with_name(a.corpus.name + ".partial")
    index = {json.loads(x)["ex"]: json.loads(x) for x in (root / "executions.jsonl").read_bytes().splitlines() if x}
    base = sorted((json.loads(x) for x in a.rows.read_text(encoding="utf-8").splitlines() if x), key=lambda r: r["ex"])
    clean = [r for r in base if not r["fail"] and r["ex"] in index]

    def has(prefix: str) -> Callable[[dict[str, Any]], bool]:
        return lambda r: any(k.startswith(prefix) and v for k, v in r["c"].items())

    _counts, _keys, values = dc.env_values(a.tasks)
    sentinel = sorted(v for v in values if len(v) >= 16)[0]
    faults: list[tuple[str, str, Callable[[dict[str, Any]], bool], Callable[[Path, dict[str, Any]], bool]]] = [
        ("DT02", "tool-call argument changed", has("dt05|"),
         m_aer(lambda r: r.get("k") == "message" and r.get("role") == "agent" and (r.get("parts") or [{}])[0].get("t") == "tool_call", _bump_arg)),
        ("DT03", "marker status flipped", has("dt03|injection_marker|sem=absent"),
         m_sem(lambda x: x.get("type") == "injection_marker", _flip_marker)),
        ("DT04", "observed exposure class changed", has("dt04|own=observed_tool_output"),
         m_sem(_exposure_cls("observed_tool_output"), _set_class)),
        ("DT04", "observed class demoted to I (SEM ev)", has("dt04|own=observed_tool_output"),
         m_sem(_exposure_cls("observed_tool_output"), lambda x: x.update(ev="I"))),
        ("DT04", "configured_only promoted to D (PROV)", has("dt04|own=configured_only"), None),  # set below (needs the id)
        ("DT05", "pairing link moved", has("dt05|claudesdk|links_checked"),
         m_aer(lambda r: r.get("k") == "message" and r.get("role") == "tool" and "responds_to" in (r.get("parts") or [{}])[0], _move_link)),
        ("DT05", "ambiguous-batch issue removed", has("dt05|claudesdk|calls_in_multi_call_batches"),
         m_aer(lambda r: r.get("k") == "seal", _drop_issue("dtap.pairing_ambiguous_batch"))),
        ("DT06", "tier A changed to B", lambda r: r["info"].get("join") == ["joined", "A"] and has("dt04|")(r),
         m_aer(lambda r: r.get("k") == "execution", _tier_b)),
        ("DT07", "audit revises link dropped", has("dt07|audit_corrected"),
         m_aer(lambda r: r.get("k") == "judgement" and bool(r.get("revises")), lambda r: r.pop("revises"))),
        ("DT08", "prov:endTime on a core activity", has("dt08|"), m_prov(_add_time)),
        ("DT08", "t on a message record", has("dt08|"),
         m_aer(lambda r: r.get("k") == "message", lambda r: r.update(t={"raw": {"end": "x"}}))),
        ("DT13", "endorser on a sink", has("dt09|role|write_sink"),
         m_sem(lambda x: x.get("type") == "role" and "write_sink" in (x.get("value") or []), _add_endorser)),
        ("DT13", "a taint-subject sink relabelled endorser only", has("dt09|role|write_sink"), _subject_to_endorser),
        ("DT01", "env_vars value in an AER agent text", has("a03|agent_messages"), _env_sentinel(sentinel)),
        ("DT01", "env_vars key in a SEM record", has("a03|agent_messages"), _env_key_in_sem),
    ]
    results: list[dict[str, Any]] = []
    for n, (check, what, want, mutate_spec) in enumerate(faults):
        candidates = [r for r in clean if want(r)][:25]  # the first by id whose copy the fault applies to
        res: dict[str, Any] = {"check": check, "fault": what}
        if not candidates:
            res["result"] = "no_candidate"
            results.append(res)
            continue
        applied = False
        for base_row in candidates:
            row = index[base_row["ex"]]
            work = copy_execution(root, row, a.work / f"f{n:02d}")
            mutate = mutate_spec
            if mutate is None:  # configured_only -> D in the assessment bundle
                sem_lines = _read(work / next(iter(row["paths"]["sem"].values())))
                ids = {str(x["id"]) for x in sem_lines if x.get("type") == "dtap.exposure"
                       and (x.get("value") or {}).get("class") == "configured_only"}
                mutate = m_prov(_assess_ev(ids, "apv:Derived"))
            applied = mutate(work, row)
            if applied:
                break
        res["ex"] = row["ex"]
        if check == "DT01":
            env = dc.envvars(work, a.tasks, [], a.work, 8)
            hits = sum(v for part in ("values", "key_literal") for k, v in env[part]["counts"].items() if "not_in_own_raw" in k)
            res["result"] = "detected" if applied and hits else "missed"
            res["hits_not_in_own_raw"] = hits
        else:
            got = run_check(work, row)
            res["result"] = "detected" if applied and got["fail"].get(check) else ("not_applied" if not applied else "missed")
            res["fired"] = sorted({d.split(":")[0] for d in got["fail"].get(check, [])})
        results.append(res)
        shutil.rmtree(work)
    detected = sum(r["result"] == "detected" for r in results)
    out = {"faults": len(results), "detected": detected, "results": results}
    text = json.dumps(out, indent=1, sort_keys=True)
    if a.out:
        a.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if detected == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
