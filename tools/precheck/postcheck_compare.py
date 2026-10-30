"""Compare the post-check outputs of one corpus (``docs/reports/postcheck/data/<corpus>/``) with the round's records and
the pre-check, and write ``exam.json`` there (docs/reports/postcheck/README.md, checks PC0-PC11).

    uv run python tools/precheck/postcheck_compare.py --corpus C [--corpus C ...] | --all

Inputs, all committed or produced by ``run_postcheck.py``: the post-check data files, the round's
``docs/reports/regeneration/round/<corpus>/compare.json`` and the pre-check's ``docs/reports/precheck/data/<pre>/
l2-<part>.json``. Every comparison is of counts: a flattened numeric leaf of the Level-2 document (``executions``,
``issues``, ``prov``, ``outcomes``, ``identity``, ``redaction``) is listed when it differs, with both values. Nothing is
read from a corpus.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_postcheck import CORPORA, DATA, PRE, Corpus  # noqa: E402

REPO: Final = Path(__file__).resolve().parents[2]
ROUND: Final = REPO / "docs" / "reports" / "regeneration" / "round"
SECTIONS: Final = ("executions", "issues", "prov", "outcomes", "identity", "redaction", "withholding")
#: leaves that name a stage or profile version and so differ by construction (SEM profile suites@1 -> @2, D-31)
_RENAMED: Final = ("executions.stages.", "executions.register_codes.")
_CAP: Final = 400


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def flatten(doc: Any, prefix: str = "") -> dict[str, float]:
    """Numeric leaves of ``doc`` by dotted path (booleans and strings are left out; list members by index)."""
    out: dict[str, float] = {}
    if isinstance(doc, Mapping):
        for key, value in doc.items():
            out.update(flatten(value, f"{prefix}{key}."))
    elif isinstance(doc, list):
        for n, value in enumerate(doc):
            out.update(flatten(value, f"{prefix}{n}."))
    elif isinstance(doc, (int, float)) and not isinstance(doc, bool):
        out[prefix.rstrip(".")] = doc
    return out


def leaf_diff(old: Mapping[str, Any] | None, new: Mapping[str, Any] | None,
              sections: Sequence[str] = SECTIONS) -> dict[str, Any]:  # fmt: skip
    """The numeric leaves of ``sections`` that differ (``wilson95`` and ``rate`` are left out: they follow ``k``/``n``)."""
    if old is None or new is None:
        return {"available": False}
    a = {k: v for s in sections for k, v in flatten(old.get(s), f"{s}.").items()}
    b = {k: v for s in sections for k, v in flatten(new.get(s), f"{s}.").items()}
    keys = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k) and ".wilson95." not in k and not k.endswith(".rate"))
    by_section = Counter(k.split(".", 1)[0] for k in keys)
    return {"available": True, "n_changed": len(keys), "by_section": dict(sorted(by_section.items())),
            "changed": [{"leaf": k, "old": a.get(k), "new": b.get(k)} for k in keys[:_CAP]], "truncated": len(keys) > _CAP}


def sem_net(old: Mapping[str, Any] | None, new: Mapping[str, Any] | None) -> dict[str, Any]:
    """The SEM census, rg1 - p10, by ``type class`` (the round compare's key) and by ``type class variant``."""
    def agg(doc: Mapping[str, Any] | None, with_variant: bool) -> Counter[str]:
        c: Counter[str] = Counter()
        for key, n in ((doc or {}).get("sem_census") or {}).get("by_profile_type_class_variant", {}).items():
            _profile, kind, ev, variant = key.split("|", 3)
            c[f"{kind} {ev}" + (f" {variant}" if with_variant else "")] += n
        return c

    out: dict[str, Any] = {}
    for name, flag in (("by_type_class", False), ("by_type_class_variant", True)):
        a, b = agg(old, flag), agg(new, flag)
        out[name] = {k: b.get(k, 0) - a.get(k, 0) for k in sorted(set(a) | set(b)) if b.get(k, 0) != a.get(k, 0)}
    out["totals"] = {"old": sum(agg(old, False).values()), "new": sum(agg(new, False).values())}
    return out


def outcome_values(doc: Mapping[str, Any] | None) -> dict[str, tuple[int, int]]:
    """Per ``arm | measure``: ``(k, n)`` of the judgement counts (PC8)."""
    out = {}
    for arm, measures in (((doc or {}).get("outcomes") or {}).get("arms") or {}).items():
        for measure, v in measures.items():
            if isinstance(v, Mapping) and "k" in v and "n" in v:
                out[f"{arm}|{measure}"] = (int(v["k"]), int(v["n"]))
    return out


def compare(c: Corpus) -> dict[str, Any]:
    """``exam.json`` of ``c``. For a variant (``c.data``, e.g. ``adprov-v1-release-rg2``) the predecessor's
    full-population and sample files are read from the base corpus's directory when absent from the variant's, and the
    round's compare is the base corpus's (rg1 against p10), kept for reference only."""
    d = DATA / c.name
    base = DATA / c.id
    rnd = _load(ROUND / c.id / "compare.json") or {}
    raw, ids = _load(d / "raw.json"), _load(d / "ids.json")

    def old_file(name: str) -> Path:
        return d / name if (d / name).is_file() else base / name

    full_old, full_new = _load(old_file(f"l2-full-{c.old_tag}.json")), _load(d / f"l2-full-{c.new_tag}.json")
    exam: dict[str, Any] = {"format": "agentprov-postcheck-exam/0.1", "corpus_id": c.id, "tree": c.new,
                            "predecessor": c.old}
    exam["PC1_raw"] = None if raw is None else {
        "objects_equal": raw["objects"]["only_old"] == raw["objects"]["only_new"] == raw["objects"]["size_mismatch"] == 0,
        "objects": raw["objects"]["new"], "origins_rows_equal": raw["origins"]["equal"],
        "origin_pairs_equal": raw["origins"].get("object_origin_pairs_equal"), "members_rows_equal": raw["members"]["equal"],
        "origins": {k: raw["origins"][k] for k in ("old", "new", "only_old", "only_new")},
        "members": {k: raw["members"][k] for k in ("old", "new", "only_old", "only_new")}}  # fmt: skip
    if ids is not None:
        mine = {k: v for k, v in ids["transitions"]["completeness"].items()}
        exam["PC2_ids"] = {"executions": ids["executions"], "completeness_equals_round": mine == rnd.get("completeness"),
                           "completeness": mine, "issues_net": ids["issues"]["net"],
                           "issues_net_equals_round": ids["issues"]["net"] == (rnd.get("issue_codes_net") or {}),
                           "status": ids["transitions"]["status"], "unit": ids["transitions"]["unit"],
                           "raw_refs_changed": ids["raw_refs_changed"], "stage_digests_changed": ids["stage_digests_changed"],
                           "round_executions_changed": rnd.get("executions_changed")}  # fmt: skip
    for pc, step in (("PC3_verify", "verify"), ("PC4_dryrun", "dryrun"), ("PC5_validate", "validate")):
        doc = _load(d / f"{step}.json")
        exam[pc] = None if doc is None else {k: doc.get(k) for k in ("exit_code", "outcome", "counters", "issues_by_code",
                                                                       "refusal")} | {"failures": doc.get("failures")}
    if full_old is not None and full_new is not None:
        net = sem_net(full_old, full_new)
        round_sem = {k: v for k, v in (rnd.get("sem_annotations_net_by_kind_class") or {}).items() if v}
        exam["PC6_full"] = {"executions": {"old": full_old["executions"]["n"], "new": full_new["executions"]["n"]},
                            "degenerate": [full_old["executions"]["degenerate"], full_new["executions"]["degenerate"]],
                            "adapter_defect": [full_old["executions"]["adapter_defect"], full_new["executions"]["adapter_defect"]],
                            "unreadable": [full_old["executions"]["unreadable"], full_new["executions"]["unreadable"]],
                            "sem_net": net, "sem_net_equals_round": net["by_type_class"] == round_sem,
                            "round_sem_net": round_sem, "diff": leaf_diff(full_old, full_new)}  # fmt: skip
        a, b = outcome_values(full_old), outcome_values(full_new)
        moved = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
        exam["PC8_outcomes"] = {"arm_measures": len(b), "moved": len(moved),
                                "moved_first": [{"arm_measure": k, "old": a.get(k), "new": b.get(k)} for k in moved[:50]]}
    parts = {}
    for p in c.parts:
        pre = _load(PRE / p.pre / f"l2-{p.part}.json")
        s_old = _load(old_file(f"l2-sample-{p.part}-{c.old_tag}.json"))
        s_new = _load(d / f"l2-sample-{p.part}-{c.new_tag}.json")
        tie, scratch = _load(d / f"tie-{p.part}.json"), _load(d / f"l2-scratch-{p.part}.json")
        parts[p.part] = {
            "sample_join_rg1": None if s_new is None else s_new.get("sample_join"),
            "precheck_code": None if pre is None else (pre.get("code") or {}).get("commit"),
            "precheck_vs_rg1": leaf_diff(pre, s_new), "p10_vs_rg1": leaf_diff(s_old, s_new),
            "scratch_vs_rg1": leaf_diff(scratch, s_new, ("executions", "issues", "prov", "outcomes")),
            "tie": None if tie is None else {"executions": tie["executions"], "stage_code_equal": tie["stage_code_equal"]},
            "scratch_commands": None if scratch is None else {
                k: {"exit_code": v.get("exit_code"), "outcome": v.get("outcome"), "issues_by_code": v.get("issues_by_code")}
                if isinstance(v, Mapping) and "exit_code" in v else (v if not isinstance(v, Mapping) else
                {kk: vv for kk, vv in v.items() if kk in ("changed", "unexplained", "failed", "identical", "error", "counts")})
                for k, v in (scratch.get("commands") or {}).items()},
        }  # fmt: skip
    exam["PC7_sample"] = parts
    scan = _load(d / "scan.json")
    exam["PC10_scan"] = None if scan is None else {k: scan.get(k) for k in ("native", "gitleaks")}
    seal = _load(d / "seal-forecast.json")
    exam["PC11_seal"] = None if seal is None else {k: seal.get(k) for k in ("refused", "steps", "card_lint", "statements",
                                                                            "withholding_policy", "row_modes")}
    return exam


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--corpus", action="append", default=[])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--variant", action="append", default=[], help="ID:NEW:OLD, as run_postcheck.py --variant")
    a = ap.parse_args(argv)
    from l2_common import guard_output, write_json

    corpora = list(CORPORA)
    for v in a.variant:
        cid, new, old = v.split(":")
        base_c = next(x for x in CORPORA if x.id == cid)
        corpora.append(Corpus(cid, base_c.parts, new=new, old=old, data=f"{cid}-{new}"))
    for c in corpora:
        if not a.all and c.id not in a.corpus and c.name not in a.corpus:
            continue
        if a.all and c.data and c.name not in a.corpus and not a.variant:
            continue
        exam = compare(c)
        out = DATA / c.name / "exam.json"
        guard_output(out)
        write_json(out, exam)
        print(json.dumps({"corpus": c.id, "out": str(out.relative_to(REPO))}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
