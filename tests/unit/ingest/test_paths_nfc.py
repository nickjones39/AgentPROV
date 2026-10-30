"""D-622 (pre-round local review D-1): ``discover`` records each entry under its NFC name, the label ``open_evidence``
opens; a non-NFC name only when its NFC spelling is the same file; sibling collisions are all rejected."""

from __future__ import annotations

import os
import unicodedata

import pytest

from agentprov.ingest import paths
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.paths import discover, open_evidence

NFD = "café.json"
NFC = unicodedata.normalize("NFC", NFD)


def _write(root, name: str, data: bytes) -> None:
    root.mkdir(parents=True, exist_ok=True)
    with open(os.path.join(str(root), name), "wb") as handle:
        handle.write(data)


def test_an_nfd_name_is_recorded_under_its_nfc_label_or_rejected(tmp_path):
    """APFS: the NFC label opens the NFD file, so it is kept as NFC (before: the NFD label). A normalisation-sensitive
    file system (Linux): the NFC label would open nothing, so the entry is rejected (before: the import crashed)."""
    _write(tmp_path / "in", NFD, b"{}")
    found = discover(tmp_path / "in", IngestLimits())
    labels = [f.label for f in found.files]
    assert NFD not in labels or NFD == NFC
    if labels:
        assert labels == [NFC]
        with open_evidence(tmp_path / "in", NFC, IngestLimits()) as stream:
            assert stream.read() == b"{}"
    else:
        assert [(r.label, r.code) for r in found.rejected] == [(NFC, "ingest.name.invalid")]


def test_an_nfd_name_whose_nfc_form_is_another_file_is_rejected(tmp_path, monkeypatch):
    """The Linux case, simulated: the NFC spelling does not name the same file."""
    _write(tmp_path / "in", NFD, b"{}")
    monkeypatch.setattr(paths, "_same_entry", lambda ref, raw, nfc: False)
    found = discover(tmp_path / "in", IngestLimits())
    on_disk = os.listdir(tmp_path / "in")
    if on_disk == [NFD]:  # the file system kept the NFD spelling (APFS, ext4)
        assert not found.files and [(r.label, r.code) for r in found.rejected] == [(NFC, "ingest.name.invalid")]
    else:  # a file system that normalises names on write: nothing to reject
        assert [f.label for f in found.files] == [NFC]


class _Alias:
    """A directory entry seen under another name (a sibling that collides with ``entry`` on another file system)."""

    def __init__(self, entry: os.DirEntry, name: str) -> None:
        self._entry, self.name = entry, name

    def __getattr__(self, item: str):
        return getattr(self._entry, item)


@pytest.mark.parametrize("other", ["A.json", NFD], ids=["case", "normalisation"])
def test_siblings_that_collide_are_all_rejected(tmp_path, monkeypatch, other):
    """``A.json`` next to ``a.json`` (or an NFD/NFC pair) is one file on a case- or normalisation-insensitive volume.
    Both are rejected, as archive members sharing a collision key are (G.3.5); before, both were recorded."""
    base = "a.json" if other == "A.json" else NFC
    _write(tmp_path / "in", base, b"{}")
    _write(tmp_path / "in", "b.json", b"[]")
    real = os.scandir

    class _Scan:
        def __init__(self, ref):
            self._it = real(ref)

        def __enter__(self):
            entries = list(self._it.__enter__())
            first = next(e for e in entries if e.name == base)
            return iter([*entries, _Alias(first, other)])

        def __exit__(self, *exc):
            return self._it.__exit__(*exc)

    monkeypatch.setattr(paths.os, "scandir", _Scan)
    found = discover(tmp_path / "in", IngestLimits())
    assert [f.label for f in found.files] == ["b.json"]
    assert sorted(r.code for r in found.rejected) == ["ingest.path.duplicate", "ingest.path.duplicate"]
