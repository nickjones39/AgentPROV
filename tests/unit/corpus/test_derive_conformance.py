"""G2c-5 for derive and recompute (D-432, regen entry D-525): ``--skip-prov-conformance`` skips tier 4 of a recomputed
validation only, marks NEW, never changes a PROV byte, and the mark follows the validation layer NEW holds: kept when the
layer is carried, cleared by a full recompute."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import derive_support as ds
import pytest

from agentprov.cli.main import main


@pytest.fixture(autouse=True)
def _home(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> None:
    monkeypatch.setenv("AGENTPROV_HOME", str(tmp_path_factory.mktemp("home")))
    monkeypatch.delenv("AGENTPROV_PROGRESS", raising=False)


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, dict[str, Any], str]:
    capsys.readouterr()
    code = main([*argv, "--json", "--progress", "off", "--in-process"])
    out, err = capsys.readouterr()
    return code, json.loads(out.splitlines()[-1]) if out.strip() else {}, err


def _manifest(corpus: Path) -> dict[str, Any]:
    return json.loads((ds.partial(corpus) / "corpus.json").read_text())


def _validation_stage(corpus: Path) -> dict[str, Any]:
    stages = json.loads((ds.partial(corpus) / "derivation.json").read_text())["stages"]
    return next(s for s in stages if s["stage"] == "validation")


def _prov(corpus: Path) -> dict[str, bytes]:
    root = ds.partial(corpus)
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted((root / "prov").rglob("*")) if p.is_file()}


@pytest.fixture(scope="module")
def source(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return ds.agentdojo_corpus(tmp_path_factory.mktemp("src"), count=2)


def test_a_skipped_recompute_marks_new_and_changes_no_prov_byte(capsys, source, tmp_path):
    code, summary, err = _run(capsys, "recompute", "--corpus", str(source), "--out", str(tmp_path / "s"),
                              "--stages", "sem,prov,validation", "--skip-prov-conformance")
    assert code == 0, err
    assert any("--skip-prov-conformance" in n for n in summary["notices"])
    assert _manifest(tmp_path / "s")["validation"] == {"prov_conformance": "skipped"}
    stage = _validation_stage(tmp_path / "s")
    assert stage["skipped"] == ["tier4:agentprov-prov/0.1"] and not any(c.startswith("tier4:") for c in stage["checks"])
    assert _run(capsys, "recompute", "--corpus", str(source), "--out", str(tmp_path / "f"),
                "--stages", "sem,prov,validation")[0] == 0
    assert _prov(tmp_path / "s") == _prov(tmp_path / "f")
    assert "validation" not in _manifest(tmp_path / "f")


def test_a_skipped_layer_is_never_carried_and_a_full_recompute_clears_the_mark(capsys, source, tmp_path):
    assert _run(capsys, "recompute", "--corpus", str(source), "--out", str(tmp_path / "s"),
                "--stages", "sem,prov,validation", "--skip-prov-conformance")[0] == 0
    code, _summary, err = _run(capsys, "derive", "--corpus", str(tmp_path / "s"), "--out", str(tmp_path / "v"),
                               "--views", "transcript-v1")
    assert code == 4 and "corpus.derive.version_mismatch" in err  # a skipped validation is another version: recompute
    code, _summary, err = _run(capsys, "recompute", "--corpus", str(tmp_path / "s"), "--out", str(tmp_path / "c"),
                               "--stages", "sem,prov,validation")
    assert code in (0, 1), err
    assert "validation" not in _manifest(tmp_path / "c")  # a full recompute ran tier 4 again


def test_a_release_corpus_refuses_the_skip(source, monkeypatch):
    from agentprov.corpus import derive
    from agentprov.corpus.reader import CorpusReader

    monkeypatch.setattr(derive, "_mode_of", lambda stages: "release")
    with pytest.raises(ValueError, match="dev-mode option"):
        derive.resolve_plan(CorpusReader.open(str(source)), "recompute", stages=["sem", "prov", "validation"],
                            prov_conformance=False)


@pytest.mark.parametrize("first", [True, False], ids=["skipped-then-full", "full-then-skipped"])
def test_a_recompute_is_never_resumed_under_the_other_conformance_setting(capsys, tmp_path, monkeypatch, first):
    """Pre-round review PR-7: a recompute interrupted under --skip-prov-conformance and resumed without it was accepted,
    and NEW claimed full tier 4 with rows that carry no PV checks. The setting is now part of the resume identity (the
    validation stage definition in ``derived_from``), so either change of it is refused."""
    from agentprov.corpus import derive

    src = ds.agentdojo_corpus(tmp_path, count=2)
    out = tmp_path / "new"
    real, calls = derive.Derivation._finish_unit, {"n": 0}

    def flaky(self: Any, *args: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 2:
            raise KeyboardInterrupt
        return real(self, *args, **kwargs)

    skip = ["--skip-prov-conformance"]
    argv = ["recompute", "--corpus", str(src), "--out", str(out), "--stages", "sem,prov,validation", "--no-reuse"]
    monkeypatch.setattr(derive.Derivation, "_finish_unit", flaky)
    code, _, _ = _run(capsys, *argv, *(skip if first else []))
    assert code == 130 and ds.partial(out).exists()
    monkeypatch.setattr(derive.Derivation, "_finish_unit", real)
    code, _, err = _run(capsys, *argv, *([] if first else skip))
    assert code == 4 and "corpus.derive.resume_mismatch" in err
    code, _, err = _run(capsys, *argv, *(skip if first else []))  # the same setting resumes it
    assert code in (0, 1), err
