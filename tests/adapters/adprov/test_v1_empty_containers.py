"""Regen item 75 (CA-17): a present-but-empty optional container survives the v1 round trip (C.15.3, J.3.2).

Before the fix an assistant turn's ``"tool_calls": []`` and a top-level ``"discarded_attempts": []`` were lost in
``serialise(render(map(file)))`` with no seal issue: the view emits ``tool_calls`` only for a message with tool-call parts
and ``discarded_attempts`` only for non-scored attempt scopes. Now the importer records the observed turn key order when
``tool_calls`` is an empty array (``ext.adprov.keys``) and the header flag ``exec.ext.adprov.v1.discarded_attempts_empty``,
which the view honours. Each shape round-trips byte-identically (gate A2) and validates. Documents are built in code.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest


def _empty_tool_calls(doc: dict[str, Any]) -> None:
    turn = next(t for t in doc["turns"] if t.get("role") == "assistant" and "tool_calls" not in t)
    turn["tool_calls"] = []


def _empty_tool_calls_with_refusal(doc: dict[str, Any]) -> None:
    turn = next(t for t in doc["turns"] if t.get("role") == "assistant" and "tool_calls" not in t)
    turn["tool_calls"] = []
    turn["refusal"] = "no (synthetic)"


def _empty_discarded(doc: dict[str, Any]) -> None:
    doc["discarded_attempts"] = []


CASES: dict[str, Callable[[dict[str, Any]], None]] = {
    "tool_calls_empty": _empty_tool_calls,
    "tool_calls_empty_with_refusal": _empty_tool_calls_with_refusal,
    "discarded_attempts_empty": _empty_discarded,
}


@pytest.mark.parametrize("variant", ["released", "converted"])
@pytest.mark.parametrize("name", sorted(CASES))
def test_present_empty_container_round_trips(v1, name: str, variant: str) -> None:
    doc = v1.released() if variant == "released" else v1.converted()
    CASES[name](doc)
    raw = v1.dump(doc)
    m = v1.map(raw)
    assert not m.outcome.degenerate, m.outcome.error_code
    assert m.view_bytes() == raw, "A2: an empty container was dropped in the round trip"
    report = m.validate()
    assert report.ok, sorted({f.code + " " + f.pointer for f in report.errors})


def test_absent_containers_stay_absent(v1) -> None:
    raw = v1.dump(v1.released())
    m = v1.map(raw)
    assert m.view_bytes() == raw
    assert "discarded_attempts_empty" not in m.header["ext"]["adprov"]["v1"]
    assert not any("keys" in (r.get("ext") or {}).get("adprov", {}) for r in m.of_kind("message"))
