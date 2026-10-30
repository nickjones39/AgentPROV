"""GUI review GR-23: the Package page's 1 s timer refreshes only the job-driven steps. The corpus steps are read on a
step or field change, a pane's text is replaced only when it changed (scroll and selection kept), DATASHEET.md is read
under a display budget and an over-limit WITHHELD.json is refused before it is read."""

from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import IO, Any

import pytest

_NL = chr(10)


def _sealed(base: Path, datasheet: str | None = None) -> Path:
    corpus = base / "c"
    corpus.mkdir(parents=True)
    (corpus / "corpus.json").write_text(json.dumps({"format": "agentprov-corpus/0.1", "sealed": True, "counts": {}}))
    if datasheet is not None:
        (corpus / "DATASHEET.md").write_text(datasheet)
    return corpus


def _sparse(path: Path, size: int, head: bytes = b"") -> None:
    with path.open("wb") as f:
        f.write(head)
        f.truncate(size)


class _Counted:
    """A stream wrapper that adds up the bytes read from each label."""

    def __init__(self, stream: IO[bytes], label: str, read: Counter[str]) -> None:
        self._stream, self._label, self._read = stream, label, read

    def read(self, n: int = -1) -> bytes:
        data = self._stream.read(n)
        self._read[self._label] += len(data)
        return data

    def __getattr__(self, name: str) -> Any:
        return getattr(self._stream, name)

    def __enter__(self) -> _Counted:
        return self

    def __exit__(self, *exc: object) -> None:
        self._stream.close()


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> tuple[Counter[str], Counter[str]]:
    from agentprov.corpus.reader import CorpusReader

    opened: Counter[str] = Counter()
    read: Counter[str] = Counter()
    real = CorpusReader.open_file

    def open_file(self: CorpusReader, label: str, **kwargs: Any) -> Any:  # stored=, json_document= (GR-35)
        opened[label] += 1
        return _Counted(real(self, label, **kwargs), label, read)

    monkeypatch.setattr(CorpusReader, "open_file", open_file)
    return opened, read


def _page(corpus: Path, step: int) -> Any:
    from agentprov_gui.ui.package import PackagePage

    page = PackagePage(lambda spec: None, None)
    page.timer.stop()
    page.resize(900, 600)
    page.show()
    page.corpus.setText(str(corpus))
    page.steps.setCurrentRow(step)
    return page


def _select_and_scroll(qapp: Any, page: Any, step: int) -> tuple[int, int]:
    from PySide6.QtGui import QTextCursor

    qapp.processEvents()
    text = page.texts[step]
    cursor = text.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.Down, QTextCursor.MoveMode.KeepAnchor, 5)
    text.setTextCursor(cursor)
    bar = text.verticalScrollBar()
    assert bar.maximum() > 0
    bar.setValue(bar.maximum() // 2)
    return bar.value(), len(text.textCursor().selectedText())


@pytest.mark.parametrize("step", [2, 3])
def test_timer_keeps_scroll_and_selection(qapp: Any, tmp_path: Path, step: int) -> None:
    if step == 2:
        work = tmp_path / "c.partial"
        work.mkdir()
        counts = {f"k{i:04d}": i for i in range(400)}
        (work / "corpus.json").write_text(json.dumps({"format": "agentprov-corpus/0.1", "counts": counts}))
        corpus = tmp_path / "c"
    else:
        corpus = _sealed(tmp_path, _NL.join(f"line {i} of the datasheet" for i in range(800)))
    page = _page(corpus, step)
    before = _select_and_scroll(qapp, page, step)
    assert before[0] > 0 and before[1] > 0
    for _ in range(3):
        page.timer.timeout.emit()
        qapp.processEvents()
    text = page.texts[step]
    assert (text.verticalScrollBar().value(), len(text.textCursor().selectedText())) == before
    page.close()


def test_timer_does_not_reread_corpus_documents(qapp: Any, tmp_path: Path, spy: Any) -> None:
    opened, _ = spy
    corpus = _sealed(tmp_path, "datasheet" + _NL)
    (corpus / "WITHHELD.json").write_text(json.dumps({"entries": [{"reason": "r", "basis": "b"}]}))
    page = _page(corpus, 3)
    page.steps.setCurrentRow(1)
    assert "1 withheld entries" in page.texts[1].toPlainText()
    seen = Counter(opened)
    assert seen["DATASHEET.md"] == 1 and seen["WITHHELD.json"] == 1
    for _ in range(3):
        page.timer.timeout.emit()
    page.steps.setCurrentRow(3)
    for _ in range(3):
        page.timer.timeout.emit()
    assert opened["DATASHEET.md"] == 2 and opened["WITHHELD.json"] == 1  # once more for the step change only
    page.close()


def test_field_change_refreshes_the_corpus_step(qapp: Any, tmp_path: Path) -> None:
    first = _sealed(tmp_path / "a", "first datasheet" + _NL)
    second = _sealed(tmp_path / "b", "second datasheet" + _NL)
    page = _page(first, 3)
    assert page.texts[3].toPlainText().startswith("first datasheet")
    page.corpus.setText(str(second))
    page.corpus.editingFinished.emit()
    assert page.texts[3].toPlainText().startswith("second datasheet")
    page.close()


def test_timer_still_refreshes_job_steps(qapp: Any, tmp_path: Path) -> None:
    page = _page(_sealed(tmp_path), 5)
    assert page.texts[5].toPlainText() == "not started"
    page.jobs["verify"] = SimpleNamespace(job_id="j1", state="running", exit_code=None, outcome=None,
                                          file=lambda name: tmp_path / "absent" / name)
    page.timer.timeout.emit()
    assert page.texts[5].toPlainText() == "job j1: running"
    page.close()


def test_datasheet_is_read_under_a_display_budget(qapp: Any, tmp_path: Path, spy: Any) -> None:
    _, read = spy
    corpus = _sealed(tmp_path)
    _sparse(corpus / "DATASHEET.md", 64 * 1024 * 1024, b"# Datasheet" + _NL.encode())
    page = _page(corpus, 3)
    shown = page.texts[3].toPlainText()
    assert read["DATASHEET.md"] < 1024 * 1024
    assert shown.startswith("# Datasheet") and "not shown" in shown.rsplit(_NL, 1)[-1]
    page.close()


def test_oversized_withheld_is_refused_unread(qapp: Any, tmp_path: Path, spy: Any) -> None:
    from agentprov.ingest.limits import IngestLimits

    _, read = spy
    corpus = _sealed(tmp_path)
    _sparse(corpus / "WITHHELD.json", IngestLimits().max_json_bytes + 1, b"{")
    page = _page(corpus, 1)
    shown = page.texts[1].toPlainText()
    assert read["WITHHELD.json"] == 0
    assert shown.startswith("WITHHELD.json cannot be read") and "JSON limit" in shown
    assert os.path.getsize(corpus / "WITHHELD.json") > IngestLimits().max_json_bytes
    page.close()


def test_withheld_errors_keep_their_code(qapp: Any, tmp_path: Path) -> None:
    corpus = _sealed(tmp_path)
    (corpus / "WITHHELD.json").write_text("[1]")
    page = _page(corpus, 1)
    assert page.texts[1].toPlainText() == "WITHHELD.json cannot be read (corpus.read.json)"
    (corpus / "WITHHELD.json").write_text("{")
    page.steps.setCurrentRow(0)
    page.steps.setCurrentRow(1)
    assert page.texts[1].toPlainText() == "WITHHELD.json cannot be read (corpus.read.json)"
    page.close()
