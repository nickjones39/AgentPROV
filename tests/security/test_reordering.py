"""SEC-16 (K.12.5; T-16): reordered, inserted, duplicated or removed records are detected, or the limit is stated.

AER: the seal binds the line sequence, so any swap is ``aer.seal.digest`` (``aer.order.noncanonical``, the corpus-tier
re-map check of C.17 V28, is not implemented yet; docs/reports/hardening/sec-coverage.md). Capture: the hash chain plus
``session.end``'s ``n_events``. A forger who rebuilds the whole chain *and* the event count produces a self-consistent
log: a hash chain shows internal consistency, not truth (G.5.4); only an external anchor detects that.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
import rfc8785
from aer_support import make_registry, vector_bytes

from agentprov.aer.reader import AerIntegrityError, load_aer_bytes
from agentprov.aer.validate import AerValidator
from agentprov_capture.verify import line_hash, split_lines, strict_loads, verify_chain

ROOT = Path(__file__).resolve().parents[2]
CAPTURE_VECTOR = ROOT / "docs" / "architecture" / "examples" / "C" / "synthetic.capture.jsonl"
AER_VECTOR = "agentdojo_2024_pi_detector"  # C.16.1, a sealed AER


def _validate_codes(data: bytes) -> set[str]:
    v = AerValidator(store=None, catalogues=make_registry(), mode="dev")
    for line in data.splitlines(keepends=True):
        v.feed(line)
    return {f.code for f in v.finish().findings}


def _lines() -> list[bytes]:
    return vector_bytes(AER_VECTOR).splitlines(keepends=True)


def test_sec16_the_vector_reads_clean() -> None:
    load_aer_bytes(b"".join(_lines()))


@pytest.mark.parametrize("swap", [(1, 2), (2, 5), (3, -2)])
def test_sec16_any_swap_of_two_aer_lines_is_a_seal_digest_failure(swap: tuple[int, int]) -> None:
    lines = _lines()
    i, j = swap
    lines[i], lines[j] = lines[j], lines[i]
    with pytest.raises(AerIntegrityError) as exc:
        load_aer_bytes(b"".join(lines))
    assert exc.value.code in ("aer.seal.digest", "aer.seal.position")
    assert "aer.seal.digest" in _validate_codes(b"".join(lines)) or "aer.ref.forward" in _validate_codes(b"".join(lines))


@pytest.mark.parametrize("edit", ["duplicate", "remove", "insert"])
def test_sec16_a_duplicated_removed_or_inserted_aer_line_fails_the_seal(edit: str) -> None:
    lines = _lines()
    if edit == "duplicate":
        lines.insert(3, lines[3])
    elif edit == "remove":
        del lines[3]
    else:
        record = json.loads(lines[1])
        record["id"] = record["id"] + "x"
        lines.insert(2, rfc8785.dumps(record) + b"\n")
    with pytest.raises(AerIntegrityError) as exc:
        load_aer_bytes(b"".join(lines))
    assert exc.value.code in ("aer.seal.digest", "aer.seal.count")


# ------------------------------------------------------------------------------------------------ capture
def _events() -> list[dict[str, Any]]:
    return [json.loads(line) for line in CAPTURE_VECTOR.read_bytes().splitlines()]


def _rebuild(events: list[dict[str, Any]]) -> bytes:
    out, prev = [], None
    for index, event in enumerate(events):
        event = copy.deepcopy(event)
        event["prev"], event["seq"] = prev, index
        line = rfc8785.dumps(event) + b"\n"
        out.append(line)
        prev = line_hash(line)
    return b"".join(out)


def _codes(data: bytes) -> list[str]:
    lines = split_lines(data)
    events = [strict_loads(line[:-1]) for line in lines if line.endswith(b"\n")]
    return [i.code for i in verify_chain(lines, events).issues]


def test_sec16_the_capture_vector_verifies() -> None:
    assert _codes(CAPTURE_VECTOR.read_bytes()) == []


def test_sec16_a_forged_event_with_a_rebuilt_chain_is_caught_by_the_event_count() -> None:
    events = _events()
    forged = copy.deepcopy(events[-2])
    events.insert(len(events) - 1, forged)
    assert "cap.chain.n_events_mismatch" in _codes(_rebuild(events))


def test_sec16_a_fully_rebuilt_forgery_is_self_consistent_which_is_the_stated_limit() -> None:
    events = _events()
    events.insert(len(events) - 1, copy.deepcopy(events[-2]))
    end = events[-1]
    counted = [k for k in ("n_events",) if k in json.dumps(end)]
    assert counted, "session.end carries the event count"

    def bump(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: (v + 1 if k == "n_events" and isinstance(v, int) else bump(v)) for k, v in value.items()}
        return value

    events[-1] = bump(end)
    assert _codes(_rebuild(events)) == []  # undetectable without an external anchor (G.5.4, G.5.7)


def test_sec16_reordered_capture_lines_without_a_rebuilt_chain_are_caught() -> None:
    lines = CAPTURE_VECTOR.read_bytes().splitlines(keepends=True)
    lines[2], lines[3] = lines[3], lines[2]
    assert set(_codes(b"".join(lines))) & {"cap.chain.seq_gap", "cap.chain.prev_mismatch"}

