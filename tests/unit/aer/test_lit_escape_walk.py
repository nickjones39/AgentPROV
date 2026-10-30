"""Regen item 60 (CA-1, C.11.3): the first-level members of a ``{"$lit": body}`` escape are literal source keys.

The validator's number/blob walk (and so the writer's ``seal.blobs``) and the test helper ``seal_record`` must not
read the body as a ``$blob`` or ``$int`` reserved form; values nested inside the body keep normal ``$``-form semantics.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from aer_support import example_records, example_store, make_registry, seal_record

from agentprov.aer._structure import check_record
from agentprov.aer.canon import LexHints, decode_value, encode_value
from agentprov.aer.validate import validate_records
from agentprov.aer.writer import AerWriter, AerWriteError

FAKE = "sha256:" + "e" * 64
PAYLOAD = b'{"wire":"request"}'
ESCAPED = [{"$blob": FAKE, "bytes": 3}, {"$int": "5"}, {"$k": {"$blob": FAKE, "bytes": 3}}, {"$k": {"$int": "5"}}]
IDS = ["blob", "int", "nested-blob", "nested-int"]


def with_args(args: Any) -> list[dict[str, Any]]:
    recs = example_records()
    next(r for r in recs if r["id"] == "m1")["parts"][1]["args"] = args
    return recs


def escaped(source: dict[str, Any]) -> list[dict[str, Any]]:
    """The records with the tool call's ``args`` set to ``source`` as ``encode_value`` writes it."""
    args = encode_value(source, at="/parts/1/args", lex=LexHints())
    assert args == {"$lit": {k: encode_value(v, at="", lex=LexHints()) for k, v in source.items()}}
    assert decode_value(args, at="/parts/1/args", lex=None) == source
    recs = with_args(args)
    assert check_record(next(r for r in recs if r["id"] == "m1")) == []
    return recs


def errors(recs: list[dict[str, Any]], store: Any = None) -> list[tuple[str, str]]:
    report = validate_records([*recs, seal_record(recs)], store=store, catalogues=make_registry())
    return [(f.code, f.pointer) for f in report.errors]


def write(recs: list[dict[str, Any]], tmp_path: Path) -> dict[str, Any]:
    writer = AerWriter(tmp_path / "x.aer.jsonl", recs[0], catalogues=make_registry())
    for rec in recs[1:]:
        writer.add(rec)
    info = writer.seal(issues=[])
    seal: dict[str, Any] = json.loads(info.path.read_bytes().splitlines()[-1])
    return seal


@pytest.mark.parametrize("source", ESCAPED, ids=IDS)
def test_an_escaped_body_is_not_read_as_reserved_forms(source: dict[str, Any]) -> None:
    recs = escaped(source)
    assert "blobs" not in seal_record(recs)
    assert errors(recs, store=example_store()) == []
    assert errors(recs) == []


@pytest.mark.parametrize("source", ESCAPED, ids=IDS)
def test_the_writer_maps_an_escaped_body_without_inventing_a_blob(source: dict[str, Any], tmp_path: Path) -> None:
    assert FAKE not in write(escaped(source), tmp_path).get("blobs", [])


def test_values_nested_in_an_escaped_body_keep_reserved_semantics(tmp_path: Path) -> None:
    store = example_store()
    digest = "sha256:" + store.put(PAYLOAD)
    blob = {"$blob": digest, "bytes": len(PAYLOAD)}
    recs = with_args({"$lit": {"$k": blob, "n": {"$int": "9007199254740993"}}})
    assert seal_record(recs)["blobs"] == [digest]
    assert errors(recs, store=store) == []
    assert write(recs, tmp_path)["blobs"] == [digest]
    assert ("aer.blob.missing", "/parts/1/args/$lit/$k") in errors(recs, store=example_store())
    in_range = with_args({"$lit": {"$k": {"$int": "5"}}})
    assert ("aer.schema.pattern", "/parts/1/args/$lit/$k") in errors(in_range)
    deep = with_args({"$lit": {"a/b": {"$lit": {"$blob": FAKE, "bytes": 3}}, "c": {"$int": "5"}}})
    assert errors(deep, store=example_store()) == [("aer.schema.pattern", "/parts/1/args/$lit/c")]


def test_genuine_top_level_reserved_forms_behave_as_before(tmp_path: Path) -> None:
    store = example_store()
    digest = "sha256:" + store.put(PAYLOAD)
    recs = with_args({"$blob": digest, "bytes": len(PAYLOAD)})
    assert seal_record(recs)["blobs"] == [digest]
    assert errors(recs, store=store) == []
    assert write(recs, tmp_path)["blobs"] == [digest]
    assert ("aer.blob.missing", "/parts/1/args") in errors(recs, store=example_store())
    assert errors(with_args({"q": {"$int": "9007199254740993"}})) == []
    narrow = with_args({"q": {"$int": "5"}})
    assert ("aer.schema.pattern", "/parts/1/args/q") in errors(narrow)
    with pytest.raises(AerWriteError, match=r"aer\.schema\.pattern"):
        write(narrow, tmp_path)
