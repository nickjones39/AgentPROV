"""Array-index tokens of JSON Pointers are ASCII digits only (RFC 6901; escaping audit F-04).

``str.isdigit()`` is true for superscripts (``int`` then raises ``ValueError``) and for other-script digits (``int`` accepts
them, so a second spelling of one location resolved). Every site that reads a pointer token must refuse such a token
as "not an index", cleanly. Adversarial characters are written as escapes."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from validate_support import minimal_aer

from agentprov.adapters.agentdojo.semantics import suites
from agentprov.prov import engine
from agentprov.prov.rules import nodes
from agentprov.testing import sem_v23
from agentprov.validate import linkage
from agentprov.validate.profiles import _Ctx
from agentprov.validate._provdoc import ProvView
from agentprov.views import transcript_v1
from validate_support import minimal_doc

#: SUPERSCRIPT TWO (isdigit, not decimal: int() raises), ARABIC-INDIC ONE and FULLWIDTH ONE (int() accepts both).
NON_ASCII_DIGITS = ["²", "١", "１", "1١", "١١"]

AER = minimal_aer(
    {"k": "message", "id": "m1", "ev": "O", "role": "user", "parts": [{"t": "text", "text": "a"}, {"t": "text", "text": "b"}]},
)


@pytest.mark.parametrize("digit", NON_ASCII_DIGITS)
def test_linkage_resolve_pointer_refuses_non_ascii_digits(digit: str) -> None:
    assert linkage.resolve_pointer(AER, f"m1/parts/{digit}") is None
    assert linkage.resolve_pointer(AER, f"m1/parts/{digit}/text") is None
    assert linkage.resolve_pointer(AER, "m1/parts/1") is not None  # the ASCII spelling still resolves


@pytest.mark.parametrize("digit", NON_ASCII_DIGITS)
def test_validate_profiles_present_refuses_non_ascii_digits(digit: str) -> None:
    ctx = _Ctx(ProvView.parse(minimal_doc({})), AER)
    record = AER.get("m1")
    assert ctx.present(record, "/parts/1") is True
    assert ctx.present(record, f"/parts/{digit}") is False


@pytest.mark.parametrize("digit", NON_ASCII_DIGITS)
def test_prov_engine_resolve_refuses_non_ascii_digits(digit: str) -> None:
    value = {"parts": ["a", "b"]}
    assert engine.Ctx._resolve(value, "/parts/1") == "b"
    assert engine.Ctx._resolve(value, f"/parts/{digit}") is engine._MISSING


@pytest.mark.parametrize("digit", NON_ASCII_DIGITS)
def test_aer_reader_part_refuses_non_ascii_ordinals(digit: str) -> None:
    assert AER.part("m1#1") == {"t": "text", "text": "b"}
    assert AER.part(f"m1#{digit}") is None


@pytest.mark.parametrize("digit", NON_ASCII_DIGITS)
def test_transcript_view_part_refuses_non_ascii_ordinals(digit: str) -> None:
    view = transcript_v1._Aer(AER)
    assert view.part("m1#1") == {"t": "text", "text": "b"}
    assert view.part(f"m1#{digit}") is None


@pytest.mark.parametrize("digit", NON_ASCII_DIGITS)
def test_sem_pointer_helpers_refuse_non_ascii_digits(digit: str) -> None:
    record: dict[str, Any] = {"parts": ["a", "b"]}
    assert suites._has(record, "/parts/1") is True
    assert suites._has(record, f"/parts/{digit}") is False
    assert sem_v23.pointer_resolves(record, "/parts/1") is True
    assert sem_v23.pointer_resolves(record, f"/parts/{digit}") is False


@pytest.mark.parametrize("digit", NON_ASCII_DIGITS)
def test_status_target_does_not_read_a_non_ascii_token_as_a_part(digit: str) -> None:
    ctx = SimpleNamespace(node=lambda name: "x:" + name)
    record = {"k": "message"}
    assert nodes._status_target(ctx, "m1", record, "/parts/1/text")[0] == "x:m1-1"
    node, props = nodes._status_target(ctx, "m1", record, f"/parts/{digit}/text")
    assert node == "x:m1" and props == ()
