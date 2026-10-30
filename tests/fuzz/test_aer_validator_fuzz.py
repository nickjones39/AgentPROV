"""K.11.1 over the AER validator and reader, on mutations of the sealed C.16 vectors (an AER from a deposit is untrusted).

``tests/property/test_validator_props.py`` mutates single records (schema agreement) and feeds arbitrary lines; this
suite mutates whole sealed files: bytes, lines (drop, duplicate, swap, splice from another vector) and JSON values at
any pointer. The streaming validator never raises and is deterministic; the reader either loads or raises a typed
format or integrity error.
"""

from __future__ import annotations

import json
from typing import Any

from aer_support import VECTOR_NAMES, make_registry, vector_bytes
from fuzz_support import budget, byte_mutations, outcome
from hypothesis import given
from hypothesis import strategies as st

from agentprov.aer.reader import AerFormatError, AerIntegrityError, load_aer_bytes
from agentprov.aer.validate import AerValidator

VECTORS = [vector_bytes(name) for name in VECTOR_NAMES]
REGISTRY = make_registry()


def validate(data: bytes) -> tuple[tuple[str, ...], int]:
    v = AerValidator(store=None, catalogues=REGISTRY, mode="release")
    for line in data.split(b"\n"):
        v.feed(line + b"\n")
    report = v.finish()
    return tuple(sorted(f"{f.code}@{f.line}:{f.pointer}" for f in report.findings)), report.n_records


def check(data: bytes) -> None:
    first = validate(data)  # never raises
    assert first == validate(data)
    result = outcome(lambda: len(load_aer_bytes(data).records), AerFormatError, AerIntegrityError)
    assert result[0] in ("ok", "ingest", "AerFormatError", "AerIntegrityError"), result


@budget(120)
@given(st.sampled_from(range(len(VECTORS))).flatmap(lambda i: byte_mutations(VECTORS[i], max_ops=4)))
def test_byte_mutations_of_sealed_vectors(data: bytes) -> None:
    check(data)


@budget(120)
@given(st.data())
def test_line_level_mutations_of_sealed_vectors(data: st.DataObject) -> None:
    lines = VECTORS[data.draw(st.integers(0, len(VECTORS) - 1))].split(b"\n")[:-1]
    for _ in range(data.draw(st.integers(1, 4))):
        op = data.draw(st.sampled_from(["drop", "dup", "swap", "splice"]))
        i = data.draw(st.integers(0, len(lines) - 1)) if lines else 0
        if op == "drop" and lines:
            del lines[i]
        elif op == "dup" and lines:
            lines.insert(i, lines[i])
        elif op == "swap" and len(lines) > 1:
            j = data.draw(st.integers(0, len(lines) - 1))
            lines[i], lines[j] = lines[j], lines[i]
        elif op == "splice":
            other = VECTORS[data.draw(st.integers(0, len(VECTORS) - 1))].split(b"\n")[:-1]
            lines.insert(i, other[data.draw(st.integers(0, len(other) - 1))])
    check(b"\n".join(lines) + b"\n")


hostile = st.one_of(st.none(), st.booleans(), st.integers(-(2**80), 2**80), st.floats(allow_nan=False),
                    st.text(max_size=20), st.sampled_from(["/rule/" + "9" * 5000, "../x", "sha256:" + "0" * 64,
                                                           {"$blob": "x"}, {"$int": "1" * 5000}, [], {}]))


def _set(doc: Any, path: list[Any], value: Any) -> None:
    for step in path[:-1]:
        doc = doc[step]
    doc[path[-1]] = value


def _paths(doc: Any, prefix: tuple[Any, ...] = ()) -> list[list[Any]]:
    out: list[list[Any]] = []
    if isinstance(doc, dict):
        for k, v in doc.items():
            out.append([*prefix, k])
            out += _paths(v, (*prefix, k))
    elif isinstance(doc, list):
        for i, v in enumerate(doc):
            out.append([*prefix, i])
            out += _paths(v, (*prefix, i))
    return out


@budget(150)
@given(st.data())
def test_value_mutations_at_any_pointer(data: st.DataObject) -> None:
    lines = VECTORS[data.draw(st.integers(0, len(VECTORS) - 1))].split(b"\n")[:-1]
    i = data.draw(st.integers(0, len(lines) - 1))
    record = json.loads(lines[i])
    paths = _paths(record)
    if paths:
        _set(record, data.draw(st.sampled_from(paths)), data.draw(hostile))
    if data.draw(st.booleans()):
        unk = record.get("unk") if isinstance(record.get("unk"), dict) else {}
        unk[data.draw(st.sampled_from(["/rule/" + "9" * 5000, "/x/~2", "/", "", "a"]))] = "lost"
        record["unk"] = unk
    lines[i] = json.dumps(record, separators=(",", ":"), ensure_ascii=False).encode()
    check(b"\n".join(lines) + b"\n")
