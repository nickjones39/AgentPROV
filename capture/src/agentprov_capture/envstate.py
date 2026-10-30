"""Environment-state digests, snapshots and diffs (C.13.3 ``pass.start``/``pass.end``/``state``; B CAP-18, F-12).

Extracted from the baseline ``agentdojo_prov/envstate.py`` (rules E-1...E-5 of the audit) and changed in exactly the
ways the specification decided:

* **E-1** ``dump_state``: a duck-typed ``model_dump(mode="json")`` (pydantic), else a JSON round trip with ``default=str``.
  No benchmark import.
* **E-2 (changed)** the canonical form is **JCS** (RFC 8785) of the dump, and the digest is a mapping
  ``{"sha256": <hex, no prefix>, "canon": "jcs-rfc8785"}`` that is the ``env`` member of ``pass.start`` as is
  (C.13.8). The baseline's ``sort_keys``/``ensure_ascii=False`` form is *not* reproduced; baseline digests are
  imported with ``canon: "adprov.envstate@1"`` (C.3) and never recomputed. Values JCS cannot carry are encoded as in
  C.11.2-C.11.3 before hashing: integers beyond +-(2^53-1) as ``{"$int": "<decimal>"}``, ``NaN``/``Infinity``/
  ``-0.0`` as ``{"$float": ...}``, lone surrogates as ``{"$utf16": <base64>}``, objects whose first-level member
  starts with ``$`` as ``{"$lit": <object>}``.
* **E-3** keys are walked in sorted order; list elements are matched by canonical content (multiset), and a
  same-multiset different-order list gives one ``reordered`` entry.
* **E-4 (F-12 fixed)** values are cut at ``VALUE_CAP`` characters and entries at ``ENTRY_CAP``; ``truncated`` is
  true if **any** entry or value was cut (the baseline ignored value cuts).
* **E-5** the end record carries ``changed`` and a ``diff`` only when the state changed.

Paths in diff entries are RFC 6901 JSON Pointers (the baseline used dotted paths, ambiguous for keys containing a
dot); an element added to or removed from a list is reported at the pointer of the *list* with ``"element": true``.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
from typing import Any, Final

import rfc8785

__all__ = [
    "CANON",
    "DIFF_FORMAT",
    "ENTRY_CAP",
    "VALUE_CAP",
    "diff",
    "digest",
    "dump_state",
    "end_env",
    "normalise",
    "snapshot",
]

CANON: Final = "jcs-rfc8785"
DIFF_FORMAT: Final = "agentprov.envdiff@1"
VALUE_CAP: Final = 400
ENTRY_CAP: Final = 200
_MAX_SAFE_INT: Final = 2**53 - 1


def dump_state(env: Any) -> Any:
    """The environment as plain JSON-able data (E-1): a pydantic-style ``model_dump(mode="json")`` or a JSON round trip
    with ``default=str``."""
    if hasattr(env, "model_dump"):
        return env.model_dump(mode="json")
    return json.loads(json.dumps(env, default=str))


def normalise(value: Any) -> Any:
    """Encode what JCS cannot carry (C.11.2-C.11.3) so ``rfc8785`` accepts any plain JSON-able value."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value if abs(value) <= _MAX_SAFE_INT else {"$int": str(value)}
    if isinstance(value, float):
        if math.isnan(value):
            return {"$float": "NaN"}
        if math.isinf(value):
            return {"$float": "Infinity" if value > 0 else "-Infinity"}
        if value == 0.0 and math.copysign(1.0, value) < 0:
            return {"$float": "-0"}
        return value
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            units = value.encode("utf-16-be", "surrogatepass")
            return {"$utf16": base64.b64encode(units).decode("ascii")}
        return value
    if isinstance(value, dict):
        out = {normalise_key(k): normalise(v) for k, v in value.items()}
        if any(k.startswith("$") for k in out):
            return {"$lit": out}
        return out
    if isinstance(value, (list, tuple)):
        return [normalise(v) for v in value]
    raise TypeError(f"cannot canonicalise a {type(value).__name__}; dump_state() the environment first")


def normalise_key(key: Any) -> str:
    if not isinstance(key, str):
        raise TypeError("object keys must be strings; dump_state() the environment first")
    return key


def snapshot(dump: Any) -> bytes:
    """The canonical bytes of an environment dump: JCS of :func:`normalise` (store as a blob for a full snapshot)."""
    return rfc8785.dumps(normalise(dump))


def digest(dump: Any) -> dict[str, str]:
    """``{"sha256": <hex>, "canon": "jcs-rfc8785"}`` of the dump (E-2): the ``env`` of ``pass.start``."""
    return {"sha256": hashlib.sha256(snapshot(dump)).hexdigest(), "canon": CANON}


def _canon_text(value: Any) -> str:
    """JCS text of an already normalised value."""
    return rfc8785.dumps(value).decode("utf-8")


def _ptr(parts: list[str]) -> str:
    return "".join("/" + p.replace("~", "~0").replace("/", "~1") for p in parts)


def _cut(value: Any, cuts: list[bool]) -> str:
    text = _canon_text(value)
    if len(text) > VALUE_CAP:
        cuts[0] = True
        return text[:VALUE_CAP] + "…"
    return text


def _walk(before: Any, after: Any, path: list[str], out: list[dict[str, Any]], cuts: list[bool]) -> None:
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(set(before) | set(after), key=str):
            sub = [*path, str(key)]
            if key not in after:
                out.append({"op": "removed", "path": _ptr(sub), "before": _cut(before[key], cuts)})
            elif key not in before:
                out.append({"op": "added", "path": _ptr(sub), "after": _cut(after[key], cuts)})
            else:
                _walk(before[key], after[key], sub, out, cuts)
    elif isinstance(before, list) and isinstance(after, list):
        # elements are matched by content, not position: deleting the first element must not report every later one
        canon_before = [_canon_text(x) for x in before]
        canon_after = [_canon_text(x) for x in after]
        remaining = list(canon_after)
        gone = []
        for item, c in zip(before, canon_before, strict=True):
            if c in remaining:
                remaining.remove(c)
            else:
                gone.append(item)
        if not gone and not remaining and canon_before != canon_after:
            out.append({"op": "reordered", "path": _ptr(path)})
        for item in gone:
            out.append({"op": "removed", "path": _ptr(path), "element": True, "before": _cut(item, cuts)})
        for c in remaining:
            out.append({"op": "added", "path": _ptr(path), "element": True, "after": _cut(json.loads(c), cuts)})
    elif _canon_text(before) != _canon_text(after):
        out.append({"op": "changed", "path": _ptr(path), "before": _cut(before, cuts), "after": _cut(after, cuts)})


def diff(before: Any, after: Any) -> dict[str, Any]:
    """What a pass changed, as the ``env.diff`` mapping ``{"format", "value": {"n_changes", "entries"}, "truncated"}``.

    Lossy by design (value and entry caps); the digests, not the diff, decide whether two states are equal.
    """
    entries: list[dict[str, Any]] = []
    cuts = [False]
    _walk(normalise(before), normalise(after), [], entries, cuts)
    return {
        "format": DIFF_FORMAT,
        "value": {"n_changes": len(entries), "entries": entries[:ENTRY_CAP]},
        "truncated": cuts[0] or len(entries) > ENTRY_CAP,
    }


def end_env(before: Any, after: Any, *, snapshot_ref: dict[str, Any] | None = None, with_diff: bool = True) -> dict[str, Any]:
    """The ``env`` member of ``pass.end`` (E-5): the digest of ``after``, ``changed`` (digest differs from ``before``),
    a ``diff`` only when changed (and ``with_diff``), and an optional ``snapshot`` blob reference."""
    after_digest = digest(after)
    out: dict[str, Any] = {**after_digest, "changed": digest(before) != after_digest}
    if out["changed"] and with_diff:
        out["diff"] = diff(before, after)
    if snapshot_ref is not None:
        out["snapshot"] = snapshot_ref
    return out
