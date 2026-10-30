"""Build the phase-10k fixtures, byte-identical, chosen by structure, never read back or printed (D-266).

    uv run python -I tools/credleak/build_fixtures.py --zip p15b-run-data-v3-2026-09-13.zip

Reads the pinned deposit zip through :func:`agentprov.ingest.archives.open_archive` (the G.3.5 gate; nothing is
extracted). For each criterion it copies the **smallest** matching run cell (ties by label) to
``tests/fixtures/credleak/cells/<label below p15b-run-data/>``, with ``SOURCE.json`` (label, sha256, size, CRC-32, the
zip's DOI, file and sha256, licence class, criteria). A cell is a candidate only when none of the shipped profile's
``[withhold]`` rules matches its bytes (the planted-credential tag and the two key shapes, D-265): fixtures hold no
planted value, so raw bytes are copied unedited. Only paths, sizes, criteria and the count of skipped cells are printed.

The committed fixtures were edited afterwards (fixture scrub 2026-10-21): three cells had one third-party account in
their ``ls -l`` owner/group columns replaced by ``user``, recorded in SOURCE.json (``modified``, ``derived_from``). A
rebuild copies the original bytes again, so the scrub must then be repeated.

The deposit holds no licence file (its licence is the record's metadata, CC-BY-4.0), so the attribution is written to
``tests/fixtures/LICENSES/credleak-p15b-ATTRIBUTION.txt`` beside the committed ``CC-BY-4.0.txt``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zlib
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures"
PREFIX = "p15b-run-data/"
CANONICAL_TOOLS = frozenset({"Bash", "Read", "Glob", "Edit", "WebFetch", "McpToolCall", "Write", "Grep", "ListMcpTools",
                             "WebSearch"})
ATTRIBUTION = """Fixtures under tests/fixtures/credleak/ are run cells of

  Run data and analysis code for "How Credentials Leak from 'Safe' LLM Coding Agents: An Attack-Surface Measurement",
  Zenodo record 22737462 (version v3, 2026-09-13), https://doi.org/10.5281/zenodo.22737462

licensed under the Creative Commons Attribution 4.0 International licence (CC-BY-4.0; the record's metadata; full text
in CC-BY-4.0.txt in this directory). The cells were copied byte for byte (tools/credleak/build_fixtures.py), and only
cells that carry none of the study's planted canary credentials were chosen.

Modifications: on 2026-10-21, a third-party account name was replaced by `user` (space-padded to the column width) in
the ls -l owner and group columns of 3 cells. The original digests are in SOURCE.json under derived_from. Nothing else
was changed.
"""


def _criteria(doc: dict[str, Any], label: str) -> set[str]:
    out: set[str] = set()
    runs = [r for r in doc.get("runs", []) if isinstance(r, dict)]
    rel = label[len(PREFIX):]
    parts = rel.split("/")
    turns = [t for r in runs for t in r.get("turns", []) if isinstance(t, dict)]
    calls = [c for t in turns for c in t.get("toolCalls", []) if isinstance(c, dict)]
    if len(runs) == 1:
        out.add("single_run_excluded" if "excluded-models" in parts else "single_run_roster")
    if any(p.startswith("_") for p in parts[:-1]):
        out.add("underscore_dir")
    if "__note" in doc:
        out.add("note")
    if any(len(r.get("turns", [])) > 1 for r in runs):
        out.add("multiturn")
    if any(not isinstance(v, str) for c in calls for v in (c.get("input") or {}).values()):
        out.add("non_string_input")
    if any(c.get("tool") not in CANONICAL_TOOLS for c in calls):
        out.add("variant_tool_name")
    if any("durationMs" in t for t in turns):
        out.add("turn_duration")
    if any("durationMs" in c for c in calls):
        out.add("call_duration")
    if calls and not any("taskEngaged" in r for r in runs):
        out.add("old_schema_with_calls")
    if any(r.get("hijackSucceeded") is True for r in runs):
        out.add("hijacked")
    if any(r.get("invocationError") is True for r in runs):
        out.add("invocation_error")
    return out


def build(zip_path: Path) -> list[dict[str, Any]]:
    from agentprov.adapters.profiles import load_profile
    from importlib import resources

    from agentprov.corpus.withhold import policy_of_profile, scan_chunks
    from agentprov.ingest.archives import iter_zip_members, open_archive
    from agentprov.ingest.loaders import strict_json_loads

    profile = load_profile("credleak-p15b")
    pin = next(p for p in profile.data["source"]["pins"] if p.get("primary") is True)
    container = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    if container != pin["sha256"]:
        raise SystemExit("the zip is not the pinned deposit file")
    data = resources.files("agentprov").joinpath("adapters", "credleak", "profiles", "credleak-p15b.profile.toml").read_bytes()
    policy = policy_of_profile(data, profile_id=profile.id, profile_version=profile.version)
    assert policy is not None
    candidates: dict[str, list[tuple[int, str, bytes]]] = {}
    skipped = 0
    with zip_path.open("rb") as fh, open_archive(fh, release=True) as archive:
        for member in iter_zip_members(archive, lambda label: label.startswith(PREFIX) and label.endswith(".json")):
            if member.disposition != "selected" or member.label is None or " " in member.label:
                continue
            data = archive.read_member(member)
            if scan_chunks([data], policy.rules):
                skipped += 1
                continue
            try:
                doc = strict_json_loads(data)
            except Exception:  # noqa: BLE001 - a member the strict loader rejects is never a fixture
                continue
            if not (isinstance(doc, dict) and isinstance(doc.get("runs"), list)):
                continue
            for criterion in _criteria(doc, member.label):
                candidates.setdefault(criterion, []).append((member.file_size, member.label, data))
    best: dict[str, tuple[int, str, bytes]] = {c: min(rows, key=lambda r: r[:2]) for c, rows in candidates.items()}
    roster = sorted(candidates.get("single_run_roster", []), key=lambda r: r[:2])
    if len(roster) < 2:
        raise SystemExit("fewer than two clean single-run roster cells")
    best["single_run_roster_2"] = roster[1]  # two clean roster runs for the withholding test
    root = FIXTURES / "credleak"
    if root.exists():
        for old in sorted(root.rglob("*"), reverse=True):
            old.unlink() if old.is_file() else old.rmdir()
    rows: dict[str, dict[str, Any]] = {}
    for criterion, (size, label, data) in sorted(best.items()):
        rel = label[len(PREFIX):]
        row = rows.setdefault(rel, {"label": label, "path": f"cells/{rel}", "size": size,
                                    "sha256": hashlib.sha256(data).hexdigest(),
                                    "crc32": f"{zlib.crc32(data) & 0xFFFFFFFF:08x}", "doi": pin["doi"], "file": pin["file"],
                                    "container_sha256": container, "licence_class": "permissive", "synthetic": False,
                                    "criteria": []})
        row["criteria"].append(criterion.removesuffix("_2"))
        target = root / "cells" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    for row in rows.values():
        row["criteria"] = sorted(set(row["criteria"]))
    (root / "SOURCE.json").write_text(json.dumps(sorted(rows.values(), key=lambda r: r["path"]), indent=2, sort_keys=True)
                                      + "\n", encoding="utf-8")
    (FIXTURES / "LICENSES" / "credleak-p15b-ATTRIBUTION.txt").write_text(ATTRIBUTION, encoding="utf-8")
    print(json.dumps({"cells_with_a_rule_hit_skipped": skipped, "fixtures": [
        {"path": r["path"], "size": r["size"], "criteria": r["criteria"]} for r in sorted(rows.values(), key=lambda r: r["path"])]},
        indent=1))
    return list(rows.values())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--zip", type=Path, required=True)
    build(parser.parse_args().zip)


if __name__ == "__main__":
    main()
