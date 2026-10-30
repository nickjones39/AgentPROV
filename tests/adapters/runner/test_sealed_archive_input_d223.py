"""D-223: the sealed ``agentprov-corpus/0.2`` snapshot keeps its stored archive input, so a re-map re-expands it.

A sealed manifest records no pin, and before D-223 it dropped the snapshot's ``input`` too: a re-map of a sealed corpus
imported from a downloaded archive (D-200) then walked the stored zip as an ordinary file and reproduced none of its
executions (0 identical, 1 failed, 3 corpus files unexplained on this fixture). Here a working archive-input corpus is
put in the sealed form the way ``package`` builds it (:func:`agentprov.corpus.package._sealed_per_unit`, which carries
``input``), and ``recompute --dry-run`` must report every execution identical.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from test_deferrals_part_a import _import_archive, _recompute  # noqa: E402

from agentprov.corpus.package import _sealed_per_unit  # noqa: E402


def _sealed_copy(partial: Path, dest: Path, *, keep_input: bool = True) -> dict[str, Any]:
    shutil.copytree(partial, dest)
    path = dest / "corpus.json"
    manifest = json.loads(path.read_text("utf-8"))
    working = manifest["sources"][0]["snapshots"][0]
    sealed = {k: v for k, v in working.items() if k not in ("pin", "verification", "input")}
    if keep_input:
        sealed.update(_sealed_per_unit(working, {}, "agentprov-corpus/0.2"))
    manifest["sources"][0]["snapshots"][0] = sealed
    manifest["sealed"] = True
    path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", "utf-8")
    return sealed


def test_the_sealed_snapshot_keeps_the_archive_input_and_re_maps_identically(tmp_path, monkeypatch, capsys):
    _report, partial, pin = _import_archive(tmp_path, "a")
    sealed = _sealed_copy(partial, tmp_path / "sealed.partial")
    assert sealed["input"] == {"kind": "archive", "label": pin["file"], "sha256": "sha256:" + pin["sha256"],
                               "bytes": pin["bytes"]}
    code, summary = _recompute(tmp_path / "sealed.partial", tmp_path, monkeypatch, capsys)
    assert code == 0, summary
    assert summary["counters"]["identical"] == summary["counters"]["selected"] == 1
    assert summary["counters"]["corpus_unexplained"] == 0


def test_without_the_archive_input_the_re_map_does_not_reproduce_the_corpus(tmp_path, monkeypatch, capsys):
    """The gap D-223 closes, kept as a check that the test above depends on ``input``."""
    _report, partial, _pin = _import_archive(tmp_path, "a")
    _sealed_copy(partial, tmp_path / "sealed.partial", keep_input=False)
    code, summary = _recompute(tmp_path / "sealed.partial", tmp_path, monkeypatch, capsys)
    assert code != 0 and summary["counters"]["identical"] == 0
