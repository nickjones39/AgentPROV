"""The committed MCPHunt fixtures (docs/architecture D.21.12; D-289): every trace is its source element byte for byte,
and none carries a canary flag, a taint read or a credential or password shape. Prints nothing of their content."""

from __future__ import annotations

import hashlib
import re

import mcphunt_support as support

SHAPES = re.compile(rb"\b[rs]k_(?:live|test)_[A-Za-z0-9]{16,}|\b(?:AKIA|ASIA)[0-9A-Z]{16}\b|\bxox[abpors]-[A-Za-z0-9-]{10,}"
                    rb"|\bgh[pousr]_[A-Za-z0-9]{30,}|PRIVATE KEY-----|\beyJ[A-Za-z0-9_-]{10,}\."
                    rb"|(?i:\b(?:password|passwd|secret|api[_-]?key|token|ssn)\s*[=:]\s*\S{4,})|\b\d{3}-\d{2}-\d{4}\b")


def test_every_fixture_trace_is_its_source_element():
    src = support.source()
    assert src["revision"] == support.REVISION
    # byte identity: each element's recorded digest is the digest of its slice of the fixture document
    for e in src["elements"]:
        doc = (support.FIXTURES / e["fixture_file"]).read_bytes()
        assert hashlib.sha256(doc[e["fixture_offset"]:e["fixture_offset"] + e["bytes"]]).hexdigest() == e["sha256"]
        assert len(e["source_sha256"]) == 64 and e["source_offset"] >= 0


def test_no_fixture_trace_carries_a_canary():
    for e in support.source()["elements"]:
        t = support.items(e["fixture_file"])[e["fixture_index"]].value["trace"]
        assert not any(ev["canary_in_args"] or ev["canary_in_result"] for ev in t["events"])
        assert t["labeling"]["taint_summary"]["taints_read"] == 0 and not t["labeling"]["taint_flows"]
    for path in (support.FIXTURES / "docs").rglob("*.json"):
        assert not SHAPES.search(path.read_bytes()), path.name
    licence = (support.REPO / "tests" / "fixtures" / "LICENSES" / "CC-BY-4.0.txt").read_text(encoding="utf-8")
    assert "Attribution 4.0" in licence
    notice = (support.REPO / "tests" / "fixtures" / "LICENSES" / "MCPHunt-ATTRIBUTION.txt").read_text(encoding="utf-8")
    assert support.REVISION in notice and "CC-BY-4.0" in notice and "arXiv:2604.27819" in notice
