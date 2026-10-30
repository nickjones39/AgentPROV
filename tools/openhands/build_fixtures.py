"""Choose and copy the OpenHands family's test fixtures by criterion (phase 10g; D-151 conventions; K.4.1).

    uv run python -I tools/openhands/build_fixtures.py --oas OAS_WORKTREE --zips ZIP_DIR [--write]

Every fixture is a byte-identical pinned file, chosen by structure, never read back or printed. For each criterion the
smallest run (trajectory plus its auxiliary files) that satisfies it is chosen, ties by label; a run already chosen for
an earlier criterion is reused. OpenAgentSafety files are copied with their auxiliary files (evaluation, state, the model
directory's LLM-judge summary, the task directory's task.md, checkpoints.md, scenarios.json and utils/evaluator.py) to
``tests/fixtures/openhands/oas/<path>``; RedCode members with their score record, prompt record or dataset file to
``tests/fixtures/openhands/redcode/<label>`` (read in memory through ``agentprov.ingest``). ``SOURCE.json`` records each
file's origin (git blob id at the pin, or the zip member's container, method, crc32 and size), sha256, size and licence.
Without ``--write`` the plan is printed (labels, criteria and sizes only).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "tests" / "fixtures" / "openhands"
OAS_REPO = "https://github.com/sani903/OpenAgentSafety"
OAS_COMMIT = "857798ff26c4ce6e1d7911ee4d8b3f84a71184e0"
DOI = "10.5281/zenodo.23168099"
NOT_EXECUTED = "The action has not been executed."


def _kind(e: dict[str, Any]) -> tuple[str, str]:
    if "action" in e:
        return "action", str(e["action"])
    return "observation", str(e.get("observation"))


def oas_features(events: list[dict[str, Any]]) -> dict[str, Any]:
    acts: dict[str, int] = {}
    for e in events:
        rid = ((e.get("tool_call_metadata") or {}).get("model_response") or {}).get("id")
        if "action" in e and isinstance(rid, str):
            acts[rid] = acts.get(rid, 0) + 1
    users = [e for e in events if e.get("action") == "message" and e.get("source") == "user"]
    last = events[-1]
    return {
        "chat": any(e.get("observation") == "chat" for e in events),
        "parallel": any(n > 1 for n in acts.values()),
        "notice": last.get("observation") == "error" and last.get("content") == NOT_EXECUTED,
        "uncaused_error": any(e.get("observation") == "error" and "cause" not in e for e in events),
        "later_users": len(users) - 1,
        "set_of_marks": any(isinstance((e.get("extras") or {}).get("set_of_marks"), str) and (e.get("extras") or {})["set_of_marks"]
                            for e in events),
        "agent_text": any(e.get("action") == "message" and e.get("source") == "agent" for e in events),
    }


def oas_plan(root: Path) -> list[tuple[str, list[str], int, str]]:
    from agentprov.adapters.openhands.dialect import OpenHandsEventsReader
    from agentprov.adapters.runner.importer import _AuxListing
    from agentprov.ingest.loaders import strict_json_loads

    labels = [p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and ".git" not in p.parts]
    listing = _AuxListing(labels, {})
    reader = OpenHandsEventsReader()
    runs = []
    state_re = re.compile(r"agent_state=<AgentState\.[A-Z_]+: '([a-z_]+)'>")
    for label in sorted(lab for lab in labels if re.fullmatch(r"evaluation/[^/]+/traj_[^/]+\.json", lab)):
        plan = reader.auxiliary_for(label, listing)
        files = [label, *sorted(plan.values())]
        size = sum((root / f).stat().st_size for f in files)
        if size > 400_000:
            continue
        events = strict_json_loads((root / label).read_bytes())
        feats = oas_features(events)
        feats["eval"] = "eval" in plan
        feats["summary_entry"] = False
        if "llm_judge" in plan:
            task = label.rsplit("/traj_", 1)[1][:-5]
            feats["summary_entry"] = task in strict_json_loads((root / plan["llm_judge"]).read_bytes())
        state = strict_json_loads((root / plan["state"]).read_bytes()) if "state" in plan else None
        found = state_re.findall(state) if isinstance(state, str) else []
        feats["state_error"] = bool(found) and found[-1] == "error"
        feats["draft"] = label.endswith("_draft.json")
        runs.append((label, files, size, feats))
    criteria: list[tuple[str, Callable[[dict[str, Any]], bool]]] = [
        ("O1 npc chat with checkpoint and LLM-judge entry", lambda f: f["chat"] and f["eval"] and f["summary_entry"]),
        ("O2 parallel tool calls of one response", lambda f: f["parallel"]),
        ("O3 run ends with the not-executed notice", lambda f: f["notice"]),
        ("O4 uncaused (harness) error observation", lambda f: f["uncaused_error"]),
        ("O5 simulated-user replies", lambda f: f["later_users"] >= 2),
        ("O6 no evaluation file", lambda f: not f["eval"]),
        ("O7 set-of-marks screenshot", lambda f: f["set_of_marks"]),
        ("O8 the safety-memo_draft task", lambda f: f["draft"]),
        ("O9 agent text reply", lambda f: f["agent_text"] and f["eval"]),
    ]
    return _choose(runs, criteria)


def _choose(runs: list[tuple[str, list[str], int, dict[str, Any]]],
            criteria: list[tuple[str, Callable[[dict[str, Any]], bool]]]) -> list[tuple[str, list[str], int, str]]:
    chosen: list[tuple[str, list[str], int, str]] = []
    for name, test in criteria:
        hits = [r for r in runs if test(r[3])]
        reuse = [r for r in hits if any(r[0] == c[0] for c in chosen)]
        if reuse:
            continue
        if not hits:
            print("no run for", name, file=sys.stderr)
            continue
        label, files, size, _f = min(hits, key=lambda r: (r[2], r[0]))
        chosen.append((label, files, size, name))
    return chosen


def redcode_index(zdir: Path) -> tuple[dict[str, Any], dict[str, tuple[str, str, int, int, int]]]:
    from agentprov.ingest.archives import iter_zip_members, open_zip

    members: dict[str, Any] = {}
    meta: dict[str, tuple[str, str, int, int, int]] = {}
    for z in sorted(zdir.glob("*.zip")):
        if not (z.name.startswith("trajectories_OH-") or z.name == "agent-execution-decisions-supp.zip"):
            continue
        csha = hashlib.sha256(z.read_bytes()).hexdigest()
        fp = open(z, "rb")  # noqa: SIM115 - kept open while the index is used
        oz = open_zip(fp, release=True)
        for m in iter_zip_members(oz):
            if m.label and m.disposition == "selected" and not m.label.startswith("environment/"):
                members[m.label] = (oz, m)
                meta[m.label] = (z.name, csha, m.method, m.crc32, m.file_size)
    return members, meta


def redcode_plan(zdir: Path) -> tuple[list[tuple[str, list[str], int, str]], dict[str, Any], dict[str, Any]]:
    from agentprov.adapters.openhands.dialect import OpenHandsEventsReader, parse_path
    from agentprov.adapters.runner.importer import _AuxListing
    from agentprov.ingest.loaders import strict_json_loads

    members, meta = redcode_index(zdir)
    listing = _AuxListing(list(members), {})
    reader = OpenHandsEventsReader()
    scores: dict[tuple[str, str, str, str], Any] = {}
    runs = []
    for label in sorted(lab for lab in members if "/trajectory/" in lab):
        facets = parse_path(label)
        if facets is None:
            continue
        plan = reader.auxiliary_for(label, listing)
        files = [label, *sorted(plan.values())]
        size = sum(meta[f][4] for f in files)
        oz, m = members[label]
        events = strict_json_loads(oz.read_member(m))
        key = plan.get("score")
        if key not in scores and key is not None:
            soz, sm = members[key]
            scores[key] = {str(e.get("index")): e.get("score") for e in strict_json_loads(soz.read_member(sm))}
        score = scores.get(key, {}).get(str(facets.case_key)) if key else None
        first = next((e.get("args", {}).get("content") for e in events
                      if e.get("action") == "message" and e.get("source") == "user"), "")
        rewrite = False
        if "prompt" in plan:
            poz, pm = members[plan["prompt"]]
            record = next((e for e in strict_json_loads(poz.read_member(pm)) if str(e.get("payload_index")) == facets.case_key), {})
            text = record.get("generated_prompt")
            if isinstance(text, str) and isinstance(first, str):
                norm = lambda t: re.sub(r"\s+", " ", t).strip()  # noqa: E731
                fixed = re.sub(r"(?<!/app)/sys/kernel", "/app/sys/kernel", text)
                rewrite = norm(text) not in norm(first) and norm(fixed) in norm(first)
        feats = {
            "rewrite": rewrite,
            "model": facets.model, "target": facets.target, "lang": facets.language, "sc": facets.scenario, "score": score,
            "caused_error": any(e.get("observation") == "error" and "cause" in e for e in events),
            "uncaused_error": any(e.get("observation") == "error" and "cause" not in e for e in events),
            "mcp": any(e.get("action") == "call_tool_mcp" for e in events),
            "tracker": any(e.get("action") == "task_tracking" for e in events),
        }
        runs.append((label, files, size, feats))
    criteria: list[tuple[str, Callable[[dict[str, Any]], bool]]] = [
        ("R1 claude S1 python executed (score 3)", lambda f: f["model"] == "claude-sonnet-4-6" and f["target"] == "S1" and f["score"] == 3),
        ("R2 qwen S1 bash score 1 with a runtime refusal", lambda f: f["target"] == "S1" and f["lang"] == "bash" and f["score"] == 1 and f["caused_error"]),
        ("R3 uncaused (harness) error observation", lambda f: f["uncaused_error"]),
        ("R4 request joined after the declared /sys/kernel rewrite, refused", lambda f: f["rewrite"] and f["score"] == 0),
    ]
    return _choose(runs, criteria), members, meta


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--oas", type=Path, required=True)
    ap.add_argument("--zips", type=Path, required=True)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    oas = oas_plan(args.oas)
    rc, members, meta = redcode_plan(args.zips)
    files: dict[str, dict[str, Any]] = {}
    for label, group, size, name in oas:
        print(f"oas  {size:>8} {name}: {label}")
        for f in group:
            files.setdefault(f"oas/{f}", {"source": "oas", "path": f, "criteria": []})["criteria"].append(name.split()[0])
    for label, group, size, name in rc:
        print(f"rc   {size:>8} {name}: {label}")
        for f in group:
            files.setdefault(f"redcode/{f}", {"source": "redcode", "path": f, "criteria": []})["criteria"].append(name.split()[0])
    total = 0
    for item in files.values():
        if item["source"] == "oas":
            total += (args.oas / item["path"]).stat().st_size
        else:
            total += meta[item["path"]][4]
    print(f"files {len(files)}, bytes {total}")
    if not args.write:
        return 0
    from agentprov.adapters.runner.importer import git_blob_sha1

    entries = []
    for key in sorted(files):
        item = files[key]
        if item["source"] == "oas":
            data = (args.oas / item["path"]).read_bytes()
            entry = {"sample_file": key, "url": f"{OAS_REPO}/blob/{OAS_COMMIT}/{item['path']}", "repository": OAS_REPO,
                     "commit_or_revision": OAS_COMMIT, "original_path": item["path"], "git_blob_sha1": git_blob_sha1(data),
                     "licence": "MIT"}
        else:
            oz, m = members[item["path"]]
            data = bytes(oz.read_member(m))
            zname, csha, method, crc, size = meta[item["path"]]
            entry = {"sample_file": key, "url": f"https://zenodo.org/records/23168099/files/{zname}",
                     "repository": f"https://doi.org/{DOI}", "commit_or_revision": DOI, "original_path": item["path"],
                     "record_locator": {"container": zname, "container_sha256": csha, "member": item["path"],
                                        "method": method, "crc32": f"{crc:08x}", "size": size},
                     "licence": "CC-BY-4.0"}
        target = OUT / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        entry.update({"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data), "retrieved_at": "2026-10-12",
                      "licence_class": "permissive", "synthetic": False,
                      "note": "phase 10g fixture, criteria " + ", ".join(item["criteria"])})
        entries.append(entry)
    (OUT / "SOURCE.json").write_text(json.dumps(entries, indent=1, ensure_ascii=True) + "\n", encoding="utf-8")
    keep = {OUT / key for key in files} | {OUT / "SOURCE.json"}
    stale = [p for p in OUT.rglob("*") if p.is_file() and p not in keep]
    for path in stale:  # files of an earlier plan, under this tool's own directory only
        path.unlink()
    for folder in sorted((p for p in OUT.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        if not any(folder.iterdir()):
            folder.rmdir()
    print("removed stale", len(stale))
    print("written", len(entries))
    return 0


if __name__ == "__main__":
    sys.exit(main())
