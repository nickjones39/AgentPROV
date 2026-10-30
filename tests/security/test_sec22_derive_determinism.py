"""SEC-22: ``derive`` and ``recompute`` outputs do not depend on worker count, run, process or hash seed (G.10 SEC-22;
K.12.10; K.13 RPR-8; invariant 4; HL H.8; T-01...T-06, T-26).

Invariant 4: provenance is recomputed from the AER and compared as bytes, identical across runs, processes and worker
counts. Phase 11 proved ``recompute`` from raw identical for ``--jobs 1``, ``--jobs 4`` and ``--in-process`` on one
AgentDojo corpus (``tests/unit/corpus/test_derive.py::test_outputs_do_not_depend_on_the_worker_count``). Added here:

* ``derive`` (adding SEM, PROV and validation to an AER-only corpus) for ``--jobs 1``, ``--jobs 3``, ``--in-process`` and
  a second ``--jobs 3`` run: byte-identical trees (the recorded ``producer.isolation`` aside, D-43);
* ``recompute`` with both stage sets (``sem,prov,validation`` from the stored AER; the default re-map from the stored raw
  objects) repeated and across worker counts, for the AgentDojo family and the archive-container family (a synthetic
  Inspect ``.eval``, whose re-map re-runs ``expand`` in T1);
* the ``--json`` summaries of those runs, byte-identical across worker counts;
* ``slow``: the same commands in fresh interpreters with ``PYTHONHASHSEED`` 0 and 4242, against the in-process tree.

The default run keeps one case per command (``derive`` on AgentDojo, ``recompute`` from raw on the container family, its
dry-run summary); the other families and stage sets are ``slow``.

Source corpora are built at test time (golden licence-cleared AgentDojo logs, never printed; a synthetic ``.eval``) and
every command runs under ``fs_guard`` over its source.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import corpus_harness as harness
import derive_support as ds
import pytest

from agentprov.io.canonical import jcs_bytes
from agentprov.testing import fs_guard

cli = harness.cli  # the corpus_harness fixture, bound in this module so pytest finds it

WORKERS = (("j1", ["--jobs", "1"]), ("j3", ["--jobs", "3"]), ("j3-again", ["--jobs", "3"]), ("ip", ["--in-process"]))


#: D-780: the building commit and its history. An in-process run of the suite records the fixed test commit; a fresh
#: interpreter reads git, so the two are compared without them (each fresh run is compared with the other below).
BUILD_KEYS = ("git_commit", "git_tree_clean", "git_commit_absent_reason", "build_steps")


def _comparable(tree: dict[str, bytes], *, without_build: bool = False) -> dict[str, bytes]:
    """The tree with the one value that records how the jobs ran (``producer.isolation``, D-43) removed, and with
    ``without_build`` the building commit too."""
    manifest = json.loads(tree["corpus.json"])
    manifest["producer"].pop("isolation", None)
    for key in BUILD_KEYS if without_build else ():
        manifest["producer"].pop(key, None)
    return {**tree, "corpus.json": jcs_bytes(manifest)}


def _summary(run: Any) -> dict[str, Any]:
    document = json.loads(run.out.strip().split("\n")[-1])
    for key in ("elapsed_s", "duration_s", "timing"):
        document.pop(key, None)
    return document


@pytest.fixture(scope="module")
def sources(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    base = tmp_path_factory.mktemp("sec22-sources")
    return {
        "agentdojo-aer": ds.agentdojo_corpus(base, name="agentdojo-aer", count=3, until="aer"),
        "agentdojo": ds.agentdojo_corpus(base, name="agentdojo", count=3),
        "inspect-aer": harness.inspect_working(base / "inspect-aer", mode="dev", samples=2, until="aer"),
        "inspect": harness.inspect_working(base / "inspect", mode="dev", samples=2),
    }


def _runs(cli: Any, tmp_path: Path, src: Path, *argv: str) -> tuple[dict[str, dict[str, bytes]], dict[str, Any]]:
    trees, summaries = {}, {}
    for name, flags in WORKERS:
        out = tmp_path / name
        with fs_guard.unchanged(ds.partial(src)):
            run = cli(*argv, "--corpus", str(src), "--out", str(out), *flags, "--json", "--progress", "off")
        assert run.code == 0, run.err
        trees[name] = ds.tree_bytes(ds.partial(out))
        summaries[name] = _summary(run)
    return trees, summaries


def _assert_identical(trees: dict[str, dict[str, bytes]]) -> None:
    reference = trees["j1"]
    assert len(reference) > 5
    for name, tree in trees.items():
        if name == "ip":
            assert _comparable(tree) == _comparable(reference), sorted(
                k for k in tree if _comparable(tree).get(k) != _comparable(reference).get(k))
            assert tree["corpus.json"] != reference["corpus.json"]  # isolation recorded as "in-process"
        else:
            assert tree == reference, (name, sorted(k for k in tree if tree.get(k) != reference.get(k)))


@pytest.mark.parametrize("family", ["agentdojo-aer", pytest.param("inspect-aer", marks=pytest.mark.slow)])
def test_sec22_derive_is_byte_identical_across_worker_counts_runs_and_in_process(cli, sources, tmp_path, family):
    trees, summaries = _runs(cli, tmp_path, sources[family], "derive", "--no-reuse")
    _assert_identical(trees)
    rows = [json.loads(line) for line in trees["j1"]["executions.jsonl"].split(b"\n") if line]
    assert rows and all({"sem", "prov", "validation"} <= set(r["stages"]) for r in rows)  # the layers were derived
    assert summaries["j1"]["counters"] == summaries["j3"]["counters"] == summaries["j3-again"]["counters"]


@pytest.mark.parametrize(("family", "stages"), [
    pytest.param("inspect", None, id="inspect-from-raw"),
    pytest.param("inspect", "sem,prov,validation", id="inspect-from-aer", marks=pytest.mark.slow),
    pytest.param("agentdojo", None, id="agentdojo-from-raw", marks=pytest.mark.slow),
    pytest.param("agentdojo", "sem,prov,validation", id="agentdojo-from-aer", marks=pytest.mark.slow),
])
def test_sec22_recompute_is_byte_identical_across_worker_counts_runs_and_in_process(cli, sources, tmp_path, family,
                                                                                    stages):
    argv = ["recompute", "--no-reuse", *(["--stages", stages] if stages else [])]
    trees, summaries = _runs(cli, tmp_path, sources[family], *argv)
    _assert_identical(trees)
    if family == "inspect" and stages is None:
        members = trees["j1"]["raw/members.jsonl"]
        assert members and members == ds.tree_bytes(ds.partial(sources[family]))["raw/members.jsonl"]  # expand re-run
    assert summaries["j1"]["counters"] == summaries["j3"]["counters"] == summaries["j3-again"]["counters"]
    assert summaries["j1"]["counters"]["identical"] == summaries["j1"]["counters"]["selected"] > 0


@pytest.mark.parametrize("family", ["inspect", pytest.param("agentdojo", marks=pytest.mark.slow)])
def test_sec22_recompute_dry_run_summaries_are_byte_identical_across_worker_counts(cli, sources, family):
    src = sources[family]
    documents = []
    for flags in (["--jobs", "1"], ["--jobs", "3"], ["--in-process"]):
        with fs_guard.unchanged(ds.partial(src)):
            run = cli("recompute", "--corpus", str(src), "--dry-run", *flags, "--json", "--progress", "off")
        assert run.code == 0, run.err
        documents.append(_summary(run))
    for document in documents:
        document.get("notices", []).sort()
    assert jcs_bytes(documents[0]["counters"]) == jcs_bytes(documents[1]["counters"]) == jcs_bytes(documents[2]["counters"])
    assert documents[0]["failures"] == documents[1]["failures"] == documents[2]["failures"] == []


# ------------------------------------------------------------------------------------------------ fresh interpreters
def _fresh(argv: list[str], seed: str, home: Path) -> subprocess.CompletedProcess[bytes]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("AGENTPROV_", "PYTHONHASHSEED"))}
    env.update(PYTHONHASHSEED=seed, AGENTPROV_HOME=str(home))
    return subprocess.run([sys.executable, "-m", "agentprov", *argv, "--progress", "off"], env=env, capture_output=True,
                          timeout=600, check=False)


@pytest.mark.slow
@pytest.mark.parametrize(("command", "family"), [("derive", "agentdojo-aer"), ("derive", "inspect-aer"),
                                                 ("recompute", "agentdojo"), ("recompute", "inspect")])
def test_sec22_outputs_do_not_depend_on_the_process_or_its_hash_seed(cli, sources, tmp_path, command, family):
    src = sources[family]
    with fs_guard.unchanged(ds.partial(src)):
        reference = cli(command, "--corpus", str(src), "--out", str(tmp_path / "ip"), "--no-reuse", "--in-process",
                        "--json", "--progress", "off")
    assert reference.code == 0, reference.err
    expected = _comparable(ds.tree_bytes(ds.partial(tmp_path / "ip")), without_build=True)
    steps: list[Any] = []
    for seed in ("0", "4242"):
        out = tmp_path / f"seed-{seed}"
        with fs_guard.unchanged(ds.partial(src)):
            done = _fresh([command, "--corpus", str(src), "--out", str(out), "--no-reuse", "--jobs", "2"], seed,
                          tmp_path / f"home-{seed}")
        assert done.returncode == 0, done.stderr.decode("utf-8", "replace")[-2000:]
        tree = ds.tree_bytes(ds.partial(out))
        assert _comparable(tree, without_build=True) == expected, seed
        producer = json.loads(tree["corpus.json"])["producer"]
        steps.append({k: producer.get(k) for k in BUILD_KEYS})
    assert steps[0] == steps[1] and steps[0]["build_steps"], "the building commit is the same in every fresh process"
