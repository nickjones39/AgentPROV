"""GR-35: a corpus.json larger than one JSON document is refused by its size before any byte of it is read.

Discovery runs on the UI thread at every refresh; with the default limits the core opens a manifest up to
``max_artefact_bytes`` (2 GiB) and reads it whole before the 64 MiB JSON limit refuses it.
"""

from __future__ import annotations

from pathlib import Path
from typing import IO, Any

import agentprov.corpus.reader as core_reader
import pytest
from agentprov.ingest.limits import IngestLimits

from agentprov_gui.readmodel.corpus import discover, summarise


def test_oversized_manifest_is_refused_before_reading(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    corpus = tmp_path / "roots" / "bloated"
    corpus.mkdir(parents=True)
    with (corpus / "corpus.json").open("wb") as fh:
        fh.write(b'{"sealed": ' + b"true")
        fh.truncate(IngestLimits().max_json_bytes + 16 * 1024 * 1024)  # sparse: nothing is really written
    opened: list[str] = []
    real = core_reader.open_evidence

    def spy(*args: Any, **kwargs: Any) -> IO[bytes]:
        stream = real(*args, **kwargs)
        opened.append(str(args[1]))
        return stream

    monkeypatch.setattr(core_reader, "open_evidence", spy)
    s = summarise(corpus)
    assert s.state == "unreadable" and s.error == "corpus.read.manifest"
    assert opened == []  # refused on its fstat size, never handed out for reading
    assert [c.error for c in discover([corpus.parent])] == ["corpus.read.manifest"]
    assert opened == []
