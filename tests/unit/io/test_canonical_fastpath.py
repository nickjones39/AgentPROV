"""D-416: ``jcs_bytes``'s stdlib fast path writes exactly what ``rfc8785`` writes, and falls back for everything else.

The reference is ``rfc8785.dumps``: for every value ``jcs_bytes`` gives the same bytes or raises the same exception
type. The cases cover what RFC 8785 makes delicate: member order by UTF-16 code units (astral keys, the surrogate
boundary), the escapes (short forms, lower-case ``\\u00xx``, nothing else escaped, so U+2028, U+2029 and DEL are raw),
lone surrogates, ``bool`` before ``int``, subclasses (``int()`` and ``dict()`` coercion in rfc8785), ``-0`` and the
integer bounds, floats, depth, cycles and the recursion limit; with the C encoder and the pure-Python one. Reviewed by
core review B (2026-10-15).
"""

from __future__ import annotations

import enum
import json.encoder
import sys
from collections import OrderedDict, defaultdict
from collections.abc import Iterator
from typing import Any

import pytest
import rfc8785
from hypothesis import given, settings
from hypothesis import strategies as st

from agentprov.io import canonical
from agentprov.io.canonical import jcs_bytes

S = settings(max_examples=2000, deadline=None, derandomize=True)


@pytest.fixture(params=["c", "python"])
def encoder(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> str:
    """Both stdlib encoders: the C accelerator and the pure-Python fallback."""
    if request.param == "python":
        monkeypatch.setattr(json.encoder, "c_make_encoder", None)
        monkeypatch.setattr(json.encoder, "c_encode_basestring", None)
        monkeypatch.setattr(json.encoder, "encode_basestring", json.encoder.py_encode_basestring)
    return str(request.param)


def outcome(fn: Any, obj: Any) -> bytes | type[BaseException]:
    try:
        return fn(obj)
    except Exception as exc:  # noqa: BLE001 - the exception type is what is compared
        return type(exc)


def same(obj: Any) -> None:
    assert outcome(jcs_bytes, obj) == outcome(rfc8785.dumps, obj)


ASTRAL_KEYS = [*range(0x10000, 0x110000, 97), 0x1F600, 0x10FFFF]


def test_every_code_point_as_a_value(encoder: str) -> None:
    for cp in range(0x110000):
        s = chr(cp)
        same(s)
        same("a" + s + "z")


def test_every_bmp_code_point_and_astral_samples_as_keys(encoder: str) -> None:
    for cp in [*range(0x10000), *ASTRAL_KEYS]:
        s = chr(cp)
        same({s: cp})
        same({"k" + s: 0, "k": 1, "k\uffff": 2})


@pytest.mark.parametrize("s", ["\u2028", "\u2029", "\x7f", "\x00", "\x1f", "\b\f\n\r\t", '"\\/', "\ud800", "\udfff",
                               "a\ud83dz", "\ud83d\ude00", "\U0001f600", "\ufeff", "\ue000", "\uffff", "\ud7ff"])
def test_delicate_strings_take_the_fast_path_or_fall_back(s: str) -> None:
    same(s)
    same({s: s})
    same([s, {"x": s}])


def test_the_escapes_and_raw_characters_are_spelled_as_rfc8785_spells_them() -> None:
    assert jcs_bytes("\x01\b\f\n\r\t\x1f\"\\") == b'"\\u0001\\b\\f\\n\\r\\t\\u001f\\"\\\\"'
    assert jcs_bytes("\u2028\u2029\x7f/") == b'"\xe2\x80\xa8\xe2\x80\xa9\x7f/"'
    assert canonical._plain("\u2028\u2029\x7f", 0)


def test_lone_surrogates_fail_as_rfc8785_fails() -> None:
    with pytest.raises(rfc8785.CanonicalizationError):
        jcs_bytes("\ud800")
    with pytest.raises(UnicodeEncodeError):  # rfc8785's UTF-16 sort key raises for a key
        jcs_bytes({"\ud800": 1, "a": 2})


def test_member_order_is_by_utf16_code_units() -> None:
    # By code point U+E000 sorts before U+1F600; by UTF-16 code units (D83D DE00) after it. The astral key falls back.
    obj = {"\ue000": 1, "\U0001f600": 2, "a": 3}
    assert not canonical._plain(obj, 0)
    assert jcs_bytes(obj) == rfc8785.dumps(obj) == b'{"a":3,"\xf0\x9f\x98\x80":2,"\xee\x80\x80":1}'
    bmp = {"\ue000": 1, "\uffff": 2, "\u00e9": 3, "Z": 4, "a": 5, "\ud7ff": 6}
    assert canonical._plain(bmp, 0)
    same(bmp)


def test_wide_keys_around_the_surrogate_block(encoder: str) -> None:
    keys = [chr(c) for r in (range(0xD7F0, 0xD800), range(0xE000, 0xE010), range(0xFFF0, 0x10000)) for c in r]
    wide = {a + b: i for i, (a, b) in enumerate((a, b) for a in keys for b in keys)}
    assert canonical._plain(wide, 0)
    assert jcs_bytes(wide) == rfc8785.dumps(wide)


def test_the_guard_boundaries() -> None:
    assert canonical._plain(2**53 - 1, 0) and canonical._plain(-(2**53 - 1), 0)
    assert not canonical._plain(2**53, 0) and not canonical._plain(-(2**53), 0)
    deep: Any = 0
    for _ in range(128):
        deep = [deep]
    assert canonical._plain(deep, 0) and not canonical._plain([deep], 0)
    assert canonical._plain({"\uffff": 1}, 0) and not canonical._plain({"\U00010000": 1}, 0)


class Colour(enum.IntEnum):
    RED = 1


class Flag(enum.IntFlag):
    A = 1


class Word(enum.StrEnum):
    W = "w"


class Text(str):
    pass


class Number(int):
    pass


class DictSub(dict):
    pass


class IntCoerced(int):  # rfc8785 reads int(obj), so __int__; json writes int.__repr__ (core review B, B1)
    def __int__(self) -> int:
        return 7


class AlwaysInRange(int):  # rfc8785's bound check uses the overridden comparisons (B1)
    def __le__(self, other: object) -> bool:
        return True

    def __ge__(self, other: object) -> bool:
        return True

    def __lt__(self, other: object) -> bool:
        return False

    def __gt__(self, other: object) -> bool:
        return False


class OtherItems(dict):  # json calls items(); rfc8785's dict(obj) copies the storage (B2)
    def items(self) -> Any:
        return [("z", 1)]


class OtherLookup(dict):  # (B2)
    def __iter__(self) -> Iterator[Any]:
        return iter(["a"])

    def __getitem__(self, key: Any) -> Any:
        return 5


@pytest.mark.parametrize("obj", [
    True, False, None, 0, -0, 1, -1, 2**53 - 1, -(2**53 - 1), 2**53, -(2**53), 2**53 + 1, 10**30,
    0.0, -0.0, 1.0, 1.5, 1e21, 1e-7, float("nan"), float("inf"), -float("inf"),
    [True, 1, False, 0], {"b": True, "a": 1}, (1, 2), [(1,)], Colour.RED, Flag.A, Word.W, [Colour.RED],
    Text("x"), {"k": Text("x")}, Number(3), DictSub(a=1), OrderedDict(b=1, a=2), defaultdict(int, a=1),
    IntCoerced(3), [IntCoerced(3)], AlwaysInRange(10**30), OtherItems(a=1), {"k": OtherItems(a=1)}, OtherLookup(a=1),
    {1: "x"}, {True: 1}, {None: 1}, {(1,): 2}, b"x", {"k": b"x"}, set(), object(), {}, [], [[]], [{}], {"": ""},
])
def test_types_bounds_and_subclasses(obj: Any) -> None:
    same(obj)


def test_bool_is_not_taken_for_int() -> None:
    assert jcs_bytes([True, 1, False, 0]) == b"[true,1,false,0]"


@pytest.mark.parametrize("depth", [1, 126, 127, 128, 129, 130, 400])
def test_nesting_around_the_depth_bound(depth: int) -> None:
    obj: Any = 0
    for i in range(depth):
        obj = [obj] if i % 2 else {"k": obj}
    same(obj)


def test_cycles_fall_back() -> None:
    a: list[Any] = []
    a.append(a)
    d: dict[str, Any] = {}
    d["d"] = d
    assert not canonical._plain(a, 0) and not canonical._plain(d, 0)
    same(a)
    same(d)


def test_near_the_recursion_limit_the_fast_path_never_fails_where_rfc8785_succeeds() -> None:
    # Core review B, finding A: the guard ran outside the try and could raise RecursionError where rfc8785 encodes.
    obj: Any = 0
    for _ in range(120):
        obj = [obj]

    def at(depth: int, fn: Any) -> bytes | type[BaseException] | None:
        if depth:
            return at(depth - 1, fn)
        return outcome(fn, obj)

    def at_depth(extra: int, fn: Any) -> bytes | type[BaseException] | None:
        try:
            return at(extra, fn)
        except RecursionError:  # the helper's own frames hit the limit before calling fn
            return None

    old = sys.getrecursionlimit()
    sys.setrecursionlimit(1000)
    checked = 0
    try:
        for extra in range(0, 1000, 2):
            reference = at_depth(extra, rfc8785.dumps)
            if isinstance(reference, bytes):
                checked += 1
                assert at_depth(extra, jcs_bytes) == reference, extra
    finally:
        sys.setrecursionlimit(old)
    assert checked


# ---- the differential -------------------------------------------------------------------------------------------

TEXT = st.text(st.characters(codec=None, min_codepoint=0, max_codepoint=0x10FFFF), max_size=12) | st.sampled_from(
    ["\u2028", "\u2029", "\x7f", "\ud800", "\udbff\udc00", "\ue000", "\ud7ff", "\U0001f600", "\x00", "\b", "/"])
INTS = st.integers(-(2**60), 2**60) | st.sampled_from([0, -0, 2**53 - 1, -(2**53 - 1), 2**53, -(2**53), 2**53 + 1])
SCALARS = st.none() | st.booleans() | INTS | TEXT | st.floats(allow_nan=True, allow_infinity=True) | st.sampled_from(
    [Colour.RED, Flag.A, Word.W, Text("t"), Number(5), IntCoerced(2), -0.0])
KEYS = TEXT | st.sampled_from([1, True, None])
VALUES = st.recursive(
    SCALARS,
    lambda inner: st.lists(inner, max_size=5) | st.dictionaries(KEYS, inner, max_size=5)
    | st.builds(tuple, st.lists(inner, max_size=3)) | st.builds(DictSub, st.dictionaries(TEXT, inner, max_size=3))
    | st.builds(OtherItems, st.dictionaries(TEXT, inner, max_size=3)),
    max_leaves=30,
)
PLAIN = st.recursive(
    st.none() | st.booleans() | st.integers(-(2**53 - 1), 2**53 - 1)
    | st.text(st.characters(codec="utf-8", max_codepoint=0xFFFF), max_size=12),
    lambda inner: st.lists(inner, max_size=5)
    | st.dictionaries(st.text(st.characters(codec="utf-8", max_codepoint=0xFFFF), max_size=6), inner, max_size=5),
    max_leaves=40,
)


@S
@given(VALUES)
def test_differential_any_value(obj: Any) -> None:
    same(obj)


@S
@given(PLAIN)
def test_differential_plain_values_take_the_fast_path(obj: Any) -> None:
    assert canonical._plain(obj, 0)  # so the fast path is exercised, not just the fallback
    assert jcs_bytes(obj) == rfc8785.dumps(obj)


def test_differential_with_the_pure_python_encoder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(json.encoder, "c_make_encoder", None)
    monkeypatch.setattr(json.encoder, "encode_basestring", json.encoder.py_encode_basestring)

    @settings(max_examples=500, deadline=None, derandomize=True)
    @given(PLAIN)
    def check(obj: Any) -> None:
        assert jcs_bytes(obj) == rfc8785.dumps(obj)

    check()
