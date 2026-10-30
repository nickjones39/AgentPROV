"""Ultrareview, area pipeline (``~/.agentprov/review/pipeline.findings.json``; user decision 2026-10-22): the runner
findings #1 (every read path keeps the per-candidate size guard) and #3 (the ``aer`` stage's rules do not depend on
which units the last run sealed)."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import import_support as support
import pytest

from agentprov.adapters.runner.importer import (
    GitPinTree,
    LocalTree,
    PinnedObject,
    import_source,
    merge_aer_rules,
    read_pinned,
)
from agentprov.adapters.types import Origin
from agentprov.corpus.writer import CorpusWriter
from agentprov.errors import IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.raw.fetch import TreeEntry

sys.path.insert(0, str(Path(__file__).resolve().parent))


# ------------------------------------------------------------------------------------------------ #1
class _Fetcher:
    """A fetch cache stand-in: a git tree of two blobs (the wiring under test is the tree's size guard)."""

    def __init__(self, blobs: dict[str, bytes]) -> None:
        self.blobs = blobs
        self.asked: list[str] = []

    def git_tree(self, recipe: Any) -> tuple[list[TreeEntry], list[Any]]:
        return [TreeEntry("100644", "blob", f"{n:040x}", len(data), path)
                for n, (path, data) in enumerate(sorted(self.blobs.items()))], []

    def history_index(self, recipe: Any) -> None:
        return None

    def iter_git_blobs(self, recipe: Any, entries: list[TreeEntry]) -> Any:
        for entry in entries:
            self.asked.append(entry.path)
            yield SimpleNamespace(data=self.blobs[entry.path])


def test_a_git_blob_over_the_limit_is_that_candidate_s_ingest_error(tmp_path):
    """Before, GitPinTree.read handed every blob on, and the store's size check raised out of the import."""
    fetcher = _Fetcher({"a.json": b"x" * 10, "big.json": b"y" * 100})
    recipe = SimpleNamespace(repo="https://example.invalid/r.git", commit="0" * 40, paths=())
    tree = GitPinTree(fetcher, recipe, limits=IngestLimits(max_artefact_bytes=50))  # type: ignore[arg-type]
    read = {candidate.label: data for candidate, data in tree.read(list(tree.walk()))}
    assert read["a.json"] == b"x" * 10
    big = read["big.json"]
    assert isinstance(big, IngestError) and big.code == "ingest.size.file"
    assert fetcher.asked == ["a.json"]  # the over-limit blob is never fetched


def test_git_pin_tree_open_keeps_max_bytes_and_the_import_limit():
    """Pre-round verification V-7: ``GitPinTree.open`` ignored ``max_bytes`` and the import's limits."""
    fetcher = _Fetcher({"a.json": b"x" * 10, "big.json": b"y" * 100})
    recipe = SimpleNamespace(repo="https://example.invalid/r.git", commit="0" * 40, paths=())
    tree = GitPinTree(fetcher, recipe, limits=IngestLimits(max_artefact_bytes=50))  # type: ignore[arg-type]
    assert tree.open("a.json") == b"x" * 10
    with pytest.raises(IngestError) as over:
        tree.open("big.json")  # the import's limit
    assert over.value.code == "ingest.size.file"
    with pytest.raises(IngestError):
        tree.open("a.json", max_bytes=5)  # a caller's tighter bound
    assert fetcher.asked == ["a.json"]  # neither over-limit blob was fetched


def test_a_pinned_object_is_read_no_further_than_the_limit(tmp_path):
    data = b"z" * 100
    (tmp_path / "obj").write_bytes(data)
    obj = PinnedObject("main/x.json", Origin.local(str(tmp_path / "obj")), str(tmp_path / "obj"),
                       hashlib.sha256(data).hexdigest(), len(data))
    assert read_pinned(obj, IngestLimits()) == data
    small = read_pinned(obj, IngestLimits(max_artefact_bytes=50))
    assert isinstance(small, IngestError) and small.code == "ingest.size.file"
    lying = PinnedObject(obj.label, obj.origin, obj.path, obj.sha256, 10)  # a pin that understates the size
    assert isinstance(read_pinned(lying, IngestLimits(max_artefact_bytes=50)), IngestError)


def test_an_import_with_an_over_limit_pinned_object_registers_it_and_finishes(tmp_path):
    """MCPHunt-shaped (D-530 R3): before, the object's bytes reached the store and its size error ended the import."""
    import test_mcphunt_lfs_overlay_d530 as lfs

    document = (lfs.support.FIXTURES / "docs" / lfs.LABEL).read_bytes()
    sha = hashlib.sha256(document).hexdigest()
    root = tmp_path / "in"
    (root / "main").mkdir(parents=True)
    (root / lfs.LABEL).write_bytes(lfs.POINTER % (sha.encode(), len(document)))
    (tmp_path / "object.json").write_bytes(document)
    obj = PinnedObject(lfs.LABEL, Origin.hf(lfs.DATASET, lfs.support.REVISION, lfs.LABEL), str(tmp_path / "object.json"),
                       sha, len(document))
    limits = lfs.support.limits().replace(max_artefact_bytes=len(document) - 1)
    with CorpusWriter(tmp_path / "c", limits=limits) as writer:
        report = import_source("mcphunt", LocalTree(root, limits=limits), corpus=writer, profile_id="mcphunt",
                               part="head", pin_check=support.vouch(root, repo=lfs.REPO_URL, commit=lfs.support.REVISION),
                               pinned_objects=[obj], in_process=True, until="aer", limits=limits)
    register = [json.loads(x) for x in (tmp_path / "c.partial" / "register.jsonl").read_text().splitlines()]
    assert any(e["code"] == "ingest.size.file" and e["disposition"] == "not_imported" for e in register)
    manifest = json.loads((tmp_path / "c.partial" / "corpus.json").read_text())
    assert "incomplete" not in manifest["sources"][0]["snapshots"][0]  # the run finished
    assert report.counters["mapped"] == 0


def test_a_staged_file_that_grew_after_its_size_check_is_refused(tmp_path, monkeypatch):
    """Nit (live staging): ``open_evidence`` checks the size at ``fstat``; a file that grew afterwards was read to
    ``max + 1`` bytes and stored truncated or one byte over the limit. It is now refused (``ingest.size.file``)."""
    import io

    import pytest

    from agentprov.adapters.runner import live

    (tmp_path / "stage").mkdir()
    (tmp_path / "stage" / "capture.jsonl").write_bytes(b"x" * 10)
    monkeypatch.setattr(live, "open_evidence", lambda root, label, limits, **kw: io.BytesIO(b"x" * 100))
    with pytest.raises(IngestError) as refused:
        live.stage_objects(tmp_path / "stage", session="s", limits=IngestLimits(max_artefact_bytes=50))
    assert refused.value.code == "ingest.size.file"


# ------------------------------------------------------------------------------------------------ #3
def _aer_stage(partial: Path) -> dict[str, Any]:
    return next(s for s in json.loads((partial / "derivation.json").read_text())["stages"] if s["stage"] == "aer")


def test_a_resume_keeps_the_namespaces_an_earlier_run_recorded(tmp_path):
    """A run that seals no unit declaring a namespace (every candidate resumed) recorded the mapper's catalogues only,
    so ``rules`` and ``fn_digest`` moved with no AER changed. The corpus's stage keeps the earlier run's namespaces."""
    support.agentdojo_tree(tmp_path / "in", count=2)

    def run() -> Any:
        with CorpusWriter(tmp_path / "c") as writer:
            return import_source("agentdojo", LocalTree(tmp_path / "in"), corpus=writer, part="2024-06", until="aer",
                                 pin_check=support.vouch(tmp_path / "in"), in_process=True)

    run()
    path = tmp_path / "c.partial" / "derivation.json"
    derivation = json.loads(path.read_text())
    stage = next(s for s in derivation["stages"] if s["stage"] == "aer")
    extra = "sha256:" + "ab" * 32  # as if an earlier run had sealed a unit that declares namespace `rescont`
    stage.update(rules={**stage["rules"], "rescont": 1}, rules_sha256={**stage["rules_sha256"], "rescont": extra})
    path.write_text(json.dumps(derivation))
    assert run().counters["skipped_resume"] == 2
    after = _aer_stage(tmp_path / "c.partial")
    assert after["rules"]["rescont"] == 1 and after["rules_sha256"]["rescont"] == extra  # before: dropped


def test_merge_aer_rules_needs_the_same_function():
    base = {"stage": "aer", "fn": "map", "adapter": "a@1", "engine_code_sha256": "sha256:1", "rules": {"aer": 1},
            "rules_sha256": {"aer": "sha256:a"}}
    previous = {**base, "rules": {"aer": 1, "x": 2}, "rules_sha256": {"aer": "sha256:a", "x": "sha256:x"}}
    merged = merge_aer_rules(previous, {**base, "fn_digest": "sha256:old"})
    assert merged["rules"] == {"aer": 1, "x": 2} and merged["fn_digest"] != "sha256:old"
    other = merge_aer_rules({**previous, "engine_code_sha256": "sha256:2"}, dict(base))
    assert other["rules"] == {"aer": 1}  # another function: nothing carried
    assert merge_aer_rules(None, dict(base)) == base


# ------------------------------------------------------------------------------------------------ nits
def test_a_refused_pipeline_removes_its_scratch_tree(tmp_path, monkeypatch):
    """Nit: the constructor made its scratch tree before checks that can raise, and nothing removed it."""
    import tempfile

    from agentprov.adapters.runner import importer
    from agentprov.errors import AgentProvError

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "tmp"))
    (tmp_path / "tmp").mkdir()
    support.agentdojo_tree(tmp_path / "in", count=1)

    def refused(self: Any) -> dict[str, int]:
        raise AgentProvError("refused for the test", code="adapter.profile_missing")

    monkeypatch.setattr(importer._Pipeline, "_catalogues", refused)
    with CorpusWriter(tmp_path / "c") as writer, pytest.raises(AgentProvError):
        import_source("agentdojo", LocalTree(tmp_path / "in"), corpus=writer, part="2024-06", in_process=True,
                      pin_check=support.vouch(tmp_path / "in"))
    assert not [p for p in (tmp_path / "tmp").iterdir() if p.name.startswith("agentprov-import-")]


def test_the_importer_and_derive_build_the_stage_definitions_in_one_place():
    """Nit: the importer kept its own copies of the sem/prov/validation definitions and their helpers."""
    from agentprov import stage_definitions
    from agentprov.adapters.runner import importer
    from agentprov.corpus import derive
    from agentprov.prov.specs import SPEC_ID

    for name in ("code_sha256", "with_digest", "sem_stage_definition", "prov_stage_definition",
                 "validation_stage_definition", "SemanticsInfo"):
        assert getattr(derive, name) is getattr(stage_definitions, name)
    assert importer.code_sha256 is stage_definitions.code_sha256 and importer._with_digest is stage_definitions.with_digest
    assert stage_definitions.validation_stage_definition([], "dev")["checks"] == ["aer.validator", "tier4:" + SPEC_ID]


def test_import_arguments_hold_the_re_map_contract(tmp_path):
    """Nit: ``import_arguments`` returned the plan's ``until`` and every caller clamped it to ``aer``."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "unit" / "corpus"))
    import derive_support as ds

    from agentprov.corpus.derive import Catalogues, Derivation, resolve_plan
    from agentprov.corpus.reader import CorpusReader

    corpus = ds.agentdojo_corpus(tmp_path, count=1)
    reader = CorpusReader(ds.partial(corpus), state="working")
    plan = resolve_plan(reader, "recompute")
    assert plan.until == "validation"
    catalogues = Catalogues(source_profile_sha256=lambda *_: None, semantics=lambda _ref: None)
    assert Derivation(reader, plan, catalogues=catalogues).import_arguments()["until"] == "aer"
