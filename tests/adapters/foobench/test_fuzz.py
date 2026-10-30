"""Hypothesis fuzz of the FooBench reader and mapper (docs/architecture D.12.1 row 9; K.11.1 F-1, F-5).

Reader: any bytes either parse or raise ``MalformedArtefact`` or ``IngestError`` (with a G.3.9 code) and nothing else;
``sniff`` never raises. Mapper: any selection and order of the fixture's events still ends in a sealed AER that
validates, a degenerate one (D.2.8 case 3) at worst, never an exception.
"""

from __future__ import annotations

import hashlib
import json

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from agentprov.adapters.foobench.dialect import FooJsonlReader
from agentprov.adapters.types import ArtefactRef, Origin
from agentprov.errors import INGEST_CODES, IngestError, MalformedArtefact
from agentprov.ingest.limits import IngestLimits

LIMITS = IngestLimits()
READER = FooJsonlReader()
FUZZ = settings(max_examples=250, deadline=2000, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
MAPFUZZ = settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])


def ref_of(data: bytes) -> ArtefactRef:
    return ArtefactRef("a0", hashlib.sha256(data).hexdigest(), len(data), "application/x-ndjson", Origin.local("fuzz"),
                       "primary", "native")  # type: ignore[arg-type]


def parse(data: bytes) -> list[object]:
    return list(READER.parse(data, ref_of(data), limits=LIMITS))


def outcome(data: bytes) -> tuple[str, object]:
    try:
        return ("ok", [(i.locator.key(), i.value) for i in parse(data)])
    except IngestError as exc:
        assert exc.code in INGEST_CODES
        return ("ingest", exc.code)
    except MalformedArtefact:
        return ("malformed", None)


def mutate(seed: bytes):
    def apply(ops: list[tuple[str, int, int]]) -> bytes:
        data = bytearray(seed)
        for op, pos, val in ops:
            if not data:
                break
            i = pos % len(data)
            if op == "flip":
                data[i] ^= (val % 255) + 1
            elif op == "cut":
                del data[i:]
            elif op == "ins":
                data[i:i] = bytes([val % 256])
            elif op == "del":
                del data[i : i + 1 + val % 8]
        return bytes(data)

    ops = st.tuples(st.sampled_from(["flip", "cut", "ins", "del"]), st.integers(0, 10**6), st.integers(0, 10**6))
    return st.lists(ops, max_size=6).map(apply)


SEED = (
    b'{"schema":"foobench/1","run":"r","task":"t"}\n'
    b'{"type":"llm_request","id":"r0","actor":"agent","ts":"2026-10-01T12:00:00Z"}\n'
    b'{"type":"telemetry","value":[1,2.5,"x",null,{"b":true}]}\n'
)


@FUZZ
@given(st.binary(max_size=400))
def test_arbitrary_bytes_sniff_totally_and_parse_or_fail_closed(data):
    assert isinstance(READER.sniff(data, label="x", limits=LIMITS).match, bool)
    outcome(data)


@FUZZ
@given(mutate(SEED))
def test_mutated_seed_parses_or_fails_closed_deterministically(data):
    assert READER.sniff(data, label="x", limits=LIMITS) == READER.sniff(data, label="x", limits=LIMITS)
    assert outcome(data) == outcome(data)


@FUZZ
@given(st.data())
def test_mutated_fixture_parses_or_fails_closed(foo, data):
    raw = data.draw(mutate(foo.raw(foo.PRIMARY)))
    outcome(raw)


json_values = st.recursive(
    st.none() | st.booleans() | st.integers(-(2**40), 2**40) | st.text(max_size=8),
    lambda children: st.lists(children, max_size=3) | st.dictionaries(st.text(max_size=5), children, max_size=3),
    max_leaves=8,
)


@FUZZ
@given(st.lists(json_values, max_size=6))
def test_arbitrary_json_lines_after_a_header_parse_or_fail_closed(values):
    data = b'{"schema":"foobench/1","task":"t"}\n' + b"".join(json.dumps(v).encode() + b"\n" for v in values)
    status, _ = outcome(data)
    if status == "ok":
        assert all(isinstance(v, dict) and isinstance(v.get("type"), str) for v in values)


@MAPFUZZ
@given(st.data())
def test_any_selection_of_fixture_events_ends_in_a_valid_sealed_aer(foo, data):
    """The mapper never raises: a selection that breaks a reference gives a degenerate AER, still valid and sealed."""
    lines = foo.raw(foo.PRIMARY).splitlines()
    header, events = lines[0], lines[1:]
    chosen = data.draw(st.lists(st.sampled_from(events), max_size=len(events) + 2))
    raw = b"\n".join([header, *chosen]) + b"\n"
    sub = data.draw(st.sampled_from([foo.raw(foo.SUB), None, b"garbage\n"]))
    mapped = foo.map(raw, sub)
    report = mapped.validate()
    assert report.ok, sorted({f.code for f in report.errors})
    assert mapped.records[0]["k"] == "execution" and mapped.records[-1]["k"] == "seal"
    # a degenerate AER is the declared outcome of a malformed file, never of an unexpected exception in the mapper
    assert mapped.outcome.error_code in (None, "adapter.malformed_artefact"), mapped.outcome.error_code
    assert "adapter_defect" not in mapped.issue_codes()


POOL = st.sampled_from([None, 0, 1, "", "x", "2026-13-45T25:61:61Z", [], {}, [1], {"a": 1}, True, "sha256:zz", -1, 2**60])


@MAPFUZZ
@given(st.data())
def test_field_level_damage_to_the_fixture_still_ends_in_a_valid_sealed_aer(foo, data):
    """Wrong types, missing keys and absurd values in any event give a sealed, valid AER (degenerate at worst)."""
    events = foo.events(foo.raw(foo.PRIMARY))
    for _ in range(data.draw(st.integers(1, 4))):
        event = data.draw(st.sampled_from(events[1:]))
        key = data.draw(st.sampled_from(sorted(event)))
        if data.draw(st.booleans()):
            del event[key]
        else:
            event[key] = data.draw(POOL)
    try:
        mapped = foo.map(foo.lines(events))
    except (MalformedArtefact, IngestError):
        return  # the reader refuses the file (a register entry, D.2.8 case 4): nothing reaches the mapper
    report = mapped.validate()
    assert report.ok, sorted({f.code for f in report.errors})
    assert mapped.outcome.error_code in (None, "adapter.malformed_artefact") and "adapter_defect" not in mapped.issue_codes()


# Regression (full suite, 2026-10-11): a damaged blob size gave ``adapter_defect`` (2**60 is not I-JSON, so the writer
# refused the record) or an AER failing AER-V21 (``aer.blob.digest``: a size other than the stored blob's). ``@example``
# cannot pin draws made through ``st.data()``, so the failing damage is replayed here directly, for the screenshot's
# top-level size and for the nested blob part of a message, at the integers of ``POOL`` and the I-JSON boundary.
@pytest.mark.parametrize("value", [0, 1, 2**60, 2**53, 10**6, -1])
@pytest.mark.parametrize("where", ["screenshot", "message_part"])
def test_a_damaged_blob_size_ends_in_a_valid_sealed_aer(foo, where, value):
    events = foo.events(foo.raw(foo.PRIMARY))
    if where == "screenshot":
        (event,) = [e for e in events if e.get("type") == "screenshot"]
        event["bytes"] = value
    else:
        (blob,) = [p["blob"] for e in events for p in e.get("add", ()) if isinstance(p.get("blob"), dict)]
        blob["bytes"] = value
    mapped = foo.map(foo.lines(events))
    report = mapped.validate()
    assert report.ok, sorted({f.code for f in report.errors})
    assert mapped.records[0]["k"] == "execution" and mapped.records[-1]["k"] == "seal"
    assert mapped.outcome.error_code == "adapter.malformed_artefact", mapped.outcome.error_code
    assert mapped.issue_codes() == ["unparseable_artefact"]


def test_the_declared_blob_size_is_kept_when_it_matches_the_supplied_blob(mapped, foo):
    png = foo.raw(foo.PNG)
    (art,) = [r for r in mapped.of_kind("artefact") if r.get("type") == "foobench:screenshot"]
    assert art["content_ref"]["bytes"] == len(png) and not mapped.outcome.degenerate


def test_an_unsupplied_blob_keeps_the_declared_size_for_aer_v21(foo):
    """Without the blob's bytes the mapper cannot check the size; it keeps the declaration and the validator checks it
    against the store (AER-V21), so the damage is still caught, never silently corrected."""
    from agentprov.adapters.foobench.mapper import FooMapper
    from agentprov.adapters.runner import map_unit

    events = foo.events(foo.raw(foo.PRIMARY))
    (event,) = [e for e in events if e.get("type") == "screenshot"]
    event["bytes"] = 1
    raw, sub = foo.lines(events), foo.raw(foo.SUB)
    outcome = map_unit(foo.unit(raw, sub), FooMapper(), foo.profile(), registry=foo.registry(), auxiliary={foo.SUB: sub})
    assert not outcome.degenerate
    (art,) = [r for r in outcome.records if r.get("type") == "foobench:screenshot"]
    assert art["content_ref"]["bytes"] == 1


# Regression (seed sweep, 2026-10-11, ``--hypothesis-seed=40``): ``store_patch = [1]`` on the memory write reached the
# writer as a ``state_change.patch`` that is not RFC 6902, and the runner sealed ``adapter_defect``.
@pytest.mark.parametrize("patch", [
    [1], [{}], [{"op": "add"}], [{"op": "frobnicate", "path": "/k"}], [{"op": "add", "path": "k", "value": 1}],
    [{"op": "add", "path": "/k"}], [{"op": "move", "path": "/k"}], [{"op": "copy", "path": "/k", "from": 3}],
    [{"op": "remove", "path": "/k", "$x": 1}], [{"op": 1, "path": "/k"}], [{"op": "add", "path": "/~2", "value": 1}],
])
def test_a_damaged_store_patch_ends_in_a_valid_sealed_aer(foo, patch):
    events = foo.events(foo.raw(foo.PRIMARY))
    (event,) = [e for e in events if e.get("type") == "memory_write"]
    event["store_patch"] = patch
    mapped = foo.map(foo.lines(events))
    report = mapped.validate()
    assert report.ok, sorted({f.code for f in report.errors})
    assert mapped.outcome.error_code == "adapter.malformed_artefact" and mapped.issue_codes() == ["unparseable_artefact"]


@pytest.mark.parametrize("patch", [[], [{"op": "remove", "path": ""}], [{"op": "copy", "path": "/a~1b", "from": "/k"}],
                                   [{"op": "test", "path": "/k", "value": {"$blob": "x"}}]])
def test_a_well_formed_store_patch_is_kept(foo, patch):
    events = foo.events(foo.raw(foo.PRIMARY))
    (event,) = [e for e in events if e.get("type") == "memory_write"]
    event["store_patch"] = patch
    mapped = foo.map(foo.lines(events))
    assert mapped.validate().ok and not mapped.outcome.degenerate
    assert [r for r in mapped.of_kind("state_change") if r.get("target") == "agent_store"]


# ------------------------------------------------------------------------------- phase 12a: framing and determinism
FRAMING = st.sampled_from([b"", b" ", b"\r", b"\xef\xbb\xbf", b"\x00", b"{", b'{"type": 1}', b'{"type":"llm_request"', b"\xff",
                           b'{"a":1,"a":2}', b'{"type":"telemetry","v":NaN}', b'"\\ud800"'])


@MAPFUZZ
@given(st.data())
def test_line_level_framing_damage_parses_or_fails_closed_and_maps_to_a_valid_aer(foo, data):
    """K.11.1 JSONL mutations on the real fixture: insert framing defects, split or merge lines, CRLF; the reader refuses
    with a typed error or the mapper seals a valid AER (degenerate at worst), and never an ``adapter_defect``."""
    lines = foo.raw(foo.PRIMARY).split(b"\n")[:-1]
    for _ in range(data.draw(st.integers(1, 3))):
        op = data.draw(st.sampled_from(["insert", "split", "merge", "crlf"]))
        i = data.draw(st.integers(0, len(lines) - 1))
        if op == "insert":
            lines.insert(i + 1, data.draw(FRAMING))
        elif op == "split" and len(lines[i]) > 2:
            at = data.draw(st.integers(1, len(lines[i]) - 1))
            lines[i : i + 1] = [lines[i][:at], lines[i][at:]]
        elif op == "merge" and i + 1 < len(lines):
            lines[i : i + 2] = [lines[i] + lines[i + 1]]
        elif op == "crlf":
            lines[i] += b"\r"
    raw = b"\n".join(lines) + b"\n"
    if outcome(raw)[0] != "ok":
        return
    mapped = foo.map(raw)
    assert mapped.validate().ok
    assert mapped.outcome.error_code in (None, "adapter.malformed_artefact") and "adapter_defect" not in mapped.issue_codes()


@MAPFUZZ
@given(st.data())
def test_mapping_any_selection_is_byte_deterministic(foo, data):
    """F-5 at the byte level: the same input maps to the same sealed AER bytes, run after run."""
    lines = foo.raw(foo.PRIMARY).splitlines()
    chosen = data.draw(st.lists(st.sampled_from(lines[1:]), max_size=len(lines)))
    raw = b"\n".join([lines[0], *chosen]) + b"\n"
    assert foo.map(raw).data == foo.map(raw).data
