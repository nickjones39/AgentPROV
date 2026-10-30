"""Choose and copy the qwencode family's test fixtures by criterion (phase 10o part C; D-151 conventions; K.4.1; D-360).

    uv run python -I tools/qwencode/build_fixtures.py RUNS.zip SUPP.zip [--write]

Every fixture is a byte-identical member of a pinned zip, read in memory through ``agentprov.ingest`` (never extracted)
and chosen by structure, never read back or printed. A run fixture brings the files its plan names: the group's API
sample, the scenario's score record file and request file and the execution rules (members of the supplementary zip,
written under ``supp/``). For each criterion the run that adds the fewest bytes is chosen, ties by label; a run already
chosen is reused. Runs holding a home path other than ``/home/user/`` are never candidates. The set must fit the
per-source budget of 512 KiB unless ``tests/FIXTURES.json`` records an exception (``--budget``; qwencode: 800 KiB). Files go to ``tests/fixtures/qwencode/runs/<label>`` and ``supp/<label>``; ``SOURCE.json``
records each file's container, label, method, CRC-32, size, sha256 and licence. Without ``--write`` the plan is printed
(criteria, groups and sizes only, never content).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zlib
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

from agentprov.adapters.qwencode.dialect import API_SAMPLE, SUPP_ROLE, QwenJsonReader, parse_label, parse_output
from agentprov.adapters.runner.importer import _AuxListing
from agentprov.errors import IngestError, MalformedArtefact
from agentprov.ingest.archives import iter_zip_members, open_archive
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "tests" / "fixtures" / "qwencode"
DOI = "10.5281/zenodo.23168099"
BUDGET = 512 * 1024
HOME = re.compile(rb"/(?:Users|home)/(?!user/)[A-Za-z0-9._-]+/")
SUPP_PREFIXES = ("results/Qwen/", "dataset/RedCode-Exec/", "prompt_generator/output/", "OH_evaluation/execution_rules.md")


def read_zip(path: str, want: Callable[[str], bool]) -> tuple[str, str, dict[str, tuple[bytes, int]]]:
    limits = IngestLimits()
    with open(path, "rb") as fp:
        sha = hashlib.sha256(fp.read()).hexdigest()
    out: dict[str, tuple[bytes, int]] = {}
    with open(path, "rb") as fp, open_archive(fp, limits, release=False) as z:
        for m in iter_zip_members(z, want, limits):
            if m.disposition == "selected" and m.label is not None:
                out[m.label] = (z.read_member(m), int(m.method))
    return Path(path).name, sha, out


def features(data: bytes, score: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {"empty": not data, "score": None if score is None else score.get("score")}
    if not data:
        return out
    try:
        parsed = parse_output(data, IngestLimits())
    except (IngestError, MalformedArtefact):
        out["broken"] = True
        return out
    msgs = parsed.messages
    blocks = [c for m in msgs if m.get("type") == "assistant" for c in m["message"]["content"]]
    results = [c for m in msgs if m.get("type") == "user" for c in m["message"]["content"] if c.get("type") == "tool_result"]
    res = next((m for m in msgs if m.get("type") == "result"), None)
    a_out = sum(m["message"]["usage"]["output_tokens"] for m in msgs if m.get("type") == "assistant")
    out.update({
        "truncated": parsed.cut is not None,
        "calls": sum(1 for c in blocks if c.get("type") == "tool_use"),
        "tool_error": any(c.get("is_error") for c in results),
        "multi_block": any(len(m["message"]["content"]) > 1 for m in msgs if m.get("type") == "assistant"),
        "subagent": any(m.get("type") == "system" and m.get("subtype") != "init" for m in msgs),
        "user_text": any(c.get("type") == "text" for m in msgs if m.get("type") == "user" for c in m["message"]["content"]),
        "usage_above": res is not None and res["usage"]["output_tokens"] > a_out,
        "cap": bool(score and score.get("exceeded_soft_iteration_cap")),
    })
    return out


CRITERIA: list[tuple[str, Callable[[dict[str, Any], Any], bool]]] = [
    ("s1_dataset_request", lambda f, x: x.target == "S1" and f.get("calls", 0) > 0),
    ("s2_s3_prompt_request", lambda f, x: x.target in ("S2", "S3") and f.get("calls", 0) > 0),
    ("python", lambda f, x: x.language == "python" and f.get("calls", 0) > 0),
    ("bash_suffix", lambda f, x: x.language == "bash" and x.suffix == "sh" and f.get("calls", 0) > 0),
    ("executed_score_3", lambda f, x: f.get("score") == 3 and not f.get("truncated")),
    ("refused_score_0", lambda f, x: f.get("score") == 0 and not f.get("empty")),
    ("score_1_ambiguous", lambda f, x: f.get("score") == 1 and not f.get("empty")),
    ("tool_error", lambda f, x: f.get("tool_error")),
    ("multi_block_message", lambda f, x: f.get("multi_block")),
    ("usage_above_logged", lambda f, x: f.get("usage_above")),
    ("soft_cap_exceeded", lambda f, x: f.get("cap") and not f.get("empty")),
    ("subagent", lambda f, x: f.get("subagent")),
    ("user_text", lambda f, x: f.get("user_text")),
    ("truncated_capture", lambda f, x: f.get("truncated")),
    ("empty_output", lambda f, x: f.get("empty")),
]
#: One group's API sample is a fixture (its own criterion); every other run maps without one, as a run whose group sample
#: is missing would.
API_SAMPLE_GROUP: Final = ("S2", "bash")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs")
    ap.add_argument("supp")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--budget", type=int, default=BUDGET, help="bytes; above 512 KiB only with a tests/FIXTURES.json exception")
    args = ap.parse_args(argv)
    runs_name, runs_sha, runs = read_zip(args.runs, lambda label: "/trajectory/" in label)
    supp_name, supp_sha, supp = read_zip(args.supp, lambda label: label.startswith(SUPP_PREFIXES) and "/OH/" not in label)
    listing = _AuxListing(sorted(runs), {SUPP_ROLE: sorted(supp)})
    reader = QwenJsonReader()
    scores: dict[tuple[str, str, str], dict[str, Any]] = {}
    for label, (data, _m) in supp.items():
        if label.startswith("results/Qwen/") and "/conversation_log/index" in label:
            p = label.split("/")
            for e in strict_json_loads(data, IngestLimits()):
                scores[(p[3], p[4], str(e["index"]))] = e
    cands: list[tuple[str, set[str], dict[str, Any], Any]] = []
    excluded = 0
    for label in sorted(runs):
        f = parse_label(label)
        if f is None:
            continue
        plan = reader.auxiliary_for(label, listing)
        files = {label} | {ref for role, ref in plan.items() if role != "api_sample"}
        if any(HOME.search(runs[x][0] if x in runs else supp[x.split(":", 1)[1]][0]) for x in files):
            excluded += 1
            continue
        cands.append((label, files, features(runs[label][0], scores.get((f.target, f.language, f.case_key))), f))

    def size(ref: str) -> int:
        return len(runs[ref][0]) if ref in runs else len(supp[ref.split(":", 1)[1]][0])

    chosen: dict[str, list[str]] = {}
    have: set[str] = set()
    sat = {c[0]: {name for name, test in CRITERIA if test(c[2], c[3])} for c in cands}
    uncovered = {name for name, _t in CRITERIA if any(name in v for v in sat.values())}
    for name, _t in CRITERIA:
        if name not in uncovered:
            print(f"no run for {name}")
    while uncovered:  # greedy weighted set cover: most uncovered criteria per added byte, ties by label
        def gain(c: tuple[str, set[str], dict[str, Any], Any], open_: set[str] = uncovered,
                 got: set[str] = have) -> tuple[float, str]:
            new = len(sat[c[0]] & open_)
            cost = sum(size(x) for x in c[1] - got) + 1
            return (-(new / cost) if new else 0.0, c[0])
        best = min((c for c in cands if sat[c[0]] & uncovered), key=gain)
        chosen[best[0]] = sorted(sat[best[0]] & uncovered)
        uncovered -= sat[best[0]]
        have |= best[1]
    sample = next((lab for lab in runs if lab.endswith(API_SAMPLE) and lab.split("/")[3:5] == list(API_SAMPLE_GROUP)), None)
    if sample is not None:
        have.add(sample)
    total = sum(size(x) for x in have)
    for label in sorted(chosen):
        f = parse_label(label)
        assert f is not None
        print(f"{size(label):>8}  {f.target}/{f.language:<6}  {', '.join(chosen[label])}")
    print(f"runs {len(chosen)}, files {len(have)}, bytes {total} (budget {args.budget}); runs excluded for a home path: {excluded}")
    if total > args.budget:
        print("over budget")
        return 1
    if not args.write:
        return 0
    crit_of: dict[str, list[str]] = {sample: ["api_sample"]} if sample is not None else {}
    for label, crits in chosen.items():
        for ref in next(c[1] for c in cands if c[0] == label):
            crit_of.setdefault(ref, []).extend(crits)
    entries = []
    for ref in sorted(have):
        in_supp = ref.startswith(SUPP_ROLE + ":")
        label = ref.split(":", 1)[1] if in_supp else ref
        data, method = (supp if in_supp else runs)[label]
        sample = f"{'supp' if in_supp else 'runs'}/{label}"
        target = OUT / sample
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        container, csha = (supp_name, supp_sha) if in_supp else (runs_name, runs_sha)
        entries.append({"sample_file": sample, "label": label, "pin_role": SUPP_ROLE if in_supp else "runs",
                        "url": f"https://zenodo.org/records/23168099/files/{container}", "repository": f"https://doi.org/{DOI}",
                        "commit_or_revision": DOI,
                        "record_locator": {"container": container, "container_sha256": csha, "member": label, "method": method,
                                           "crc32": f"{zlib.crc32(data):08x}", "size": len(data)},
                        "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data), "licence": "CC-BY-4.0",
                        "licence_class": "permissive", "synthetic": False, "retrieved_at": "2026-10-12",
                        "note": "phase 10o part C fixture, criteria " + ", ".join(sorted(set(crit_of.get(ref, []))))})
    (OUT / "SOURCE.json").write_text(json.dumps(entries, indent=1, ensure_ascii=True) + "\n", encoding="utf-8")
    print("written", len(entries))
    return 0


if __name__ == "__main__":
    sys.exit(main())
