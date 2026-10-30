"""The import pipeline ``import_source`` (docs/architecture D.2.9; MN N.2.2; HL H.1, H.6.1; K.13 determinism).

Library-level tests over small real inputs (the golden fixtures, loaded programmatically) and synthetic ones: the pinned
origins (git tree, ``--verify-against-pin`` blob and listing checks), byte identity with the adapter-level mapping, the
container (Inspect) mode, identity guards and interruption. No test touches the network: the git pin is a local
repository fetched through the test seam of ``raw.fetch``.
"""

from __future__ import annotations

import json
import sys
import os
import subprocess
from pathlib import Path
from typing import Any

import import_support as support
import pytest
from fetch_support import REPO_URL, git, needs_git

from agentprov.adapters.adprov.dialect import TranscriptV1Reader
from agentprov.adapters.runner import aer_bytes, map_artefact
from agentprov.adapters.runner.importer import (
    GitPinTree,
    IdentityRefusedError,
    ImportFilters,
    LocalTree,
    PinCheck,
    UnpinnedInputError,
    git_blob_sha1,
    import_source,
    listing_sha256,
)
from agentprov.adapters.types import Origin
from agentprov.corpus.writer import CorpusWriter
from agentprov.io.canonical import sha256_hex
from agentprov.progress import ProgressEvent
from agentprov.raw.fetch import Fetcher, Recipe

AGENTDOJO = "https://github.com/ethz-spylab/agentdojo"
C274885 = "c274885610efaaafec38b6d3eb07152ba7ff3f94"
BASELINE = "579a908354b93361efe0905ffb7623256aa96a06"
AER_DIGESTS = Path(__file__).resolve().parents[1] / "agentdojo" / "aer_digests.json"


def _run(source: str, tree: Any, out: Path, **kwargs: Any) -> Any:
    kwargs.setdefault("in_process", True)
    if isinstance(tree, LocalTree) and "pin_check" not in kwargs:
        survey = {"repo": support.SURVEY, "commit": support.SURVEY_COMMIT} if source == "agent-security-tools-survey" else {}
        kwargs["pin_check"] = support.vouch(Path(tree.root), **survey)
    with CorpusWriter(out) as corpus:
        return import_source(source, tree, corpus=corpus, **kwargs)


def _aers(partial: Path) -> dict[str, bytes]:
    rows = [json.loads(line) for line in (partial / "executions.jsonl").read_text().splitlines()]
    return {row["ex"]: (partial / row["paths"]["aer"]).read_bytes() for row in rows}


def _header(data: bytes) -> dict[str, Any]:
    return json.loads(data.split(b"\n", 1)[0])


# ------------------------------------------------------------------------------------------------ pinned origins
def test_verify_against_a_git_listing_gives_the_golden_aer_bytes(tmp_path):
    """A file whose blob id matches the pin's tree gets the pinned git origin, and the product path then writes exactly the
    AER bytes the adapter tests pin (tests/adapters/agentdojo/aer_digests.json; D.6.10 item 1)."""
    entries = support.agentdojo_tree(tmp_path / "in")
    listing = {path: str(e.origin["git_blob_sha1"]) for path, e in entries.items()}
    check = PinCheck("blob", {"commit": C274885, "role": "2024-06"}, listing=listing, repo=AGENTDOJO)
    report = _run("agentdojo", LocalTree(tmp_path / "in"), tmp_path / "c", part="2024-06", pin_check=check, until="aer")
    assert report.exit_code == 0 and report.counters["mapped"] == len(entries) and check.verified == len(entries)
    expected = json.loads(AER_DIGESTS.read_text(encoding="utf-8"))
    produced = {}
    for data in _aers(tmp_path / "c.partial").values():
        origin = _header(data)["artifacts"][0]["origin"]
        assert origin["kind"] == "git" and origin["commit"] == C274885
        produced[next(e.id for p, e in entries.items() if p == origin["path"])] = sha256_hex(data)
    assert produced == {k: v for k, v in expected.items() if k in produced} and len(produced) == len(entries)


def test_a_file_the_pin_does_not_vouch_for_is_registered_not_imported(tmp_path):
    """Its AER could carry only a local origin, which the release-mode AER writer refuses (C.17 AER-V20)."""
    entries = support.agentdojo_tree(tmp_path / "in", count=2)
    first = next(iter(entries))
    check = PinCheck("blob", {"commit": C274885}, listing={first: "0" * 40}, repo=AGENTDOJO)
    report = _run("agentdojo", LocalTree(tmp_path / "in"), tmp_path / "c", part="2024-06", pin_check=check, until="aer")
    assert check.unverified == 2 and check.verified == 0
    assert (report.counters["mapped"], report.counters["registered"], report.exit_code) == (0, 2, 1)
    assert {f["code"] for f in report.failures} == {"raw.origin.blob_mismatch"}
    assert (tmp_path / "c.partial" / "executions.jsonl").read_bytes() == b""
    assert any("did not match the pin" in n for n in report.notices)


def test_an_input_tree_without_a_pin_check_is_refused(tmp_path):
    support.agentdojo_tree(tmp_path / "in", count=1)
    with pytest.raises(UnpinnedInputError):
        _run("agentdojo", LocalTree(tmp_path / "in"), tmp_path / "c", part="2024-06", pin_check=None)
    assert not (tmp_path / "c.partial" / "executions.jsonl").exists()


def test_a_listing_pin_gives_the_frozen_corpus_origin_and_the_migration_bytes(tmp_path):
    """The AgentDojo-PROV trees are pinned by their J.1.4 listing digest; a match records the corpus origin the migration
    gates record, so the AER bytes equal the adapter-level mapping of those gates."""
    labels = support.adprov_tree(tmp_path / "in")
    pairs = [(label, sha256_hex((tmp_path / "in" / label).read_bytes())) for label in labels]
    pin = {"role": "release", "tree": "corpus/corpus-prov", "commit": BASELINE, "listing_sha256": listing_sha256(pairs),
           "expected_files": len(pairs)}
    check = PinCheck("listing", pin, listing_origin=TranscriptV1Reader.listing_origin)
    report = _run("adprov-v1", LocalTree(tmp_path / "in"), tmp_path / "c", part="release", pin_check=check, until="aer")
    assert report.exit_code == 0 and check.listing_ok and check.verified == len(labels)
    produced = {_header(d)["artifacts"][0]["origin"]["path"]: d for d in _aers(tmp_path / "c.partial").values()}
    for label in labels:
        raw = (tmp_path / "in" / label).read_bytes()
        origin = Origin.corpus("AgentDojo-PROV", "2.3", f"corpus-prov/{label}", producer_commit=BASELINE)
        expected, _info = aer_bytes(map_artefact(raw, origin, profile_id="adprov-v1")[0])
        assert produced[f"corpus-prov/{label}"] == expected


def test_a_listing_mismatch_keeps_every_origin_local(tmp_path):
    support.adprov_tree(tmp_path / "in")
    pin = {"tree": "corpus/corpus-prov", "commit": BASELINE, "listing_sha256": "0" * 64}
    check = PinCheck("listing", pin, listing_origin=TranscriptV1Reader.listing_origin)
    _run("adprov-v1", LocalTree(tmp_path / "in"), tmp_path / "c", part="release", pin_check=check, until="aer")
    assert check.listing_ok is False and check.verified == 0


@needs_git
def test_a_git_pin_tree_reads_verified_blobs_with_git_origins(tmp_path):
    entries = support.agentdojo_tree(tmp_path / "upstream", count=3)
    repo = tmp_path / "upstream"
    git(repo, "init", "-q", "-b", "main")
    (repo / "README.md").write_bytes(b"not a candidate\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "runs")
    commit = git(repo, "rev-parse", "HEAD")
    recipe = Recipe(kind="git", repo=REPO_URL, commit=commit, paths=("runs/",))
    fetcher = Fetcher(tmp_path / "cache", allow_network=True, remote_urls={REPO_URL: f"file://{repo}"}, file_protocol=True)
    fetcher.fetch(recipe)
    tree = GitPinTree(Fetcher(tmp_path / "cache"), recipe)  # the second fetcher has no network: the cache serves
    report = _run("agentdojo", tree, tmp_path / "c", part="2024-06", until="aer")
    assert report.counters["seen"] == report.counters["mapped"] == 3
    for data in _aers(tmp_path / "c.partial").values():
        origin = _header(data)["artifacts"][0]["origin"]
        raw = entries[origin["path"]].native_bytes()
        assert origin == {"kind": "git", "repo": REPO_URL, "commit": commit, "path": origin["path"], "blob_sha1": git_blob_sha1(raw)}
        expected, _info = aer_bytes(map_artefact(raw, Origin.git(REPO_URL, commit, origin["path"], git_blob_sha1(raw)),
                                                 profile_id="agentdojo-upstream")[0])
        assert data == expected
    rows = [json.loads(line) for line in (tmp_path / "c.partial" / "raw" / "origins.jsonl").read_text().splitlines()]
    assert len(rows) == 3 and {r["origin"]["kind"] for r in rows} == {"git"}


# ------------------------------------------------------------------------------------------------ determinism
def test_outputs_do_not_depend_on_workers_batches_or_in_process(tmp_path):
    support.agentdojo_tree(tmp_path / "in", count=4)
    runs = {
        "in-process": {"in_process": True, "batch_size": 256},
        "one-worker": {"in_process": False, "workers": 1, "batch_size": 1},
        "three-workers": {"in_process": False, "workers": 3, "batch_size": 3},
    }
    trees = {}
    for name, options in runs.items():
        report = _run("agentdojo", LocalTree(tmp_path / "in"), tmp_path / name, part="2024-06", **options)
        assert report.exit_code == 0 and report.counters["validated"] == 4
        files = support.tree_bytes(tmp_path / f"{name}.partial")
        manifest = json.loads(files.pop("corpus.json"))
        manifest["producer"].pop("isolation")
        trees[name] = (files, manifest)
    first = trees["in-process"]
    for name, other in trees.items():
        assert other[0] == first[0], name
        assert other[1] == first[1], name


# ------------------------------------------------------------------------------------------------ dispositions
def test_dispositions_degenerate_not_dialect_duplicate_and_excluded(tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agentdojo"))
    import agentdojo_support

    entries = support.agentdojo_tree(tmp_path / "in", count=1)
    (path,) = entries
    data = (tmp_path / "in" / path).read_bytes()
    extra = {
        # a TraceLogger log with a malformed field: a degenerate AER (D.2.8 case 3)
        "runs/m/banking/user_task_0/none/none.json": agentdojo_support.log_bytes(agentdojo_support.base_log(injections=[1])),
        # not JSON at all: no value was read, so the degenerate header declares the task id not captured (D-219,
        # aer/0.2) and the artefact seals as a degenerate AER too
        "runs/m/s/t/a/bad.json": b'{"broken": ',
        "runs/m/s/t/a/other.json": b'{"not": "a trace logger log"}',  # valid JSON, another dialect: a register entry
        "runs/m/s/t/a/copy.json": data,  # identical bytes at a second path: dedup.collapsed
        "runs/m/s/t/a/.DS_Store": b"stray",  # never a candidate
    }
    for rel, body in extra.items():
        target = tmp_path / "in" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
    report = _run("agentdojo", LocalTree(tmp_path / "in"), tmp_path / "c", part="2024-06")
    c = report.counters
    assert (c["seen"], c["mapped"], c["degenerate"], c["failed"], c["registered"], c["duplicates"]) == (5, 3, 2, 0, 1, 1)
    assert report.exit_code == 1
    assert sorted(f["code"] for f in report.failures) == ["map.unparseable_artefact", "map.unparseable_artefact"]
    register = [json.loads(line) for line in (tmp_path / "c.partial" / "register.jsonl").read_text().splitlines()]
    codes = {r["code"] for r in register}
    assert {"dedup.collapsed", "select.not_execution_artefact", "map.unparseable_artefact"} <= codes
    assert "map.adapter_defect" not in codes  # D-219: the unparseable artefact seals as a degenerate AER, not a failed unit
    stored = {json.loads(line)["sha256"] for line in (tmp_path / "c.partial" / "raw" / "origins.jsonl").read_text().splitlines()}
    assert "sha256:" + sha256_hex(b'{"broken": ') in stored  # store-first: the unmappable bytes are kept
    rows = [json.loads(line) for line in (tmp_path / "c.partial" / "executions.jsonl").read_text().splitlines()]
    assert sorted(r["status"] for r in rows) == ["failed", "failed", "ok"]
    degenerate = next(r for r in rows if r["status"] == "failed")
    assert degenerate["stages"]["prov"] == {"agentprov-prov/0.1": "ok"}  # a degenerate AER still derives (header only)
    origins = [json.loads(line) for line in (tmp_path / "c.partial" / "raw" / "origins.jsonl").read_text().splitlines()]
    assert sum(1 for o in origins if o["sha256"] == "sha256:" + sha256_hex(data)) == 2


def test_filters_apply_after_mapping_and_mark_the_corpus_partial(tmp_path):
    entries = support.agentdojo_tree(tmp_path / "in")
    suites = sorted({json.loads(e.native_bytes())["suite_name"] for e in entries.values()})
    keep = suites[0]
    report = _run("agentdojo", LocalTree(tmp_path / "in"), tmp_path / "c", part="2024-06", until="aer",
                  filters=ImportFilters(select={"suite": frozenset({keep})}))
    expected = sum(1 for e in entries.values() if json.loads(e.native_bytes())["suite_name"] == keep)
    assert report.counters["mapped"] == expected and report.counters["filtered"] == len(entries) - expected
    manifest = json.loads((tmp_path / "c.partial" / "corpus.json").read_text())
    assert manifest["partial"] is True and manifest["selection"]["filters"]["select"] == {"suite": [keep]}


def test_limit_counts_newly_written_units_and_resume_continues(tmp_path):
    support.agentdojo_tree(tmp_path / "in", count=5)
    tree = LocalTree(tmp_path / "in")
    first = _run("agentdojo", tree, tmp_path / "c", part="2024-06", until="aer", limit=2)
    assert first.counters["mapped"] == 2
    second = _run("agentdojo", tree, tmp_path / "c", part="2024-06", until="aer", limit=2)
    assert (second.counters["mapped"], second.counters["skipped_resume"]) == (2, 2)
    third = _run("agentdojo", tree, tmp_path / "c", part="2024-06", until="aer")
    assert (third.counters["mapped"], third.counters["skipped_resume"]) == (1, 4)
    whole = _run("agentdojo", tree, tmp_path / "w", part="2024-06", until="aer")
    a, b = support.tree_bytes(tmp_path / "c.partial"), support.tree_bytes(tmp_path / "w.partial")
    ma, mb = json.loads(a.pop("corpus.json")), json.loads(b.pop("corpus.json"))
    assert a == b and ma["counts"] == mb["counts"] and whole.counters["mapped"] == 5


def test_an_interrupted_import_flushes_and_resumes_to_the_same_tree(tmp_path):
    support.agentdojo_tree(tmp_path / "in", count=4)

    class Stop:
        done = 0

        def emit(self, event: ProgressEvent) -> None:
            if event.kind == "unit_done":
                Stop.done += 1
                if Stop.done == 2:
                    raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        _run("agentdojo", LocalTree(tmp_path / "in"), tmp_path / "c", part="2024-06", until="aer", batch_size=1,
             progress=Stop())
    assert len((tmp_path / "c.partial" / "executions.jsonl").read_text().splitlines()) == 2
    resumed = _run("agentdojo", LocalTree(tmp_path / "in"), tmp_path / "c", part="2024-06", until="aer")
    assert resumed.counters["skipped_resume"] == 2 and resumed.counters["mapped"] == 2
    _run("agentdojo", LocalTree(tmp_path / "in"), tmp_path / "w", part="2024-06", until="aer")
    a, b = support.tree_bytes(tmp_path / "c.partial"), support.tree_bytes(tmp_path / "w.partial")
    a.pop("corpus.json"), b.pop("corpus.json")
    assert a == b


def test_a_working_corpus_of_another_identity_is_refused(tmp_path):
    support.agentdojo_tree(tmp_path / "in", count=1)
    _run("agentdojo", LocalTree(tmp_path / "in"), tmp_path / "c", part="2024-06", until="aer", corpus_id="one")
    with pytest.raises(IdentityRefusedError):
        _run("agentdojo", LocalTree(tmp_path / "in"), tmp_path / "c", part="2024-06", until="aer", corpus_id="two")


def test_a_dry_run_writes_nothing_and_reports_the_same_counters(tmp_path):
    support.agentdojo_tree(tmp_path / "in", count=2)
    before = sorted(p.name for p in tmp_path.iterdir())
    dry = import_source("agentdojo", LocalTree(tmp_path / "in"), corpus=None, dry_run=True, part="2024-06", in_process=True,
                        pin_check=support.vouch(tmp_path / "in"))
    assert sorted(p.name for p in tmp_path.iterdir()) == before
    real = _run("agentdojo", LocalTree(tmp_path / "in"), tmp_path / "c", part="2024-06")
    assert dry.counters == real.counters and dry.corpus_root is None


# ------------------------------------------------------------------------------------------------ container mode
def test_an_inspect_log_is_expanded_planned_and_mapped_per_sample(tmp_path):
    support.inspect_tree(tmp_path / "in")
    report = _run("agent-security-tools-survey", LocalTree(tmp_path / "in"), tmp_path / "c", part="agentharm", limit=3)
    assert report.exit_code == 0 and report.counters["seen"] == 1
    assert report.counters["mapped"] == report.counters["validated"] == 3
    partial = tmp_path / "c.partial"
    members = [json.loads(line) for line in (partial / "raw" / "members.jsonl").read_text().splitlines()]
    assert sum(1 for m in members if m["disposition"] == "selected") >= 177  # header.json + 176 samples
    for data in _aers(partial).values():
        artefacts = _header(data)["artifacts"]
        assert artefacts[0]["origin"]["kind"] == "member" and artefacts[0]["role"] == "primary"
        assert [a["role"] for a in artefacts[1:]] == ["supporting"]  # header.json, the auxiliary artefact
    derivation = json.loads((partial / "derivation.json").read_text())
    assert [s["stage"] for s in derivation["stages"]] == ["expand", "aer", "sem", "prov", "validation"]
    assert len(list((partial / "sem" / "inspect.agentharm-2").rglob("*.sem.jsonl"))) == report.counters["annotated"] == 3


def test_an_out_of_band_inspect_log_is_registered_dialect_planned(tmp_path):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "inspect"))
    import inspect_support

    data = inspect_support.build_eval(inspect_support.synthetic_header(producer="0.3.100"),
                                      {"s1_epoch_1.json": inspect_support.basic_sample("s1")})
    target = tmp_path / "in" / "agentharm" / "results" / "x" / "log.eval"
    target.parent.mkdir(parents=True)
    target.write_bytes(data)
    report = _run("agent-security-tools-survey", LocalTree(tmp_path / "in"), tmp_path / "c", part="agentharm")
    assert report.exit_code == 0 and report.counters["mapped"] == 0 and report.counters["registered"] == 1
    assert [r["code"] for r in report.register] == ["select.dialect_planned"]


# ------------------------------------------------------------------------------------------------ helpers
def test_listing_digest_is_the_j14_construction():
    pairs = [("b/x.transcript.json", "1" * 64), ("a/y.transcript.json", "2" * 64)]
    expected = sha256_hex(b"2222222222222222222222222222222222222222222222222222222222222222  a/y.transcript.json\n"
                          b"1111111111111111111111111111111111111111111111111111111111111111  b/x.transcript.json\n")
    assert listing_sha256(pairs) == expected


def test_git_blob_sha1_matches_git(tmp_path):
    data = b"hello\n"
    (tmp_path / "f").write_bytes(data)
    if subprocess.run(["git", "--version"], capture_output=True).returncode != 0:  # pragma: no cover
        pytest.skip("git is not installed")
    out = subprocess.run(["git", "hash-object", str(tmp_path / "f")], capture_output=True, text=True, check=True,
                         env={**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
    assert git_blob_sha1(data) == out.stdout.strip()
