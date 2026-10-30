"""Every ``SOURCE.json`` entry of the fixture tree carries its licence class (K.4.1(1), K.4.2; U-06, D-943, D-946).

A real (non-synthetic) fixture without a ``licence_class`` cannot be placed by the public export (D-943: only
``permissive`` real fixtures may be public), so a new fixture must not arrive unclassified. The checks read the
``SOURCE.json`` metadata only and print paths and counts, never fixture text (R-42).
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from agentprov.testing import fixture_caps, golden

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

#: D-946: the 145 entries that had no class until 2026-10-29, all classed ``permissive`` from their profiles' licence
#: tables (docs/reports/release/u06-fixture-classes.md).
D946 = {"agentops": 25, "autogen": 9, "drift": 9, "mcphunt": 1, "memo-ozdincer": 3, "wirelog": 98}


def _entries() -> list[tuple[str, int, object]]:
    """(directory relative to the tree, index, entry) for every SOURCE.json entry at any depth.

    A file is a list of entries, or one object that is itself the entry (``mcphunt``'s record slices).
    """
    out: list[tuple[str, int, object]] = []
    for path in sorted(FIXTURES.rglob("SOURCE.json")):
        data = json.loads(path.read_bytes())
        rel = path.parent.relative_to(FIXTURES).as_posix()
        items = data if isinstance(data, list) else [data]
        out.extend((rel, i, item) for i, item in enumerate(items))
    return out


def test_every_source_entry_records_synthetic_and_every_real_one_a_licence_class_from_the_closed_set():
    entries = _entries()
    assert entries, "no SOURCE.json under tests/fixtures"
    problems = []
    for rel, i, item in entries:
        if not isinstance(item, dict):
            problems.append(f"{rel}[{i}]: not an object")
            continue
        if not isinstance(item.get("synthetic"), bool):
            problems.append(f"{rel}[{i}]: synthetic missing or not a boolean")
        cls = item.get("licence_class")
        if item.get("synthetic") is not True and cls not in golden.LICENCE_CLASSES:
            problems.append(f"{rel}[{i}]: real fixture without a licence_class from {sorted(golden.LICENCE_CLASSES)}")
        elif cls is not None and cls not in golden.LICENCE_CLASSES:
            problems.append(f"{rel}[{i}]: licence_class outside the closed set")
    assert problems == []


def test_the_d946_sources_are_classed_as_the_report_records():
    seen = Counter((rel.split("/", 1)[0], item.get("licence_class"), item.get("synthetic")) for rel, _i, item in _entries()
                   if isinstance(item, dict) and rel.split("/", 1)[0] in D946)
    assert seen == Counter({(src, "permissive", False): n for src, n in D946.items()})


def test_every_registered_licence_notice_is_the_file_its_entry_digests():
    """``LICENSES/SOURCE.json`` pins each notice it lists (size, sha256, git blob id), so a public permissive fixture
    goes out with the exact licence text recorded for it (D-943; the DRIFT and MCPHunt notices of 2026-10-29)."""
    licences = FIXTURES / "LICENSES"
    entries = json.loads((licences / "SOURCE.json").read_bytes())
    problems = []
    private = fixture_caps.export_private(FIXTURES)
    for entry in entries:
        path = licences / entry["sample_file"]
        if not path.is_file() and f"LICENSES/{entry['sample_file']}" in private:
            continue  # the public export leaves a non-permissive notice out (AgentHarm's; D-943)
        raw = path.read_bytes()
        if (len(raw), hashlib.sha256(raw).hexdigest(), golden.git_blob_sha1(raw)) != (
                entry["size_bytes"], entry["sha256"], entry["git_blob_sha1"]):
            problems.append(entry["sample_file"])
    assert problems == []
    assert {"DRIFT-MIT.txt", "MCPHunt-ATTRIBUTION.txt"} <= {e["sample_file"] for e in entries}
