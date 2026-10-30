"""Reader of the FooBench JSONL dialect (docs/architecture D.12.1 row 2, D.2.3; K.6.4, K.11)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from agentprov.adapters.foobench import ADAPTER_ID
from agentprov.adapters.foobench.dialect import DIALECT_ID, FLAG_SUB, VARIANT, FooJsonlReader, parse_events
from agentprov.adapters.types import ArtefactRef, CandidateArtefact, Origin
from agentprov.errors import IngestError, MalformedArtefact
from agentprov.ingest.limits import IngestLimits

LIMITS = IngestLimits()
#: Every event type the fixture must contain (D.12 scenario; Q.3 fixture list), including the unknown `telemetry`.
EVENT_TYPES = frozenset(
    {
        "llm_request", "llm_response", "tool_start", "tool_end", "guard_verdict", "plan_update", "memory_write",
        "memory_read", "screenshot", "handoff", "approval", "text_action", "checkpoint_restore", "telemetry",
    }
)  # fmt: skip
HEADER = b'{"schema":"foobench/1","run":"r","task":"t"}\n'


def ref_of(data: bytes) -> ArtefactRef:
    return ArtefactRef("a0", hashlib.sha256(data).hexdigest(), len(data), "application/x-ndjson",
                       Origin.local("fixture"), "primary", "native")  # type: ignore[arg-type]


class _Tree:
    def __init__(self, *labels: str) -> None:
        self.labels = labels

    def walk(self) -> Iterator[CandidateArtefact]:
        for label in self.labels:
            yield CandidateArtefact(label, 1, Origin.local(label))

    def open(self, label: str, *, max_bytes: int) -> bytes:  # pragma: no cover - never opened by discovery
        raise AssertionError("discovery must not read contents")


def test_dialect_and_adapter_ids():
    assert ADAPTER_ID == DIALECT_ID == "foobench.jsonl" and VARIANT == "v1"
    reader = FooJsonlReader()
    assert reader.dialect_id == DIALECT_ID and reader.variants == {VARIANT}


def test_fixture_sniffs_as_the_dialect_and_the_sub_file_is_flagged(foo):
    reader = FooJsonlReader()
    primary = reader.sniff(foo.raw(foo.PRIMARY), label=foo.PRIMARY, limits=LIMITS)
    sub = reader.sniff(foo.raw(foo.SUB), label=foo.SUB, limits=LIMITS)
    assert primary.match and primary.dialect == DIALECT_ID and primary.variant == VARIANT and primary.flags == frozenset()
    assert sub.match and sub.flags == {FLAG_SUB}


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"\n",
        b"\xef\xbb\xbf" + HEADER,
        b"[1, 2]\n",
        b'{"schema": "foobench/2"}\n',
        b'{"schema": 1}\n',
        b'{"run": "r"}\n',
        b'{"schema": "foobench/1", "schema": "foobench/1"}\n',
        b'{"adprov_schema": "transcript/v1", "meta": {}, "turns": []}',
        b"\xff\xfe not utf-8\n",
        b'{"schema": "foobench/1"',
    ],
)
def test_foreign_or_unsafe_bytes_never_match_and_never_raise(data):
    result = FooJsonlReader().sniff(data, label="x", limits=LIMITS)
    assert not result.match and result.reasons


def test_sniff_looks_at_the_first_line_only():
    # the second line is garbage, but the dialect is decided by line 0 (parse is where the rest is checked)
    assert FooJsonlReader().sniff(HEADER + b"not json\n", label="x", limits=LIMITS).match


def test_parse_yields_one_item_for_the_whole_file_with_zero_based_event_lines(foo):
    raw = foo.raw(foo.PRIMARY)
    (item,) = list(FooJsonlReader().parse(raw, ref_of(raw), limits=LIMITS))
    assert item.locator.key() == {} and item.locator.a == "a0"  # the execution's key locator is {} (the whole primary file)
    assert item.dialect == DIALECT_ID and item.variant == VARIANT and item.flags == frozenset()
    physical = raw.split(b"\n")[:-1]
    events = item.value["events"]
    assert [e["line"] for e in events] == list(range(1, len(physical)))  # line 0 is the header
    assert item.value["header"]["schema"] == "foobench/1"
    for entry in events:
        assert physical[entry["line"]].startswith(b'{"type":"' + entry["event"]["type"].encode() + b'"')


def test_the_fixture_holds_every_event_type_and_exactly_two_approvals(foo):
    events = foo.events(foo.raw(foo.PRIMARY))[1:]
    assert {e["type"] for e in events} == EVENT_TYPES
    assert sorted(e["decision"] for e in events if e["type"] == "approval") == ["approve", "edit"]
    assert sum(e["type"] == "telemetry" for e in events) == 1  # the one event type the adapter does not know


def test_the_hand_off_events_live_in_a_second_file(foo):
    raw = foo.raw(foo.SUB)
    parsed = parse_events(raw, LIMITS)
    assert parsed.header["parent"]["call"] == "c3" and {e["type"] for _, e in parsed.events} == {"llm_request", "llm_response"}
    handoff = next(e for e in foo.events(foo.raw(foo.PRIMARY))[1:] if e["type"] == "handoff")
    assert handoff["sub_file"] == foo.SUB


def test_fixture_is_what_the_generator_writes():
    path = Path(__file__).resolve().parents[3] / "tools" / "gen_foobench_fixture.py"
    spec = importlib.util.spec_from_file_location("gen_foobench_fixture", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        files = module.build()
    finally:
        sys.modules.pop(spec.name, None)
    for name, data in files.items():
        assert (module.OUT / name).read_bytes() == data, name


def test_source_json_records_the_self_authored_permissive_synthetic_fixture(foo):
    """K.4.1: every fixture file has a SOURCE.json entry; K.4.2: own work is `permissive`, kept apart by `synthetic: true`."""
    entries = json.loads(foo.raw("SOURCE.json"))
    assert sorted(e["sample_file"] for e in entries) == sorted([foo.PRIMARY, foo.SUB, foo.PNG])
    for entry in entries:
        data = foo.raw(entry["sample_file"])
        assert entry["sha256"] == hashlib.sha256(data).hexdigest() and entry["size_bytes"] == len(data)
        assert entry["licence_class"] == "permissive" and entry["synthetic"] is True
        assert entry["original_path"] == "tools/gen_foobench_fixture.py" and entry["url"] is None


@pytest.mark.parametrize(
    ("data", "exc"),
    [
        (HEADER + b'{"type":"x"}', IngestError),  # no final newline
        (HEADER + b"\n", IngestError),  # blank line
        (HEADER + b'{"type":"x"}\r\n', IngestError),  # CRLF
        (b"\xef\xbb\xbf" + HEADER, IngestError),  # BOM
        (HEADER + b'{"type":"x","type":"y"}\n', IngestError),  # duplicate key
        (HEADER + b'{"type":"x","v":NaN}\n', IngestError),  # non-finite number
        (HEADER + b"not json\n", IngestError),
        (b'{"schema":"foobench/2"}\n', MalformedArtefact),  # not this dialect's header
        (b"[1]\n", MalformedArtefact),
        (b'{"schema":"foobench/1"}\n', MalformedArtefact),  # the task id is required (nothing may stand in for it)
        (b'{"schema":"foobench/1","parent":1}\n', MalformedArtefact),
        (HEADER + b"[1]\n", MalformedArtefact),  # an event must be an object
        (HEADER + b'{"kind":"x"}\n', MalformedArtefact),  # ... with a string type
        (HEADER + b'{"type":3}\n', MalformedArtefact),
    ],
)
def test_parse_fails_closed(data, exc):
    with pytest.raises(exc):
        list(FooJsonlReader().parse(data, ref_of(data), limits=LIMITS))


def test_parse_enforces_tier1_limits(foo):
    raw = foo.raw(foo.PRIMARY)
    with pytest.raises(IngestError) as info:
        list(FooJsonlReader().parse(raw, ref_of(raw), limits=LIMITS.replace(max_jsonl_line_bytes=64)))
    assert info.value.code.startswith("ingest.")
    with pytest.raises(IngestError):
        list(FooJsonlReader().parse(raw, ref_of(raw), limits=LIMITS.replace(max_artefact_bytes=len(raw) - 1)))
    list(FooJsonlReader().parse(raw, ref_of(raw), limits=LIMITS.replace(max_artefact_bytes=len(raw))))


def test_discovery_applies_the_profile_globs_and_leaves_the_sub_file_to_its_parent(foo):
    tree = _Tree("a/trace-001.jsonl", "a/sub-trace-001.jsonl", "a/.DS_Store", "a/._trace.jsonl", "a/notes.txt", "b/trace-002.jsonl")
    labels = [c.label for c in FooJsonlReader().iter_artefacts(tree, foo.profile())]
    assert labels == ["a/trace-001.jsonl", "b/trace-002.jsonl"]
    assert foo.profile().data["import"]["auxiliary"] == ("**/sub-*.jsonl",)
