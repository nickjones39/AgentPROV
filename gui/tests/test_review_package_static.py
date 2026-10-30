"""GUI review GR-54 (GR-23 follow-up): on the job-driven steps 1 (Corpus) and 5 (Seal) the 1 s timer refreshes only the
job status. The preconditions (corpus.json, the writer's lock, the checkout's git state) and the conformance mark are
read once per step, corpus field, checkout or finished-job change, never on every tick."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> Counter[str]:
    from agentprov.corpus.reader import CorpusReader

    import agentprov_gui.ui.package as package

    seen: Counter[str] = Counter()
    real_summarise, real_manifest = package.summarise, CorpusReader.manifest

    def summarise(path: Path) -> Any:
        seen["summarise"] += 1
        return real_summarise(path)

    def manifest(self: CorpusReader) -> Any:
        seen["manifest"] += 1
        return real_manifest(self)

    def git_commit(repo: Path) -> str:
        seen["git"] += 1
        return "0" * 40

    monkeypatch.setattr(package, "summarise", summarise)
    monkeypatch.setattr(package, "git_commit", git_commit)
    monkeypatch.setattr(CorpusReader, "manifest", manifest)
    return seen


def _corpus(base: Path) -> Path:
    corpus = base / "c"
    corpus.mkdir(parents=True)
    (corpus / "corpus.json").write_text(json.dumps({"format": "agentprov-corpus/0.1", "sealed": True,
                                                    "partial": False, "release": True, "counts": {}}))
    return corpus


def _page(tmp_path: Path, step: int) -> Any:
    from agentprov_gui.ui.package import PackagePage

    page = PackagePage(lambda spec: None, tmp_path / "checkout")
    page.timer.stop()
    page.show()
    page.corpus.setText(str(_corpus(tmp_path)))
    page.corpus.editingFinished.emit()
    page.steps.setCurrentRow(step)
    return page


def _job(tmp_path: Path, exit_code: int | None) -> Any:
    return SimpleNamespace(job_id="j1", state="running" if exit_code is None else "finished", exit_code=exit_code,
                           outcome=None if exit_code is None else "ok", file=lambda name: tmp_path / "absent" / name)


@pytest.mark.parametrize("step", [0, 4])
def test_ticks_do_not_reread_the_corpus_or_run_git(qapp: Any, tmp_path: Path, calls: Counter[str], step: int) -> None:
    page = _page(tmp_path, step)
    before = Counter(calls)
    assert before["summarise"] >= 1
    for _ in range(5):
        page.timer.timeout.emit()
    assert calls == before
    page.close()


def test_ticks_still_show_the_job_status_on_step_one(qapp: Any, tmp_path: Path, calls: Counter[str]) -> None:
    page = _page(tmp_path, 0)
    assert "checkout commit: " + "0" * 40 in page.texts[0].toPlainText()
    page.jobs["dry-run"] = _job(tmp_path, None)
    page.timer.timeout.emit()
    shown = page.texts[0].toPlainText()
    assert shown.endswith("job j1: running") and "partial: false" in shown
    assert calls["git"] == 1
    page.close()


def test_static_part_is_reread_on_a_change(qapp: Any, tmp_path: Path, calls: Counter[str]) -> None:
    page = _page(tmp_path, 0)
    assert calls["git"] == 1
    page.corpus.editingFinished.emit()  # the corpus field
    assert calls["git"] == 2
    page.checkout = tmp_path / "other"  # Settings saved a new checkout
    page.timer.timeout.emit()
    assert calls["git"] == 3
    page.jobs["dry-run"] = _job(tmp_path, None)  # a running job changes only the job text
    page.timer.timeout.emit()
    assert calls["git"] == 3
    page.jobs["dry-run"] = _job(tmp_path, 0)  # a finished job may have changed corpus.json
    page.timer.timeout.emit()
    page.timer.timeout.emit()
    assert calls["git"] == 4
    page.steps.setCurrentRow(1)
    page.steps.setCurrentRow(0)  # the step
    assert calls["git"] == 5
    page.close()
