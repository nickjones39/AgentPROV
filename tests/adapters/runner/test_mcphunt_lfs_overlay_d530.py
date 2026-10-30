"""D-530 item 6 on the MCPHunt shape: an LFS document is imported from its pinned object (runner item R3).

``McpHuntReader`` has no per-unit inputs (no ``auxiliary_for``). Before D-530 the runner placed pinned objects only in
the per-unit discovery, so an MCPHunt import ignored them and the LFS pointers were all that was walked (phase 10m's
trial: ``raw.origin.blob_mismatch`` for the LFS documents). Here the input tree holds a git-pinned LFS pointer at
``main/MiniMax_M2_7.json`` (one of the profile's 15 ``lfs_object`` files) and the object is the committed fixture document
of that name (byte-identical element slices, canary-free by evidence; loaded, never printed). The CLI part builds one
pinned object per ``lfs_object`` pin whose pointer the input holds: all 15 for a full tree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import import_support

from agentprov.adapters.profiles import load_profile
from agentprov.adapters.runner.importer import LocalTree, PinnedObject, import_source
from agentprov.adapters.types import Origin
from agentprov.corpus.writer import CorpusWriter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcphunt"))
import mcphunt_support as support  # noqa: E402

DATASET = "lihaonan0716/mcphunt-agent-traces"
REPO_URL = "https://huggingface.co/datasets/" + DATASET
LABEL = "main/MiniMax_M2_7.json"
POINTER = b"version https://git-lfs.github.com/spec/v1\noid sha256:%s\nsize %d\n"


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines()] if path.exists() else []


def test_an_mcphunt_lfs_document_is_mapped_from_its_pinned_object(tmp_path):
    document = (support.FIXTURES / "docs" / LABEL).read_bytes()
    sha = hashlib.sha256(document).hexdigest()
    root = tmp_path / "in"
    (root / "main").mkdir(parents=True)
    (root / LABEL).write_bytes(POINTER % (sha.encode(), len(document)))
    (tmp_path / "object.json").write_bytes(document)
    origin = Origin.hf(DATASET, support.REVISION, LABEL)
    obj = PinnedObject(LABEL, origin, str(tmp_path / "object.json"), sha, len(document))
    with CorpusWriter(tmp_path / "c", limits=support.limits()) as writer:
        report = import_source("mcphunt", LocalTree(root), corpus=writer, profile_id="mcphunt", part="head",
                               pin_check=import_support.vouch(root, repo=REPO_URL, commit=support.REVISION),
                               pinned_objects=[obj], in_process=True, until="aer", limits=support.limits())
    partial = tmp_path / "c.partial"
    register = _jsonl(partial / "register.jsonl")
    assert not [r for r in register if r["code"] in ("raw.origin.blob_mismatch", "raw.fetch.digest")]
    # the object is a candidate of its own, vouched for by its pin (sha256, size) and stored under its hf origin; how
    # a document maps is RB-1's (one execution per trace), not R3's
    assert {"origin": origin.to_json(), "sha256": "sha256:" + sha} in _jsonl(partial / "raw" / "origins.jsonl")
    headers = [json.loads((partial / row["paths"]["aer"]).read_bytes().split(b"\n", 1)[0])
               for row in _jsonl(partial / "executions.jsonl")]
    from_object = [h["artifacts"][0]["origin"] for h in headers if h["artifacts"][0]["origin"]["kind"] == "hf"]
    assert from_object and all(o == origin.to_json() for o in from_object)  # one execution per trace once RB-1 is in
    assert report.counters["seen"] >= 2  # the pointer and the object's traces


def _import_lfs(tmp: Path, name: str, **kwargs: object) -> tuple[object, list[dict], list[dict], dict]:
    document = (support.FIXTURES / "docs" / LABEL).read_bytes()
    sha = hashlib.sha256(document).hexdigest()
    root = tmp / "in"
    (root / "main").mkdir(parents=True, exist_ok=True)
    (root / LABEL).write_bytes(POINTER % (sha.encode(), len(document)))
    (tmp / "object.json").write_bytes(document)
    obj = PinnedObject(LABEL, Origin.hf(DATASET, support.REVISION, LABEL), str(tmp / "object.json"), sha, len(document))
    with CorpusWriter(tmp / name, limits=support.limits()) as writer:
        report = import_source("mcphunt", LocalTree(root), corpus=writer, profile_id="mcphunt", part="head",
                               pin_check=import_support.vouch(root, repo=REPO_URL, commit=support.REVISION),
                               pinned_objects=[obj], in_process=True, until="aer", limits=support.limits(), **kwargs)
    partial = tmp / f"{name}.partial"
    manifest = json.loads((partial / "corpus.json").read_text("utf-8"))
    return report, _jsonl(partial / "executions.jsonl"), _jsonl(partial / "register.jsonl"), manifest


def test_a_sample_keys_a_pinned_object_apart_from_its_pointer_pr8(tmp_path):
    """PR-8 (D-529 x D-530 item 6): the pointer and its object share a label, so a sample keyed by label alone stored one
    over the other and the pointer's whole-file key selected every trace of the object (``--sample 1`` sealed both) and
    sampled out the pointer's ``select.not_execution_artefact`` row. The object is now its own candidate identity, and
    the pointer, which yields no execution, never competes in the draw and is always registered."""
    from agentprov.adapters.runner.importer import ImportSample

    _report, full_rows, full_register, _m = _import_lfs(tmp_path, "full")
    traces = len(full_rows)
    pointer_row = [r for r in full_register if r["code"] == "select.not_execution_artefact"]
    assert traces >= 2 and len(pointer_row) == 1
    for n in (1, traces):
        report, rows, register, manifest = _import_lfs(tmp_path, f"s{n}", sample=ImportSample(n, "first"))
        assert len(rows) == n, (n, report.counters)  # never every trace of the object for a smaller sample
        assert [r["subject"] for r in register if r["code"] == "select.not_execution_artefact"] == [pointer_row[0]["subject"]]
        sample = manifest["selection"]["sample"]
        assert (sample["candidates"], sample["selected"]) == (traces, n)


def test_the_cli_builds_one_pinned_object_per_lfs_pin_the_input_holds(tmp_path, monkeypatch):
    from agentprov.cli import import_
    from agentprov.cli.common import CommandResult, Context

    profile = load_profile("mcphunt")
    lfs = [dict(p) for p in profile.data["source"]["pins"] if p["role"] == "lfs_object"]
    assert len(lfs) == 15
    by_file = {p["file"]: p for p in lfs}

    class _Fetcher:  # the verified cache holds every object (the real ones are up to 56 MB; the wiring is under test)
        def plan(self, recipe):
            return SimpleNamespace(cached=True, host="huggingface.co")

        def fetch(self, recipe):
            pin = by_file[recipe.file]
            return SimpleNamespace(path=tmp_path / "obj", sha256=pin["sha256"], bytes=pin["bytes"], problems=(),
                                   network_used=False)

    monkeypatch.setattr(import_, "_fetcher", lambda args, ctx: _Fetcher())
    args = argparse.Namespace(context=[], no_context=[], dry_run=False, allow_network=False, cache_dir=str(tmp_path))
    labels = [*by_file, "main/plain_document.json"]
    tree = SimpleNamespace(walk=lambda: iter(SimpleNamespace(label=label) for label in labels))
    contexts, objects, _local = import_._per_unit_inputs(args, Context(args), profile, None, tree, None,
                                                         CommandResult(dry_run=False))
    assert contexts == [] and sorted(o.label for o in objects) == sorted(by_file)
    assert all(o.origin.kind == "hf" and o.origin.data["revision"] == support.REVISION for o in objects)
    assert {o.label: o.sha256 for o in objects} == {f: p["sha256"] for f, p in by_file.items()}
    partial_tree = SimpleNamespace(walk=lambda: iter([SimpleNamespace(label=LABEL)]))
    _c, some, _l = import_._per_unit_inputs(args, Context(args), profile, None, partial_tree, None, CommandResult(dry_run=False))
    assert [o.label for o in some] == [LABEL]  # a sample fetches only the objects of the pointers it holds
