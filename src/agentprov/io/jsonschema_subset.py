"""A small stdlib subset of JSON Schema, shared below the adapter layer (D.4.1; C.14.4).

The keywords are those of the ``family.schema.json`` checker of ``agentprov.adapters.agentdojo.profile`` (``type``,
``properties``, ``additionalProperties``, ``required``, ``items``, ``enum``, ``pattern``, ``minimum``), plus the type
``null`` and the annotation keywords ``$schema``, ``title`` and ``description``, which constrain nothing. It lives in
layer L0 so that the SEM validator (L2) can check a namespaced annotation value against the schema its semantics profile
declares (C.14.2 ``type``; C.14.4) without importing an adapter family. (The AgentDojo family keeps its own copy until it
re-exports this one; the two agree on every keyword the family schema uses.)

``pattern`` runs a regular expression. A schema read from an untrusted file (a SEM header's ``ns``) must not run one:
Python's ``re`` has no time limit, so a hostile pattern could stall the validator. Callers pass ``patterns=False`` for
such schemas; ``pattern`` is then not evaluated and :func:`check_against_schema` says so through ``skipped``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from functools import cache
from typing import Any, Final

__all__ = ["SUPPORTED_KEYWORDS", "check_against_schema", "pattern_matches", "unsupported_keywords"]

_TYPES: Final = {
    "object": (dict, Mapping),
    "array": (list, tuple),
    "string": (str,),
    "boolean": (bool,),
}
#: Every keyword this checker understands; anything else makes a schema uncheckable (:func:`unsupported_keywords`).
SUPPORTED_KEYWORDS: Final = frozenset(
    {"type", "properties", "additionalProperties", "required", "items", "enum", "pattern", "minimum",
     "$schema", "title", "description"}
)  # fmt: skip
_TYPE_NAMES: Final = frozenset({"object", "array", "string", "boolean", "integer", "number", "null"})


def _end_anchored(pattern: str) -> str:
    """``pattern`` with every top-level ``$`` written as ``\\Z``.

    JSON Schema patterns are ECMA-262 expressions, where ``$`` matches only at the very end of the input; Python's ``$``
    also matches before a trailing newline, so ``^m[0-9]+$`` accepted ``"m12\\n"`` (escaping audit F-06). Escaped
    characters and character classes are copied as they are."""
    out: list[str] = []
    i, n = 0, len(pattern)
    in_class = False
    while i < n:
        char = pattern[i]
        if char == "\\":
            out.append(pattern[i : i + 2])
            i += 2
            continue
        if in_class:
            in_class = char != "]"
        elif char == "[":
            in_class = True
            out.append(char)
            i += 1
            if pattern.startswith("^", i):  # "[^" and a "]" right after the opener is a literal
                out.append("^")
                i += 1
            if pattern.startswith("]", i):
                out.append("]")
                i += 1
            continue
        elif char == "$":
            out.append("\\Z")
            i += 1
            continue
        out.append(char)
        i += 1
    return "".join(out)


@cache
def _compiled(pattern: str) -> re.Pattern[str]:
    return re.compile(_end_anchored(pattern))


def pattern_matches(pattern: str, value: str) -> bool:
    """Whether ``pattern`` (a JSON Schema ``pattern``, searched, not anchored implicitly) matches ``value``, with ``$``
    meaning the end of the input and nothing else (see :func:`_end_anchored`)."""
    return _compiled(pattern).search(value) is not None


def _json_equal(a: object, b: object) -> bool:
    """JSON value equality: Python's ``==`` except that a boolean never equals a number (``True == 1`` in Python)."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a is b
    if isinstance(a, Mapping) and isinstance(b, Mapping):
        return a.keys() == b.keys() and all(_json_equal(a[k], b[k]) for k in a)
    if isinstance(a, list | tuple) and isinstance(b, list | tuple):
        return len(a) == len(b) and all(_json_equal(x, y) for x, y in zip(a, b, strict=True))
    if isinstance(a, Mapping | list | tuple) or isinstance(b, Mapping | list | tuple):
        return False
    return a == b


def _type_ok(value: object, expected: str) -> bool:
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if expected == "null":
        return value is None
    return isinstance(value, _TYPES[expected])


def unsupported_keywords(schema: object, where: str = "") -> list[str]:
    """Pointers into ``schema`` where it is not a schema this checker can evaluate: a non-object, an unknown keyword,
    an unknown ``type``, or a malformed ``properties``/``items``/``required``/``enum``/``pattern``/``minimum``.
    ``[]`` when every keyword is understood. Iterative over nested schemas (bounded by the input's own depth cap)."""
    out: list[str] = []
    stack: list[tuple[object, str]] = [(schema, where)]
    while stack:
        node, at = stack.pop()
        if not isinstance(node, Mapping):
            out.append(at or "/")
            continue
        for key in node:
            if key not in SUPPORTED_KEYWORDS:
                out.append(f"{at}/{key}")
        expected = node.get("type")
        if "type" in node and (not isinstance(expected, str) or expected not in _TYPE_NAMES):  # a list: unhashable
            out.append(f"{at}/type")
        props = node.get("properties", {})
        if not isinstance(props, Mapping):
            out.append(f"{at}/properties")
        else:
            stack.extend((sub, f"{at}/properties/{name}") for name, sub in props.items())
        extra = node.get("additionalProperties", True)
        if isinstance(extra, Mapping):
            stack.append((extra, f"{at}/additionalProperties"))
        elif not isinstance(extra, bool):
            out.append(f"{at}/additionalProperties")
        if "items" in node:
            stack.append((node["items"], f"{at}/items"))
        required = node.get("required", [])
        if not isinstance(required, list) or not all(isinstance(r, str) for r in required):
            out.append(f"{at}/required")
        if "enum" in node and not isinstance(node["enum"], list):
            out.append(f"{at}/enum")
        if "pattern" in node and not isinstance(node["pattern"], str):
            out.append(f"{at}/pattern")
        minimum = node.get("minimum", 0)
        if not isinstance(minimum, int | float) or isinstance(minimum, bool):
            out.append(f"{at}/minimum")
    return sorted(out)


def check_against_schema(
    value: object,
    schema: Mapping[str, Any],
    where: str = "",
    *,
    patterns: bool = True,
    skipped: list[str] | None = None,
) -> list[str]:
    """Problems of ``value`` under ``schema`` (the subset named in the module docstring); ``[]`` when it conforms.

    With ``patterns=False`` a ``pattern`` keyword is not evaluated; its pointer is appended to ``skipped`` (when given).
    The schema is assumed to have passed :func:`unsupported_keywords`.
    """
    out: list[str] = []
    expected = schema.get("type")
    if isinstance(expected, str) and not _type_ok(value, expected):
        return [f"{where or '/'}: expected {expected}"]
    if "enum" in schema and not any(_json_equal(value, member) for member in schema["enum"]):
        out.append(f"{where or '/'}: not one of the enumerated values")
    if isinstance(value, str) and "pattern" in schema:
        if not patterns:
            if skipped is not None:
                skipped.append(where or "/")
        elif not pattern_matches(schema["pattern"], value):
            out.append(f"{where or '/'}: does not match the pattern")
    if (isinstance(value, int | float) and not isinstance(value, bool) and "minimum" in schema
            and value < schema["minimum"]):
        out.append(f"{where or '/'}: below the minimum")
    if isinstance(value, Mapping):
        props: Mapping[str, Any] = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        for name in schema.get("required", ()):
            if name not in value:
                out.append(f"{where}/{name}: required")
        for key, item in value.items():
            if key in props:
                out.extend(check_against_schema(item, props[key], f"{where}/{key}", patterns=patterns, skipped=skipped))
            elif extra is False:
                out.append(f"{where}/{key}: not allowed (closed schema)")
            elif isinstance(extra, Mapping):
                out.extend(check_against_schema(item, extra, f"{where}/{key}", patterns=patterns, skipped=skipped))
    if isinstance(value, list | tuple) and isinstance(schema.get("items"), Mapping):
        for i, item in enumerate(value):
            out.extend(check_against_schema(item, schema["items"], f"{where}/{i}", patterns=patterns, skipped=skipped))
    return out
