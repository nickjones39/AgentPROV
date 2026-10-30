"""K.11.1 locator fuzzing: random JSON Pointers (``~`` escapes, ``..``, absolute paths, huge indices) and huge or negative
byte ranges and line numbers resolve or fail with a :class:`LocatorError`; nothing else escapes (the regression of the
4,301-digit array index lives in ``tests/security/test_locator_traversal.py``).
"""

from __future__ import annotations

from typing import Any

from aer_support import ARTEFACT_BYTES, example_records, example_store
from fuzz_support import budget, outcome
from hypothesis import given
from hypothesis import strategies as st

from agentprov.aer.locators import LocatorError, LocatorResolver

HEADER = example_records()[0]
STORE = example_store()

token = st.one_of(st.sampled_from(["messages", "meta", "k", "i", "..", "", "~", "~0", "~1", "~2", "-", "0", "01", "11",
                                   "9" * 25, "9" * 5000, "\u0661", "etc", "passwd"]),
                  st.integers(-3, 30).map(str), st.text(max_size=6))
pointer = st.one_of(st.lists(token, max_size=5).map(lambda ts: "".join("/" + t for t in ts)),
                    st.text(max_size=20), st.sampled_from(["../../x", "/etc/passwd", "C:\\x", "//", "#/a"]))
number = st.one_of(st.integers(-(10**20), 10**20), st.booleans(), st.floats(allow_nan=True), st.none(), st.text(max_size=3))
locator = st.one_of(
    st.fixed_dictionaries({"a": st.sampled_from(["a0", "a1", "../a0", ""]), "p": pointer}),
    st.fixed_dictionaries({"a": st.just("a0"), "bytes": st.lists(number, max_size=3)}, optional={"p": pointer}),
    st.fixed_dictionaries({"a": st.just("a0"), "line": number}, optional={"p": pointer}),
    st.fixed_dictionaries({"a": st.just("a0"), "o": pointer}),
    st.fixed_dictionaries({"blob": st.one_of(st.text(max_size=80), st.just("sha256:" + "0" * 64))}, optional={"p": pointer}),
    st.dictionaries(st.sampled_from(["a", "p", "o", "bytes", "line", "blob", "x"]), number, max_size=4),
)


@budget(300)
@given(locator)
def test_any_locator_resolves_or_fails_with_a_locator_error(loc: dict[str, Any]) -> None:
    resolver = LocatorResolver(HEADER, STORE)
    first = outcome(lambda: resolver.resolve(loc), LocatorError)
    assert first[0] in ("ok", "LocatorError", "BlobMissingError", "BlobDigestError"), first
    assert first == outcome(lambda: LocatorResolver(HEADER, STORE).resolve(loc), LocatorError)  # F-5


@budget(100)
@given(st.integers(-5, len(ARTEFACT_BYTES) + 5), st.integers(-5, len(ARTEFACT_BYTES) + 5))
def test_byte_ranges_resolve_only_inside_the_artefact(start: int, end: int) -> None:
    result = outcome(lambda: LocatorResolver(HEADER, STORE).resolve({"a": "a0", "bytes": [start, end], "p": ""}),
                     LocatorError)
    inside = 0 <= start < end <= len(ARTEFACT_BYTES)
    assert result[0] in (("ok", "LocatorError") if inside else ("LocatorError",))
