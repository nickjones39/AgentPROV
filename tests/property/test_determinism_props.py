"""C.11.7: the AER file is a pure function of the records; plus reference-order and shuffle properties."""

from __future__ import annotations

import copy
import hashlib
import tempfile
from pathlib import Path
from typing import Any

from aer_support import ARTEFACT_BYTES, ARTEFACT_SHA, MemoryStore, codes_of, example_records, make_registry, seal_record
from hypothesis import given, settings
from hypothesis import strategies as st

from agentprov.aer.canon import dumps_line
from agentprov.aer.validate import validate_records
from agentprov.aer.writer import AerWriter

S = settings(max_examples=60, deadline=None, derandomize=True)


def write_bytes(records: list[dict[str, Any]]) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "x.aer.jsonl"
        writer = AerWriter(path, records[0], catalogues=make_registry())
        for rec in records[1:]:
            writer.add(rec)
        writer.seal(issues=[])
        return path.read_bytes()


def shuffle_members(value: Any, rnd: Any) -> Any:
    if isinstance(value, dict):
        keys = list(value)
        rnd.shuffle(keys)
        return {k: shuffle_members(value[k], rnd) for k in keys}
    if isinstance(value, list):
        return [shuffle_members(v, rnd) for v in value]
    return value


@S
@given(st.randoms(use_true_random=False))
def test_output_bytes_do_not_depend_on_member_insertion_order(rnd: Any) -> None:
    base = example_records()
    shuffled = [shuffle_members(copy.deepcopy(r), rnd) for r in base]
    assert write_bytes(shuffled) == write_bytes(base)


@S
@given(st.integers(1, 6))
def test_a_run_with_n_tool_round_trips_is_valid_and_deterministic(n: int) -> None:
    records = example_records()[:7]  # header .. m0
    previous_inputs = ["m0"]
    for i in range(n):
        mc, call_msg, te, result = f"mc{i}", f"c{i}", f"te{i}", f"r{i}"
        records += [
            {"k": "model_call", "id": mc, "ev": "D", "rule": ["tst.d@1"], "actor": "agent", "role": "agent", "scope": "att0",
             "input": list(previous_inputs), "status": "kept"},
            {"k": "message", "id": call_msg, "ev": "O", "by": "source", "src": [{"a": "a0", "p": f"/messages/{i}"}], "scope": "att0",
             "role": "assistant", "actor": "agent", "generated_by": mc,
             "parts": [{"t": "text", "text": None}, {"t": "tool_call", "name": "f", "args": {"i": i}}]},
            {"k": "tool_execution", "id": te, "ev": "D", "rule": ["tst.d@1"], "actor": "env", "scope": "att0", "call": f"{call_msg}#1",
             "name": "f", "status": "ok"},
            {"k": "message", "id": result, "ev": "O", "by": "source", "src": [{"a": "a0", "p": f"/messages/{i}"}], "scope": "att0",
             "role": "tool", "actor": "env", "generated_by": te,
             "parts": [{"t": "tool_result", "responds_to": f"{call_msg}#1", "text": str(i)}]},
        ]
        previous_inputs = [*previous_inputs, call_msg, result]
    full = [*records, seal_record(records)]
    store = MemoryStore({ARTEFACT_SHA: ARTEFACT_BYTES})
    report = validate_records(full, store=store, catalogues=make_registry())
    assert report.ok, report.findings
    assert write_bytes(records) == write_bytes(copy.deepcopy(records))
    assert report.execution_digest == hashlib.sha256(b"".join(dumps_line(r) for r in records)).hexdigest()


REFERENCE_FIELDS = ("scope", "actor", "generated_by", "on_behalf_of", "parent", "call")


def references(record: dict[str, Any]) -> list[str]:
    """An independent extraction of the references of the example's record kinds (base ids only)."""
    out = [str(record[f]).split("#")[0] for f in REFERENCE_FIELDS if isinstance(record.get(f), str)]
    out += [str(i).split("#")[0] for i in record.get("input", [])]
    for part in record.get("parts", []):
        if part.get("t") == "tool_result":
            out.append(str(part["responds_to"]).split("#")[0])
    return out


@S
@given(st.randoms(use_true_random=False))
def test_forward_reference_findings_match_an_independent_reference_check(rnd: Any) -> None:
    records = example_records()
    body = records[1:]
    rnd.shuffle(body)
    permuted = [records[0], *body]
    seen = {"exec"}
    expect_forward = False
    for rec in permuted:
        if any(ref not in seen for ref in references(rec)):
            expect_forward = True
        seen.add(rec["id"])
    report = validate_records([*permuted, seal_record(permuted)], store=None, catalogues=make_registry())
    assert ("aer.ref.forward" in codes_of(report)) == expect_forward
