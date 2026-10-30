"""Regen item 66 (CA-7, C.11.2): an integer too long to spell in decimal is a ``CanonError``, not a ``ValueError``.

``encode_value`` wraps a large integer as ``{"$int": "<decimal>"}``. CPython refuses ``str()`` of an integer with
more than 4300 decimal digits; the strict YAML loader accepts such a value through a ``0x``/``0b`` literal
(power-of-two bases are exempt from the parse-time limit), so the bare ``ValueError`` leaked out of the encoder.
"""

from __future__ import annotations

import pytest

from agentprov.aer.canon import CanonError, LexHints, encode_value
from agentprov.ingest import yamlsafe


@pytest.mark.parametrize("doc", [b"a: 0x" + b"f" * 4000, b"a: 0b" + b"1" * 16000], ids=["hex", "binary"])
def test_yaml_long_radix_int_is_a_canon_error(doc: bytes) -> None:
    value = yamlsafe.safe_load(doc)
    assert isinstance(value["a"], int) and value["a"].bit_length() > 14_000
    with pytest.raises(CanonError):
        encode_value(value, at="/ext/x", lex=LexHints())


@pytest.mark.parametrize("value", [1 << 16000, -(1 << 16000)], ids=["positive", "negative"])
def test_huge_int_is_a_canon_error(value: int) -> None:
    with pytest.raises(CanonError):
        encode_value(value, at="/x", lex=LexHints())


def test_large_int_within_the_digit_limit_is_still_wrapped() -> None:
    value = 10**4000
    assert encode_value(value, at="/x", lex=LexHints()) == {"$int": str(value)}
    assert encode_value(-(2**53), at="/x", lex=LexHints()) == {"$int": str(-(2**53))}
    assert encode_value(2**53 - 1, at="/x", lex=LexHints()) == 2**53 - 1
