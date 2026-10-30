"""Structural shapes: one declaration that is both an in-code validator and a JSON Schema (draft 2020-12) fragment.

The corpus-layer documents (``corpus.json`` and the ``$defs`` of ``schemas/corpus-0.1.schema.json``: index row, register
entry, derivation document, ``raw/members.jsonl`` row; HL H.2.1) are declared once, as :class:`Shape` trees, in
:mod:`agentprov.corpus.manifest`. Each shape

* checks a parsed JSON value and appends :class:`Issue` records (``check``), and
* renders itself as a JSON Schema fragment (``schema``).

The published schema file is generated from these declarations and a test pins the committed file equal to the
generated one; a Hypothesis test (HL-T1) checks, on mutated documents, that the in-code check and the
:mod:`jsonschema` reading of the generated schema agree. The in-code validator stays authoritative (H.2.1(2)): the
manifest validator adds **semantic** checks that JSON Schema cannot express (no floating-point numbers, sorted arrays,
digest equalities, count reconciliation), reported with ``level = "semantic"``.

Regular expressions: a shape's pattern is written without anchors; the in-code check uses :func:`re.fullmatch` and the
schema gets ``^(?:…)$``. (Under Python's ``re.search`` a ``$`` also matches before a final line feed, so the schema
reading is weaker than the in-code check on strings that end in ``\\n``; nothing in a corpus-layer document may.)
Booleans are never integers, and floating-point numbers are never integers (H.1.4(3)), whatever their value.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

__all__ = [
    "Arr",
    "Bool",
    "Const",
    "Enum",
    "Int",
    "Issue",
    "MapOf",
    "Null",
    "Nullable",
    "Obj",
    "Ref",
    "Shape",
    "Str",
    "Tagged",
    "pointer_join",
]

_I_JSON_MAX: Final = 2**53 - 1


@dataclass(frozen=True, slots=True)
class Issue:
    """One validation finding. ``pointer`` is a JSON Pointer into the document; ``level`` is ``schema`` (also caught by
    the published JSON Schema) or ``semantic`` (in-code only)."""

    pointer: str
    code: str
    detail: str
    level: str = "schema"


def pointer_join(base: str, token: str | int) -> str:
    text = str(token).replace("~", "~0").replace("/", "~1")
    return f"{base}/{text}"


def _kind(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, Mapping):
        return "object"
    return "unknown"


class Shape:
    """Base class: ``check(value, pointer, issues, defs)`` and ``schema()``."""

    def check(self, value: Any, pointer: str, issues: list[Issue], defs: Mapping[str, Shape]) -> None:
        raise NotImplementedError

    def schema(self) -> dict[str, Any]:
        raise NotImplementedError

    def _type_error(self, value: Any, pointer: str, issues: list[Issue], expected: str) -> None:
        issues.append(Issue(pointer, "type", f"expected {expected}, found {_kind(value)}"))


@dataclass(frozen=True)
class Str(Shape):
    pattern: str | None = None
    min_len: int = 0
    max_len: int | None = None

    def check(self, value: Any, pointer: str, issues: list[Issue], defs: Mapping[str, Shape]) -> None:
        if not isinstance(value, str):
            self._type_error(value, pointer, issues, "a string")
            return
        if len(value) < self.min_len or (self.max_len is not None and len(value) > self.max_len):
            issues.append(Issue(pointer, "length", "string length out of range"))
        if self.pattern is not None and re.fullmatch(self.pattern, value) is None:
            issues.append(Issue(pointer, "pattern", "string does not match its pattern"))

    def schema(self) -> dict[str, Any]:
        out: dict[str, Any] = {"type": "string"}
        if self.min_len:
            out["minLength"] = self.min_len
        if self.max_len is not None:
            out["maxLength"] = self.max_len
        if self.pattern is not None:
            out["pattern"] = f"^(?:{self.pattern})$"
        return out


@dataclass(frozen=True)
class Int(Shape):
    minimum: int | None = 0
    maximum: int | None = _I_JSON_MAX

    def check(self, value: Any, pointer: str, issues: list[Issue], defs: Mapping[str, Shape]) -> None:
        if isinstance(value, bool) or not isinstance(value, int):
            self._type_error(value, pointer, issues, "an integer")
            return
        if (self.minimum is not None and value < self.minimum) or (self.maximum is not None and value > self.maximum):
            issues.append(Issue(pointer, "range", "integer out of range"))

    def schema(self) -> dict[str, Any]:
        out: dict[str, Any] = {"type": "integer"}
        if self.minimum is not None:
            out["minimum"] = self.minimum
        if self.maximum is not None:
            out["maximum"] = self.maximum
        return out


@dataclass(frozen=True)
class Bool(Shape):
    def check(self, value: Any, pointer: str, issues: list[Issue], defs: Mapping[str, Shape]) -> None:
        if not isinstance(value, bool):
            self._type_error(value, pointer, issues, "a boolean")

    def schema(self) -> dict[str, Any]:
        return {"type": "boolean"}


@dataclass(frozen=True)
class Null(Shape):
    def check(self, value: Any, pointer: str, issues: list[Issue], defs: Mapping[str, Shape]) -> None:
        if value is not None:
            self._type_error(value, pointer, issues, "null")

    def schema(self) -> dict[str, Any]:
        return {"type": "null"}


@dataclass(frozen=True)
class Const(Shape):
    value: str | int | bool

    def check(self, value: Any, pointer: str, issues: list[Issue], defs: Mapping[str, Shape]) -> None:
        if _kind(value) != _kind(self.value) or value != self.value:
            issues.append(Issue(pointer, "const", "unexpected value"))

    def schema(self) -> dict[str, Any]:
        return {"const": self.value}


@dataclass(frozen=True)
class Enum(Shape):
    values: tuple[str, ...]

    def check(self, value: Any, pointer: str, issues: list[Issue], defs: Mapping[str, Shape]) -> None:
        if not isinstance(value, str) or value not in self.values:
            issues.append(Issue(pointer, "enum", "value outside the closed vocabulary"))

    def schema(self) -> dict[str, Any]:
        return {"enum": list(self.values)}


@dataclass(frozen=True)
class Nullable(Shape):
    inner: Shape

    def check(self, value: Any, pointer: str, issues: list[Issue], defs: Mapping[str, Shape]) -> None:
        if value is not None:
            self.inner.check(value, pointer, issues, defs)

    def schema(self) -> dict[str, Any]:
        return {"anyOf": [{"type": "null"}, self.inner.schema()]}


@dataclass(frozen=True)
class Arr(Shape):
    items: Shape
    min_items: int = 0

    def check(self, value: Any, pointer: str, issues: list[Issue], defs: Mapping[str, Shape]) -> None:
        if not isinstance(value, list):
            self._type_error(value, pointer, issues, "an array")
            return
        if len(value) < self.min_items:
            issues.append(Issue(pointer, "min_items", f"at least {self.min_items} item(s)"))
        for i, item in enumerate(value):
            self.items.check(item, pointer_join(pointer, i), issues, defs)

    def schema(self) -> dict[str, Any]:
        out: dict[str, Any] = {"type": "array", "items": self.items.schema()}
        if self.min_items:
            out["minItems"] = self.min_items
        return out


@dataclass(frozen=True)
class Obj(Shape):
    """A closed object: ``required`` and ``optional`` members, nothing else (H.2.1(2))."""

    required: Mapping[str, Shape]
    optional: Mapping[str, Shape] = field(default_factory=dict)

    def check(self, value: Any, pointer: str, issues: list[Issue], defs: Mapping[str, Shape]) -> None:
        if not isinstance(value, Mapping):
            self._type_error(value, pointer, issues, "an object")
            return
        for name in sorted(set(self.required) - set(value)):
            issues.append(Issue(pointer_join(pointer, name), "required", "missing member"))
        for name in sorted(set(value) - set(self.required) - set(self.optional), key=str):
            issues.append(Issue(pointer_join(pointer, str(name)), "additional", "unknown member (closed object)"))
        for name, shape in (*self.required.items(), *self.optional.items()):
            if name in value:
                shape.check(value[name], pointer_join(pointer, name), issues, defs)

    def schema(self) -> dict[str, Any]:
        properties = {name: shape.schema() for name, shape in sorted({**self.required, **self.optional}.items())}
        return {
            "type": "object",
            "properties": properties,
            "required": sorted(self.required),
            "additionalProperties": False,
        }


@dataclass(frozen=True)
class MapOf(Shape):
    """An object used as a map: every key matches ``key_pattern`` (when given), every value has shape ``values``."""

    values: Shape
    key_pattern: str | None = None
    keys: tuple[str, ...] | None = None  # a closed key set (all optional)

    def check(self, value: Any, pointer: str, issues: list[Issue], defs: Mapping[str, Shape]) -> None:
        if not isinstance(value, Mapping):
            self._type_error(value, pointer, issues, "an object")
            return
        for key in sorted(value, key=str):
            here = pointer_join(pointer, str(key))
            if self.key_pattern is not None and re.fullmatch(self.key_pattern, str(key)) is None:
                issues.append(Issue(here, "key", "member name does not match its pattern"))
            if self.keys is not None and key not in self.keys:
                issues.append(Issue(here, "additional", "unknown member (closed key set)"))
            self.values.check(value[key], here, issues, defs)

    def schema(self) -> dict[str, Any]:
        out: dict[str, Any] = {"type": "object", "additionalProperties": self.values.schema()}
        if self.key_pattern is not None:
            out["propertyNames"] = {"pattern": f"^(?:{self.key_pattern})$"}
        if self.keys is not None:
            out["propertyNames"] = {"enum": list(self.keys)}
        return out


@dataclass(frozen=True)
class Tagged(Shape):
    """A tagged union of closed objects on member ``tag`` (e.g. ``Origin`` on ``kind``)."""

    tag: str
    variants: Mapping[str, Obj]

    def check(self, value: Any, pointer: str, issues: list[Issue], defs: Mapping[str, Shape]) -> None:
        if not isinstance(value, Mapping):
            self._type_error(value, pointer, issues, "an object")
            return
        kind = value.get(self.tag)
        if not isinstance(kind, str) or kind not in self.variants:
            issues.append(Issue(pointer_join(pointer, self.tag), "tag", "unknown variant"))
            return
        variant = self.variants[kind]
        Obj({**variant.required, self.tag: Const(kind)}, variant.optional).check(value, pointer, issues, defs)

    def schema(self) -> dict[str, Any]:
        return {
            "oneOf": [
                Obj({**variant.required, self.tag: Const(kind)}, variant.optional).schema()
                for kind, variant in sorted(self.variants.items())
            ]
        }


@dataclass(frozen=True)
class AnyOf(Shape):
    """The value has at least one of the shapes (used for small unions such as ``string | array of strings``)."""

    options: Sequence[Shape]

    def check(self, value: Any, pointer: str, issues: list[Issue], defs: Mapping[str, Shape]) -> None:
        best: list[Issue] | None = None
        for option in self.options:
            found: list[Issue] = []
            option.check(value, pointer, found, defs)
            if not found:
                return
            if best is None or len(found) < len(best):
                best = found
        issues.extend(best or [Issue(pointer, "any_of", "matches no alternative")])

    def schema(self) -> dict[str, Any]:
        return {"anyOf": [o.schema() for o in self.options]}


@dataclass(frozen=True)
class Ref(Shape):
    """A reference to a named ``$defs`` entry (resolved through ``defs`` when checking)."""

    name: str

    def check(self, value: Any, pointer: str, issues: list[Issue], defs: Mapping[str, Shape]) -> None:
        defs[self.name].check(value, pointer, issues, defs)

    def schema(self) -> dict[str, Any]:
        return {"$ref": f"#/$defs/{self.name}"}


__all__ += ["AnyOf"]
