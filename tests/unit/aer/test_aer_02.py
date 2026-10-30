"""``aer/0.2`` (D-210..D-212): the two relaxations of ``aer/0.1`` limits, and ``aer/0.1`` unchanged beside them.

* D-210: a live header may omit ``instrumentation`` when its ``unk`` declares it ``not_captured`` (a verifiable capture
  prefix cut before the ``instrumentation`` event).
* D-211: a part's ``text`` (text, reasoning, refusal), ``args`` (tool_call) or ``value`` (other) may be absent when the
  record's ``unk`` declares it ``withheld`` or ``not_captured`` (a redacted member).

Neither applies to an ``aer/0.1`` file: the frozen rules are unchanged (D-14), and the writer seals every record as
``aer/0.2``.
"""

from __future__ import annotations

import base64
import copy
import json
from importlib import resources
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from aer_support import codes_of, edit, example_records, make_registry, validate_example
from schema_builder import OUTS, render

from agentprov import aer
from agentprov.aer import _structure
from agentprov.aer.writer import AerWriter


def versioned(records: list[dict[str, Any]], version: str) -> list[dict[str, Any]]:
    out = copy.deepcopy(records)
    out[0]["aer"] = version
    return out


def _withheld_text(version: str, reason: str | None = "withheld") -> list[dict[str, Any]]:
    records = versioned(example_records(), version)
    message = next(r for r in records if r["id"] == "m0")
    del message["parts"][0]["text"]
    if reason is not None:
        message["unk"] = {"/parts/0/text": reason}
    return records


# ------------------------------------------------------------------------------------------------ D-211
@pytest.mark.parametrize("reason", ["withheld", "not_captured"])
def test_aer_02_a_part_text_declared_withheld_or_not_captured_may_be_absent(reason: str) -> None:
    report = validate_example(_withheld_text("0.2", reason))
    assert report.ok, report.findings


def test_aer_01_keeps_the_part_text_required() -> None:
    assert "aer.schema.required" in codes_of(validate_example(_withheld_text("0.1")))


@pytest.mark.parametrize("reason", [None, "not_recorded", "ambiguous"])
def test_aer_02_an_absent_part_text_needs_a_withheld_or_not_captured_declaration(reason: str | None) -> None:
    assert "aer.schema.required" in codes_of(validate_example(_withheld_text("0.2", reason)))


def test_aer_02_tool_call_args_may_be_withheld_but_its_name_may_not() -> None:
    records = versioned(example_records(), "0.2")
    m1 = next(r for r in records if r["id"] == "m1")
    del m1["parts"][1]["args"]
    m1["unk"] = {"/parts/1/args": "withheld"}
    assert validate_example(records).ok
    no_name = edit(records, "m1")
    m1b = next(r for r in no_name if r["id"] == "m1")
    del m1b["parts"][1]["name"]
    m1b["unk"] = {"/parts/1/args": "withheld", "/parts/1/name": "withheld"}
    assert "aer.schema.required" in codes_of(validate_example(no_name))


# ------------------------------------------------------------------------------------------------ D-210
def _live_header(version: str, *, instrumentation: bool, unk: dict[str, str] | None) -> dict[str, Any]:
    header = copy.deepcopy(example_records()[0])
    header.update(aer=version, mode="live", capture={"session": "0" * 8 + "-0000-7000-8000-" + "0" * 12, "log": "a0",
                                                     "attempt": 0})
    header.pop("unk", None)
    if instrumentation:
        header["instrumentation"] = []
    if unk is not None:
        header["unk"] = unk
    return header


def _live_codes(header: dict[str, Any]) -> set[str]:
    return {key for _code, _pointer, key in _structure.check_record(header)}


def test_aer_02_a_live_header_cut_before_instrumentation_declares_it_not_captured() -> None:
    cut = _live_header("0.2", instrumentation=False, unk={"/instrumentation": "not_captured"})
    assert "required_for_live" not in _live_codes(cut)


def test_aer_02_a_live_header_still_needs_instrumentation_otherwise() -> None:
    assert "required_for_live" in _live_codes(_live_header("0.2", instrumentation=False, unk=None))
    assert "required_for_live" in _live_codes(_live_header("0.2", instrumentation=False,
                                                            unk={"/instrumentation": "ambiguous"}))


def test_aer_01_live_headers_keep_instrumentation_required() -> None:
    cut = _live_header("0.1", instrumentation=False, unk={"/instrumentation": "not_captured"})
    assert "required_for_live" in _live_codes(cut)


# ------------------------------------------------------------------------------------------------ versions
def test_the_writer_seals_aer_02_whatever_the_mapper_wrote(tmp_path: Path) -> None:
    records = example_records()
    assert records[0]["aer"] == "0.1"  # an adapter's header may still name 0.1: the format is the core's
    writer = AerWriter(tmp_path / "x.aer.jsonl", records[0], catalogues=make_registry())
    for record in records[1:]:
        writer.add(record)
    writer.seal(issues=[])
    header = json.loads((tmp_path / "x.aer.jsonl").read_bytes().split(b"\n", 1)[0])
    assert header["aer"] == aer.AER_VERSION == "0.2"


def test_an_unknown_version_is_refused() -> None:
    assert "aer.schema.pattern" in codes_of(validate_example(versioned(example_records(), "0.3")))


# ------------------------------------------------------------------------------------------------ the published schema
def test_the_aer_02_schema_file_is_fresh_and_valid() -> None:
    data = resources.files("agentprov").joinpath("schemas", "aer-0.2.schema.json").read_text(encoding="utf-8")
    assert data == render("0.2") and OUTS["0.2"].read_text(encoding="utf-8") == data
    schema = json.loads(data)
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = jsonschema.Draft202012Validator(schema)
    cut = _live_header("0.2", instrumentation=False, unk={"/instrumentation": "not_captured"})
    assert not list(validator.iter_errors(cut))
    assert list(validator.iter_errors(_live_header("0.2", instrumentation=False, unk=None)))
    assert list(validator.iter_errors(versioned([example_records()[0]], "0.1")[0]))  # the 0.2 schema is 0.2's


def test_the_aer_01_schema_file_is_unchanged_by_the_builder() -> None:
    data = resources.files("agentprov").joinpath("schemas", "aer-0.1.schema.json").read_text(encoding="utf-8")
    assert data == render("0.1") == render()


# ------------------------------------------------------------------------------------------------ D-216
MIB = 1024 * 1024


def _long_text(version: str, text: str) -> list[dict[str, Any]]:
    records = versioned(example_records(), version)
    next(r for r in records if r["id"] == "m0")["parts"][0]["text"] = text
    return records


def test_aer_02_refuses_an_inline_string_over_1_mib() -> None:
    report = validate_example(_long_text("0.2", "a" * (MIB + 1)))
    found = [f for f in report.findings if f.code == "aer.string.inline_limit"]
    assert [(f.invariant, f.pointer) for f in found] == [("AER-V01", "/parts/0/text")]


def test_aer_02_counts_utf8_bytes_not_code_points() -> None:
    assert validate_example(_long_text("0.2", "a" * MIB)).ok  # exactly 1 MiB is allowed
    over = chr(0xE9) * (MIB // 2 + 1)  # about half a MiB of code points, 2 UTF-8 bytes each: just over 1 MiB
    assert "aer.string.inline_limit" in codes_of(validate_example(_long_text("0.2", over)))


def test_aer_01_keeps_its_frozen_rules_for_long_strings() -> None:
    assert "aer.string.inline_limit" not in codes_of(validate_example(_long_text("0.1", "a" * (MIB + 1))))


def test_the_writer_refuses_a_record_with_an_inline_string_over_1_mib(tmp_path: Path) -> None:
    from agentprov.aer.writer import AerWriteError

    records = _long_text("0.2", "a" * (MIB + 1))
    writer = AerWriter(tmp_path / "x.aer.jsonl", records[0], catalogues=make_registry())
    with pytest.raises(AerWriteError) as exc:
        for record in records[1:]:
            writer.add(record)
    assert "aer.string.inline_limit" in str(exc.value)


# ------------------------------------------------------------------------------------------------ D-219
def _degenerate(version: str, *, reason: str | None = "not_captured", extra: bool = False) -> list[dict[str, Any]]:
    """A degenerate file (D.2.8 case 3): the header and its run scope; the task id is not named."""
    records = versioned(example_records(), version)
    header = copy.deepcopy(records[0])
    del header["task"]["task_id"]
    if reason is not None:
        header["unk"] = {**header.get("unk", {}), "/task/task_id": reason}
    # the runner's degenerate run scope (``adapters.runner._degenerate``): it cites the artefact and names no actor
    run = {"k": "scope", "id": "run", "kind": "run", "ev": "O", "by": "source", "src": [{"a": "a0", "p": ""}],
           "unk": {"/status": "not_recorded", "/t": "not_recorded"}}
    out = [header, run]
    if extra:
        out.append(copy.deepcopy(next(r for r in records if r.get("k") == "actor")))
    return out


def test_aer_02_a_degenerate_header_may_declare_its_task_id_not_captured() -> None:
    report = validate_example(_degenerate("0.2"))
    assert "aer.schema.required" not in codes_of(report), report.findings


def test_aer_02_only_a_degenerate_file_may_leave_its_task_unnamed() -> None:
    report = validate_example(_degenerate("0.2", extra=True))
    found = [(f.code, f.pointer) for f in report.findings if f.code == "aer.schema.required"]
    assert ("aer.schema.required", "/task/task_id") in found


@pytest.mark.parametrize(("version", "reason"), [("0.1", "not_captured"), ("0.2", "not_recorded"), ("0.2", None)])
def test_the_task_id_stays_required_otherwise(version: str, reason: str | None) -> None:
    assert "aer.schema.required" in codes_of(validate_example(_degenerate(version, reason=reason)))


def test_the_writer_seals_a_degenerate_file_without_a_task_id(tmp_path: Path) -> None:
    header, run = _degenerate("0.2")
    writer = AerWriter(tmp_path / "d.aer.jsonl", header, catalogues=make_registry())
    writer.add(run)
    writer.seal(issues=[])
    sealed = json.loads((tmp_path / "d.aer.jsonl").read_bytes().split(b"\n", 1)[0])
    assert "task_id" not in sealed["task"] and sealed["unk"]["/task/task_id"] == "not_captured"


def test_aer_02_applies_the_inline_limit_to_the_seal_too() -> None:
    """Pre-round review #30: C.2.1(6) holds for every line of an aer/0.2 file, the seal's issue details included."""
    issue = {"code": "test_issue", "ids": ["exec"], "rule": "tst.d@1", "detail": "a" * (MIB + 1)}
    report = validate_example(versioned(example_records(), "0.2"), issues=[issue])
    found = [f for f in report.findings if f.code == "aer.string.inline_limit"]
    assert found and all(f.pointer.startswith("/issues/") for f in found)
    small = {**issue, "detail": "short"}
    assert "aer.string.inline_limit" not in codes_of(validate_example(versioned(example_records(), "0.2"), issues=[small]))


# ------------------------------------------------------------------------------------------------ V-7: the schema holds
def _published_02() -> jsonschema.Draft202012Validator:
    data = resources.files("agentprov").joinpath("schemas", "aer-0.2.schema.json").read_text(encoding="utf-8")
    return jsonschema.Draft202012Validator(json.loads(data))


@pytest.mark.parametrize(("reason", "accepted"), [("not_captured", True), ("not_recorded", False), (None, False)])
def test_the_aer_02_schema_holds_the_header_task_id_condition_v7(reason: str | None, accepted: bool) -> None:
    # pre-round verification V-7 (#31 residual): a task without task_id must declare it not_captured, as the validator has
    header = _degenerate("0.2", reason=reason)[0]
    assert (not list(_published_02().iter_errors(header))) is accepted
    assert ("aer.schema.required" not in codes_of(validate_example(_degenerate("0.2", reason=reason)))) is accepted


def _with_args(args: Any) -> dict[str, Any]:
    message = copy.deepcopy(next(r for r in versioned(example_records(), "0.2") if r["id"] == "m1"))
    message["parts"][1]["args"] = args
    return message


@pytest.mark.parametrize(("args", "accepted"), [
    ({"x": {"$utf16": base64.b64encode(b"\x00a\x00").decode()}}, False),  # an odd byte count
    ({"x": {"$utf16": base64.b64encode("a\ud800".encode("utf-16-be", "surrogatepass")).decode()}}, True),
    ({"$lit": {"a": 1}}, False),  # no member name beginning with $
    ({"$lit": {"$k": 1, "a": 1}}, True),
])
def test_the_aer_02_schema_holds_the_reserved_form_shapes_v7(args: Any, accepted: bool) -> None:
    # pre-round verification V-7 (#28): what JSON Schema can say of the canonical forms; the validator holds the rest
    assert (not list(_published_02().iter_errors(_with_args(args)))) is accepted
