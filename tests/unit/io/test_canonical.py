"""io.canonical: JCS bytes, digests, references and the base32 spelling (C.4.1, C.11.1)."""

from __future__ import annotations

import hashlib

import pytest

from agentprov.io.canonical import (
    base32_lower_nopad,
    is_sha256_hex,
    is_sha256_ref,
    jcs_bytes,
    sha256_hex,
    sha256_of_ref,
    sha256_ref,
)


def test_jcs_sorts_members_by_utf16_code_units_and_has_no_whitespace() -> None:
    # U+FF5D (BMP) sorts after U+1F600 (surrogate pair D83D) in UTF-16 order, unlike code-point order.
    assert jcs_bytes({"｝": 1, "\U0001f600": 2, "b": 3, "a": 4}) == (
        b'{"a":4,"b":3,"\xf0\x9f\x98\x80":2,"\xef\xbd\x9d":1}'
    )


def test_jcs_number_spelling_is_fixed() -> None:
    assert jcs_bytes([1.0, 0.0, 1e21, 1e-7, 100, -0.0]) == b"[1,0,1e+21,1e-7,100,0]"


def test_jcs_is_independent_of_insertion_order() -> None:
    assert jcs_bytes({"b": 1, "a": 2}) == jcs_bytes({"a": 2, "b": 1})


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), 2**53, "\ud800"])
def test_jcs_rejects_unrepresentable_values(bad: object) -> None:
    with pytest.raises(Exception, match=r"."):  # the rfc8785 error types (mapped by aer.canon)
        jcs_bytes(bad)


def test_sha256_helpers() -> None:
    data = b"abc"
    expected = hashlib.sha256(data).hexdigest()
    assert sha256_hex(data) == expected
    assert sha256_ref(data) == "sha256:" + expected
    assert sha256_of_ref("sha256:" + expected) == expected
    assert is_sha256_hex(expected) and is_sha256_ref("sha256:" + expected)


@pytest.mark.parametrize(
    "bad", ["", "sha256:", "sha256:ABC", "SHA256:" + "0" * 64, "sha256:" + "g" * 64, "0" * 63]
)
def test_malformed_references(bad: str) -> None:
    assert not is_sha256_ref(bad)
    with pytest.raises(ValueError):
        sha256_of_ref(bad)


def test_hex_predicate_rejects_upper_case_and_non_strings() -> None:
    assert not is_sha256_hex("A" * 64)
    assert not is_sha256_hex(None)
    assert not is_sha256_hex(b"0" * 64)


def test_base32_is_lower_case_unpadded_rfc4648() -> None:
    assert base32_lower_nopad(b"") == ""
    assert base32_lower_nopad(b"f") == "my"
    assert base32_lower_nopad(b"foobar") == "mzxw6ytboi"
    digest = hashlib.sha256(b"x").digest()
    out = base32_lower_nopad(digest)
    assert len(out) == 52 and set(out) <= set("abcdefghijklmnopqrstuvwxyz234567")
