"""D-394 x NF-36 (regen item 130): a drained import returns normally but stopped early, so it never completes its
snapshot. Before, a drained completion run of a ``--limit`` snapshot recorded it whole and cleared ``partial``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import import_support as support
import pytest

from agentprov import drain
from agentprov.adapters.runner.importer import LocalTree, import_source
from agentprov.corpus.writer import CorpusWriter
from agentprov.progress import ProgressEvent


class _DrainAfterFirst:
    def __init__(self) -> None:
        self.done = 0

    def emit(self, event: ProgressEvent) -> None:
        if event.kind == "unit_done":
            self.done += 1
            if self.done == 1:
                drain.request()


@pytest.fixture(autouse=True)
def _fresh_drain() -> Any:
    drain.reset()
    yield
    drain.reset()


def _run(tmp: Path, **kwargs: Any) -> Any:
    with CorpusWriter(tmp / "c") as corpus:
        return import_source("agentdojo", LocalTree(tmp / "in"), corpus=corpus, part="2024-06", in_process=True,
                             batch_size=1, drain=True, pin_check=support.vouch(tmp / "in"), **kwargs)


def _state(tmp: Path) -> tuple[int, bool, Any]:
    partial = tmp / "c.partial"
    manifest = json.loads((partial / "corpus.json").read_text())
    rows = len((partial / "executions.jsonl").read_text().splitlines())
    return rows, manifest["partial"], manifest["sources"][0]["snapshots"][0].get("selection")


def test_a_drained_completion_run_leaves_the_snapshot_partial(tmp_path):
    support.agentdojo_tree(tmp_path / "in", count=4)
    _run(tmp_path, limit=1)
    report = _run(tmp_path, progress=_DrainAfterFirst())
    assert any("drained" in n for n in report.notices)
    rows, partial, selection = _state(tmp_path)
    assert rows < 4 and partial is True and selection["limit"] == rows  # the cap counts what the snapshot holds
    drain.reset()
    _run(tmp_path)  # the completion run, undrained, makes it whole
    assert _state(tmp_path) == (4, False, None)


def test_a_drained_limit_run_keeps_its_cap(tmp_path):
    support.agentdojo_tree(tmp_path / "in", count=4)
    _run(tmp_path, limit=3, progress=_DrainAfterFirst())
    rows, partial, selection = _state(tmp_path)
    assert rows < 3 and partial is True and selection["limit"] == rows
