"""Lone UTF-16 surrogates in source text, mapped with a disclosure (regeneration-batch item 7, escaping audit F-01;
DECISIONS D-23, D-378).

A source written with ``json.dumps(ensure_ascii=True)`` can carry an escaped lone surrogate (``"\\ud83d"``, an emoji cut
in half), which the strict loader keeps as a lone surrogate code point. :func:`agentprov.aer.canon.encode_value` writes
such a string as the reserved ``{"$utf16": ...}`` form, which is valid only in ``Json`` positions (``args``, ``value``,
``content``, ``params``, ``ext``, ...); a typed string field (a message part's ``text``, a tool ``name``) rejects it, and
an object key cannot carry it at all, so before this the whole execution became a degenerate ``adapter_defect`` AER.

aer/0.1 stays frozen (D-23). Instead the mappers of the batch's families (``agentdojo``, ``adprov``, ``inspect``) run
:func:`scrub_record` over each finished record: every lone surrogate in a typed string position, and in any object key,
is replaced by U+FFFD; a ``$utf16`` value in a ``Json`` position is kept (it is lossless there). Each replaced pointer is
tagged ``D`` and cites the family's rule ``<ns>.lone_surrogate_replaced@1`` scoped to it, and the mapper seals an info
issue ``<ns>.lone_surrogate_replaced`` listing the records. The original stays in the raw store; nothing is dropped.
Pure.
"""

from __future__ import annotations

import base64
from collections.abc import Callable, Sequence
from typing import Any, Final

from agentprov.aer.canon import pointer_escape

__all__ = ["JSON_FIELDS", "has_lone_surrogate", "replace_lone_surrogates", "scrub_keys", "scrub_record", "surrogates"]

#: Record fields whose value is ``Json`` (C.3, ``aer._structure`` ``s_json``/``s_ext``): a ``$utf16`` value below them is
#: valid and kept. A pointer through any of these names is a ``Json`` position.
JSON_FIELDS: Final = frozenset({"args", "args_effective", "value", "params", "returned", "content", "patch", "ext"})
REPLACEMENT: Final = "�"


def has_lone_surrogate(text: str) -> bool:
    """Whether ``text`` holds a code point U+D800..U+DFFF (a lone surrogate: Python ``str`` never pairs them)."""
    return any("\ud800" <= ch <= "\udfff" for ch in text)


def replace_lone_surrogates(text: str) -> str:
    """``text`` with every lone surrogate replaced by U+FFFD."""
    return "".join(REPLACEMENT if "\ud800" <= ch <= "\udfff" else ch for ch in text)


def scrub_keys(value: Any) -> tuple[Any, bool]:
    """``value`` with every object key's lone surrogates replaced (values untouched), and whether any key changed.

    For a ``Json`` value about to be encoded: a key cannot be ``$utf16``-wrapped (C.11.3), so it is replaced. Two keys
    that become equal keep the first value (a collision is itself disclosed by the replacement)."""
    changed = False
    if isinstance(value, dict):
        out: dict[Any, Any] = {}
        for key, item in value.items():
            new_item, inner = scrub_keys(item)
            changed |= inner
            if isinstance(key, str) and has_lone_surrogate(key):
                key, changed = replace_lone_surrogates(key), True
            out.setdefault(key, new_item)
        return (out, True) if changed else (value, False)  # unchanged: the caller keeps its own object
    if isinstance(value, list):
        items = [scrub_keys(item) for item in value]
        if any(inner for _, inner in items):
            return [item for item, _ in items], True
        return value, False
    return value, False


def _is_json(tokens: tuple[str, ...]) -> bool:
    return any(token in JSON_FIELDS for token in tokens)


def scrub_record(record: dict[str, Any], cite: Callable[[str], str]) -> list[str]:
    """Replace the lone surrogates of a finished record in place (module docstring); return the replaced pointers.

    A plain ``str`` holding a lone surrogate (assigned without encoding) is replaced wherever it is; a ``$utf16`` value
    is decoded and replaced only outside ``Json`` positions. Each replaced pointer gets ``evf`` ``D`` (``I`` in an ``I``
    record) and the rule
    ``cite(pointer)`` (the mapper's scoped citation of its ``<ns>.lone_surrogate_replaced@1``)."""
    replaced: list[str] = []

    def walk(node: Any, tokens: tuple[str, ...]) -> Any:
        if isinstance(node, str):
            if has_lone_surrogate(node):
                replaced.append("".join("/" + pointer_escape(t) for t in tokens))
                return replace_lone_surrogates(node)
            return node
        if isinstance(node, dict):
            if set(node) == {"$utf16"} and isinstance(node["$utf16"], str) and not _is_json(tokens):
                raw = base64.b64decode(node["$utf16"])
                replaced.append("".join("/" + pointer_escape(t) for t in tokens))
                return replace_lone_surrogates(raw.decode("utf-16-be", "surrogatepass"))
            out: dict[str, Any] = {}
            for key, item in node.items():
                new_key = key
                if isinstance(key, str) and has_lone_surrogate(key):
                    new_key = replace_lone_surrogates(key)
                    replaced.append("".join("/" + pointer_escape(t) for t in (*tokens, new_key)))
                out.setdefault(new_key, walk(item, (*tokens, str(new_key))))
            return out
        if isinstance(node, list):
            return [walk(item, (*tokens, str(i))) for i, item in enumerate(node)]
        return node

    for key in [k for k in record if k not in ("k", "id", "evf", "rule", "unk", "src", "after")]:
        record[key] = walk(record[key], (key,))
    if replaced:
        evf = record.setdefault("evf", {})
        rules = record.setdefault("rule", [])
        floor = "I" if record.get("ev") == "I" else "D"  # never stronger than the record (C.6.5 rule 1)
        for pointer in replaced:
            evf[pointer] = "I" if evf.get(pointer) == "I" else floor
            ref = cite(pointer)
            if ref not in rules:
                rules.append(ref)
    return replaced


def surrogates(mapper: Any, records: Sequence[dict[str, Any]], namespace: str) -> None:
    """The mappers' post-pass: :func:`scrub_record` over ``records`` citing ``<namespace>.lone_surrogate_replaced@1``
    through ``mapper.ctx.rule`` (the scoped citation, as given), then one info issue ``<namespace>.lone_surrogate_replaced`` listing the
    records it changed, plus ``exec`` when ``mapper.surrogate_keys`` says a source key was replaced before mapping (its
    position in the AER is not tracked; the replacement character discloses it). Nothing when no surrogate occurs."""
    rule = f"{namespace}.lone_surrogate_replaced@1"
    # cited as given: the rule is code-independent (a transformation by AgentPROV), never an _unverified twin
    changed = [str(r["id"]) for r in records if scrub_record(r, lambda p: mapper.ctx.rule(rule, p))]
    if getattr(mapper, "surrogate_keys", False) and "exec" not in changed:
        changed.insert(0, "exec")
    if changed:
        issue = mapper.defer if hasattr(mapper, "defer") else mapper.issue
        issue(f"{namespace}.lone_surrogate_replaced", changed, rule, severity="info",
              detail="lone UTF-16 surrogates replaced by U+FFFD (the raw store keeps the original)")
