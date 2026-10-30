"""D-221 (NF-24, NF-29): the sealed ``agentprov-corpus/0.2`` snapshot carries the per-unit inputs of D.16.14.

A sealed manifest records no pins, so before D-221 the sealed form dropped ``context`` and ``pinned_objects`` and every
re-map of the sealed corpus ran without the ``tasks:`` joins (the bug pass's fixture: 23 of 25 unexplained). Here the
DTap fixture is imported with a pinned ``tasks`` tree and an LFS object, and its snapshot is put in the sealed form the
way ``package`` builds it (:func:`agentprov.corpus.package._sealed_per_unit`). A re-map of that sealed snapshot must
rebuild the same context tree (role, labels, digests, origins) and the same pinned objects as the working snapshot, so
the units are mapped with the same joins. ``context_skipped`` is recorded and kept by a re-map.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import dtap_support as support
from test_import import _object

from agentprov.adapters.profiles import load_profile
from agentprov.corpus.manifest import DEFS_BY_FORMAT, _snapshot
from agentprov.corpus.package import _sealed_per_unit
from agentprov.corpus.rawtree import StoredRawTree
from agentprov.corpus.reader import WORKING, CorpusReader
from agentprov.corpus.shapes import Issue

TASKS_PIN = {"kind": "git", "role": "tasks", "repo": support.TASKS_REPO, "commit": support.TASKS_COMMIT}


def _import(tmp: Path) -> Any:
    runs_pin = dict(next(p for p in load_profile(support.PROFILE).data["source"]["pins"] if p["role"] == "runs"))
    return support.run_import(tmp, support.runs_files(), support.tasks_files(), objects=[_object(tmp)], pin=runs_pin,
                              tasks_pin=TASKS_PIN, context_skipped=["auditor"])


def _inputs(tree: StoredRawTree) -> tuple[list[Any], list[Any]]:
    context = [(c.role, sorted((label, sha, origin.canonical()) for label, (sha, origin) in c.tree._entries.items()))
               for c in tree.recorded_context]
    pinned = [(o["label"], o["sha256"], o["origin"].canonical(), o["size"]) for o in tree.recorded_pinned_objects]
    return context, pinned


def _sealed_copy(partial: Path, dest: Path) -> dict[str, Any]:
    """A copy of the working corpus whose snapshot is in the sealed form (no pins; D-221's per-unit members)."""
    shutil.copytree(partial, dest)
    path = dest / "corpus.json"
    manifest = json.loads(path.read_text("utf-8"))
    working = manifest["sources"][0]["snapshots"][0]
    by_sha: dict[str, list[dict[str, Any]]] = {}
    for row in CorpusReader(partial, state=WORKING, used_partial=True).origins():
        by_sha.setdefault(row.sha256, []).append({"kind": row.origin.kind, **row.origin.data})
    sealed = {k: v for k, v in working.items() if k not in ("pin", "verification", "context", "pinned_objects",
                                                            "context_skipped")}
    sealed.update(_sealed_per_unit(working, by_sha, "agentprov-corpus/0.2"))
    manifest["sources"][0]["snapshots"][0] = sealed
    manifest["sealed"] = True
    path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", "utf-8")
    return sealed


def test_the_working_snapshot_records_the_role_pin_and_the_skipped_roles(tmp_path):
    imp = _import(tmp_path)
    snapshot = json.loads((imp.partial / "corpus.json").read_text("utf-8"))["sources"][0]["snapshots"][0]
    assert snapshot["context"][0]["pin"] == TASKS_PIN
    assert snapshot["context_skipped"] == ["auditor"]


def test_the_sealed_snapshot_is_valid_corpus_0_2_and_holds_the_per_unit_inputs(tmp_path):
    imp = _import(tmp_path)
    sealed = _sealed_copy(imp.partial, tmp_path / "sealed.partial")
    issues: list[Issue] = []
    shape = _snapshot("agentprov-corpus/0.2")
    shape.check({**sealed, "origin": {"kind": "git", "repo": support.RUNS_REPO, "commit": support.RUNS_COMMIT},
                 "alt_origins": [], "raw_policy": "include",
                 "selection": {"include": [], "exclude": []}}, "", issues, DEFS_BY_FORMAT["agentprov-corpus/0.2"])
    assert not [i for i in issues if i.pointer.startswith(("/context", "/pinned_objects"))], issues
    (context,) = sealed["context"]
    assert context["role"] == "tasks" and "pin" not in context
    assert context["origin"] == {"kind": "git", "repo": support.TASKS_REPO, "commit": support.TASKS_COMMIT, "subtree": ""}
    assert context["verification"]["unverified"] == 0 and context["stored"] > 0
    assert len(sealed["pinned_objects"]) == 1 and sealed["pinned_objects"][0]["sha256"].startswith("sha256:")
    assert sealed["context_skipped"] == ["auditor"]


def test_a_re_map_of_the_sealed_snapshot_rebuilds_the_same_per_unit_inputs(tmp_path):
    imp = _import(tmp_path)
    working = StoredRawTree(CorpusReader(imp.partial, state=WORKING, used_partial=True))
    _sealed_copy(imp.partial, tmp_path / "sealed.partial")
    sealed = StoredRawTree(CorpusReader(tmp_path / "sealed.partial", state=WORKING, used_partial=True))
    assert _inputs(sealed) == _inputs(working) and _inputs(working)[0][0][1]  # the tasks files, with their origins
    assert [c.pin for c in sealed.recorded_context] == [None]  # matched by the sealed origin, never recorded as a pin
    assert sealed.recorded_context_skipped == working.recorded_context_skipped == ["auditor"]
    assert sorted(sealed._entries) == sorted(working._entries)  # the primary inputs are the same files


def test_a_re_map_keeps_the_skipped_roles(tmp_path, monkeypatch):
    from agentprov.cli.main import main

    imp = _import(tmp_path)
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("AGENTPROV_UPSTREAM_CACHE", raising=False)
    out = tmp_path / "remapped"
    assert main(["recompute", "--corpus", str(imp.partial), "--out", str(out), "--no-reuse", "--in-process",
                 "--progress", "off", "-q"]) == 0
    after = json.loads((out.with_name(out.name + ".partial") / "corpus.json").read_text("utf-8"))["sources"][0]["snapshots"][0]
    assert after["context_skipped"] == ["auditor"]
