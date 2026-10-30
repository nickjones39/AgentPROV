"""GR-22: Show content in the PROV-JSON tab must not freeze the UI on a large JCS document (one line of megabytes).
The pane shows a re-formatted display copy, fenced as data, whose header still names the original file's sha256."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

#: A line longer than this is a layout stall in a NoWrap QPlainTextEdit.
MAX_LINE = 10_000


def _jcs(doc: dict[str, Any]) -> str:
    return json.dumps(doc, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def test_large_jcs_document_shows_quickly_with_original_digest(qapp: Any) -> None:
    from agentprov_gui.ui.detail import ProvJsonTab

    entities = {f"ex:e{i}": {"prov:value": "a" * 80, "prov:type": "apv:Message"} for i in range(8000)}
    entities["ex:big"] = {"prov:value": "b" * 50_000}  # one huge string value stays one JSON line
    doc = {"prefix": {"apv": "urn:apv#"}, "bundle": {"urn:b.core.1": {"entity": entities}}}
    raw = _jcs(doc)
    assert "\n" not in raw and len(raw) > 1_000_000
    digest = hashlib.sha256(raw.encode()).hexdigest()

    tab = ProvJsonTab()
    tab.resize(1200, 700)
    tab.show()
    tab.set_documents({"agentprov-prov/0.1": (doc, raw, "prov/x.prov.json", len(raw))}, 500)
    qapp.processEvents()
    t0 = time.perf_counter()
    tab.show_cb.setChecked(True)
    qapp.processEvents()
    tab.text.repaint()
    qapp.processEvents()
    elapsed = time.perf_counter() - t0

    shown = tab.text.toPlainText()
    lines = shown.split("\n")
    assert lines[0].startswith("<<UNTRUSTED ")
    assert "re-formatted for display" in lines[0] and f"sha256={digest}" in lines[0], lines[0][:400]
    assert lines[-1].startswith("<<END UNTRUSTED ")
    assert max(len(x) for x in lines) <= MAX_LINE, max(len(x) for x in lines)
    assert elapsed < 2.0, elapsed
    tab.close()


def test_non_dict_document_falls_back_to_the_raw_text(qapp: Any) -> None:
    from agentprov_gui import text as T

    raw = "[" + ",".join(["1"] * 5000) + "]"
    out = T.fenced_display(raw, json.loads(raw), "prov/x.prov.json")
    assert out.startswith("<<UNTRUSTED ") and "re-formatted" not in out.split("\n")[0]
    assert f"sha256={hashlib.sha256(raw.encode()).hexdigest()}" in out.split("\n")[0]
    assert max(len(x) for x in out.split("\n")) <= MAX_LINE


def test_display_header_states_every_transformation(qapp: Any) -> None:
    """GR-58: the display copy sorts keys and normalises number lexemes, so the header must not claim it is only
    re-indented (a reader comparing it with the file would otherwise trust a key order and numbers the file lacks)."""
    from agentprov_gui import text as T

    raw = '{"z":1,"entity":{"ex:a":{"apv:m":1' + "E2" + ',"apv:k":1.10}}}'
    out = T.fenced_display(raw, json.loads(raw), "prov/x.prov.json")
    header = out.split("\n")[0]
    assert "re-indented for display;" not in header, header
    assert "keys sorted" in header and "numbers normalised" in header, header
    assert f"sha256={hashlib.sha256(raw.encode()).hexdigest()} chars={len(raw)}" in header, header
    assert out.index('"entity"') < out.index('"z"') and '"apv:m": 100.0' in out
