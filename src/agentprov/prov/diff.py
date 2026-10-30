"""Order-insensitive semantic diff of two PROV-JSON documents (HL H.8.4(3); MN N.2.4(5); B COR-21).

Ported from the baseline's ``agentdojo_prov.recompute.diff_documents`` (AgentDojo-PROV at ``579a908``, MIT licence,
same author). The baseline listing is kept: node and relation additions and removals by id (``-section/id``,
``+section/id``) and, for ids present in both documents, every attribute whose value moved (``~section/id.attr: old ->
new``). Two changes make it fit ``agentprov-prov/0.1`` and the bump discipline of H.8.4:

* **Bundles are recursed.** A bundled document keeps most statements inside ``bundle/<bundle id>``; a bundle present in
  both documents is diffed section by section, its lines prefixed ``bundle/<id>/``. A bundle present in only one is one
  ``-``/``+`` line, as any other node.
* **Values are compared by type and value**, never with Python ``==``. ``True == 1 == 1.0`` in Python, so the baseline
  listing could not show a ``true`` -> ``1`` or ``3`` -> ``3.0`` change (baseline R2, HL-T6). Here a bool, an int and a
  float are three different things, recursively through lists and objects.

Whether an execution counts as changed is decided by comparing canonical bytes (``corpus.derive``), never by this
listing: it explains a byte difference, it does not detect one. Values are rendered with ``repr`` and may quote source
data; callers escape every line before it reaches a terminal (``escape_untrusted``, R-42).

Pure: no I/O.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

__all__ = ["diff_documents", "same_value"]

_BUNDLE = "bundle"


def _kind(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if value is None:
        return "null"
    if isinstance(value, Mapping):
        return "object"
    if isinstance(value, list | tuple):
        return "array"
    return type(value).__name__


def same_value(a: Any, b: Any) -> bool:
    """Type-faithful equality of two JSON values: ``True``, ``1`` and ``1.0`` all differ (iterative)."""
    stack: list[tuple[Any, Any]] = [(a, b)]
    while stack:
        x, y = stack.pop()
        kind = _kind(x)
        if kind != _kind(y):
            return False
        if kind == "object":
            if set(x) != set(y):
                return False
            stack.extend((x[k], y[k]) for k in x)
        elif kind == "array":
            if len(x) != len(y):
                return False
            stack.extend(zip(x, y, strict=True))
        elif kind == "float":
            if repr(x) != repr(y):  # -0.0 and 0.0 stay distinct
                return False
        elif x != y:
            return False
    return True


def _section_diff(prefix: str, section: str, o_sec: Any, n_sec: Any, out: list[str]) -> None:
    if not isinstance(o_sec, Mapping) or not isinstance(n_sec, Mapping):
        if not same_value(o_sec, n_sec):
            out.append(f"{prefix}{section}: {o_sec!r} -> {n_sec!r}")
        return
    for gone in sorted(set(o_sec) - set(n_sec)):
        out.append(f"-{prefix}{section}/{gone}")
    for added in sorted(set(n_sec) - set(o_sec)):
        out.append(f"+{prefix}{section}/{added}")
    for key in sorted(set(o_sec) & set(n_sec)):
        o_item, n_item = o_sec[key], n_sec[key]
        if section == _BUNDLE and not prefix and isinstance(o_item, Mapping) and isinstance(n_item, Mapping):
            _document_diff(f"{_BUNDLE}/{key}/", o_item, n_item, out)
            continue
        o_item = {} if o_item is None else o_item
        n_item = {} if n_item is None else n_item
        if not isinstance(o_item, Mapping) or not isinstance(n_item, Mapping):
            if not same_value(o_item, n_item):
                out.append(f"~{prefix}{section}/{key}: {o_item!r} -> {n_item!r}")
            continue
        for attr in sorted(set(o_item) | set(n_item)):
            present_o, present_n = attr in o_item, attr in n_item
            o_val, n_val = o_item.get(attr), n_item.get(attr)
            if present_o != present_n or not same_value(o_val, n_val):
                out.append(f"~{prefix}{section}/{key}.{attr}: {o_val!r} -> {n_val!r}")


def _document_diff(prefix: str, old: Mapping[str, Any], new: Mapping[str, Any], out: list[str]) -> None:
    for section in sorted(set(old) | set(new)):
        _section_diff(prefix, section, old.get(section) or {}, new.get(section) or {}, out)


def diff_documents(old: Mapping[str, Any], new: Mapping[str, Any]) -> list[str]:
    """Human-readable list of what changed between two PROV-JSON documents (see the module docstring).

    Order-insensitive: PROV-JSON sections are objects keyed by node id, so a reordering is not a change. Relation ids of
    the baseline graphs are positional (``u_00006``), so an inserted relation there shows as a run of paired ``-``/``+``
    lines; ``agentprov-prov/0.1`` relation ids are content-derived, so its lines mean what they say.
    """
    out: list[str] = []
    _document_diff("", old, new, out)
    return out
