"""D-529 ``--sample-mode spread`` for ``credleak.cell``: the stratum is the section and channel of the path grammar
(D.19.1)."""

from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path
from typing import Any

import credleak_support as support

from agentprov.adapters.credleak.dialect import CredleakCellReader
from agentprov.adapters.runner.importer import ArchiveTree, ImportSample, import_source
from agentprov.corpus.writer import CorpusWriter

CELLS = {
    "p15b-run-data/01-injection-map/chan-a/model-x/run-1.json": support.synthetic_cell(runs=3, scenario="T1.1", technique="T1"),
    "p15b-run-data/03-egress-axis/chan-b/model-y/run-2.json": support.synthetic_cell(runs=3, scenario="T1.2", technique="T1"),
}


def test_the_stratum_is_the_section_and_channel():
    assert CredleakCellReader.sample_stratum("p15b-run-data/01-injection-map/chan-a/model-x/run-1.json") == \
        "01-injection-map/chan-a"
    assert CredleakCellReader.sample_stratum("elsewhere/file.json") is None


def _deposit(base: Path) -> tuple[Path, dict[str, Any]]:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for label, data in CELLS.items():
            zf.writestr(label, data)
    path = base / "deposit.zip"
    path.write_bytes(buf.getvalue())
    data = path.read_bytes()
    pin = {"role": "head", "kind": "zenodo", "doi": "10.5281/zenodo.1", "record": 1, "version": "v1",
           "file": path.name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    return path, pin


def test_spread_takes_one_run_from_each_section(tmp_path):
    import json

    path, pin = _deposit(tmp_path)
    tree = ArchiveTree(path, pin=pin, sha256=pin["sha256"], size=pin["bytes"])
    with CorpusWriter(tmp_path / "c") as writer:
        report = import_source("credleak-p15b", tree, corpus=writer, profile_id="credleak-p15b", part="head", pin=pin,
                               workers=1, snapshot_id="head", until="aer", sample=ImportSample(2, "spread"))
    rows = [json.loads(line) for line in (tmp_path / "c.partial" / "executions.jsonl").read_text().splitlines()]
    assert report.counters["mapped"] == 2 and len({r["source_key"].split("#")[0] for r in rows}) == 2
