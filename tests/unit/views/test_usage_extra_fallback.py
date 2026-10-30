"""Regen item 73 (CA-15): a known usage key whose value the mapper did not type renders from ``usage_extra``.

The adprov mapper types a listed usage key (``prompt_tokens`` and the rest of the [[usage]] table) only for a
non-negative int; any other value (a float, a negative number, a string, a bool) is kept verbatim at
``scope:run:/ext/adprov/usage_extra/<key>``. ``_handler_usage`` read only ``/usage/<aer>`` for a listed key, so the
view rendered ``null`` and the round trip lost byte identity (C.15.3). Built from the C.14.5 vector, in memory.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agentprov.adapters.runner import aer_bytes, map_artefact
from agentprov.adapters.types import Origin
from agentprov.views.transcript_v1 import render, serialise

REPO = Path(__file__).resolve().parents[3]
VECTOR = REPO / "docs" / "architecture" / "examples" / "C" / "adprov_v1_llama_injecagent.aer.jsonl"


def _source() -> dict[str, Any]:
    doc: dict[str, Any] = render([json.loads(line) for line in VECTOR.read_bytes().splitlines()])
    return doc


def _roundtrip(src: bytes) -> bytes:
    origin = Origin.corpus("AgentDojo-PROV", "2.3", "x/y.transcript.json",
                           producer_commit="579a908354b93361efe0905ffb7623256aa96a06")
    outcome, _ = map_artefact(src, origin, profile_id="adprov-v1")
    assert not outcome.degenerate, outcome.error_code
    data, _ = aer_bytes(outcome)
    return serialise(render([json.loads(line) for line in data.splitlines()]))


@pytest.mark.parametrize("value", [9278.0, -1, "9278", True, None])
def test_known_usage_key_with_untyped_value_roundtrips(value: Any) -> None:
    doc = _source()
    usage = doc["meta"]["model_config"]["usage"]
    assert "prompt_tokens" in usage
    usage["prompt_tokens"] = value
    src = serialise(doc)
    out = _roundtrip(src)
    got = json.loads(out)["meta"]["model_config"]["usage"]["prompt_tokens"]
    assert got == value and type(got) is type(value), f"prompt_tokens {value!r} rendered as {got!r}"
    assert out == src


def test_typed_usage_key_still_renders_from_usage() -> None:
    src = serialise(_source())
    assert _roundtrip(src) == src
