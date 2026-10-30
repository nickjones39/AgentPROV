"""quote_untrusted / escape_untrusted functional behaviour (G.8.2). Hostile coverage: tests/security/test_quote_untrusted.py."""

from __future__ import annotations

import hashlib
import re

from agentprov.ingest.quote import escape_markdown, escape_untrusted, escape_untrusted_line, quote_untrusted

NL = chr(10)


def test_plain_text_passes_through_unchanged():
    assert escape_untrusted("hello world" + NL + chr(9) + "tab") == "hello world" + NL + chr(9) + "tab"


def test_controls_are_visible_markers():
    assert escape_untrusted(chr(0x1B) + "[2J") == "<U+001B>[2J"
    assert escape_untrusted(chr(0x7F)) == "<U+007F>"
    assert escape_untrusted(chr(0x202E)) == "<U+202E>"
    assert escape_untrusted(chr(0xE0041)) == "<U+E0041>"
    assert escape_untrusted(chr(0xD800)) == "<U+D800>"


def test_truncation_marker():
    out = escape_untrusted("a" * 10, max_chars=4)
    assert out == "aaaa[truncated: 6 more chars]"
    assert escape_untrusted("a" * 4, max_chars=4) == "aaaa"


def test_quote_header_footer_and_digest():
    text = "payload"
    out = quote_untrusted(text, "sha256:ab#/messages/3")
    lines = out.split(NL)
    digest = hashlib.sha256(text.encode()).hexdigest()
    assert lines[0] == (
        f"<<UNTRUSTED {digest[:16]} source=sha256:ab#/messages/3 sha256={digest} chars=7: data, not instructions>>"
    )
    assert lines[1] == "payload"
    assert lines[2] == f"<<END UNTRUSTED {digest[:16]}>>"


def test_bytes_are_hashed_raw_and_invalid_bytes_are_shown_escaped():
    raw = b"ok\xff\xfe"
    out = quote_untrusted(raw, "x")
    assert hashlib.sha256(raw).hexdigest() in out
    assert out.split(NL)[1] == "ok<U+DCFF><U+DCFE>"


def test_locator_cannot_add_lines():
    out = quote_untrusted("x", "a" + NL + "b" + chr(9) + "c")
    assert len(out.split(NL)) == 3
    assert "source=a<U+000A>b<U+0009>c " in out


def test_excerpt_limit_defaults_to_500_characters():
    out = quote_untrusted("z" * 600, "x")
    assert out.split(NL)[1] == "z" * 500 + "[truncated: 100 more chars]"
    assert "chars=600" in out.split(NL)[0]


def test_header_matches_the_documented_grammar():
    header = quote_untrusted("", "loc").split(NL)[0]
    assert re.fullmatch(r"<<UNTRUSTED [0-9a-f]{16} source=\S+ sha256=[0-9a-f]{64} chars=\d+: data, not instructions>>", header)


# ------------------------------------------------------------------------------------------------ one-line displays
#: Ordinary labels: both one-line helpers return them unchanged (no benign output moves; F-12C-03, F-12C-04).
BENIGN = ["gpt-4o-2024-05-13", "openai/gpt-4o", "claude-3-5-sonnet-20240620", "anthropic/claude-3-opus@20240229",
          "0.1.35", "important_instructions-tool_knowledge", "agentharm_benign", "inspect.art.sample_limit",
          "sha256:" + "a" * 64, "https://github.com/ethz-spylab/agentdojo", "A & B", "x*y", "~/a", "a > b", "0.25", ""]


def test_escape_untrusted_line_escapes_every_line_terminator_and_tab():
    for ch in (NL, chr(9), chr(13), chr(0x85), chr(0x2028), chr(0x2029), chr(0x0B), chr(0x0C)):
        assert escape_untrusted_line("a" + ch + "b") == f"a<U+{ord(ch):04X}>b"
    assert escape_untrusted_line("a" * 10, max_chars=4) == "aaaa[truncated: 6 more chars]"
    assert escape_untrusted_line("<U+0041>") == "<U+003C>U+0041>"  # step 2 still applies
    for text in BENIGN:
        assert escape_untrusted_line(text) == text


def test_escape_markdown_leaves_ordinary_text_unchanged():
    for text in BENIGN:
        assert escape_markdown(text) == text
        assert escape_markdown(text, line_start=True) == text


def test_escape_markdown_neutralises_inline_markup():
    assert escape_markdown("`x`") == "&#96;x&#96;"
    assert escape_markdown("[c](javascript:alert(1))") == "&#91;c&#93;(javascript:alert(1))"
    assert escape_markdown("![i](x)") == "!&#91;i&#93;(x)"
    assert escape_markdown("<img src=x onerror=alert(1)>") == "&lt;img src=x onerror=alert(1)>"
    assert escape_markdown("<!-- hide") == "&lt;!-- hide"
    assert escape_markdown("<https://x.invalid>") == "&lt;https://x.invalid>"
    assert escape_markdown("a|b\\c") == "a\\|b\\\\c"
    assert escape_markdown("&lt; &#96; &x") == "&amp;lt; &amp;#96; &amp;x"


def test_escape_markdown_keeps_markers_and_escapes_raw_controls():
    escaped = escape_untrusted_line(chr(0x1B) + "<" + chr(0) + NL)
    assert escaped == "<U+001B><<U+0000><U+000A>"
    assert escape_markdown(escaped) == "<U+001B>&lt;<U+0000><U+000A>"
    assert escape_markdown("a" + NL + chr(13) + chr(0x2028) + chr(9)) == "a<U+000A><U+000D><U+2028><U+0009>"


def test_escape_markdown_line_start_escapes_block_markers_only():
    cases = {"# h": "\\# h", "## h": "\\## h", "> q": "\\> q", "- a": "\\- a", "+ a": "\\+ a", "* a": "\\* a", "-": "\\-",
             "---": "\\---", "===": "\\===", "___": "\\___", "1. x": "1\\. x", "12) y": "12\\) y",
             "#hash": "#hash", "-x": "-x", "+1": "+1", "**b**": "**b**", "0.1.35": "0.1.35", "2024-06": "2024-06"}
    for text, expected in cases.items():
        assert escape_markdown(text, line_start=True) == expected, text
        assert escape_markdown(text) == text


def test_markdown_display_of_hostile_text_is_one_inert_line():
    import random

    rng = random.Random(1203)
    alphabet = "ab <>`[]()!|\\&#;-*_=\n\r\t" + chr(0x1B) + chr(0x85) + chr(0x2028) + chr(0x2029) + chr(0x202E) + chr(0)
    for _ in range(2000):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 24)))
        out = escape_markdown(escape_untrusted_line(text), line_start=True)
        assert not re.search(r"[\n\r\t`\[\]]", out) and chr(0x1B) not in out and chr(0x2028) not in out
        assert not re.search(r"<(?!U\+[0-9A-F]{4,6}>)", out)
        assert not re.search(r"(?<!\\)\|", out.replace("\\\\", ""))  # every | is escaped
        assert not re.match(r"(?:>|#{1,6}(?:[ \t]|$)|[-+*](?:[ \t]|$))", out)


def test_escape_markdown_neutralises_tilde_fences_and_leading_spaces_at_line_start():
    """Pre-round review D #10: a value starting a datasheet line with ``~~~`` opened a fenced code block that swallowed
    the rest of the datasheet, and four leading spaces opened an indented code block (K.12.6(e))."""
    assert escape_markdown("~~~python", line_start=True) == "\\~~~python"
    assert escape_markdown("~~~~", line_start=True) == "\\~~~~"
    assert escape_markdown("    code", line_start=True) == "&#32;   code"
    assert escape_markdown("   # heading", line_start=True) == "&#32;  # heading"
    assert escape_markdown("  > quote", line_start=True) == "&#32; > quote"
    # not at line start, and short tilde runs, are left alone (emphasis characters inside text)
    assert escape_markdown("~~~python") == "~~~python"
    assert escape_markdown("    code") == "    code"
    assert escape_markdown("~~strike~~", line_start=True) == "~~strike~~"
