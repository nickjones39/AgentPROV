"""AU-RP-5 (D-1063, regen-batch item 183): the working manifest's snapshot verification counts each file the pin vouched
for once, although the pipeline asks the pin about a file twice when it is both a primary candidate and another unit's
same-tree auxiliary (DTap ``attempt:<n>``). Only counts are compared; no fixture content is printed."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import dtap_support as ds
import pytest

from agentprov.adapters.runner.importer import PinCheck, git_blob_sha1
from agentprov.adapters.types import CandidateArtefact
from agentprov.raw.origins import Origin


def test_a_pin_counts_a_label_it_was_asked_about_twice_once():
    data = b"{}"
    check = PinCheck("blob", {"commit": "0" * 40}, listing={"runs/a.json": git_blob_sha1(data)}, repo="https://x.org/r")
    candidate = CandidateArtefact("runs/a.json", len(data), Origin.local("runs/a.json"))
    other = CandidateArtefact("runs/b.json", len(data), Origin.local("runs/b.json"))
    for _ in range(3):
        assert check.origin_for(candidate, data) is not None
        assert check.origin_for(other, data) is None
    assert (check.verified, check.unverified) == (1, 1)
    # bytes that no longer match for a label already vouched for: that label counts as unverified, never both
    assert check.origin_for(candidate, b"[]") is None
    assert (check.verified, check.unverified) == (0, 2)


def test_dtap_snapshot_verification_counts_each_runs_file_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    if not (ds.FIXTURES / "SOURCE.json").is_file():
        pytest.skip("the committed DTap fixtures are absent")
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path / "home"))
    runs, tasks = ds.runs_files(), ds.tasks_files()
    dirs = Counter(label.rpartition("/")[0] for label in runs)
    assert any(n > 1 for n in dirs.values())  # the case under test: a directory with more than one attempt
    imported = ds.run_import(tmp_path, runs, tasks, until="aer")
    snapshot = json.loads((imported.partial / "corpus.json").read_text())["sources"][0]["snapshots"][0]
    assert snapshot["verification"] == {"kind": "blob", "verified": len(runs), "unverified": 0}
