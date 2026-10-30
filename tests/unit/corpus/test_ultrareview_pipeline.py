"""Ultrareview, area pipeline (``~/.agentprov/review/pipeline.findings.json``; user decision 2026-10-22, fix every serious
finding before the round): the import/derive findings #2, #4, #5 and #6."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import derive_support as ds
import pytest

from agentprov.cli.main import main
from agentprov.corpus.derive import resolve_plan
from agentprov.corpus.reader import CorpusReader


@pytest.fixture(autouse=True)
def _home(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> None:
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path_factory.mktemp("home")))
    monkeypatch.delenv("AGENTPROV_PROGRESS", raising=False)


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str]:
    capsys.readouterr()
    code = main([*argv, "--json", "--progress", "off", "--in-process"])
    return code, capsys.readouterr().err


def _manifest(corpus: Path) -> dict[str, Any]:
    return json.loads((ds.partial(corpus) / "corpus.json").read_text())


def _stages(corpus: Path) -> dict[str, dict[str, Any]]:
    return {s["stage"]: s for s in json.loads((ds.partial(corpus) / "derivation.json").read_text())["stages"]}


def _reader(corpus: Path) -> CorpusReader:
    return CorpusReader(ds.partial(corpus), state="working")


# ------------------------------------------------------------------------------------------------ #2
def test_skipping_tier_4_on_a_part_without_semantics_fails_no_execution(tmp_path):
    """No semantics profile and a skipped tier 4 leave no check beyond the AER validator: that is no failure. Before,
    every execution was ``failed`` with a ``validate.failed`` row "tiers 3-4: " and the import exited 1."""
    corpus = ds.agentdojo_corpus(tmp_path, count=2, semantics=[], prov_conformance=False)
    rows = ds.rows(ds.partial(corpus))
    assert rows and all(r["stages"]["validation"] == "ok" for r in rows)
    register = (ds.partial(corpus) / "register.jsonl").read_text()
    assert "validate.failed" not in register
    assert _manifest(corpus)["validation"] == {"prov_conformance": "skipped"}  # still marked unvalidated


def test_without_the_skip_a_missing_tier_4_still_fails(tmp_path):
    from types import SimpleNamespace

    from agentprov.adapters.runner.importer import _Pipeline

    row = {"checks": {"aer.validator": "pass"}}
    assert _Pipeline._tier4_verdict(SimpleNamespace(mode="dev", prov_conformance=True), row) == "fail"  # type: ignore[arg-type]
    assert _Pipeline._tier4_verdict(SimpleNamespace(mode="dev", prov_conformance=False), row) == "pass"  # type: ignore[arg-type]


# ------------------------------------------------------------------------------------------------ #4
def test_a_later_until_raw_run_keeps_the_furthest_stage(tmp_path):
    corpus = ds.agentdojo_corpus(tmp_path, count=2)
    ds.agentdojo_corpus(tmp_path, count=2, until="raw")  # the same corpus, re-run to store raw files only
    assert _manifest(corpus)["selection"]["until"] == "validation"  # before: "raw"
    assert resolve_plan(_reader(corpus), "recompute").until == "validation"


def test_a_lowered_until_in_an_older_manifest_is_read_from_the_layers(tmp_path):
    corpus = ds.agentdojo_corpus(tmp_path, count=2)
    path = ds.partial(corpus) / "corpus.json"
    manifest = json.loads(path.read_text())
    manifest["selection"]["until"] = "raw"  # as an importer before the fix wrote it
    path.write_text(json.dumps(manifest))
    assert resolve_plan(_reader(corpus), "recompute").until == "validation"  # before: "raw", and NEW held nothing


def test_a_raw_only_corpus_stays_raw(tmp_path):
    corpus = ds.agentdojo_corpus(tmp_path, count=2, until="raw")
    assert _manifest(corpus)["selection"]["until"] == "raw"
    assert resolve_plan(_reader(corpus), "recompute").until == "raw"


# ------------------------------------------------------------------------------------------------ #5
def test_a_release_import_records_its_mode_whatever_until_was(tmp_path):
    corpus = ds.agentdojo_corpus(tmp_path, count=2, mode="release", until="aer", in_process=False)
    assert _stages(corpus)["aer"]["mode"] == "release"
    assert resolve_plan(_reader(corpus), "recompute").mode == "release"  # before: "dev" (only validation said so)


def test_a_dev_import_aer_stage_is_unchanged_and_never_resumes_a_release_corpus(tmp_path):
    from agentprov.adapters.runner.importer import IdentityRefusedError

    dev = ds.agentdojo_corpus(tmp_path, name="dev", count=2, until="aer")
    assert "mode" not in _stages(dev)["aer"]
    ds.agentdojo_corpus(tmp_path, name="rel", count=1, mode="release", until="aer", in_process=False)
    with pytest.raises(IdentityRefusedError):
        ds.agentdojo_corpus(tmp_path, name="rel", count=2, until="aer")  # the dev run of a release corpus


# ------------------------------------------------------------------------------------------------ #6
def test_derive_adds_a_view_to_a_skipped_tier_4_corpus_under_the_same_setting(tmp_path, capsys):
    corpus = ds.agentdojo_corpus(tmp_path, count=2, prov_conformance=False)
    code, err = _run(capsys, "derive", "--corpus", str(corpus), "--out", str(tmp_path / "new"),
                     "--skip-prov-conformance", "--views", "transcript-v1")
    assert code in (0, 1) and "corpus.derive.version_mismatch" not in err, err  # before: refused, exit 4


# ------------------------------------------------------------------------------------------------ RC-9
def test_a_skip_recompute_of_a_validated_source_reuses_sem_and_prov(tmp_path, capsys):
    """Pre-round re-check RC-9: since PR-7 a --skip-prov-conformance recompute of a fully validated source reused
    nothing. It now carries SEM and PROV and rebuilds each validation row without tier 4, byte for byte what a
    recompute with --no-reuse writes."""
    from test_derive import _without_reuse_record, files, run

    src = ds.agentdojo_corpus(tmp_path, count=3)
    n = len(ds.rows(ds.partial(src)))
    trees = []
    for name, extra in (("reuse", []), ("full", ["--no-reuse"])):
        result = run(capsys, "recompute", "--corpus", str(src), "--out", str(tmp_path / name), "--stages",
                     "sem,prov,validation", "--skip-prov-conformance", *extra)
        assert result.code == 0, result.err
        trees.append(files(ds.partial(tmp_path / name)))
        if not extra:
            assert result.counters["reused"] == n  # before: 0
    assert _without_reuse_record(trees[0]) == _without_reuse_record(trees[1])
    results = [json.loads(line) for line in trees[0]["validation/results.jsonl"].decode().splitlines()]
    assert results and not any(k.startswith("pv.") for r in results for k in r["checks"])


def test_a_full_recompute_of_a_skipped_source_still_reuses_nothing(tmp_path, capsys):
    from test_derive import run

    src = ds.agentdojo_corpus(tmp_path, count=2, prov_conformance=False)
    result = run(capsys, "recompute", "--corpus", str(src), "--out", str(tmp_path / "new"), "--stages",
                 "sem,prov,validation")
    assert result.code == 0, result.err
    assert result.counters.get("reused", 0) == 0  # tier 4 runs: the run that clears the mark (G2c-5)


# ------------------------------------------------------------------------------------------------ V-7
def test_recompute_reproduces_an_execution_the_source_holds_at_the_aer_only(tmp_path, capsys):
    """Pre-round verification V-7: a corpus mapped to validation, then extended by an ``import --until aer`` run, holds
    one AER-only execution and keeps its furthest ``until`` (#4). Recompute derived SEM, PROV and validation for it too,
    and the dry run still called it identical (the comparison looks only at the layers the source row holds). It is
    now kept at the AER, so NEW's coverage is the source's, row for row."""
    from test_derive import run

    corpus = ds.agentdojo_corpus(tmp_path, count=2)
    ds.agentdojo_corpus(tmp_path, count=3, until="aer")
    source = {r["ex"]: sorted(r["stages"]) for r in ds.rows(ds.partial(corpus))}
    assert sorted(map(len, source.values())) == [2, 5, 5]  # one AER-only execution
    dry = run(capsys, "recompute", "--corpus", str(corpus), "--dry-run", "--in-process")
    assert dry.code == 0 and dry.counters["identical"] == 3 and dry.counters["derived"] == 2, dry.err
    out = run(capsys, "recompute", "--corpus", str(corpus), "--out", str(tmp_path / "new"), "--in-process", "--no-reuse")
    assert out.code == 0, out.err
    assert {r["ex"]: sorted(r["stages"]) for r in ds.rows(ds.partial(tmp_path / "new"))} == source
