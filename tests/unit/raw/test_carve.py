"""D-218: carving one string value of a stored artefact (``agentprov.raw.carve``) and the ``carved`` origin kind."""

from __future__ import annotations

import base64
import json

import pytest

from agentprov.raw.carve import CarveError, carve
from agentprov.raw.origins import Origin, OriginError

DOC = json.dumps({"a": {"text": "héllo", "img": "data:image/png;base64," + base64.b64encode(b"\x89PNG").decode()},
                  "list": ["x", 1], "n": 3}).encode()
JSONL = b'{"msg": "first"}\n{"msg": "second"}\n'


def test_utf8_carves_the_string_bytes():
    assert carve(DOC, {"p": "/a/text"}, "utf8").data == "héllo".encode()
    assert carve(DOC, {"p": "/list/0"}, "utf8").data == b"x"


def test_base64_carves_a_data_uri_payload_with_its_media_type():
    got = carve(DOC, {"p": "/a/img"}, "base64")
    assert got.data == b"\x89PNG" and got.media == "image/png"


def test_a_jsonl_line_is_parsed_alone():
    assert carve(JSONL, {"line": 1, "p": "/msg"}, "utf8").data == b"second"


def test_a_byte_range_is_parsed_alone():
    start = JSONL.index(b"{", 1)
    assert carve(JSONL, {"bytes": [start, len(JSONL) - 1], "p": "/msg"}, "utf8").data == b"second"


@pytest.mark.parametrize(("loc", "transform"), [
    ({"p": "/n"}, "utf8"),                      # not a string
    ({"p": "/missing"}, "utf8"),                # does not resolve
    ({"p": "/list/2"}, "utf8"),                 # index out of range
    ({"p": "/a/text"}, "base64"),               # not a data: URI
    ({"p": "/a/text"}, "rot13"),                # unknown transform
    ({"p": "/a", "line": 0, "bytes": [0, 1]}, "utf8"),  # line and bytes
    ({"a": "a0", "p": "/a/text"}, "utf8"),      # an artefact id is not part of a carving locator
    ({"line": 5, "p": "/msg"}, "utf8"),         # outside the artefact
])
def test_what_cannot_be_carved_is_refused(loc, transform):
    with pytest.raises(CarveError):
        carve(DOC if "line" not in loc else JSONL, loc, transform)


def test_bad_json_and_a_lone_surrogate_are_refused():
    with pytest.raises(CarveError):
        carve(b"{not json", {"p": ""}, "utf8")
    with pytest.raises(CarveError):
        carve(b'{"s": "\\ud800"}', {"p": "/s"}, "utf8")
    with pytest.raises(CarveError):
        carve(b'{"s": "data:text/plain;base64,@@@"}', {"p": "/s"}, "base64")


def test_the_carved_origin_kind():
    origin = Origin.carved("a" * 64, {"p": "/x", "line": 2}, "utf8")
    assert origin.kind == "carved" and origin.data == {"from": "a" * 64, "loc": {"line": 2, "p": "/x"}, "transform": "utf8"}
    assert Origin.from_json(origin.to_json()) == origin
    for bad in (("b" * 63, {"p": "/x"}, "utf8"), ("a" * 64, {"q": "/x"}, "utf8"), ("a" * 64, {"p": "/x"}, "gzip"),
                ("a" * 64, {"p": "/x", "line": -1}, "utf8")):
        with pytest.raises(OriginError):
            Origin.carved(*bad)


def test_a_carver_parses_each_region_once(monkeypatch):
    from agentprov.raw import carve as module

    calls = []
    real = module._document

    def counting(data, loc, limits):
        calls.append(tuple(sorted(k for k in loc if k != "p")))
        return real(data, loc, limits)

    monkeypatch.setattr(module, "_document", counting)
    carver = module.Carver(DOC)
    assert carver.carve({"p": "/a/text"}, "utf8").data == carve(DOC, {"p": "/a/text"}, "utf8").data
    assert carver.carve({"p": "/list/0"}, "utf8").data == b"x"
    assert calls.count(()) == 2  # the module-level carve above parsed once; the Carver parsed the document once
    lines = module.Carver(JSONL)
    assert [lines.carve({"line": n, "p": "/msg"}, "utf8").data for n in (0, 1, 0)] == [b"first", b"second", b"first"]
    assert calls.count(("line",)) == 2


# D-222: a region of at least ``span_min`` bytes is read by its string's byte span; the outcome is the same either way.

def _outcome(data, loc, transform, span_min):
    try:
        return carve(data, loc, transform, span_min=span_min)
    except CarveError as exc:
        return ("refused", exc.code, str(exc))


SPAN_CASES = [
    (DOC, {"p": "/a/text"}, "utf8"), (DOC, {"p": "/a/img"}, "base64"), (DOC, {"p": "/list/0"}, "utf8"),
    (DOC, {"p": "/n"}, "utf8"), (DOC, {"p": "/missing"}, "utf8"), (DOC, {"p": "/list/2"}, "utf8"),
    (DOC, {"p": "/a/text"}, "base64"), (JSONL, {"line": 0, "p": "/msg"}, "utf8"),
    (JSONL, {"line": 1, "p": "/msg"}, "utf8"), (JSONL, {"line": 2, "p": "/msg"}, "utf8"),
    (JSONL, {"line": 5, "p": "/msg"}, "utf8"), (JSONL.rstrip(b"\n"), {"line": 1, "p": "/msg"}, "utf8"),
    (b'{"a": "x"}\n\n{"a": "y"}', {"line": 1, "p": "/a"}, "utf8"), (b'{"a": "x"}\n\n{"a": "y"}', {"line": 2, "p": "/a"}, "utf8"),
    (JSONL, {"bytes": [JSONL.index(b"{", 1), len(JSONL) - 1], "p": "/msg"}, "utf8"),
    (JSONL, {"bytes": [0, 3], "p": "/msg"}, "utf8"), (JSONL, {"bytes": [3, 3], "p": "/msg"}, "utf8"),
    (JSONL, {"bytes": [0, len(JSONL) + 1], "p": "/msg"}, "utf8"), (JSONL, {"bytes": [True, 4], "p": "/msg"}, "utf8"),
    (JSONL, {"line": -1, "p": "/msg"}, "utf8"), (JSONL, {"line": True, "p": "/msg"}, "utf8"),
    (b"{not json", {"p": ""}, "utf8"), (b'{"s": "\\ud800"}', {"p": "/s"}, "utf8"),
    (b'"top"', {"p": ""}, "utf8"), (b'{"s": "x", "s": "y"}', {"p": "/s"}, "utf8"),
]  # fmt: skip


@pytest.mark.parametrize(("data", "loc", "transform"), SPAN_CASES)
def test_a_carve_by_span_equals_a_carve_by_whole_parse(data, loc, transform):
    assert _outcome(data, loc, transform, 0) == _outcome(data, loc, transform, 1 << 40)


def test_a_carver_never_keeps_a_region_read_by_span(monkeypatch):
    from agentprov.raw import carve as module

    calls = []
    real = module._document
    monkeypatch.setattr(module, "_document", lambda data, loc, limits: calls.append(loc) or real(data, loc, limits))
    carver = module.Carver(DOC, span_min=0)
    assert carver.carve({"p": "/a/text"}, "utf8").data == "héllo".encode()
    assert not calls and not carver._documents
    with pytest.raises(CarveError):  # not a string: the span path proves nothing and the whole parse refuses
        carver.carve({"p": "/n"}, "utf8")
    assert len(calls) == 1


def test_a_carve_by_span_does_not_build_the_regions_other_values():
    import tracemalloc

    big = "line with \"quotes\" and é\n" * 160_000  # about 4 MB, with escapes and non-ASCII text
    events = [{"tool": "t", "args": {"q": "x" * 20}, "n": i} for i in range(2_000)]  # small siblings
    events.insert(3, {"result_full": big})
    data = json.dumps({"trace": {"events": events}}, ensure_ascii=False).encode()
    loc = {"p": "/trace/events/3/result_full"}
    peaks = []
    for span_min in (0, 1 << 40):
        tracemalloc.start()
        got = carve(data, loc, "utf8", span_min=span_min)
        peaks.append(tracemalloc.get_traced_memory()[1])
        tracemalloc.stop()
        assert got.data == big.encode()
    assert peaks[0] < 0.5 * peaks[1], peaks
