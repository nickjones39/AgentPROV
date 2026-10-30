"""Display text for untrusted strings (design §11 S2/S3; G.8.2). No Qt here.

Every data-derived string the GUI shows passes one of these functions before it reaches a widget:

* :func:`line` for one-line cells, tree nodes, chips, window titles and tooltips: ``escape_untrusted_line`` of the core,
  truncated;
* :func:`clean` for strings the CLI already escaped (its log, progress and summary JSON): unchanged when no code point
  would be escaped, else :func:`line`. ``escape_untrusted`` is not idempotent (it re-escapes the ``<`` of a ``<U+…>``
  marker), so the CLI's own markers must not be escaped twice (S3);
* :func:`fenced` for shown content: ``quote_untrusted`` with the record's locator and the viewer limit (S2).
* :func:`fenced_display` for a whole shown document: fenced, re-formatted for display, with no line too long to lay out.

The results are display-only: never hashed, stored or compared (G.8.2).
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from functools import lru_cache
from typing import Final

from agentprov.ingest.quote import (
    ESCAPED_CATEGORIES,
    EXTRA_ESCAPED,
    escape_untrusted,
    escape_untrusted_line,
    quote_untrusted,
)
from agentprov.render import style

__all__ = [
    "CELL_CHARS",
    "CONTENT_CHARS_DEFAULT",
    "CONTENT_CHARS_MAX",
    "clean",
    "content_digest_label",
    "display_lines",
    "fenced",
    "fenced_display",
    "fenced_full",
    "is_content_value",
    "is_iri",
    "line",
    "multiline",
    "plain_value",
    "window_title",
]

#: Characters of one table cell or tree label before the visible truncation marker.
CELL_CHARS: Final = 200
#: The content display limit (design §6.1 Raw, §6.6 Viewer): default 500, maximum 2,000.
CONTENT_CHARS_DEFAULT: Final = 500
CONTENT_CHARS_MAX: Final = 2000
#: Characters of one displayed line of a whole document before it is broken: a NoWrap plain-text pane lays out a
#: multi-megabyte line on the UI thread for seconds (GR-22).
DISPLAY_LINE_CHARS: Final = 4000


def _would_escape(text: str) -> bool:
    for ch in text:
        if ch in "\n\t" or unicodedata.category(ch) in ESCAPED_CATEGORIES or ord(ch) in EXTRA_ESCAPED:
            return True
    return False


@lru_cache(maxsize=65536)
def _line_cached(text: str, max_chars: int) -> str:
    return escape_untrusted_line(text, max_chars=max_chars)


def line(value: object, max_chars: int = CELL_CHARS) -> str:
    """One display line of a data-derived value (S3). ``None`` is an empty string, never the text ``None``."""
    if value is None:
        return ""
    text = value if isinstance(value, str) else str(value)
    if len(text) > 4096:  # do not keep huge strings in the cache
        return escape_untrusted_line(text, max_chars=max_chars)
    return _line_cached(text, max_chars)


def window_title(text: str) -> str:
    """A display string for a window title, with Qt's window-modified placeholder ``[*]`` doubled so it shows literally
    (GR-40). Applied after :func:`line`; ``[[*]]`` would not do, Qt shows it as ``[]``."""
    return text.replace("[*]", "[*][*]")


def clean(value: object, max_chars: int = CELL_CHARS) -> str:
    """A string the CLI already escaped: unchanged unless a code point would be escaped (S3), then :func:`line`."""
    if value is None:
        return ""
    text = value if isinstance(value, str) else str(value)
    if len(text) <= max_chars and not _would_escape(text):
        return text
    return line(text, max_chars)


def multiline(value: str, max_chars: int) -> str:
    """Escaped text that may keep LF and TAB (a read-only plain-text pane), truncated visibly."""
    return escape_untrusted(value, max_chars=max_chars)


def fenced(value: str | bytes, locator: str, max_chars: int = CONTENT_CHARS_DEFAULT) -> str:
    """Shown content (S2): fenced as data with its locator and sha256, escaped and truncated."""
    return quote_untrusted(value, locator, max_chars=max(1, min(max_chars, CONTENT_CHARS_MAX)))


def fenced_full(value: str, locator: str) -> str:
    """A whole document fenced as data, untruncated (the PROV-JSON tab is where the complete text is read; §7.2)."""
    return quote_untrusted(value, locator, max_chars=max(len(value), 1))


def _break_long_lines(text: str, width: int = DISPLAY_LINE_CHARS) -> str:
    out: list[str] = []
    for part in text.split("\n"):
        out.extend(part[i:i + width] for i in range(0, max(len(part), 1), width))
    return "\n".join(out)


def display_lines(text: str) -> str:
    """Escaped display text with every line longer than :data:`DISPLAY_LINE_CHARS` broken, so a pane lays it out in
    milliseconds (a long escaped line, such as a run of NULs, takes the UI thread minutes to wrap; GR-23)."""
    return _break_long_lines(text)


def fenced_display(raw: str, doc: object, locator: str) -> str:
    """A whole JSON document for reading (GR-22): a parsed object re-indented with sorted keys and fenced as data, the
    locator stating that it is a display copy, what changed (re-indented, keys sorted, numbers normalised; GR-58) and
    the sha256 and length of the file text; any other ``doc`` is the file text itself. Lines longer than :data:`DISPLAY_LINE_CHARS` are broken, so a JCS file (one line) or a huge
    string value cannot stall the pane's layout."""
    if not isinstance(doc, dict):
        return _break_long_lines(fenced_full(raw, locator))
    digest = hashlib.sha256(raw.encode("utf-8", "surrogatepass")).hexdigest()
    body = json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False)
    note = (f"{locator} [re-formatted for display (re-indented, keys sorted, numbers normalised); "
            f"file sha256={digest} chars={len(raw)}]")
    return _break_long_lines(fenced_full(body, note))


def content_digest_label(value: str) -> str:
    """The hidden-content placeholder ``‹text, n chars, sha256:ab12…›`` (design §7.2)."""
    digest = hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest()
    return f"‹text, {len(value):,} chars, sha256:{digest[:8]}…›"


#: A string that reads as an identifier, locator, digest or rule id rather than free text: shown without Show content.
_TOKEN_RE: Final = re.compile(r"[A-Za-z0-9_.:@#/+\-]{1,200}")


def plain_value(value: object) -> str:
    """A scalar rendering of a PROV-JSON attribute value (QNames by name, typed literals by their lexical form, lists
    joined, objects as compact JSON). The caller escapes it."""
    if isinstance(value, dict):
        if isinstance(value.get("$"), str):
            return str(value["$"])
        return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    if isinstance(value, int | float):
        return json.dumps(value)
    if isinstance(value, list):
        return ", ".join(plain_value(v) for v in value)
    return "null" if value is None else str(value)


#: An IRI (RFC 3986 characters; no space, angle bracket or double quote): a prefix value or ``xsd:anyURI`` literal shown without Show content.
_IRI_RE: Final = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]{0,31}:[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]{0,500}")
_NUMBER_RE: Final = re.compile(
    r"[+-]?(?:[0-9]{1,40}(?:\.[0-9]{0,40})?|\.[0-9]{1,40})(?:[eE][+-]?[0-9]{1,4})?|[+-]?(?:INF|inf)|NaN|nan")
_TZ: Final = r"(?:Z|[+-][0-9]{2}:[0-9]{2})?"
_DATE_RE: Final = re.compile(r"-?[0-9]{4,9}-[0-9]{2}-[0-9]{2}" + _TZ)
_DATETIME_RE: Final = re.compile(r"-?[0-9]{4,9}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,12})?" + _TZ)
#: The lexical grammar a typed literal must match to read as metadata (GR-55): QNames by ``render.style``'s QName
#: grammar (the one ``prov:type`` is shown by), IRIs, the XSD date, number and boolean forms. A literal of any other
#: type is metadata only when it is a token; one that does not match its grammar is content.
_LITERAL_RES: Final[dict[str, re.Pattern[str]]] = {
    "prov:QUALIFIED_NAME": style._QNAME_RE,
    "xsd:QName": style._QNAME_RE,
    "xsd:anyURI": _IRI_RE,
    "xsd:dateTime": _DATETIME_RE,
    "xsd:dateTimeStamp": _DATETIME_RE,
    "xsd:date": _DATE_RE,
    "xsd:boolean": re.compile(r"true|false|1|0"),
    **dict.fromkeys(
        ("xsd:double", "xsd:float", "xsd:decimal", "xsd:integer", "xsd:int", "xsd:long", "xsd:short", "xsd:byte",
         "xsd:nonNegativeInteger", "xsd:positiveInteger", "xsd:nonPositiveInteger", "xsd:negativeInteger",
         "xsd:unsignedLong", "xsd:unsignedInt", "xsd:unsignedShort", "xsd:unsignedByte"),
        _NUMBER_RE,
    ),
}


def is_iri(value: object) -> bool:
    """Whether ``value`` is a string that reads as an IRI (a prefix value shown without Show content; GR-55)."""
    return isinstance(value, str) and _IRI_RE.fullmatch(value) is not None


def is_content_value(value: object) -> bool:
    """Whether a value is data content (free text), hidden until Show content (S2): a plain or ``xsd:string`` /
    language-tagged string that does not read as an identifier, locator or digest, or a typed literal whose lexical
    form does not match the grammar of its type (GR-55). Numbers, booleans and well-formed QNames, IRIs, dates and
    numeric literals are metadata."""
    if isinstance(value, str):
        return _TOKEN_RE.fullmatch(value) is None
    if isinstance(value, dict):
        lexical = value.get("$")
        kind = value.get("type")
        if not isinstance(lexical, str):  # shown as compact JSON (plain_value): a token or content
            return _TOKEN_RE.fullmatch(plain_value(value)) is None
        if kind in (None, "xsd:string") or "lang" in value or not isinstance(kind, str):
            return _TOKEN_RE.fullmatch(lexical) is None
        return _LITERAL_RES.get(kind, _TOKEN_RE).fullmatch(lexical) is None
    if isinstance(value, list):
        return any(is_content_value(v) for v in value)
    return False
