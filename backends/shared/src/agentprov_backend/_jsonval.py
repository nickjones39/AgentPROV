"""JSON values for ``capture/0.1`` event payloads (C.11.2, C.11.3).

Benchmark content (tool arguments, tool returns, injection payloads, environment dumps) is arbitrary Python data. Before
it enters an event it is converted to plain JSON (``to_jsonable``) and then to the AER/capture value conventions
(``encode_value``): integers outside +-(2^53-1) become ``{"$int": "<decimal>"}``, non-finite floats and ``-0.0`` become
``{"$float": ...}``, strings that are not valid Unicode scalar sequences become ``{"$utf16": <base64 of UTF-16BE>}``,
and objects with a member name beginning with ``$`` are wrapped as ``{"$lit": {...}}`` (their members encoded).

Stdlib only; ``to_jsonable`` uses pydantic when the value is a pydantic model (pydantic is always present where
benchmark values exist, because the benchmark and the SDK depend on it).
"""

from __future__ import annotations

import base64
import datetime as _dt
import math
from collections.abc import Mapping
from typing import Any

__all__ = ["MAX_SAFE_INT", "encode_value", "escape_text", "to_jsonable"]

MAX_SAFE_INT = 2**53 - 1


def _valid_unicode(s: str) -> bool:
    try:
        s.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _encode_str(s: str) -> Any:
    if _valid_unicode(s):
        return s
    return {"$utf16": base64.b64encode(s.encode("utf-16-be", "surrogatepass")).decode("ascii")}


def encode_value(value: Any) -> Any:
    """Encode a plain JSON value (dict/list/str/int/float/bool/None) under C.11.3. Tuples count as lists."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        if -MAX_SAFE_INT <= value <= MAX_SAFE_INT:
            return value
        return {"$int": str(value)}
    if isinstance(value, float):
        if math.isnan(value):
            return {"$float": "NaN"}
        if math.isinf(value):
            return {"$float": "Infinity" if value > 0 else "-Infinity"}
        if value == 0.0 and math.copysign(1.0, value) < 0:
            return {"$float": "-0"}
        if value.is_integer() and abs(value) > MAX_SAFE_INT and abs(value) < 1e21:
            return {"$int": str(int(value))}
        return value
    if isinstance(value, str):
        return _encode_str(value)
    if isinstance(value, (list, tuple)):
        return [encode_value(v) for v in value]
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        reserved = False
        for k, v in value.items():
            if not isinstance(k, str):
                k = str(k)
            if not _valid_unicode(k):
                # a member name cannot carry the $utf16 form; keep it visible and lossless as an escaped label
                k = k.encode("utf-16-be", "surrogatepass").hex()
            if k.startswith("$"):
                reserved = True
            out[k] = encode_value(v)
        return {"$lit": out} if reserved else out
    raise TypeError(f"not a JSON value: {type(value).__name__}")


def to_jsonable(value: Any) -> Any:
    """Plain JSON data for a benchmark value: pydantic models are dumped in JSON mode, dates become ISO strings, sets
    become sorted lists; anything else unknown becomes its ``repr`` (never silently dropped)."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        return {str(k) if not isinstance(k, str) else k: to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, (set, frozenset)):
        items = [to_jsonable(v) for v in value]
        try:
            return sorted(items)
        except TypeError:
            return sorted(items, key=repr)
    if isinstance(value, (_dt.datetime, _dt.date, _dt.time)):
        return value.isoformat()
    if isinstance(value, bytes):
        return {"$bytes_b64": base64.b64encode(value).decode("ascii")}
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        try:
            return to_jsonable(dump(mode="json"))
        except Exception:  # noqa: BLE001 - a model that cannot dump in JSON mode is recorded by repr
            pass
    try:
        from pydantic_core import to_jsonable_python

        return to_jsonable(to_jsonable_python(value))
    except Exception:  # noqa: BLE001
        return repr(value)


_CONTROL = {i for i in range(0x20)} | {0x7F} | set(range(0x80, 0xA0)) | {0x2028, 0x2029, 0xFEFF, 0x061C}
#: Ranges written as escapes besides ``_CONTROL`` and the surrogates: zero-width and directional marks (U+200B-200F),
#: embeddings and overrides (U+202A-202E), word joiner and invisible operators (U+2060-2064), directional isolates
#: (U+2066-2069), and the Unicode tag characters (U+E0000-E007F) that can smuggle ASCII text invisibly.
_RANGES = ((0x200B, 0x200F), (0x202A, 0x202E), (0x2060, 0x2064), (0x2066, 0x2069), (0xE0000, 0xE007F))


def _escaped(cp: int) -> bool:
    return cp in _CONTROL or 0xD800 <= cp <= 0xDFFF or any(lo <= cp <= hi for lo, hi in _RANGES)


def escape_text(text: str, *, limit: int = 4000) -> str:
    """An exception message made safe to show: control, separator, BOM, bidirectional and tag code points become
    ``\\uXXXX`` escapes (``\\UXXXXXXXX`` above U+FFFF), lone surrogates likewise, and the text is truncated to ``limit``
    characters (marked with an ellipsis).

    The form is unambiguous: a backslash that is followed by ``u`` or ``U`` in the input is itself written ``\\u005c``,
    so every ``\\u`` or ``\\U`` in the output starts an escape (a literal ``\\u202e`` in the text cannot pass for U+202E).
    Other backslashes are kept."""
    out = []
    for i, ch in enumerate(text):
        cp = ord(ch)
        if _escaped(cp):
            out.append(f"\\u{cp:04x}" if cp <= 0xFFFF else f"\\U{cp:08x}")
        elif ch == "\\" and text[i + 1 : i + 2] in ("u", "U"):
            out.append("\\u005c")
        else:
            out.append(ch)
    s = "".join(out)
    if len(s) > limit:
        s = s[:limit] + "[…]"
    return s
