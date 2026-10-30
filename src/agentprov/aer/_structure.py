"""Structural (context-free) validation of one AER record: the in-code twin of the JSON Schema.

``check_record`` implements the **structural subset** of C.17 that is decidable from one record alone: closed
core objects, required members, types, patterns, closed enumerations, the ``oneOf`` alternatives of C.3, the
``$``-forms of C.11.3 and the shapes of ``unk``, ``evf``, ``rule``, ``src``, ``after`` and ``ext.lex``. It is
the subset covered by the published ``schemas/aer-0.1.schema.json`` (C.17, last paragraph); the differential
test requires the two to agree on it.

Deliberately outside this subset (the validator checks them with context): backward references and their kinds,
unknown/value conflicts, evidence obligations (``by``, ``src``, ``rule``), sentinels, time order, number ranges,
header/mode dependencies, locators against the raw store, accounting and the seal digest.

Findings are ``(code, pointer, key)`` triples. ``pointer`` is a JSON Pointer into the record; ``key`` is a short
fixed reason label. No finding ever contains a value taken from the record (it may be hostile source text).
"""

from __future__ import annotations

import base64
import binascii

import math
import re
from collections.abc import Callable, Iterable, Mapping
from typing import Any, Final

from agentprov.aer import READABLE_VERSIONS
from agentprov.aer import types as T
from agentprov.aer.canon import pointer_escape

__all__ = [
    "BASE32_RE",
    "KIND_FIELDS",
    "PATTERNS",
    "Finding",
    "check_record",
    "is_integral",
]

type Finding = tuple[str, str, str]  # (code, pointer, reason key)

# ------------------------------------------------------------------------------------------------ patterns
_ID = r"[a-z][a-z0-9_]{0,31}"
_RECORD_ID = r"(?!(?:exec|seal|as)$)(?!a(?:0|[1-9][0-9]*)$)" + _ID
_NUM = r"(?:0|[1-9][0-9]*)"
_POINTER_NONEMPTY = r"(?:/(?:[^/~]|~[01])*)+"
_POINTER_ANY = r"(?:/(?:[^/~]|~[01])*)*"
_TIME_DATE = r"[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])"
_TIME_CLOCK = r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:(?:[0-5][0-9]|60)(?:\.[0-9]+)?"
_RULE_NAME = r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+"

PATTERNS: Final[dict[str, str]] = {
    "record_id": _RECORD_ID,
    "ref": _ID + r"(?:#" + _NUM + r")?",
    "local_id": _ID,
    "part_id": _ID + r"#" + _NUM,
    "artefact_id": r"a" + _NUM,
    "pointer": _POINTER_NONEMPTY,
    "pointer_any": _POINTER_ANY,
    "hex64": r"[0-9a-f]{64}",
    "hex40": r"[0-9a-f]{40}",
    "digest": r"sha256:[0-9a-f]{64}",
    "crc32": r"[0-9a-f]{8}",
    "time": _TIME_DATE + r"T" + _TIME_CLOCK + r"Z",
    "time_naive": _TIME_DATE + r"T" + _TIME_CLOCK,
    "date": _TIME_DATE,
    "ex": r"ex_(?:[a-z2-7]{26}|[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})",
    "uuid7": r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
    "tag": r"(?:[ODI]|O:(?:capture|source|provider|benchmark|config|replay))",
    "rule_ref": _RULE_NAME + r"@[1-9][0-9]*(?:#/[\s\S]*)?",
    "rule_id": _RULE_NAME + r"@[1-9][0-9]*",
    "subtype": r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*",
    "type": r"[a-z][a-z0-9_]*:[a-z][a-z0-9_]*",
    "prefix": r"[a-z][a-z0-9_]{0,31}",
    "namespace": r"[a-z][a-z0-9_]*",
    "dotted": r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*",
    "profile_id": r"[a-z][a-z0-9_-]*",
    "semver": _NUM + r"\." + _NUM + r"\." + _NUM + r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?",
    "issue_code": r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)?",
    "int_decimal": r"-?[1-9][0-9]*",
    "base64": r"(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?",
    "activity_id": r"ac" + _NUM,
    "artefact_record_id": r"af" + _NUM,
}
_RE: Final = {name: re.compile(src) for name, src in PATTERNS.items()}
BASE32_RE: Final = re.compile(r"[a-z2-7]{26}")
_FLOAT_FORMS: Final = frozenset({"NaN", "Infinity", "-Infinity", "-0"})


def is_integral(value: object) -> bool:
    """JSON-Schema ``integer``: an int (not bool) or a finite float with an integral value."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    return isinstance(value, float) and math.isfinite(value) and value.is_integer()


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


# ------------------------------------------------------------------------------------------------ machinery
class _Sink:
    __slots__ = ("items",)

    def __init__(self) -> None:
        self.items: list[Finding] = []

    def add(self, code: str, pointer: str, key: str) -> None:
        self.items.append((code, pointer, key))


type Check = Callable[[object, str, _Sink, "_Ctx"], None]


class _Ctx:
    """Record-level facts some member checks need: the record's ``unk`` declarations and the file's format version
    (``aer/0.2`` relaxes two requirements, D-210 and D-211; ``aer/0.1`` keeps its frozen rules)."""

    __slots__ = ("unk", "unk_keys", "version")

    def __init__(self, unk_keys: frozenset[str], unk: Mapping[str, object] | None = None, version: str = "0.1") -> None:
        self.unk_keys = unk_keys
        self.unk = dict(unk or {})
        self.version = version

    def withheld(self, pointer: str) -> bool:
        """``aer/0.2`` only: the member at ``pointer`` is declared ``withheld`` or ``not_captured`` (D-211)."""
        return self.version != "0.1" and self.unk.get(pointer) in ("withheld", "not_captured")

    def not_captured(self, pointer: str) -> bool:
        """``aer/0.2`` only: the member at ``pointer`` is declared ``not_captured`` (D-219; the file must be degenerate,
        which the validator checks at the seal)."""
        return self.version != "0.1" and self.unk.get(pointer) == "not_captured"


PAT = "aer.schema.pattern"
ADD = "aer.schema.additional"
REQ = "aer.schema.required"
ONE = "aer.schema.oneof"


def s_str(pattern: str | None = None, *, enum: Iterable[str] | None = None, code: str = PAT) -> Check:
    rx = _RE[pattern] if pattern else None
    allowed = frozenset(enum) if enum is not None else None

    def check(v: object, at: str, sink: _Sink, ctx: _Ctx) -> None:
        if not isinstance(v, str):
            sink.add(code, at, "type_string")
        elif allowed is not None and v not in allowed:
            sink.add(code, at, "enum")
        elif rx is not None and rx.fullmatch(v) is None:
            sink.add(code, at, "pattern")

    return check


def _json_equal(a: object, b: object) -> bool:
    """Equality as JSON Schema ``const`` defines it: ``1 == 1.0`` but ``True != 1``."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    return a == b


def s_const(expected: object) -> Check:
    def check(v: object, at: str, sink: _Sink, ctx: _Ctx) -> None:
        if not _json_equal(v, expected):
            sink.add(PAT, at, "const")

    return check


def s_any_string(v: object, at: str, sink: _Sink, ctx: _Ctx) -> None:
    if not isinstance(v, str):
        sink.add(PAT, at, "type_string")


def s_nonempty_string(v: object, at: str, sink: _Sink, ctx: _Ctx) -> None:
    if not isinstance(v, str) or not v:
        sink.add(PAT, at, "type_nonempty_string")


def s_bool(v: object, at: str, sink: _Sink, ctx: _Ctx) -> None:
    if not isinstance(v, bool):
        sink.add(PAT, at, "type_boolean")


def s_null(v: object, at: str, sink: _Sink, ctx: _Ctx) -> None:
    if v is not None:
        sink.add(PAT, at, "type_null")


def s_int(minimum: int | None = None) -> Check:
    def check(v: object, at: str, sink: _Sink, ctx: _Ctx) -> None:
        if not is_integral(v):
            sink.add(PAT, at, "type_integer")
        elif minimum is not None and v < minimum:  # type: ignore[operator]
            sink.add(PAT, at, "minimum")

    return check


def s_num(minimum: float | None = None) -> Check:
    def check(v: object, at: str, sink: _Sink, ctx: _Ctx) -> None:
        if not _is_number(v):
            sink.add(PAT, at, "type_number")
        elif minimum is not None and v < minimum:  # type: ignore[operator]
            sink.add(PAT, at, "minimum")

    return check


def s_any(*alts: Check, key: str = "anyof", code: str = PAT) -> Check:
    def check(v: object, at: str, sink: _Sink, ctx: _Ctx) -> None:
        for alt in alts:
            probe = _Sink()
            alt(v, at, probe, ctx)
            if not probe.items:
                return
        sink.add(code, at, key)

    return check


def s_arr(item: Check, *, min_items: int = 0, max_items: int | None = None, unique: bool = False) -> Check:
    def check(v: object, at: str, sink: _Sink, ctx: _Ctx) -> None:
        if not isinstance(v, list):
            sink.add(PAT, at, "type_array")
            return
        if len(v) < min_items:
            sink.add(PAT, at, "min_items")
        if max_items is not None and len(v) > max_items:
            sink.add(PAT, at, "max_items")
        if unique and not _is_unique(v):
            sink.add(PAT, at, "unique_items")
        for i, element in enumerate(v):
            item(element, f"{at}/{i}", sink, ctx)

    return check


def _is_unique(items: list[object]) -> bool:
    seen: list[object] = []
    for item in items:
        if any(type(item) is type(s) and item == s for s in seen):
            return False
        seen.append(item)
    return True


def s_map(key_pattern: str, value: Check, *, min_props: int = 0, key_code: str = PAT) -> Check:
    rx = _RE[key_pattern]

    def check(v: object, at: str, sink: _Sink, ctx: _Ctx) -> None:
        if not isinstance(v, dict):
            sink.add(PAT, at, "type_object")
            return
        if len(v) < min_props:
            sink.add(PAT, at, "min_properties")
        for key, element in v.items():
            if not isinstance(key, str) or rx.fullmatch(key) is None:
                sink.add(key_code, f"{at}/{pointer_escape(str(key))}", "key_pattern")
            value(element, f"{at}/{pointer_escape(str(key))}", sink, ctx)

    return check


type Field = tuple[Check, bool | str]  # (check, required) where required is True, False or "unk"


def F(check: Check, required: bool | str = False) -> Field:
    """A member: ``required`` False, True, ``"unk"`` (present or declared in ``unk``), ``"withheld"`` (present, or in
    ``aer/0.2`` declared ``withheld``/``not_captured``; in ``aer/0.1`` the same as True) or ``"not_captured"`` (present,
    or in ``aer/0.2`` declared ``not_captured``, D-219)."""
    return (check, required)


class _ObjCheck:
    """A closed object check; ``fields`` stays readable (the ext-shadowing check needs the member names)."""

    __slots__ = ("extra", "fields")

    def __init__(
        self,
        fields: Mapping[str, Field],
        extra: Callable[[dict[str, Any], str, _Sink, _Ctx], None] | None,
    ) -> None:
        self.fields = dict(fields)
        self.extra = extra

    def __call__(self, v: object, at: str, sink: _Sink, ctx: _Ctx) -> None:
        if not isinstance(v, dict):
            sink.add(PAT, at, "type_object")
            return
        for key in v:
            if key not in self.fields:
                sink.add(ADD, f"{at}/{pointer_escape(str(key))}", "member_not_allowed")
        for name, (sub, required) in self.fields.items():
            pointer = f"{at}/{pointer_escape(name)}"
            if name in v:
                sub(v[name], pointer, sink, ctx)
            elif required is True or (required == "unk" and pointer not in ctx.unk_keys) or (
                required == "withheld" and not ctx.withheld(pointer)
            ) or (required == "not_captured" and not ctx.not_captured(pointer)):
                sink.add(REQ, pointer, "missing")
        if self.extra is not None:
            self.extra(v, at, sink, ctx)


def s_obj(
    fields: Mapping[str, Field],
    *,
    extra: Callable[[dict[str, Any], str, _Sink, _Ctx], None] | None = None,
) -> _ObjCheck:
    """A closed object. ``required`` True: must be present; ``"unk"``: present or declared in ``unk``."""
    return _ObjCheck(fields, extra)


# ------------------------------------------------------------------------------------------------ $-forms
def _check_reserved(v: dict[str, object], at: str, sink: _Sink, ctx: _Ctx) -> None:
    """A JSON object that has at least one ``$`` member (C.11.3)."""
    keys = [k for k in v if k.startswith("$")]
    if "$blob" in v:
        _blobref(v, at, sink, ctx)
        return
    if len(v) != 1:
        sink.add(PAT, at, "reserved_object")
        return
    name = keys[0]
    inner = v[name]
    if name == "$lit":
        # pre-round review #28 (aer/0.2; aer/0.1's rules and schema are frozen): $lit wraps an object with a member name
        # beginning with "$" (C.11.3); any other object is written plain, so a $lit around it is not the canonical form
        if not isinstance(inner, dict) or (ctx.version != "0.1" and not any(isinstance(k, str) and k.startswith("$")
                                                                           for k in inner)):
            sink.add(PAT, at, "reserved_object")
            return
        for key, element in inner.items():
            s_json(element, f"{at}/$lit/{pointer_escape(key)}", sink, ctx)
    elif name == "$int":
        if not isinstance(inner, str) or _RE["int_decimal"].fullmatch(inner) is None:
            sink.add(PAT, at, "reserved_object")
    elif name == "$float":
        if not isinstance(inner, str) or inner not in _FLOAT_FORMS:
            sink.add(PAT, at, "reserved_object")
    elif name == "$utf16":
        if not isinstance(inner, str) or _RE["base64"].fullmatch(inner) is None \
                or (ctx.version != "0.1" and not _utf16_form(inner)):  # #28, aer/0.2
            sink.add(PAT, at, "reserved_object")
    else:
        sink.add(PAT, at, "reserved_object")


def _utf16_form(text: str) -> bool:
    """Whether ``text`` is the canonical ``$utf16`` payload (C.11.3; pre-round review #28): base64 of whole UTF-16BE code
    units (an even byte count, so ``decode_value`` can read it) of a string that is not a valid Unicode scalar sequence
    (a valid one is written as a plain string)."""
    try:
        raw = base64.b64decode(text.encode("ascii"), validate=True)
    except (binascii.Error, ValueError):
        return False
    if len(raw) % 2:
        return False
    value = raw.decode("utf-16-be", "surrogatepass")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return True
    return False


def s_json(v: object, at: str, sink: _Sink, ctx: _Ctx) -> None:
    """Open ``Json`` content: any JSON value whose ``$``-objects are well formed (C.11.3, V18)."""
    if v is None or isinstance(v, bool | str) or _is_number(v):
        return
    if isinstance(v, list):
        for i, element in enumerate(v):
            s_json(element, f"{at}/{i}", sink, ctx)
        return
    if isinstance(v, dict):
        if any(isinstance(k, str) and k.startswith("$") for k in v):
            _check_reserved(v, at, sink, ctx)
            return
        for key, element in v.items():
            s_json(element, f"{at}/{pointer_escape(str(key))}", sink, ctx)
        return
    sink.add(PAT, at, "not_json")


def _blobref(v: object, at: str, sink: _Sink, ctx: _Ctx) -> None:
    if not isinstance(v, dict):
        sink.add("aer.blob.ref", at, "type_object")
        return
    allowed = {"$blob", "bytes", "media"}
    ok = (
        set(v) <= allowed
        and isinstance(v.get("$blob"), str)
        and _RE["digest"].fullmatch(v["$blob"]) is not None
        and "bytes" in v
        and is_integral(v["bytes"])
        and v["bytes"] >= 0
        and ("media" not in v or isinstance(v["media"], str))
    )
    if not ok:
        sink.add("aer.blob.ref", at, "blob_ref")


def s_blobref(v: object, at: str, sink: _Sink, ctx: _Ctx) -> None:
    if isinstance(v, dict) and "$blob" in v:
        _blobref(v, at, sink, ctx)
    else:
        sink.add("aer.blob.ref", at, "blob_ref")


# ------------------------------------------------------------------------------------------------ shared shapes
def _time_extra(v: dict[str, Any], at: str, sink: _Sink, ctx: _Ctx) -> None:
    if ("dur_s" in v) != ("dur_clock" in v):
        sink.add(REQ, f"{at}/dur_clock", "dur_clock_iff_dur_s")


s_time = s_obj(
    {
        "start": F(s_str("time")),
        "end": F(s_str("time")),
        "start_naive": F(s_str("time_naive")),
        "end_naive": F(s_str("time_naive")),
        "dur_s": F(s_num(0)),
        "dur_clock": F(s_str(enum=T.DUR_CLOCKS)),
        "mono_start_ns": F(s_int(0)),
        "mono_end_ns": F(s_int(0)),
        "raw": F(s_obj({"start": F(s_any_string), "end": F(s_any_string), "dur": F(s_any_string)})),
    },
    extra=_time_extra,
)
s_usage = s_obj(
    {
        name: F(s_int(0))
        for name in (
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "reasoning_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
            "calls",
        )
    }
)
s_model = s_obj({name: F(s_any_string) for name in ("requested", "served", "provider", "endpoint")})
s_code = s_obj(
    {
        "dist": F(s_any_string),
        "dist_version": F(s_any_string),
        "repo": F(s_any_string),
        "commit": F(s_any_string),
        "wheel_sha256": F(s_str("hex64")),
    }
)
s_ref = s_str("ref")
s_local = s_str("local_id")


_LOCATOR_FORMS: Final = frozenset(
    frozenset(f)
    for f in (
        {"a"},
        {"a", "p"},
        {"a", "bytes"},
        {"a", "bytes", "p"},
        {"a", "line"},
        {"a", "line", "p"},
        {"a", "o"},
        {"blob"},
        {"blob", "p"},
    )
)


def _locator_extra(v: dict[str, Any], at: str, sink: _Sink, ctx: _Ctx) -> None:
    if frozenset(v) not in _LOCATOR_FORMS:
        sink.add(ONE, at, "locator_form")


s_locator = s_obj(
    {
        "a": F(s_str("artefact_id")),
        "p": F(s_str("pointer_any")),
        "bytes": F(s_arr(s_int(0), min_items=2, max_items=2)),
        "line": F(s_int(0)),
        "o": F(s_str("pointer_any")),
        "blob": F(s_str("digest")),
    },
    extra=_locator_extra,
)
s_locators = s_arr(s_locator)
s_after = s_arr(
    s_obj(
        {"id": F(s_str("ref"), True), "b": F(s_str(enum=T.AFTER_BASES), True)},
    )
)
s_evf = s_map("pointer", s_str("tag"))
s_unk = s_map("pointer", s_str(enum=T.UNKNOWN_REASON_SET, code="aer.unk.reason"))
s_rules_list = s_arr(s_str("rule_ref"))


def _lex_nonempty(v: dict[str, Any], at: str, sink: _Sink, ctx: _Ctx) -> None:
    if not v:
        sink.add(PAT, at, "empty_lex")


_ext_lex = s_obj(
    {
        "ord": F(s_map("pointer", s_arr(s_any_string, min_items=2), min_props=1)),
        "flt": F(s_arr(s_str("pointer"), min_items=1, unique=True)),
    },
    extra=_lex_nonempty,
)


def s_ext(v: object, at: str, sink: _Sink, ctx: _Ctx) -> None:
    if not isinstance(v, dict):
        sink.add(PAT, at, "type_object")
        return
    for prefix, content in v.items():
        pointer = f"{at}/{pointer_escape(str(prefix))}"
        if not isinstance(prefix, str) or _RE["prefix"].fullmatch(prefix) is None:
            sink.add(PAT, pointer, "key_pattern")
        if prefix == "lex":
            _ext_lex(content, pointer, sink, ctx)
        elif not isinstance(content, dict):
            sink.add(PAT, pointer, "type_object")
        else:
            s_json(content, pointer, sink, ctx)


# ------------------------------------------------------------------------------------------------ enum escapes
def _escape(kind_field: str) -> Callable[[dict[str, Any], str, _Sink, _Ctx], None]:
    """``subtype`` is present exactly when the closed enumeration member ``kind_field`` is ``other`` (V30)."""

    def extra(v: dict[str, Any], at: str, sink: _Sink, ctx: _Ctx) -> None:
        is_other = v.get(kind_field) == "other" and kind_field in v
        if is_other != ("subtype" in v):
            sink.add("aer.subtype.missing", f"{at}/subtype", "subtype_iff_other")

    return extra


def _chain(*fns: Callable[[dict[str, Any], str, _Sink, _Ctx], None]) -> Callable[[dict[str, Any], str, _Sink, _Ctx], None]:
    def extra(v: dict[str, Any], at: str, sink: _Sink, ctx: _Ctx) -> None:
        for fn in fns:
            fn(v, at, sink, ctx)

    return extra


# ------------------------------------------------------------------------------------------------ parts
def _part_checks() -> dict[str, Check]:
    text_or_null = s_any(s_any_string, s_null)

    def result_extra(v: dict[str, Any], at: str, sink: _Sink, ctx: _Ctx) -> None:
        if ("text" in v) == ("value" in v):
            sink.add(ONE, at, "text_xor_value")

    return {
        "text": s_obj({"t": F(s_const("text"), True), "text": F(text_or_null, "withheld")}),
        "reasoning": s_obj(
            {
                "t": F(s_const("reasoning"), True),
                "text": F(text_or_null, "withheld"),
                "signature": F(s_any_string),
                "redacted": F(s_bool),
                "provider_id": F(s_any_string),
            }
        ),
        "tool_call": s_obj(
            {
                "t": F(s_const("tool_call"), True),
                "name": F(s_any_string, True),
                "args": F(s_json, "withheld"),
                "args_raw": F(s_any_string),
                "provider_call_id": F(text_or_null),
            }
        ),
        "tool_result": s_obj(
            {
                "t": F(s_const("tool_result"), True),
                "responds_to": F(s_str("part_id")),  # required-or-unk is a contextual check (needs the message's unk)
                "text": F(text_or_null),
                "value": F(s_json),
                "error": F(text_or_null),
                "name": F(s_any_string),
            },
            extra=result_extra,
        ),
        "blob": s_obj(
            {"t": F(s_const("blob"), True), "data": F(s_blobref, True), "media": F(s_any_string, True)}
        ),
        "file": s_obj(
            {"t": F(s_const("file"), True), "name": F(s_any_string), "media": F(s_any_string), "ref": F(s_any_string, True)}
        ),
        "uri": s_obj({"t": F(s_const("uri"), True), "uri": F(s_any_string, True), "media": F(s_any_string)}),
        "refusal": s_obj({"t": F(s_const("refusal"), True), "text": F(s_any_string, "withheld")}),
        "other": s_obj({"t": F(s_const("other"), True), "type": F(s_any_string, True), "value": F(s_json, "withheld")}),
    }


_PARTS = _part_checks()


def s_part(v: object, at: str, sink: _Sink, ctx: _Ctx) -> None:
    if not isinstance(v, dict):
        sink.add(PAT, at, "type_object")
        return
    t = v.get("t")
    if not isinstance(t, str):
        sink.add(REQ, f"{at}/t", "missing")
        return
    check = _PARTS.get(t)
    if check is None:
        sink.add(PAT, f"{at}/t", "enum")
        return
    check(v, at, sink, ctx)


# ------------------------------------------------------------------------------------------------ kinds
def _origin_checks() -> Check:
    def own(kind: str, fields: dict[str, Field]) -> Check:
        return s_obj({"kind": F(s_const(kind), True), **fields})

    alts = {
        "git": own(
            "git",
            {
                "repo": F(s_any_string, True),
                "commit": F(s_str("hex40"), True),
                "path": F(s_any_string, True),
                "blob_sha1": F(s_str("hex40"), True),
                "introduced_in_commit": F(s_str("hex40")),
            },
        ),
        "hf": own("hf", {"repo": F(s_any_string, True), "revision": F(s_any_string, True), "path": F(s_any_string, True)}),
        "zenodo": own("zenodo", {"doi": F(s_any_string, True), "file": F(s_any_string, True)}),
        "url": own("url", {"url": F(s_any_string, True), "retrieved": F(s_str("date"), True)}),
        "corpus": own(
            "corpus",
            {
                "corpus": F(s_any_string, True),
                "version": F(s_any_string, True),
                "producer_commit": F(s_str("hex40")),
                "path": F(s_any_string, True),
            },
        ),
        "capture": own("capture", {"session": F(s_str("uuid7"), True)}),
        "member": own(
            "member",
            {
                "container": F(s_str("hex64"), True),
                "label": F(s_any_string, True),
                "method": F(s_any(s_const(0), s_const(8), s_const(93)), True),
                "crc32": F(s_str("crc32"), True),
                "size": F(s_int(0), True),
            },
        ),
        "local": own("local", {"path": F(s_any_string, True)}),
    }

    def check(v: object, at: str, sink: _Sink, ctx: _Ctx) -> None:
        if not isinstance(v, dict):
            sink.add(PAT, at, "type_object")
            return
        kind = v.get("kind")
        if not isinstance(kind, str):
            sink.add(REQ, f"{at}/kind", "missing")
        elif kind not in alts:
            sink.add(PAT, f"{at}/kind", "enum")
        else:
            alts[kind](v, at, sink, ctx)

    return check


s_artefact_desc = s_obj(
    {
        "id": F(s_str("artefact_id"), True),
        "role": F(s_str(enum=T.ARTEFACT_ROLES), True),
        "prov_primary": F(s_str(enum=T.PROV_PRIMARY), True),
        "sha256": F(s_str("hex64"), True),
        "bytes": F(s_int(0), True),
        "media": F(s_any_string, True),
        "origin": F(_origin_checks(), True),
    }
)
s_task = s_obj(
    {
        "benchmark": F(s_any_string, True),
        "suite": F(s_any_string),
        "environment": F(s_any_string),
        "task_id": F(s_any_string, "not_captured"),  # D-219: a degenerate aer/0.2 header may declare it not captured
        "attack_id": F(s_any(s_any_string, s_null)),
        "attack_target_id": F(s_any(s_any_string, s_null)),
        "defense_id": F(s_any(s_any_string, s_null)),
    }
)
s_instrumentation = s_arr(
    s_obj(
        {
            "id": F(s_str("rule_id"), True),
            "kind": F(s_str(enum=T.INSTRUMENTATION_KINDS), True),
            "recorded": F(s_str(enum=T.INSTRUMENTATION_RECORDED), True),
            "params": F(s_json),
            "detail": F(s_any_string),
            "code_ref": F(
                s_obj(
                    {
                        "repo": F(s_any_string, True),
                        "commit": F(s_str("hex40"), True),
                        "path": F(s_any_string, True),
                        "lines": F(s_any_string),
                    }
                )
            ),
        }
    )
)


def _header_extra(v: dict[str, Any], at: str, sink: _Sink, ctx: _Ctx) -> None:
    mode = v.get("mode")
    if mode == "live":
        for name in ("capture", "instrumentation"):
            # aer/0.2 (D-210): a verifiable prefix cut before the instrumentation event declares it not captured
            cut = name == "instrumentation" and ctx.version != "0.1" and ctx.unk.get("/instrumentation") == "not_captured"
            if name not in v and not cut:
                sink.add(REQ, f"{at}/{name}", "required_for_live")
    elif mode == "import" and "capture" in v:
        sink.add(ADD, f"{at}/capture", "capture_only_live")


_ENVELOPE_COMMON: Final[dict[str, Field]] = {
    "k": F(s_any_string, True),  # replaced per kind
    "id": F(s_str("record_id"), True),
    "ev": F(s_str(enum=("O", "D", "I")), True),
    "by": F(s_str(enum=T.PARTIES)),
    "evf": F(s_evf),
    "rule": F(s_rules_list),
    "src": F(s_locators),
    "unk": F(s_unk),
    "after": F(s_after),
    "ext": F(s_ext),
}


def _envelope(kind: str, *, id_check: Check | None = None, after: bool = True) -> dict[str, Field]:
    env = dict(_ENVELOPE_COMMON)
    env["k"] = F(s_const(kind), True)
    if id_check is not None:
        env["id"] = F(id_check, True)
    if not after:
        del env["after"]
    return env


def _kind(kind: str, fields: dict[str, Field], *, extra: Callable[..., None] | None = None, **env_kw: Any) -> _ObjCheck:
    return s_obj({**_envelope(kind, **env_kw), **fields}, extra=extra)


def _scope_extra(v: dict[str, Any], at: str, sink: _Sink, ctx: _Ctx) -> None:
    kind = v.get("kind")
    is_run = kind == "run"
    if is_run != (v.get("id") == "run"):
        sink.add(PAT, f"{at}/id", "run_id_iff_run_scope")
    if "kind" in v:
        if is_run and "parent" in v:
            sink.add(ADD, f"{at}/parent", "run_has_no_parent")
        if not is_run and "parent" not in v:
            sink.add(REQ, f"{at}/parent", "missing")


def _tool_exec_extra(v: dict[str, Any], at: str, sink: _Sink, ctx: _Ctx) -> None:
    count = ("call" in v) + ("requested_by" in v) + (ctx_unk(v).get("/call") == "ambiguous")
    if count != 1:
        sink.add(ONE, at, "call_requested_by_or_unk")


def ctx_unk(v: Mapping[str, Any]) -> Mapping[str, Any]:
    unk = v.get("unk")
    return unk if isinstance(unk, dict) else {}


def _artefact_extra(v: dict[str, Any], at: str, sink: _Sink, ctx: _Ctx) -> None:
    count = ("content" in v) + ("content_ref" in v) + ("/content" in ctx_unk(v))
    if count != 1:
        sink.add(ONE, at, "content_one_of")


def _state_extra(v: dict[str, Any], at: str, sink: _Sink, ctx: _Ctx) -> None:
    if ("before_sha256" in v or "after_sha256" in v) and "canon" not in v:
        sink.add(REQ, f"{at}/canon", "canon_with_digest")


s_input_item = s_any(
    s_str("local_id"),
    s_obj(
        {
            "id": F(s_str("local_id"), True),
            "sent": F(s_arr(s_str(enum=T.SENT_TRANSFORMS), min_items=1), True),
            "sent_sha256": F(s_str("hex64")),
        }
    ),
    key="input_item",
)
def _patch_open(v: object, at: str, sink: _Sink, ctx: _Ctx) -> None:
    """RFC 6902 operations: ``op`` and ``path`` are checked, the other members (``value``, ``from``) stay open."""
    if not isinstance(v, list):
        sink.add(PAT, at, "type_array")
        return
    op_check = s_str(enum=T.JSON_PATCH_OPS)
    path_check = s_str("pointer_any")
    for i, op in enumerate(v):
        pointer = f"{at}/{i}"
        if not isinstance(op, dict):
            sink.add(PAT, pointer, "type_object")
            continue
        for member, member_check in (("op", op_check), ("path", path_check)):
            if member in op:
                member_check(op[member], f"{pointer}/{member}", sink, ctx)
            else:
                sink.add(REQ, f"{pointer}/{member}", "missing")
        for key, value in op.items():
            if key not in ("op", "path"):
                s_json(value, f"{pointer}/{pointer_escape(key)}", sink, ctx)


s_issue = s_obj(
    {
        "code": F(
            s_any(s_str(enum=T.CORE_ISSUE_CODES), s_str("subtype"), key="issue_code"),
            True,
        ),
        "ids": F(s_arr(s_ref), True),
        "rule": F(s_str("rule_ref"), True),
        "detail": F(s_any_string),
    }
)
s_check_entry = s_obj(
    {
        "id": F(s_str("rule_id"), True),
        "scope": F(s_str("local_id"), True),
        "verdict": F(s_str(enum=T.ACCOUNTING_VERDICTS), True),
        "reason": F(s_any_string),
        "observed": F(s_map("namespace", s_int(0)), True),
    }
)

_KINDS: Final[dict[str, _ObjCheck]] = {
    "execution": s_obj(
        {
            **_envelope("execution", id_check=s_const("exec"), after=False),
            "aer": F(s_str(enum=READABLE_VERSIONS), True),
            "ex": F(s_str("ex"), True),
            "mode": F(s_str(enum=T.MODES), True),
            "unit": F(s_str(enum=T.UNITS), True),
            "source_key": F(
                s_obj(
                    {
                        "sha256": F(s_str("hex64"), True),
                        "loc": F(
                            s_obj(
                                {
                                    "p": F(s_str("pointer_any")),
                                    "line": F(s_int(0)),
                                    "bytes": F(s_arr(s_int(0), min_items=2)),
                                }
                            ),
                            True,
                        ),
                    }
                ),
                True,
            ),
            "artifacts": F(s_arr(s_artefact_desc, min_items=1), True),
            "adapter": F(
                s_obj({"id": F(s_str("dotted"), True), "version": F(s_str("semver"), True)}),
                True,
            ),
            "dialect": F(s_obj({"id": F(s_str("dotted"), True), "variant": F(s_nonempty_string, True)}), True),
            "profile": F(
                s_obj(
                    {
                        "id": F(s_str("profile_id"), True),
                        "version": F(s_int(1), True),
                        "sha256": F(s_str("hex64"), True),
                    }
                ),
                True,
            ),
            "rules": F(s_map("namespace", s_int(1)), True),
            "ns": F(s_map("prefix", s_nonempty_string), True),
            "canon": F(s_const("jcs-rfc8785"), True),
            "hash": F(s_const("sha256"), True),
            "capture": F(
                s_obj(
                    {
                        "session": F(s_str("uuid7"), True),
                        "log": F(s_str("artefact_id"), True),
                        "attempt": F(s_int(0), True),
                    }
                )
            ),
            "related": F(
                s_arr(
                    s_obj(
                        {
                            "rel": F(s_str(enum=T.RELATIONS), True),
                            "ex": F(s_str("ex"), True),
                            "id": F(s_str("local_id")),
                        }
                    )
                )
            ),
            "task": F(s_task, True),
            "instrumentation": F(s_instrumentation),
        },
        extra=_header_extra,
    ),
    "actor": _kind(
        "actor",
        {
            "kind": F(s_str(enum=T.ACTOR_KINDS), "unk"),
            "subtype": F(s_str("subtype")),
            "name": F(s_any_string),
            "role": F(s_any_string),
            "model": F(s_model),
            "params": F(s_json),
            "version": F(s_any_string),
            "code": F(s_code),
            "on_behalf_of": F(s_local),
        },
        extra=_escape("kind"),
        after=False,
    ),
    "scope": _kind(
        "scope",
        {
            "kind": F(s_str(enum=T.SCOPE_KINDS), True),
            "subtype": F(s_str("subtype")),
            "parent": F(s_local),
            "actor": F(s_local),
            "index": F(s_int(0)),
            "scored": F(s_bool),
            "spawned_by": F(s_local),
            "t": F(s_time),
            "status": F(s_str(enum=T.SCOPE_STATUS)),
            "usage": F(s_usage),
        },
        extra=_chain(_escape("kind"), _scope_extra),
    ),
    "message": _kind(
        "message",
        {
            "scope": F(s_local, True),
            "role": F(s_any_string, True),
            "actor": F(s_local),
            "parts": F(s_arr(s_part), True),
            "generated_by": F(s_local),
        },
    ),
    "model_call": _kind(
        "model_call",
        {
            "actor": F(s_local, True),
            "role": F(s_str(enum=T.MODEL_CALL_ROLES), True),
            "scope": F(s_local, True),
            "input": F(s_arr(s_input_item)),
            "tools": F(s_local),
            "params": F(s_obj({"configured": F(s_json), "transmitted": F(s_json)})),
            "status": F(s_str(enum=T.MODEL_CALL_STATUS), "unk"),
            "reason": F(s_any_string),
            "retry_of": F(s_local),
            "finish_reason": F(s_any_string),
            "usage": F(s_usage),
            "served_model": F(s_any_string),
            "response_id": F(s_any_string),
            "request": F(s_blobref),
            "response": F(s_blobref),
            "t": F(s_time),
        },
    ),
    "tool_execution": _kind(
        "tool_execution",
        {
            "actor": F(s_local, True),
            "scope": F(s_local, True),
            "call": F(s_str("part_id")),
            "requested_by": F(s_local),
            "authorised_by": F(s_local),
            "name": F(s_any_string, True),
            "args": F(s_json),
            "args_effective": F(s_json),
            "status": F(s_str(enum=T.TOOL_EXECUTION_STATUS), "unk"),
            "exception": F(s_obj({"type": F(s_any_string, True), "message": F(s_any_string, True)})),
            "returned": F(s_json),
            "t": F(s_time),
        },
        extra=_tool_exec_extra,
    ),
    "decision": _kind(
        "decision",
        {
            "actor": F(s_local, True),
            "scope": F(s_local),
            "subject": F(s_ref, True),
            "verdict": F(s_str(enum=T.DECISION_VERDICTS), "unk"),
            "subtype": F(s_str("subtype")),
            "reason": F(s_any_string),
            "original": F(s_any(s_blobref, s_str("part_id"), key="original")),
            "t": F(s_time),
        },
        extra=_escape("verdict"),
    ),
    "state_change": _kind(
        "state_change",
        {
            "scope": F(s_local, True),
            "cause": F(s_local),
            "target": F(s_str(enum=T.STATE_TARGETS), True),
            "subtype": F(s_str("subtype")),
            "canon": F(s_any_string),
            "before_sha256": F(s_str("hex64")),
            "after_sha256": F(s_str("hex64")),
            "changed": F(s_bool),
            "patch": F(_patch_open),
            "diff": F(
                s_obj(
                    {"format": F(s_any_string, True), "value": F(s_json, True), "truncated": F(s_bool, True)}
                )
            ),
            "snapshot_before": F(s_blobref),
            "snapshot_after": F(s_blobref),
            "t": F(s_time),
        },
        extra=_chain(_escape("target"), _state_extra),
    ),
    "fixture": _kind(
        "fixture",
        {
            "kind": F(s_str(enum=T.FIXTURE_KINDS), True),
            "subtype": F(s_str("subtype")),
            "vector": F(s_any_string),
            "content": F(s_json, "unk"),
            "media": F(s_any_string),
            "actor": F(s_local),
        },
        extra=_escape("kind"),
    ),
    "judgement": _kind(
        "judgement",
        {
            "actor": F(s_local, True),
            "subject": F(s_ref, True),
            "name": F(s_any_string, True),
            "value": F(s_json, True),
            "origin": F(s_str(enum=T.JUDGEMENT_ORIGINS), "unk"),
            "revises": F(s_local),
            "generated_by": F(s_local),
            "inputs": F(s_arr(s_ref)),
            "t": F(s_time),
        },
    ),
    "activity": _kind(
        "activity",
        {
            "type": F(s_str("type"), True),
            "actor": F(s_local),
            "scope": F(s_local, True),
            "inputs": F(s_arr(s_ref)),
            "t": F(s_time),
            "status": F(s_str(enum=T.ACTIVITY_STATUS)),
            "label": F(s_any_string),
        },
        id_check=s_str("activity_id"),
    ),
    "artefact": _kind(
        "artefact",
        {
            "type": F(s_str("type"), True),
            "content": F(s_json),
            "content_ref": F(s_blobref),
            "sha256": F(s_str("hex64")),
            "media": F(s_any_string),
            "generated_by": F(s_local),
        },
        extra=_artefact_extra,
        id_check=s_str("artefact_record_id"),
    ),
    "seal": s_obj(
        {
            "k": F(s_const("seal"), True),
            "id": F(s_const("seal"), True),
            "n_records": F(s_int(2), True),
            "records_sha256": F(s_str("hex64"), True),
            "accounting": F(
                s_obj(
                    {
                        "status": F(s_str(enum=T.ACCOUNTING_VERDICTS), True),
                        "checks": F(s_arr(s_check_entry), True),
                    }
                ),
                True,
            ),
            "issues": F(s_arr(s_issue), True),
            "blobs": F(s_arr(s_str("digest"), unique=True)),
        }
    ),
}

def check_record(record: object, kind: str | None = None, *, version: str | None = None) -> list[Finding]:
    """Structural findings of one parsed record (empty list: structurally valid).

    ``kind`` is taken from ``record["k"]`` when omitted. An unknown or missing ``k`` is ``aer.schema.kind`` and
    stops the check. ``version`` is the file's ``execution.aer`` (the header's own value for the header; ``"0.1"`` when
    unknown, the frozen and stricter rules).
    """
    if not isinstance(record, dict):
        return [(PAT, "", "type_object")]
    k = kind if kind is not None else record.get("k")
    if not isinstance(k, str) or k not in _KINDS:
        return [("aer.schema.kind", "/k", "unknown_kind")]
    unk = record.get("unk")
    keys = frozenset(x for x in unk if isinstance(x, str)) if isinstance(unk, dict) else frozenset()
    if version is None:
        version = str(record.get("aer")) if k == "execution" and record.get("aer") in READABLE_VERSIONS else "0.1"
    sink = _Sink()
    _KINDS[k](record, "", sink, _Ctx(keys, unk if isinstance(unk, dict) else None, version))
    return sink.items


#: Core (kind) member names per record kind, excluding the envelope (used by the ext-shadowing check).
KIND_FIELDS: Final[dict[str, frozenset[str]]] = {
    kind: frozenset(name for name in check.fields if name not in _ENVELOPE_COMMON)
    for kind, check in _KINDS.items()
    if isinstance(check, _ObjCheck)
}
