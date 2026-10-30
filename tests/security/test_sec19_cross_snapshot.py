"""SEC-19: duplicates across snapshots and within a snapshot (G.10 SEC-19; K.12.5; HL H.7; T-17; D-35, D-41).

What this build guarantees, and what these tests pin:

* **Several snapshots per corpus** (D-202, which replaced the one-snapshot refusal of N.2.2(7) and resolved the drift
  D-64 recorded): a second snapshot into a working corpus is added; bytes the first snapshot already mapped are one
  execution whose row lists both snapshots, with one origin row per snapshot (H.7.2(1)) and a ``dedup.collapsed``
  entry (H.7.2(2)). Another corpus id, source, mode or profile is still refused by G4 (exit 4). The collapse itself is
  tested in ``tests/adapters/runner/test_deferrals_part_a.py``.
* **The same bytes in two snapshot corpora** (D-35's layout for AgentDojo June-2024 and HEAD) are one execution in each,
  with the same content-addressed id and ``source_key``, each attributed to its own snapshot and origin commit and never
  to the other's; the AERs differ only in the recorded origin commit (and so the seal).
* **Within a snapshot**, the same bytes at two paths are one execution with two origins (12a proved ``n_origins`` on the
  working index row: ``test_import_controls.py::test_sec19_the_same_bytes_at_two_paths_are_one_execution_with_two_origins``);
  here the sealed manifest's ``duplicates`` tallies (D-41) are checked, and ``verify --level chain`` recomputes them, so
  a forged ``n_origins``, ``snapshot_ids`` or tally is detected; finding F-12C-02 (the consistent forgery of a row's
  snapshots or origins, which the tallies missed) is fixed on branch ``fix-12c-findings``.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import corpus_harness as harness
import import_support as support
import pytest
import verify_support as vs
from corpus_harness import verify

from agentprov.adapters.runner.importer import IdentityRefusedError, LocalTree, import_source
from agentprov.corpus.writer import CorpusWriter

cli = harness.cli  # the corpus_harness fixture, bound in this module so pytest finds it

HEAD = "089ed468cf3ed0322acc66b0211f26d9d90dbf60"  # the AgentDojo HEAD pin (registry part ``head``)
COMMITS = {"2024-06": support.C274885, "head": HEAD}


def _tree(root: Path, source: Path, labels: list[str]) -> Path:
    for label in labels:
        target = root / label
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((source / label).read_bytes())
    return root


def _import(tree: Path, corpus: Path, part: str, **kwargs: Any) -> Any:
    commit = COMMITS[part]
    kwargs.setdefault("in_process", True)
    with CorpusWriter(corpus) as writer:
        return import_source("agentdojo", LocalTree(tree), corpus=writer, part=part,
                             pin_check=support.vouch(tree, commit=commit),
                             pin={"commit": commit, "kind": "git", "role": part}, **kwargs)


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines()]


@pytest.fixture
def logs(tmp_path: Path) -> tuple[Path, list[str]]:
    """Three golden native AgentDojo logs (licence-cleared fixtures, never printed) and their sorted labels."""
    source = tmp_path / "all"
    labels = sorted(support.agentdojo_tree(source, count=3))
    return source, labels


# ------------------------------------------------------------------------------------------------ several snapshots per corpus
def test_sec19_a_second_snapshot_collapses_shared_bytes_and_another_corpus_id_is_refused_with_exit_4(tmp_path, logs):
    source, labels = logs
    june = _tree(tmp_path / "in-june", source, labels[:2])
    head = _tree(tmp_path / "in-head", source, labels[1:])  # one log byte-identical at both snapshots
    corpus = tmp_path / "c"
    assert _import(june, corpus, "2024-06", corpus_id="agentdojo-upstream").exit_code == 0
    partial = corpus.with_name("c.partial")
    assert _import(head, corpus, "head", corpus_id="agentdojo-upstream").exit_code == 0
    rows = _jsonl(partial / "executions.jsonl")
    assert sorted(r["snapshot_ids"] for r in rows) == [["2024-06"], ["2024-06", "head"], ["head"]]
    assert [r["n_origins"] for r in rows if len(r["snapshot_ids"]) == 2] == [2]
    before = support.tree_bytes(partial)
    with pytest.raises(IdentityRefusedError) as refused:
        _import(head, corpus, "head", corpus_id="another-corpus")
    assert refused.value.code == "corpus.identity_mismatch" and refused.value.exit_code == 4
    # no byte and no file changes (the writer's lock file comes and goes, so the directory mtime may move)
    assert support.tree_bytes(partial) == before and not (partial / ".agentprov.lock").exists()


def test_sec19_the_same_bytes_in_two_snapshot_corpora_are_one_execution_each_with_one_id_and_their_own_snapshot(
        tmp_path, logs):
    """D-35: the June-2024 and HEAD snapshots are separate corpora that deliberately share content-addressed execution
    ids; neither attributes the shared execution to the other's snapshot or origin."""
    source, labels = logs
    june = _tree(tmp_path / "in-june", source, labels[:2])
    head = _tree(tmp_path / "in-head", source, labels[1:])
    assert _import(june, tmp_path / "june", "2024-06").exit_code == 0
    assert _import(head, tmp_path / "head", "head").exit_code == 0
    trees = {part: tmp_path / f"{part if part == 'head' else 'june'}.partial" for part in COMMITS}
    rows = {part: {r["ex"]: r for r in _jsonl(trees[part] / "executions.jsonl")} for part in COMMITS}
    shared = set(rows["2024-06"]) & set(rows["head"])
    assert len(shared) == 1 and len(rows["2024-06"]) == len(rows["head"]) == 2
    ex = shared.pop()
    for part, tree in trees.items():
        row = rows[part][ex]
        assert row["snapshot_ids"] == [part] and row["n_origins"] == 1
        origins = _jsonl(tree / "raw" / "origins.jsonl")
        assert {o["origin"]["commit"] for o in origins} == {COMMITS[part]}
        manifest = json.loads((tree / "corpus.json").read_text("utf-8"))
        assert [s["snapshot_id"] for s in manifest["sources"][0]["snapshots"]] == [part]
    assert rows["2024-06"][ex]["source_key"] == rows["head"][ex]["source_key"]
    assert rows["2024-06"][ex]["raw"] == rows["head"][ex]["raw"]
    # the AERs record the same execution (same records, kinds, ids and links); they differ where they record their
    # snapshot's origin commit, and in what that origin proves about the producing code (D-84): the June-2024 origin is
    # in the 2024-06 pin's history, so its D rules hold; the HEAD origin carries no introducing commit here (no history
    # index), so the June-2024 citations fail closed to their _unverified twins (class I), and so the seal differs
    june_aer, head_aer = ((trees[p] / rows[p][ex]["paths"]["aer"]).read_bytes().splitlines() for p in COMMITS)
    assert len(june_aer) == len(head_aer)
    def body(line: bytes) -> dict[str, object]:
        return {k: v for k, v in json.loads(line).items() if k not in ("ev", "evf", "rule")}
    assert [body(x) for x in june_aer[1:-1]] == [body(x) for x in head_aer[1:-1]]
    assert b"_unverified@" in b"".join(head_aer) and b"benchmark_from_dialect@1" in b"".join(june_aer)
    june_header, head_header = json.loads(june_aer[0]), json.loads(head_aer[0])
    assert [a["origin"]["commit"] for a in june_header["artifacts"]] == [support.C274885]
    assert [a["origin"]["commit"] for a in head_header["artifacts"]] == [HEAD]
    for artefact in head_header["artifacts"]:
        artefact["origin"]["commit"] = support.C274885
    assert body(json.dumps(head_header).encode()) == body(json.dumps(june_header).encode())


# ------------------------------------------------------------------------------------------------ within a snapshot
@pytest.fixture(scope="module")
def duplicated_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A sealed corpus of three golden logs, one of them also present at a second path of the same snapshot."""
    import seal_support as ss

    from agentprov.corpus.package import seal

    base = tmp_path_factory.mktemp("sec19-duplicated")
    entries = support.agentdojo_tree(base / "in", count=3)
    first = sorted(entries)[0]
    (base / "in" / first.replace(".json", "_copy.json")).write_bytes((base / "in" / first).read_bytes())
    with CorpusWriter(base / "c") as writer:
        report = import_source("agentdojo", LocalTree(base / "in"), corpus=writer, part="2024-06", workers=1,
                               mode="release", pin_check=support.vouch(base / "in"), pin=ss.PIN)
    assert report.exit_code == 0 and report.counters["duplicates"] == 1
    seal(base / "c", corpus_version="0.1.0", inputs=ss.inputs())
    return base / "c"


@pytest.fixture
def duplicated(duplicated_template: Path, tmp_path: Path) -> Path:
    dest = tmp_path / "corpora" / "c"
    shutil.copytree(duplicated_template, dest, symlinks=True)
    return dest


def test_sec19_a_sealed_corpus_records_the_collapse_in_its_index_register_origins_and_duplicates_summary(cli, duplicated):
    rows = vs.rows(duplicated)
    assert sorted(r["n_origins"] for r in rows) == [1, 1, 2]
    assert all(r["snapshot_ids"] == ["2024-06"] for r in rows)
    collapsed = next(r for r in rows if r["n_origins"] == 2)
    digest = collapsed["raw"][0]["sha256"]
    origins = [o for o in _jsonl(duplicated / "raw" / "origins.jsonl") if o["sha256"] == digest]
    assert len(origins) == 2 and len({o["origin"]["path"] for o in origins}) == 2
    register = _jsonl(duplicated / "register.jsonl")
    assert sum(1 for e in register if e["code"] == "dedup.collapsed") == 1
    manifest = vs.manifest(duplicated)
    assert manifest["duplicates"] == {"collapsed": 1, "content_dedup": "never", "multi_origin_executions": 1,
                                      "multi_snapshot_executions": 0, "owned_elsewhere": 0}
    assert manifest["counts"]["executions"] == 3
    run = verify(cli, duplicated, "--level", "chain")
    assert run.code == 0 and run.codes() == {}


@pytest.mark.parametrize("forgery", ["tally", "n_origins", "snapshot_ids"])
def test_sec19_a_forged_duplicate_record_is_detected_by_chain(cli, duplicated, forgery):
    """A consistent forgery (manifest digests and checksums regenerated) of the duplicate tallies, of a row's
    ``n_origins``, or of a row's ``snapshot_ids`` with the tallies left alone: ``chain`` recomputes the tallies from the
    index and register (D-41) and fails with ``manifest.duplicates``. Since the F-12C-02 fix the row is also reconciled
    with ``raw/origins.jsonl`` (``index.n_origins``) and with the manifest's snapshots (``index.snapshot.undeclared``)."""
    if forgery == "tally":
        vs.reforge(duplicated, change=lambda m: m["duplicates"].update(collapsed=0, multi_origin_executions=0))
        expected = {"manifest.duplicates": 1}
    elif forgery == "n_origins":
        vs.reforge(duplicated, index=lambda row: row.update(n_origins=1))
        expected = {"manifest.duplicates": 1, "index.n_origins": 1}
    else:
        vs.reforge(duplicated, index=lambda row: row.update(snapshot_ids=["2024-06", "head"]))
        expected = {"manifest.duplicates": 1, "index.snapshot.undeclared": 3}
    run = verify(cli, duplicated, "--level", "chain")
    assert run.code == 1 and run.codes() == expected


def test_sec19_a_dropped_second_origin_with_only_the_checksums_regenerated_is_detected(cli, duplicated):
    _drop_second_origin(duplicated)
    vs.regenerate_checksums(duplicated)
    run = verify(cli, duplicated, "--level", "chain")
    assert run.code == 1 and "manifest.files" in run.codes()


def _drop_second_origin(root: Path) -> None:
    collapsed = next(r for r in vs.rows(root) if r["n_origins"] == 2)
    digest = collapsed["raw"][0]["sha256"]
    path = root / "raw" / "origins.jsonl"
    lines = path.read_bytes().splitlines(keepends=True)
    dropped = next(i for i, line in enumerate(lines) if json.loads(line)["sha256"] == digest)
    path.write_bytes(b"".join(lines[:dropped] + lines[dropped + 1:]))


def test_sec19_a_collapsed_execution_whose_second_origin_was_dropped_is_never_passed(cli, duplicated):
    """F-12C-02 (b), fixed. A consistent forgery removes one of the two origins of a collapsed execution from
    ``raw/origins.jsonl`` (the row keeps ``n_origins: 2`` and the register keeps its ``dedup.collapsed`` entry).
    ``chain`` fails with ``index.n_origins`` (H.7.2(1): every origin appears in ``raw/origins.jsonl``); before the fix it
    exited 0."""
    _drop_second_origin(duplicated)
    vs.reforge(duplicated)
    run = verify(cli, duplicated, "--level", "chain", "--release", "--root-digest", vs.root_digest(duplicated))
    assert run.code == 1 and run.codes() == {"index.n_origins": 1}


def test_sec19_an_index_row_attributed_to_an_undeclared_snapshot_is_never_passed(cli, duplicated):
    """F-12C-02 (a), fixed. A consistent forgery attributes every execution to a second snapshot ``head`` that the
    manifest does not declare (``sources[0].snapshots`` lists only ``2024-06``) and updates
    ``duplicates.multi_snapshot_executions`` to match. ``chain`` fails with ``index.snapshot.undeclared`` (H.7.2(1): a
    row's snapshots are the corpus's snapshots; H.5.5 reconciles the index with the counts per snapshot); before the fix
    it exited 0 in dev and release mode."""
    published = vs.root_digest(duplicated)
    vs.reforge(duplicated, index=lambda row: row.update(snapshot_ids=["2024-06", "head"]),
               change=lambda m: m["duplicates"].update(multi_snapshot_executions=3))
    assert verify(cli, duplicated, "--level", "checksums", "--root-digest", published).code == 1  # the anchor holds
    for mode in ((), ("--release", "--root-digest", vs.root_digest(duplicated))):
        run = verify(cli, duplicated, "--level", "chain", *mode)
        assert run.code == 1 and run.codes() == {"index.snapshot.undeclared": 3}
