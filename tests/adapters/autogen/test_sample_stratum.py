"""D-529 ``--sample-mode spread`` for ``autogen.runs``: the stratum is the phase and arm of the label grammar
(``results/phase<N>[/<arm>]/runs.jsonl``)."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import autogen_support as support

from agentprov.adapters.autogen.dialect import AutoGenRunsReader
from agentprov.adapters.runner.importer import ArchiveTree, ImportSample, import_source
from agentprov.corpus.writer import CorpusWriter


def test_the_stratum_is_the_phase_and_arm():
    assert AutoGenRunsReader.sample_stratum("d/results/phase6/tool/runs.jsonl") == "phase6/tool"
    assert AutoGenRunsReader.sample_stratum("d/results/phase7/runs.jsonl") == "phase7"
    assert AutoGenRunsReader.sample_stratum("d/elsewhere/runs.jsonl") is None


def _deposit(base: Path) -> tuple[Path, dict[str, Any]]:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for label, (data, _method) in sorted(support.fixture_members().items()):
            info = zipfile.ZipInfo(label, (2026, 9, 29, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, data)
    path = base / "deposit.zip"
    path.write_bytes(buf.getvalue())
    data = path.read_bytes()
    pin = {"role": "deposit", "kind": "zenodo", "doi": "10.5281/zenodo.1", "record": 1, "version": "v1",
           "file": path.name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    return path, pin


def test_spread_samples_a_multi_execution_import(tmp_path):
    path, pin = _deposit(tmp_path)
    tree = ArchiveTree(path, pin=pin, sha256=pin["sha256"], size=pin["bytes"])
    with CorpusWriter(tmp_path / "c") as writer:
        report = import_source(support.PROFILE, tree, corpus=writer, profile_id=support.PROFILE, part="v1.0", pin=pin,
                               snapshot_id="v1.0", workers=1, until="aer", sample=ImportSample(2, "spread"))
    assert report.counters["mapped"] == 2
    assert json.loads((tmp_path / "c.partial" / "corpus.json").read_text())["selection"]["sample"]["stratum"] == "reader"
