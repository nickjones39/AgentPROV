"""Canonical lines, ``$``-escapes and lexical hints of AER (C.11.1-C.11.4, C.11.5).

* :func:`dumps_line`: ``JCS(record) + LF`` (C.11.1).
* :func:`encode_value` / :func:`decode_value`: the reserved ``$int``, ``$float``, ``$utf16`` and ``$lit`` forms
  (C.11.2, C.11.3) and the sparse ``ext.lex`` hints (C.11.4); ``$blob`` references pass through untouched.
* :func:`lex_hints`: the one writer of ``ext.lex`` (AD-02): mappers never write it by hand.
* :func:`loads_strict`: the strict single-line parser used by the reader and the validator, a thin wrapper of
  ``ingest.loaders.strict_json_loads``. It raises :class:`CanonError` carrying the ``ingest.*`` code of G.3.9.

Everything is deterministic: no dependence on dict iteration order of the *output* (JCS sorts members), locale
or time. Source member order is read from the input mapping's own insertion order, which the strict loaders
preserve.
"""

from __future__ import annotations

import base64
import binascii
import math
from collections.abc import Mapping
from typing import Final

from agentprov.aer.types import Json
from agentprov.errors import AgentProvError, IngestError
from agentprov.ingest.loaders import strict_json_loads
from agentprov.io.canonical import jcs_bytes

__all__ = [
    "I_JSON_MAX",
    "MAX_JSON_DEPTH",
    "CanonError",
    "LexHints",
    "decode_value",
    "dumps_line",
    "encode_value",
    "json_pointer",
    "lex_hints",
    "loads_strict",
    "pointer_escape",
    "pointer_unescape",
    "utf16_order",
]

#: Largest integer magnitude that is a plain JSON number (2^53 - 1, C.11.3).
I_JSON_MAX: Final = 2**53 - 1
#: Iterative nesting cap (A2, G.3.2 ``max_json_depth``).
MAX_JSON_DEPTH: Final = 256
_FLOAT_FORMS: Final = {"NaN": math.nan, "Infinity": math.inf, "-Infinity": -math.inf, "-0": -0.0}


class CanonError(AgentProvError):
    """A value cannot be canonicalised, or a canonical line cannot be parsed strictly.

    The message never contains the offending value (it may be hostile source text); ``code`` is ``aer.canon.*``
    for encoding problems and the closed ``ingest.*`` code of G.3.9 for parse problems.
    """

    code = "aer.canon.unrepresentable"


def pointer_escape(token: str) -> str:
    """RFC 6901 escaping of one reference token."""
    return token.replace("~", "~0").replace("/", "~1")


def pointer_unescape(token: str) -> str:
    """Inverse of :func:`pointer_escape`."""
    return token.replace("~1", "/").replace("~0", "~")


def json_pointer(*tokens: str | int) -> str:
    """The JSON Pointer made of ``tokens`` (each escaped); no tokens give the root ``""``."""
    return "".join("/" + pointer_escape(str(t)) for t in tokens)


def utf16_order(keys: list[str]) -> list[str]:
    """``keys`` sorted by UTF-16 code units: the member order JCS uses (RFC 8785 section 3.2.3)."""
    return sorted(keys, key=lambda s: s.encode("utf-16-be", "surrogatepass"))


# ------------------------------------------------------------------------------------------------ lex hints
class LexHints:
    """Collector of ``ext.lex`` entries: source member order (``ord``) and integral floats (``flt``).

    ``ord`` maps the pointer of an object whose source member order differs from JCS order to that source order;
    ``flt`` lists pointers of numbers that were floats with an integral value (C.11.4).
    """

    __slots__ = ("flt", "ord")

    def __init__(self) -> None:
        self.ord: dict[str, list[str]] = {}
        self.flt: set[str] = set()

    def __bool__(self) -> bool:
        return bool(self.ord or self.flt)

    def merge(self, other: LexHints) -> None:
        self.ord.update(other.ord)
        self.flt |= other.flt

    def as_dict(self) -> dict[str, Json]:
        """The ``ext.lex`` value: sparse, deterministic, ``{}`` when there is nothing to record."""
        out: dict[str, Json] = {}
        if self.ord:
            ordered: dict[str, Json] = {}
            for pointer in sorted(self.ord):
                keys: list[Json] = list(self.ord[pointer])
                ordered[pointer] = keys
            out["ord"] = ordered
        if self.flt:
            flt: list[Json] = list(sorted(self.flt))
            out["flt"] = flt
        return out

    @classmethod
    def from_dict(cls, value: Mapping[str, Json] | None) -> LexHints:
        """Parse an ``ext.lex`` value (already structurally validated)."""
        hints = cls()
        if value:
            ordered = value.get("ord")
            if isinstance(ordered, dict):
                for pointer, keys in ordered.items():
                    if isinstance(keys, list):
                        hints.ord[pointer] = [str(k) for k in keys]
            floats = value.get("flt")
            if isinstance(floats, list):
                hints.flt = {str(p) for p in floats}
        return hints


# ------------------------------------------------------------------------------------------------ encode
def encode_value(value: object, *, at: str, lex: LexHints) -> Json:
    """Encode a source value into AER ``Json`` (C.11.2-C.11.4), recording lexical hints into ``lex``.

    ``at`` is the JSON Pointer *into the record* where the encoded value will sit. Rules:

    * integers outside +-(2^53 - 1) become ``{"$int": "<decimal>"}``;
    * ``NaN``, ``+-Infinity`` and negative zero become ``{"$float": ...}``;
    * an integral float is written as the JCS integer and its pointer goes to ``lex.flt``; if its magnitude is
      2^53 or more but JCS would still spell it in full digits (below 1e21), it is ``$int``-wrapped too;
    * a string that is not a valid Unicode scalar sequence becomes ``{"$utf16": <base64 of UTF-16BE units>}``;
    * an object with any member name beginning with ``$`` becomes ``{"$lit": <object>}``;
    * an object whose member order differs from JCS order records that order in ``lex.ord``.

    ``CanonError`` is raised for anything that is not a JSON value (tuples, sets, bytes, non-string keys), and
    for a value that nests too deeply for the recursion or contains a reference cycle (a producer bug), and for an
    integer with too many digits to spell in decimal.
    """
    try:
        return _encode_value(value, at=at, lex=lex)
    except RecursionError as exc:
        raise CanonError("value nests too deeply or contains a reference cycle") from exc


def _encode_value(value: object, *, at: str, lex: LexHints) -> Json:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        if abs(value) <= I_JSON_MAX:
            return value
        try:
            return {"$int": str(value)}
        except ValueError as exc:  # beyond CPython's int-to-str digit limit (a YAML 0x/0b/0o literal gets here)
            raise CanonError("integer has too many digits") from exc
    if isinstance(value, float):
        if math.isnan(value):
            return {"$float": "NaN"}
        if math.isinf(value):
            return {"$float": "Infinity" if value > 0 else "-Infinity"}
        if value == 0.0 and math.copysign(1.0, value) < 0:
            return {"$float": "-0"}
        if value.is_integer():
            lex.flt.add(at)
            if abs(value) > I_JSON_MAX and abs(value) < 1e21:
                return {"$int": str(int(value))}
        return value
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            raw = value.encode("utf-16-be", "surrogatepass")
            return {"$utf16": base64.b64encode(raw).decode("ascii")}
        return value
    if isinstance(value, list):
        return [_encode_value(item, at=f"{at}/{i}", lex=lex) for i, item in enumerate(value)]
    if isinstance(value, dict):
        keys = list(value)
        for key in keys:
            if not isinstance(key, str):
                raise CanonError("object keys must be strings")
            try:
                key.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise CanonError("object keys must be valid Unicode scalar sequences") from exc
        wrap = any(k.startswith("$") for k in keys)
        base = f"{at}/$lit" if wrap else at
        if keys != utf16_order(keys):
            lex.ord[base] = keys
        body: dict[str, Json] = {k: _encode_value(value[k], at=f"{base}/{pointer_escape(k)}", lex=lex) for k in keys}
        return {"$lit": body} if wrap else body
    raise CanonError("value is not a JSON type")


def lex_hints(source_value: object, pointer_base: str) -> dict[str, Json]:
    """The ``ext.lex`` hints of ``source_value`` placed at ``pointer_base`` of a record (AD-02, C.11.4).

    The only writer of ``ext.lex``: a mapper assigns ``record["ext"]["lex"] = lex_hints(...)`` (merging with
    :meth:`LexHints.merge` when it encodes several values) and omits the member when the result is ``{}``.
    """
    hints = LexHints()
    encode_value(source_value, at=pointer_base, lex=hints)
    return hints.as_dict()


# ------------------------------------------------------------------------------------------------ decode
def _as_float(number: int) -> float:
    try:
        return float(number)
    except OverflowError as exc:
        raise CanonError("lex.flt names an integer outside the float range") from exc


def decode_value(value: Json, *, at: str, lex: LexHints | None) -> object:
    """Reverse :func:`encode_value`: unwrap ``$int``/``$float``/``$utf16``/``$lit``, apply ``lex`` hints.

    ``$blob`` references are returned as they are (they name raw bytes; see :mod:`agentprov.aer.locators`).
    ``CanonError`` on a malformed reserved object, on an ``ord`` hint that is not a permutation of the
    object's members, or on a ``flt`` hint naming an integer outside the float range.
    """
    if value is None or isinstance(value, bool | str):
        return value
    if isinstance(value, int):
        return _as_float(value) if lex is not None and at in lex.flt else value
    if isinstance(value, float):
        return value
    if isinstance(value, list):
        return [decode_value(item, at=f"{at}/{i}", lex=lex) for i, item in enumerate(value)]
    if isinstance(value, dict):
        dollar = [k for k in value if k.startswith("$")]
        if dollar:
            return _decode_reserved(value, dollar, at=at, lex=lex)
        return _decode_members(value, at=at, lex=lex)
    raise CanonError("value is not a JSON type")


def _decode_members(obj: Mapping[str, Json], *, at: str, lex: LexHints | None) -> dict[str, object]:
    keys = list(obj)
    if lex is not None and at in lex.ord:
        wanted = lex.ord[at]
        if sorted(wanted) != sorted(keys) or len(set(wanted)) != len(wanted):
            raise CanonError("lex.ord hint is not a permutation of the object's members")
        keys = wanted
    return {k: decode_value(obj[k], at=f"{at}/{pointer_escape(k)}", lex=lex) for k in keys}


def _decode_reserved(obj: Mapping[str, Json], dollar: list[str], *, at: str, lex: LexHints | None) -> object:
    if len(obj) != 1 and dollar != ["$blob"]:
        raise CanonError("reserved $-object has extra members")
    name = dollar[0]
    inner = obj[name]
    if name == "$lit":
        if not isinstance(inner, dict):
            raise CanonError("$lit must wrap an object")
        return _decode_members(inner, at=f"{at}/$lit", lex=lex)
    if name == "$blob":
        return dict(obj)
    if name == "$int":
        if not isinstance(inner, str):
            raise CanonError("$int must hold a decimal string")
        try:
            number = int(inner)
        except ValueError as exc:
            raise CanonError("$int must hold a decimal string") from exc
        return _as_float(number) if lex is not None and at in lex.flt else number
    if name == "$float":
        if not isinstance(inner, str) or inner not in _FLOAT_FORMS:
            raise CanonError("$float must be NaN, Infinity, -Infinity or -0")
        return _FLOAT_FORMS[inner]
    if name == "$utf16":
        if not isinstance(inner, str):
            raise CanonError("$utf16 must hold base64 text")
        try:
            return base64.b64decode(inner.encode("ascii"), validate=True).decode("utf-16-be", "surrogatepass")
        except (binascii.Error, UnicodeError) as exc:
            raise CanonError("$utf16 must hold base64 of UTF-16BE code units") from exc
    raise CanonError("unknown reserved $-object")


# ------------------------------------------------------------------------------------------------ lines
_EXIT: Final = object()


def _check_json_types(value: object) -> None:
    """Reject anything that is not a plain JSON value (tuples, bytes, sets, non-string keys) or a reference
    cycle; iterative. Shared acyclic sub-objects stay legal: only containers on the current path count."""
    stack: list[object] = [value]
    on_path: set[int] = set()
    while stack:
        item = stack.pop()
        if item is _EXIT:
            on_path.discard(id(stack.pop()))
            continue
        if item is None or isinstance(item, bool | int | float | str):
            continue
        if isinstance(item, list | dict):
            if id(item) in on_path:
                raise CanonError("value contains a reference cycle")
            on_path.add(id(item))
            stack.extend((item, _EXIT))
        if isinstance(item, list):
            stack.extend(item)
        elif isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str):
                    raise CanonError("object keys must be strings")
                stack.append(child)
        else:
            raise CanonError("value is not a JSON type")


def dumps_line(record: Mapping[str, object]) -> bytes:
    """``JCS(record)`` followed by one LF: one line of an AER file (C.2.1, C.11.1).

    Raises :class:`CanonError` for values JCS cannot represent (non-finite numbers, integers outside the I-JSON
    range, lone surrogates, non-JSON types). Producers encode source values with :func:`encode_value` first.
    """
    _check_json_types(record)
    try:
        return jcs_bytes(record) + b"\n"
    except (ValueError, RecursionError) as exc:
        raise CanonError("record cannot be canonicalised (not I-JSON representable)") from exc


def loads_strict(data: bytes) -> Json:
    """Parse one JSON line strictly: the AER-side wrapper of :func:`agentprov.ingest.loaders.strict_json_loads`.

    The ingest loader is the single strict parser of the core (bytes only, no BOM, strict UTF-8, duplicate member
    names, ``NaN``/``Infinity`` and overflowing floats rejected, depth capped, record-size cap). Its
    :class:`~agentprov.errors.IngestError` is re-raised as :class:`CanonError` carrying the same closed
    ``ingest.*`` code, so callers of this module handle one exception type.
    """
    try:
        value: Json = strict_json_loads(data, record=True)
    except IngestError as exc:
        raise CanonError("strict parse failed", code=exc.code) from None
    return value
