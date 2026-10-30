"""One string value of a JSON document, found without building the document (D-222).

A carved blob (D-218) is the UTF-8 of one string of a stored artefact, re-derived from the artefact's bytes. Parsing the
whole region that holds it (a JSON document, a JSONL line, a reader's ``bytes`` range) builds every sibling value and a
second copy of the string while the reader's own parsed copy is still alive: a 43.6 MB tool result inside a 46.9 MB
trace stopped its map job at the 2 GiB cap. :func:`string_value_at` returns the string at a JSON Pointer while holding
the region's bytes, one small envelope and the string itself.

How the strict rules stay identical (the argument of :mod:`agentprov.ingest.jsonstream`, for one string instead of an
array's elements):

* a byte-level walk (regular expressions; strings are matched whole, so brackets, commas, colons and quotes inside
  strings never count) follows the pointer's member names and array indices to a string token and returns its byte
  span. It never builds a value; member names are decoded by :func:`~agentprov.ingest.loaders.strict_json_loads`;
* the **envelope**, the region with that token replaced by a placeholder string, and the **token** alone are each parsed
  by :func:`~agentprov.ingest.loaders.strict_json_loads`. Replacing one string token by another leaves every other
  token, the nesting depth, the duplicate-key set and the UTF-8 validity outside the token unchanged (the cut is at
  ASCII quote bytes), and the token alone is checked for its own escapes and encoding. So the region is valid exactly
  when the envelope is valid and the token is a valid JSON string;
* the pointer must resolve, in the parsed envelope, to the placeholder. The placeholder carries the SHA-256 of the
  region, which the region cannot contain (it would have to hold its own digest), so it resolves there only if the
  walk found the value the pointer names. Then the region's value at the pointer is the token's string.

Fail closed: anything this path cannot prove (a malformed region, a pointer that does not resolve, a value that is not
a string, a parse error, a size over the cap) returns ``None``, and the caller parses the region whole as before, so
every error is the one it always was. Pure; stdlib only; no I/O.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Final

from agentprov.errors import IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

__all__ = ["string_value_at"]

_STRING: Final = re.compile(rb'"[^"\\]*+(?:\\.[^"\\]*+)*+"', re.DOTALL)
_WS: Final = re.compile(rb"[ \t\n\r]*+")
#: A scalar other than a string (a number, ``true``, ``false``, ``null``): its bytes up to the next structural byte.
_SCALAR: Final = re.compile(rb'[^ \t\n\r,:\[\]{}"]++')
#: Inside a container being skipped: up to the next bracket or lone quote (strings are matched whole).
_DEEP: Final = re.compile(rb'(?:[^"\[\]{}]++|"[^"\\]*+(?:\\.[^"\\]*+)*+")*+([\[\]{}"]|\Z)', re.DOTALL)
_OPEN: Final = frozenset(b"[{")


def _tokens(pointer: str) -> list[str] | None:
    """The reference tokens of ``pointer``, unescaped as :mod:`agentprov.raw.carve` does; ``None`` if not a pointer."""
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        return None
    return [raw.replace("~1", "/").replace("~0", "~") for raw in pointer[1:].split("/")]


def _at(view: memoryview, pos: int) -> int:
    return view[pos] if pos < len(view) else -1


def _ws(view: memoryview, pos: int) -> int:
    match = _WS.match(view, pos)
    return match.end() if match else pos


def _skip(view: memoryview, pos: int, budget: int) -> int | None:
    """The end of the value starting at ``pos``, or ``None``; containers may nest ``budget`` more levels."""
    first = _at(view, pos)
    if first == 0x22:  # '"'
        match = _STRING.match(view, pos)
        return match.end() if match else None
    if first in _OPEN:
        depth = 0
        while True:
            match = _DEEP.match(view, pos)
            if match is None:
                return None
            byte = match.group(1)
            if byte == b"" or byte == b'"':  # the end of the region, or a string that never closes
                return None
            pos = match.end()
            if byte in (b"[", b"{"):
                depth += 1
                if depth > budget:
                    return None
            else:
                depth -= 1
                if depth == 0:
                    return pos
    match = _SCALAR.match(view, pos)
    return match.end() if match else None


def _locate(view: memoryview, tokens: list[str], limits: IngestLimits) -> tuple[int, int] | None:
    """The byte span of the string token the pointer names, found by the walk (module docstring), or ``None``."""
    pos, depth = _ws(view, 0), 0
    for token in tokens:
        opener = _at(view, pos)
        if opener not in _OPEN:
            return None
        depth += 1
        if depth > limits.max_json_depth:
            return None
        pos = _ws(view, pos + 1)
        if opener == 0x7B:  # '{': the first member named ``token``
            while True:
                key = _STRING.match(view, pos)
                if key is None:
                    return None
                try:
                    name = strict_json_loads(key.group(), limits)
                except IngestError:
                    return None
                pos = _ws(view, key.end())
                if _at(view, pos) != 0x3A:  # ':'
                    return None
                pos = _ws(view, pos + 1)
                if name == token:
                    break
                end = _skip(view, pos, limits.max_json_depth - depth)
                if end is None:
                    return None
                pos = _ws(view, end)
                if _at(view, pos) != 0x2C:  # ',': '}' means the member is absent
                    return None
                pos = _ws(view, pos + 1)
        else:  # '[': the element at index ``token`` (canonical decimal, as raw.carve requires)
            if not (token.isascii() and token.isdigit()) or (len(token) > 1 and token[0] == "0"):
                return None
            for _ in range(int(token)):
                end = _skip(view, pos, limits.max_json_depth - depth)
                if end is None:
                    return None
                pos = _ws(view, end)
                if _at(view, pos) != 0x2C:
                    return None
                pos = _ws(view, pos + 1)
    match = _STRING.match(view, pos)
    return (pos, match.end()) if match else None


def _resolve(document: Any, tokens: list[str]) -> Any:
    current = document
    for token in tokens:
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isascii() and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            return None
    return current


def string_value_at(data: bytes | bytearray | memoryview, pointer: str, limits: IngestLimits | None = None, *,
                    record: bool = False) -> str | None:
    """The string at ``pointer`` of the JSON document ``data``, proven by the strict loader without parsing the document
    whole, or ``None`` when this path cannot prove it (the caller then parses it whole; module docstring). ``record``
    applies the record cap (``max_jsonl_line_bytes``) as :func:`~agentprov.ingest.loaders.strict_json_loads` does."""
    limits = limits or IngestLimits()
    view = memoryview(data).cast("B")
    if len(view) > (limits.max_jsonl_line_bytes if record else limits.max_json_bytes):
        return None
    tokens = _tokens(pointer)
    span = _locate(view, tokens, limits) if tokens is not None else None
    if tokens is None or span is None:
        return None
    start, end = span
    placeholder = "agentprov.carve.span:" + hashlib.sha256(view).hexdigest()
    envelope = b"".join((view[:start], b'"' + placeholder.encode("ascii") + b'"', view[end:]))
    try:
        document = strict_json_loads(envelope, limits, record=record)
        value = strict_json_loads(bytes(view[start:end]), limits, record=record)
    except IngestError:
        return None
    if _resolve(document, tokens) != placeholder or not isinstance(value, str):
        return None
    return value
