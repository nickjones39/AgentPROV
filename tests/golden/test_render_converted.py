"""Gate R on the golden converted pairs: R1 and R2 from the native logs alone (J.4.3; D.7.4; K.7.1; erratum E8).

For every converted pair C01…C09 and its native log N-C01…N-C09 (pinned blobs at ``c274885``)::

    A  = map(native log)                       # adapter agentdojo.tracelogger, profile agentdojo-upstream
    R1: serialise(render_converted(A)) == stored converted transcript bytes
    R2: compat serialise(build_prov(render_converted(A))) == stored converted graph bytes

Both compare byte strings, never decoded values (K.1(9)). The view runs on the AER read back from disk with every
file-opening function patched to raise, so it provably reads nothing from raw (AD-02). Each AER passes the release
validator first. R1/R2 on the golden pairs are release-blocking in CI (J.4.3; AD-07). Failures print ids, pointers and
sha256 values only (R-42).
"""

from __future__ import annotations

import builtins
import io
import os
from pathlib import Path
from typing import Any

import pytest

from agentprov.adapters.runner import aer_bytes, map_artefact
from agentprov.adapters.types import Origin
from agentprov.aer.reader import load_aer
from agentprov.testing import golden
from agentprov.views.transcript_v1 import render_converted, serialise

PAIRS = [e for e in golden.v1_pairs() if e.is_converted] if golden.golden_available() else []


def _require() -> None:
    if not PAIRS:
        reason = golden.golden_skip_reason() or "golden converted pairs not found"
        if os.environ.get("CI"):
            pytest.fail(reason)
        pytest.skip(reason)


def _ids() -> list[Any]:
    return [pytest.param(e, id=e.id) for e in PAIRS] or [pytest.param(None, id="no-golden-fixtures")]


_DOCS: dict[str, bytes] = {}


def _native_aer(entry: golden.GoldenEntry, tmp: Path) -> Any:
    native = golden.native_of(entry)
    assert native is not None and not golden.verify_entry_files(native), entry.id
    if entry.id not in _DOCS:
        o = native.origin
        outcome, _unit = map_artefact(native.native_bytes(), Origin.git(o["repo"], o["commit"], o["path"], o["git_blob_sha1"]),
                                      profile_id="agentdojo-upstream")
        assert not outcome.degenerate, f"{entry.id}: degenerate AER ({outcome.error_code})"
        _DOCS[entry.id], _info = aer_bytes(outcome)
    path = tmp / f"{entry.id}.aer.jsonl"
    path.write_bytes(_DOCS[entry.id])
    return load_aer(path)


def _view_without_raw(document: Any, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    def refuse(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("render_converted tried to open a file: it must read nothing from raw (AD-02)")

    with monkeypatch.context() as patch:
        for target, name in ((builtins, "open"), (io, "open"), (Path, "read_bytes"), (Path, "read_text"), (Path, "open")):
            patch.setattr(target, name, refuse)
        return render_converted(document)


def test_the_golden_set_has_nine_converted_pairs_with_native_logs():
    _require()
    assert [e.id for e in PAIRS] == [f"C{n:02d}" for n in range(1, 10)]
    assert all(e.native == f"N-{e.id}" for e in PAIRS)


@pytest.mark.parametrize("entry", _ids())
def test_gate_r1_converted_transcript_bytes(entry, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _require()
    document = _native_aer(entry, tmp_path)
    produced = serialise(_view_without_raw(document, monkeypatch))
    golden.assert_bytes_equal(entry.transcript_bytes(), produced, what=f"{entry.id} R1 (serialise(render_converted(AER_native)))")


@pytest.mark.parametrize("entry", _ids())
def test_gate_r2_converted_graph_bytes(entry, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _require()
    compat = pytest.importorskip("agentprov.prov.compat.adprov_v2_3")
    document = _native_aer(entry, tmp_path)
    produced = compat.SPEC.serialise(compat.SPEC.build(_view_without_raw(document, monkeypatch)))
    golden.assert_bytes_equal(entry.graph_bytes(), produced, what=f"{entry.id} R2 (compat graph from render_converted)")


def test_the_native_aer_holds_no_converter_stub(tmp_path: Path):
    """The "0" timing stub and the "benign" label are view rules (E8; adprov.v1_benign_label@1), never AER data."""
    _require()
    for entry in PAIRS:
        document = _native_aer(entry, tmp_path)
        for record in document.records:
            if record.get("k") == "tool_execution":
                assert "t" not in record and record["unk"]["/t"] == "not_recorded", entry.id
        assert document.header["task"].get("attack_id") != "benign", entry.id
