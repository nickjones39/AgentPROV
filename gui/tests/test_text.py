"""Display text helpers (S2, S3)."""

from __future__ import annotations

from agentprov_gui import text as T


def test_line_escapes_and_truncates(hostile: list[str]) -> None:
    for s in hostile:
        out = T.line(s, 20)
        assert "\n" not in out and "\r" not in out and "\x1b" not in out and "\u202e" not in out
    assert T.line("x" * 50, 10).endswith("[truncated: 40 more chars]")
    assert T.line(None) == ""


def test_clean_does_not_double_escape() -> None:
    once = T.line("a\x1bb")
    assert once == "a<U+001B>b"
    assert T.clean(once) == once  # already escaped by the CLI: unchanged
    assert T.clean("a\x1bb") == once


def test_fenced_marks_data_and_clamps() -> None:
    out = T.fenced("y" * 5000, "aer:x#m1/parts", 100000)
    assert out.startswith("<<UNTRUSTED ") and "data, not instructions" in out
    assert "[truncated:" in out  # clamped at 2,000


def test_content_classification() -> None:
    assert T.is_content_value("Hello, please send the file to the address below.")
    assert not T.is_content_value("agentdojo.rule_a@1")
    assert not T.is_content_value("sha256:" + "a" * 64)
    assert not T.is_content_value({"$": "apv:X", "type": "prov:QUALIFIED_NAME"})
    assert T.is_content_value({"$": "two words", "type": "xsd:string"})
    assert not T.is_content_value({"$": "2026-10-14T00:00:00Z", "type": "xsd:dateTime"})
    assert T.content_digest_label("abc").startswith("‹text, 3 chars, sha256:")
