"""Regen item 76 (CA-18, C.11.4): an ``ext.lex.flt`` integer beyond the float range is a ``CanonError``.

``decode_value`` turns an integer named in ``lex.flt`` back into a float. ``float()`` of an integer at or above
2**1024 raises ``OverflowError``, which leaked out of the decoder (and aborted derive) instead of its documented
``CanonError``.
"""

from __future__ import annotations

import pytest

from agentprov.aer.canon import CanonError, LexHints, decode_value
from agentprov.aer.types import Json

LEX = LexHints.from_dict({"flt": ["/params/temperature"]})


@pytest.mark.parametrize(
    "value",
    [{"$int": "1" + "0" * 400}, {"$int": str(-(2**1024))}, 2**1024],
    ids=["dollar-int", "dollar-int-negative", "bare-int"],
)
def test_flt_hint_on_an_integer_beyond_float_range_is_a_canon_error(value: Json) -> None:
    with pytest.raises(CanonError):
        decode_value(value, at="/params/temperature", lex=LEX)


def test_flt_hint_within_float_range_still_decodes_to_a_float() -> None:
    assert decode_value({"$int": str(2**1023)}, at="/params/temperature", lex=LEX) == float(2**1023)
    assert decode_value(1, at="/params/temperature", lex=LEX) == 1.0
    assert decode_value({"$int": "1" + "0" * 400}, at="/params/other", lex=LEX) == 10**400
