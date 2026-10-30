"""Choose and copy the gemini-cli family's test fixtures by criterion (phase 10o; D-151 conventions; K.4.1).

    uv run python -I tools/geminicli/build_fixtures.py RESULTS_raw.tar.zst [--write]

Every fixture is a byte-identical member of the pinned archive, read in memory through ``agentprov.ingest`` (never
extracted) and chosen by structure, never read back or printed. A fixture is a **rollout directory** (the stream, when
there is one, and every sibling except the ``.log`` files: the repository tracks no ``*.log``, and the mapper treats a
missing log like any absent sidecar), so the reader's sibling plan and the mapper's sidecars are exercised as imported.
For each criterion the smallest rollout that satisfies it is chosen, ties by label; a rollout already chosen for an earlier
criterion is reused. Rollouts are never chosen when any of their files holds a value of the Google API key shape (D-336)
or a home-directory path. The set must fit the per-source budget of 512 KiB (D-360). Files are written to
``tests/fixtures/geminicli/<member label>``; ``SOURCE.json`` records each file's container, label, CRC-32, size, sha256 and
licence. Without ``--write`` the plan is printed (criteria, cells and sizes only, never a label's mutation text beyond the
closed grammar, never content).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import zlib
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agentprov.adapters.geminicli.dialect import STREAM, VERDICT, parse_label
from agentprov.ingest.archives import open_archive
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import NO_VALUE, scan_jsonl, strict_json_loads

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "tests" / "fixtures" / "geminicli"
DOI = "10.5281/zenodo.20404563"
FILE = "RESULTS_raw.tar.zst"
BUDGET = 512 * 1024
KEY_SHAPE = re.compile(rb"AIza[0-9A-Za-z_\-]{35}")
HOME = re.compile(rb"/(?:Users|home)/[A-Za-z0-9._-]+")


def features(files: dict[str, bytes]) -> dict[str, Any]:
    """Structural features of one rollout directory (counts and flags only)."""
    stream = files.get(STREAM)
    verdict = strict_json_loads(files[VERDICT], IngestLimits()) if VERDICT in files else {}
    out: dict[str, Any] = {"stream": "absent" if stream is None else ("empty" if not stream else "ok"),
                           "elicited": bool(verdict.get("elicited")), "harness_events": bool(files.get("events.jsonl"))}
    if not stream:
        return out
    ev = [v for _n, _o, v, _f in scan_jsonl(io.BytesIO(stream), IngestLimits()) if v is not NO_VALUE]
    types = [e.get("type") for e in ev]
    uses = [e for e in ev if e.get("type") == "tool_use"]
    results = [e for e in ev if e.get("type") == "tool_result"]
    result = next((e for e in ev if e.get("type") == "result"), None)
    outstanding, most = set(), 0
    for e in ev:
        if e.get("type") == "tool_use":
            outstanding.add(e.get("tool_id"))
            most = max(most, len(outstanding))
        elif e.get("type") == "tool_result":
            outstanding.discard(e.get("tool_id"))
    names = {e.get("tool_name") for e in uses}
    out.update({
        "result": None if result is None else result.get("status"),
        "last": types[-1],
        "calls": len(uses),
        "text": any(e.get("type") == "message" and e.get("role") == "assistant" for e in ev),
        "notice": "error" in types,
        "tool_error": any(r.get("status") == "error" for r in results),
        "no_output": any(r.get("status") == "success" and "output" not in r for r in results),
        "parallel": most > 1,
        "subagent": "codebase_investigator" in names,
        "counter_differs": result is not None and (result.get("stats") or {}).get("tool_calls") != len(uses),
        "web": "google_web_search" in names,
    })
    return out


CRITERIA: list[tuple[str, Callable[[dict[str, Any]], bool]]] = [
    ("ok_with_text_and_calls", lambda f: f["stream"] == "ok" and f["result"] == "success" and f["text"] and f["calls"] > 0),
    ("error_result", lambda f: f["stream"] == "ok" and f["result"] == "error"),
    ("cli_notice", lambda f: f["stream"] == "ok" and f["notice"]),
    ("aborted_unanswered_call", lambda f: f["stream"] == "ok" and f["result"] is None and f["last"] == "tool_use"),
    ("aborted_after_result", lambda f: f["stream"] == "ok" and f["result"] is None and f["last"] == "tool_result"),
    ("parallel_calls", lambda f: f["stream"] == "ok" and f["parallel"]),
    ("tool_error_status", lambda f: f["stream"] == "ok" and f["tool_error"]),
    ("success_without_output", lambda f: f["stream"] == "ok" and f["no_output"]),
    ("subagent_counter_differs", lambda f: f["stream"] == "ok" and f["subagent"] and f["counter_differs"]),
    ("web_search", lambda f: f["stream"] == "ok" and f["web"]),
    ("elicited", lambda f: f["stream"] == "ok" and f["elicited"]),
    ("empty_stream", lambda f: f["stream"] == "empty"),
    ("no_stream_with_harness_events", lambda f: f["stream"] == "absent" and f["harness_events"]),
]
CELLS = ("MiniMax-M2", "claude-sonnet-4-6", "gemini-2.5-pro", "glm-4.7-probe", "gpt-5.3-codex")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("archive")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    limits = IngestLimits()
    with open(args.archive, "rb") as fp:
        container = hashlib.sha256(fp.read()).hexdigest()
    dirs: dict[str, dict[str, bytes]] = defaultdict(dict)
    with open(args.archive, "rb") as fp, open_archive(fp, limits, release=False) as tar:
        for m in tar.iter_members(lambda label: (f := parse_label(label)) is not None and f.scaffold == "gemini_cli", limits):
            if m.disposition == "selected" and m.label is not None:
                name = m.label.rsplit("/", 1)[-1]
                if not name.endswith(".log"):  # repository hygiene: no tracked *.log (tests/repo)
                    dirs[m.label.rpartition("/")[0]][name] = tar.read_member(m)
    candidates: list[tuple[int, str, dict[str, Any]]] = []
    excluded = 0
    for d, files in dirs.items():
        if any(KEY_SHAPE.search(b) or HOME.search(b) for b in files.values()):
            excluded += 1
            continue
        candidates.append((sum(len(b) for b in files.values()), d, features(files)))
    candidates.sort(key=lambda c: (c[0], c[1]))
    chosen: dict[str, list[str]] = {}

    def pick(name: str, test: Callable[[dict[str, Any]], bool]) -> None:
        for _size, d, f in candidates:
            if d in chosen and test(f):
                chosen[d].append(name)
                return
        for _size, d, f in candidates:
            if test(f):
                chosen.setdefault(d, []).append(name)
                return
        print(f"no rollout for {name}")

    for name, test in CRITERIA:
        pick(name, test)
    # per-cell coverage: a chosen rollout of the cell with a stream, else the cell's smallest one
    feats = {d: f for _size, d, f in candidates}
    for model in CELLS:
        def of_cell(d: str, model: str = model) -> bool:
            facets = parse_label(d + "/x")
            return facets is not None and facets.model == model and feats[d]["stream"] == "ok"
        hit = next((d for d in sorted(chosen) if of_cell(d)), None)
        if hit is None:
            hit = next((d for _size, d, _f in candidates if of_cell(d)), None)
        if hit is None:
            print(f"no rollout for cell:{model}")
            continue
        chosen.setdefault(hit, []).append(f"cell:{model}")
    total = sum(len(b) for d in chosen for b in dirs[d].values())
    for d in sorted(chosen):
        facets = parse_label(d + "/x")
        assert facets is not None
        print(f"{sum(len(b) for b in dirs[d].values()):>8}  {facets.model:<18} {', '.join(chosen[d])}")
    print(f"rollouts {len(chosen)}, files {sum(len(dirs[d]) for d in chosen)}, bytes {total} (budget {BUDGET}); "
          f"rollouts excluded for a key shape or home path: {excluded}")
    if total > BUDGET:
        print("over budget")
        return 1
    if not args.write:
        return 0
    entries = []
    for d in sorted(chosen):
        for name in sorted(dirs[d]):
            label = f"{d}/{name}"
            data = dirs[d][name]
            target = OUT / label
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            entries.append({"sample_file": label, "label": label, "url": f"https://zenodo.org/records/20404563/files/{FILE}",
                            "repository": f"https://doi.org/{DOI}", "commit_or_revision": DOI,
                            "record_locator": {"container": FILE, "container_sha256": container, "member": label,
                                               "method": 0, "crc32": f"{zlib.crc32(data):08x}", "size": len(data)},
                            "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data), "licence": "CC-BY-4.0",
                            "licence_class": "permissive", "synthetic": False, "retrieved_at": "2026-10-12",
                            "note": "phase 10o fixture, criteria " + ", ".join(chosen[d])})
    (OUT / "SOURCE.json").write_text(json.dumps(entries, indent=1, ensure_ascii=True) + "\n", encoding="utf-8")
    print("written", len(entries))
    return 0


if __name__ == "__main__":
    sys.exit(main())
