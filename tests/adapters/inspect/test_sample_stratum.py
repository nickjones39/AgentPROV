"""D-529 ``--sample-mode spread`` for ``inspect.eval``: one ``.eval`` log is one evaluation run, so its samples are one
stratum (the container label)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import import_support as support  # noqa: E402

from agentprov.adapters.inspect.dialect import InspectEvalReader
from agentprov.adapters.runner.importer import ImportSample, LocalTree, import_source
from agentprov.corpus.writer import CorpusWriter


def test_the_stratum_is_the_eval_log():
    assert InspectEvalReader.sample_stratum("logs/run-a.eval!/samples/1_epoch_1.json") == "logs/run-a.eval"
    assert InspectEvalReader.sample_stratum("logs/run-a.eval") == "logs/run-a.eval"


def test_the_stratum_of_a_nested_log_is_the_innermost_eval_and_anything_else_has_none():
    """NF-37 (regen item 131): the key splits at the last ``!/``; the head is a stratum only when it is an ``.eval``."""
    nested = "logs/inner.zip!/logs/x.eval!/samples/1_epoch_1.json"
    assert InspectEvalReader.sample_stratum(nested) == "logs/inner.zip!/logs/x.eval"
    assert InspectEvalReader.sample_stratum("logs/inner.zip!/logs/y.eval!/") == "logs/inner.zip!/logs/y.eval"  # failed plan
    assert InspectEvalReader.sample_stratum("elsewhere/file.json") is None
    assert InspectEvalReader.sample_stratum("logs/inner.zip!/notes.json") is None


def test_spread_over_a_nested_archive_draws_one_sample_per_eval_log(tmp_path, monkeypatch):
    """NF-37: three ``.eval`` logs, one beside a declared nested zip and two inside it, are three strata, so a spread
    sample of three takes one sample of each (before, both inner logs had the nested zip as their stratum)."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runner"))
    import test_nested_archives as nested

    from agentprov.adapters.runner import importer

    nested._profile(monkeypatch)
    pin, tree, _inner = nested._nested_input(
        tmp_path, direct={"logs/d.eval": nested._eval(3, samples=2)},
        inner={"logs/x.eval": nested._eval(10, samples=2), "logs/y.eval": nested._eval(11, samples=2)})
    seen: dict[str, Any] = {}
    select = importer.select_sample

    def spy(keys: Any, sample: ImportSample) -> frozenset[str]:
        seen["chosen"] = select(keys, sample)
        return seen["chosen"]

    monkeypatch.setattr(importer, "select_sample", spy)
    report = nested._import(tree, pin, tmp_path / "c", limits=nested.SMALL, sample=ImportSample(3, "spread"))
    assert report.counters["mapped"] == 3
    assert {key.rsplit("!/", 1)[0] for key in seen["chosen"]} == {
        "logs/d.eval", "logs/inner.zip!/logs/x.eval", "logs/inner.zip!/logs/y.eval"}


def test_spread_samples_a_container_import(tmp_path):
    support.inspect_tree(tmp_path / "in")
    with CorpusWriter(tmp_path / "c") as corpus:
        report = import_source("agent-security-tools-survey", LocalTree(tmp_path / "in"), corpus=corpus, part="agentharm",
                               until="aer", in_process=True, sample=ImportSample(2, "spread"),
                               pin_check=support.vouch(tmp_path / "in", repo=support.SURVEY, commit=support.SURVEY_COMMIT))
    assert report.counters["mapped"] == 2
    record = json.loads((tmp_path / "c.partial" / "corpus.json").read_text())["selection"]["sample"]
    assert record["mode"] == "spread" and record["stratum"] == "reader"
