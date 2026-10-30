"""D-530 re-map: a corpus with per-unit inputs re-maps with its context trees and pinned objects (runner items R2/R3).

Before D-530 a re-map passed no context trees, so every unit lost its ``tasks:`` configuration, and a corpus holding an
LFS object was refused outright (``corpus.rawtree.invalid``: the LFS pointer's ``git`` origin and the object's ``hf``
origin claimed one input label). The corpus here is imported the way ``tools/dtap/import_dtap.py`` does: the runs pin is
recorded, the context tree carries no pin (the manifest shape of corpora built before D-530), with one LFS pointer, its
pinned object and the ``tasks`` tree. ``recompute --dry-run`` must run and report every execution and every corpus
file identical."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import dtap_support as support
import pytest
from test_import import _object

from agentprov.adapters.profiles import load_profile


def _recompute(src: Path, tmp: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> tuple[int, Any]:
    from agentprov.cli.main import main

    monkeypatch.setenv("AGENTPROV_HOME", str(tmp / "home"))
    monkeypatch.delenv("AGENTPROV_UPSTREAM_CACHE", raising=False)
    capsys.readouterr()
    code = main(["recompute", "--corpus", str(src), "--dry-run", "--no-reuse", "--in-process", "--json", "--progress", "off"])
    return code, json.loads(capsys.readouterr().out)


def test_a_dtap_corpus_with_an_lfs_object_and_a_context_tree_re_maps_identically(tmp_path, monkeypatch, capsys):
    runs_pin = dict(next(p for p in load_profile(support.PROFILE).data["source"]["pins"] if p["role"] == "runs"))
    imp = support.run_import(tmp_path, support.runs_files(), support.tasks_files(), objects=[_object(tmp_path)], pin=runs_pin)
    snapshot = json.loads((imp.partial / "corpus.json").read_text("utf-8"))["sources"][0]["snapshots"][0]
    assert snapshot["pinned_objects"] and snapshot["context"] and "pin" not in snapshot["context"][0]
    code, summary = _recompute(imp.partial, tmp_path, monkeypatch, capsys)
    counters = summary["counters"]
    assert summary["refusal"] is None, summary["refusal"]
    assert counters["unexplained_change"] == 0 and counters["corpus_unexplained"] == 0, summary["notices"]
    assert counters["identical"] == len(imp.rows) and code == 0


def test_a_re_map_keeps_each_context_trees_pin_verification_nf26(tmp_path, monkeypatch, capsys):
    """Bug pass NF-26: the re-map's context trees come from the stored corpus (no pin check), so the new manifest used
    to say ``verification: null``; the recorded verification is carried by role."""
    from agentprov.cli.main import main

    runs_pin = dict(next(p for p in load_profile(support.PROFILE).data["source"]["pins"] if p["role"] == "runs"))
    imp = support.run_import(tmp_path, support.runs_files(), support.tasks_files(), objects=[_object(tmp_path)], pin=runs_pin)
    before = json.loads((imp.partial / "corpus.json").read_text("utf-8"))["sources"][0]["snapshots"][0]["context"]
    assert before[0]["verification"] is not None
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("AGENTPROV_UPSTREAM_CACHE", raising=False)
    out = tmp_path / "remapped"
    assert main(["recompute", "--corpus", str(imp.partial), "--out", str(out), "--no-reuse", "--in-process",
                 "--progress", "off", "-q"]) == 0
    after = json.loads((out.with_name(out.name + ".partial") / "corpus.json").read_text("utf-8"))["sources"][0]["snapshots"][0]
    assert [c["verification"] for c in after["context"]] == [c["verification"] for c in before]


@pytest.mark.parametrize("which", ["context_file", "pinned_object", "trajectory"])
def test_a_re_map_with_a_per_unit_input_absent_on_purpose_reports_unverified_pr5(tmp_path, monkeypatch, capsys, which):
    """PR-5 (BF-20, CB-6 for per-unit inputs): after a ``tasks`` file or the pinned LFS object is purged, the re-map used
    to fail (``corpus.rawtree.invalid`` for the object, a KeyError for a context file). It now runs without it, and the
    executions that needed it are reported unverified. RC-13: after a trajectory is purged, its judge file is no longer
    mapped as a new judge-only execution (it is used only by the unverified one)."""
    from agentprov.cli.main import main

    runs_pin = dict(next(p for p in load_profile(support.PROFILE).data["source"]["pins"] if p["role"] == "runs"))
    imp = support.run_import(tmp_path, support.runs_files(), support.tasks_files(), objects=[_object(tmp_path)], pin=runs_pin)
    snapshot = json.loads((imp.partial / "corpus.json").read_text("utf-8"))["sources"][0]["snapshots"][0]
    if which == "pinned_object":
        sha = str(snapshot["pinned_objects"][0]["sha256"]).removeprefix("sha256:")
    elif which == "trajectory":
        rows = [json.loads(line) for line in (imp.partial / "raw" / "origins.jsonl").read_text("utf-8").splitlines()]
        sha = next(r["sha256"] for r in rows if r["origin"].get("path") == support.F["F01"]).removeprefix("sha256:")
    else:
        rows = [json.loads(line) for line in (imp.partial / "raw" / "origins.jsonl").read_text("utf-8").splitlines()]
        sha = next(r["sha256"] for r in rows if r["origin"].get("repo") == support.TASKS_REPO).removeprefix("sha256:")
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path / "home"))
    capsys.readouterr()
    assert main(["purge", "sha256:" + sha, "--reason", "secret", "--corpus", str(imp.partial), "--yes"]) == 0
    code, summary = _recompute(imp.partial, tmp_path, monkeypatch, capsys)
    counters = summary["counters"]
    assert summary["refusal"] is None, summary
    assert counters.get("unverified", 0) >= 1 and counters.get("unexplained_change", 0) == 0, summary
    # RC-2: every corpus file is explained too (the judge row the pointer writes without its object is accounted by its
    # label, an input of an execution that needs the absent object), so the dry run exits 0
    assert counters.get("corpus_unexplained", 0) == 0 and code == 0, summary["notices"]
    from agentprov.cli.main import main as cli

    capsys.readouterr()
    rederive = cli(["verify", "--corpus", str(imp.partial), "--level", "rederive", "--in-process", "--json", "--progress", "off"])
    assert rederive == 0, capsys.readouterr().out[-600:]
