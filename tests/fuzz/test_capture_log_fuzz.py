"""K.11.1 over the capture-log verifier (C.13.2) and the core capture reader: mutations of the C.13.8 synthetic session
give only the closed ``cap.chain.*`` codes, never an exception, deterministically; the reader raises only typed errors.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from fuzz_support import budget, byte_mutations, outcome
from hypothesis import given
from hypothesis import strategies as st

from agentprov.adapters.agentdojo.capture_reader import CaptureLogReader
from agentprov.adapters.types import ArtefactRef, Origin
from agentprov.errors import MalformedArtefact
from agentprov.ingest.limits import IngestLimits
from agentprov_capture.verify import ISSUE_CODES, split_lines, strict_loads, verify_chain

VECTOR = (Path(__file__).resolve().parents[2] / "docs" / "architecture" / "examples" / "C" / "synthetic.capture.jsonl"
          ).read_bytes()
LIMITS = IngestLimits()


def chain_codes(data: bytes) -> tuple[str, ...]:
    lines = split_lines(data)
    events = []
    for line in lines:
        if line.endswith(b"\n"):
            try:
                events.append(strict_loads(line[:-1]))
            except Exception:  # noqa: BLE001 - the verifier's contract: None marks an unparsable complete line
                events.append(None)
    return tuple(i.code for i in verify_chain(lines, events).issues)


def test_the_vector_is_clean() -> None:
    assert chain_codes(VECTOR) == ()


@budget(200)
@given(byte_mutations(VECTOR, max_ops=5))
def test_mutated_capture_logs_give_only_closed_chain_codes(data: bytes) -> None:
    first = chain_codes(data)
    assert first == chain_codes(data)
    assert set(first) <= set(ISSUE_CODES)


@budget(100)
@given(st.data())
def test_line_reorders_and_drops_are_always_reported(data: st.DataObject) -> None:
    lines = split_lines(VECTOR)
    i, j = data.draw(st.integers(0, len(lines) - 1)), data.draw(st.integers(0, len(lines) - 1))
    op = data.draw(st.sampled_from(["swap", "drop", "dup"]))
    if op == "swap" and i != j:
        lines[i], lines[j] = lines[j], lines[i]
    elif op == "drop":
        del lines[i]
    elif op == "dup":
        lines.insert(i, lines[i])
    else:
        return
    assert chain_codes(b"".join(lines)) != ()  # a changed sequence never verifies


def _ref(data: bytes) -> ArtefactRef:
    return ArtefactRef("a0", hashlib.sha256(data).hexdigest(), len(data), "application/x-ndjson",
                       Origin.capture("019a0f3c-7b2e-7c41-9a55-3e1f2d0c4b8a"), "primary", "native")  # type: ignore[arg-type]


@budget(150)
@given(byte_mutations(VECTOR, max_ops=5))
def test_the_core_capture_reader_sniffs_totally_and_parses_or_raises_typed(data: bytes) -> None:
    reader = CaptureLogReader()
    reader.sniff(data, label="s.capture.jsonl", limits=LIMITS)  # never raises
    first = outcome(lambda: len(list(reader.parse(data, _ref(data), limits=LIMITS))), MalformedArtefact)
    assert first == outcome(lambda: len(list(reader.parse(data, _ref(data), limits=LIMITS))), MalformedArtefact)
