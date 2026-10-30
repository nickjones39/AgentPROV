"""Carved blobs (D-218; C.11.5): the exact bytes of one string value of a stored artefact, as their own raw object.

A string longer than an AER line may hold inline (C.2.1(6): 1 MiB of UTF-8) is stored once in the raw store and
referenced by ``$blob``. When the string comes from inside a stored artefact (a JSON document, a JSONL line), its bytes
are **carved**: re-derived from the artefact, never invented or re-encoded beyond the declared transform. The object's
origin (``raw.origins.Origin.carved``) names the source object's digest, the key locator of the value in it and the
transform, so ``verify`` and ``recompute`` can carve it again and compare digests.

Transforms (closed set):

* ``utf8``: the UTF-8 encoding of the string value. A value with a lone surrogate (an escaped ``\\ud800`` the strict
  loader admits with a finding) has no UTF-8 encoding and is refused.
* ``base64``: the decoded payload of a ``data:`` URI whose parameters end in ``;base64`` (RFC 2397); the media type
  before the parameters is returned with the bytes. Anything else is refused.

Locators are key locators (C.9.1) without an artefact id: ``p`` (RFC 6901 pointer), optionally with ``line`` (a 0-based
LF-separated line of the artefact, parsed alone) or ``bytes`` (``[start, end)``, parsed alone). Parsing goes through
the strict, bounded loader of :mod:`agentprov.ingest.loaders` (invariant 3: untrusted bytes). Pure; no I/O.

A region of at least :data:`SPAN_MIN_BYTES` is first read by :func:`agentprov.ingest.jsonspan.string_value_at` (D-222):
the string is found by its byte span and proven by the strict loader without building the region's other values, so a
large string is not held twice (a 43.6 MB tool result in a 46.9 MB trace exceeded the 2 GiB map cap). When that path
cannot prove the value it returns nothing and the region is parsed whole as before: the carved bytes, and every error,
are the same either way.
"""

from __future__ import annotations

import base64
import binascii
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from agentprov.errors import AgentProvError, IngestError
from agentprov.ingest.jsonspan import string_value_at
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads
from agentprov.raw.origins import CARVE_TRANSFORMS

__all__ = ["SPAN_MIN_BYTES", "TRANSFORMS", "CarveError", "Carved", "Carver", "carve", "carve_value"]

#: The closed set of carving transforms (D-218), declared with the ``carved`` origin kind.
TRANSFORMS: Final = CARVE_TRANSFORMS
_LOC_KEYS: Final = frozenset({"p", "line", "bytes"})
#: D-222: regions this large are first read by their string's byte span (module docstring); smaller ones are parsed
#: whole (and, in a :class:`Carver`, once for every carve of the region).
SPAN_MIN_BYTES: Final = 8 << 20
_DATA_URI: Final = re.compile(r"data:(?P<media>[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+)?(?P<params>(;[^,;]*)*);base64,",
                              re.ASCII)


class CarveError(AgentProvError):
    """The value cannot be carved: the locator does not resolve to a string, or the transform does not apply."""

    code = "raw.carve.invalid"
    exit_code = 1


@dataclass(frozen=True, slots=True)
class Carved:
    """The carved bytes and, for ``base64``, the ``data:`` URI's media type (``None`` otherwise)."""

    data: bytes
    media: str | None = None


def _unescape(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def _pointer_get(document: Any, pointer: str) -> Any:
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise CarveError("not a JSON Pointer")
    current = document
    for raw in pointer[1:].split("/"):
        token = _unescape(raw)
        if isinstance(current, list):
            if not (token.isascii() and token.isdigit()) or (len(token) > 1 and token[0] == "0") \
                    or len(token) > len(str(len(current))) or int(token) >= len(current):
                raise CarveError("the pointer does not resolve")
            current = current[int(token)]
        elif isinstance(current, dict) and token in current:
            current = current[token]
        else:
            raise CarveError("the pointer does not resolve")
    return current


def _document(data: bytes, loc: Mapping[str, Any], limits: IngestLimits) -> Any:
    try:
        if "line" in loc:
            line = loc["line"]
            if not isinstance(line, int) or isinstance(line, bool) or line < 0:
                raise CarveError("malformed line number")
            lines = data.split(b"\n")  # LF only, as the AER locator resolver (C.9.2)
            if line >= len(lines) or (line == len(lines) - 1 and lines[line] == b""):
                raise CarveError("the line is outside the artefact")
            return strict_json_loads(lines[line], limits, record=True)
        if "bytes" in loc:
            span = loc["bytes"]
            if not (isinstance(span, list | tuple) and len(span) == 2
                    and all(isinstance(n, int) and not isinstance(n, bool) for n in span)
                    and 0 <= span[0] < span[1] <= len(data)):
                raise CarveError("malformed byte range")
            return strict_json_loads(data[span[0] : span[1]], limits)
        return strict_json_loads(data, limits)
    except IngestError as exc:
        raise CarveError(f"the artefact does not parse ({exc.code})") from None


def carve_value(value: object, transform: str) -> Carved:
    """The bytes of a string ``value`` under ``transform`` (module docstring)."""
    if transform not in TRANSFORMS:
        raise CarveError(f"unknown carving transform {transform!r}")
    if not isinstance(value, str):
        raise CarveError("the located value is not a string")
    if transform == "utf8":
        try:
            return Carved(value.encode("utf-8"))
        except UnicodeEncodeError:
            raise CarveError("the string has a lone surrogate and no UTF-8 encoding") from None
    match = _DATA_URI.match(value)
    if match is None:
        raise CarveError("the string is not a base64 data: URI")
    try:
        data = base64.b64decode(value[match.end() :], validate=True)
    except (binascii.Error, ValueError):
        raise CarveError("the data: URI payload is not valid base64") from None
    return Carved(data, match.group("media"))


def _check_loc(loc: object) -> Mapping[str, Any]:
    if not isinstance(loc, Mapping) or not set(loc) <= _LOC_KEYS or not isinstance(loc.get("p", ""), str) \
            or ("line" in loc and "bytes" in loc):
        raise CarveError("a carving locator is a key locator: p, with at most one of line and bytes")
    return loc


def _region(data: bytes, loc: Mapping[str, Any]) -> tuple[memoryview, bool] | None:
    """The region of ``data`` that ``loc`` names and whether it is a record (a ``line``), as :func:`_document` reads it,
    or ``None`` for a locator :func:`_document` refuses (it then raises the refusal)."""
    view = memoryview(data)
    if "line" in loc:
        line = loc["line"]
        if not isinstance(line, int) or isinstance(line, bool) or line < 0:
            return None
        start = 0
        for _ in range(line):  # the line-th LF-separated line, as data.split(b"\n")[line]
            found = data.find(b"\n", start)
            if found < 0:
                return None
            start = found + 1
        end = data.find(b"\n", start)
        if end < 0:
            if start == len(data):  # the empty piece after a final LF is outside the artefact
                return None
            end = len(data)
        return view[start:end], True
    if "bytes" in loc:
        span = loc["bytes"]
        if not (isinstance(span, list | tuple) and len(span) == 2
                and all(isinstance(n, int) and not isinstance(n, bool) for n in span)
                and 0 <= span[0] < span[1] <= len(data)):
            return None
        return view[span[0] : span[1]], False
    return view, False


def _by_span(data: bytes, loc: Mapping[str, Any], limits: IngestLimits, span_min: int) -> str | None:
    """D-222: the string at ``loc`` read by its byte span, for a region of at least ``span_min`` bytes; else ``None``."""
    region = _region(data, loc)
    if region is None or len(region[0]) < span_min:
        return None
    return string_value_at(region[0], str(loc.get("p", "")), limits, record=region[1])


def carve(data: bytes, loc: Mapping[str, Any], transform: str, limits: IngestLimits | None = None, *,
          span_min: int = SPAN_MIN_BYTES) -> Carved:
    """Carve the string at key locator ``loc`` of the artefact bytes ``data`` under ``transform`` (D-218)."""
    loc = _check_loc(loc)
    limits = limits or IngestLimits()
    value = _by_span(data, loc, limits, span_min)
    if value is not None:
        return carve_value(value, transform)
    document = _document(data, loc, limits)
    return carve_value(_pointer_get(document, str(loc.get("p", ""))), transform)


class Carver:
    """:func:`carve` over one artefact, parsing each region once: the whole document, one ``line`` or one ``bytes``
    range is parsed on its first carve and reused for the next (a mapper that carves several strings of one large
    document parses it once; a reader that knows its item's byte range keeps every parse to that range). A region of at
    least ``span_min`` bytes is read by each string's span instead and never kept parsed (D-222)."""

    def __init__(self, data: bytes, limits: IngestLimits | None = None, *, span_min: int = SPAN_MIN_BYTES) -> None:
        self._data, self._limits, self._span_min = data, limits or IngestLimits(), span_min
        self._documents: dict[tuple[str, Any], Any] = {}

    def carve(self, loc: Mapping[str, Any], transform: str) -> Carved:
        loc = _check_loc(loc)
        region = ("line", loc["line"]) if "line" in loc else ("bytes", tuple(loc["bytes"])) if "bytes" in loc else ("", None)
        if region not in self._documents:
            value = _by_span(self._data, loc, self._limits, self._span_min)  # D-222: a large region is never held parsed
            if value is not None:
                return carve_value(value, transform)
            self._documents[region] = _document(self._data, loc, self._limits)
        return carve_value(_pointer_get(self._documents[region], str(loc.get("p", ""))), transform)
