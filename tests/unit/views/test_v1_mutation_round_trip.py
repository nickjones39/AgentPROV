"""Regen item 79 (CA-20): transcript/v1 import -> view under single-member mutations, and ``render_converted`` hostility.

Property (C.15.3 Import direction): for a single-member mutation ``src`` of the C.16.2 source transcript, either
``serialise(render(map(src))) == src`` (gate A2 bytes), or the mapping is degenerate, or the seal records an issue.
A byte difference with an empty seal-issue list is a silent divergence. The table holds only the shapes that were
silent before items 73-75; ``render_converted`` must raise ``ViewError`` and nothing else on an
``agentdojo.unknown_message`` value (item 71) and join a multi-block tool result's text blocks (item 72).
Built in memory from the C.16.2 vector and the synthetic TraceLogger log; no golden fixture.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from agentprov.adapters.runner import aer_bytes, map_artefact
from agentprov.adapters.types import Origin
from agentprov.views.transcript_v1 import ViewError, render, render_converted, serialise

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "adapters" / "agentdojo"))
from agentdojo_support import map_log, new_log  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
VECTOR = REPO / "docs" / "architecture" / "examples" / "C" / "adprov_v1_llama_injecagent.aer.jsonl"
SOURCE_SHA256 = "a8ef75b854a1bddbb9b3b265fdd48094f5ca689aab762da24a05472e56221335"  # C.16.2 source transcript


def _source() -> bytes:
    src = serialise(render([json.loads(line) for line in VECTOR.read_bytes().splitlines()]))
    assert hashlib.sha256(src).hexdigest() == SOURCE_SHA256
    return src


def _set(member: str, value: Any) -> Callable[[dict[str, Any]], None]:
    return lambda doc: doc["meta"].__setitem__(member, value)


def _set_mc(member: str, value: Any) -> Callable[[dict[str, Any]], None]:
    return lambda doc: doc["meta"]["model_config"].__setitem__(member, value)


def _set_usage(member: str, value: Any) -> Callable[[dict[str, Any]], None]:
    return lambda doc: doc["meta"]["model_config"]["usage"].__setitem__(member, value)


def _empty_tool_calls(doc: dict[str, Any]) -> None:
    next(t for t in doc["turns"] if t.get("role") == "assistant" and "tool_calls" not in t)["tool_calls"] = []


MUTATIONS: dict[str, Callable[[dict[str, Any]], None]] = {
    # item 73 (CA-15): a known usage key whose value the mapper did not type
    "usage_float": _set_usage("prompt_tokens", 9278.0),
    "usage_negative": _set_usage("prompt_tokens", -1),
    "usage_string": _set_usage("prompt_tokens", "9278"),
    "usage_bool": _set_usage("prompt_tokens", True),
    # item 74 (CA-16): released-variant meta members and an explicit-null finish_reasons
    "run_error": _set("run_error", "x"),
    "source": _set("source", "x"),
    "timing_stubbed": _set("timing_stubbed", False),
    "pipeline_name": _set("pipeline_name", "p"),
    "finish_reasons_null": _set_mc("finish_reasons", None),
    # item 75 (CA-17): a present-but-empty optional container
    "tool_calls_empty": _empty_tool_calls,
    "discarded_attempts_empty": lambda doc: doc.__setitem__("discarded_attempts", []),
}


def _exact_or_flagged(src: bytes) -> str | None:
    """None when the round trip is byte-identical, degenerate or flagged; else a description of the divergence."""
    origin = Origin.corpus("AgentDojo-PROV", "2.3", "x/y.transcript.json",
                           producer_commit="579a908354b93361efe0905ffb7623256aa96a06")
    outcome, _ = map_artefact(src, origin, profile_id="adprov-v1")
    if outcome.degenerate:
        return None
    data, _ = aer_bytes(outcome)
    records = [json.loads(line) for line in data.splitlines()]
    if records[-1].get("issues"):
        return None
    return None if serialise(render(records)) == src else "the view differs from the source and the seal has no issue"


def test_the_unmutated_source_round_trips() -> None:
    assert _exact_or_flagged(_source()) is None


@pytest.mark.parametrize("name", list(MUTATIONS))
def test_a_single_member_mutation_round_trips_exactly_or_is_flagged(name: str) -> None:
    doc = json.loads(_source())
    MUTATIONS[name](doc)
    divergence = _exact_or_flagged(json.dumps(doc, indent=2).encode())
    assert divergence is None, f"{name}: {divergence}"


def _content_int(log: dict[str, Any]) -> None:
    log["messages"][4]["content"] = 5


def _args_str(log: dict[str, Any]) -> None:
    log["messages"][3]["tool_call"]["args"] = "xy"


@pytest.mark.parametrize("mutate", [_content_int, _args_str], ids=["content-int", "echo-args-str"])
def test_render_converted_raises_only_view_error_on_an_unknown_message(mutate: Any) -> None:
    log = new_log()
    mutate(log)
    mapped = map_log(log)
    assert "agentdojo.unknown_message_shape" in mapped.codes
    try:
        render_converted(mapped.records)
    except ViewError:
        pass
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"render_converted raised {type(exc).__name__}, not ViewError: {exc}")


def test_render_converted_joins_a_multi_block_tool_result() -> None:
    log = new_log()
    log["messages"][3]["content"] = [{"type": "text", "content": "a"}, {"type": "text", "content": "b"}]
    mapped = map_log(log)
    assert "agentdojo.multi_block_tool_content" in mapped.codes
    turn = render_converted(mapped.records)["turns"][3]
    assert turn["role"] == "tool" and turn["content"] == "ab", turn["content"]
    assert turn["content_sha256"] == "sha256:" + hashlib.sha256(b"ab").hexdigest()
