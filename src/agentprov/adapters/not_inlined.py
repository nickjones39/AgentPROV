"""Strings over 1 MiB of UTF-8 not inlined: the one D-934 pass the mappers share (DECISIONS D-934, D-1063; reviews
UC-38, UC-41, AU-RC-1, AU-RC-2, AU-NC-307, AU-NC-308; regen-batch rows 181, 182 and 186).

The AER writer refuses an inline string whose UTF-8 encoding exceeds 1 MiB (C.2.1(6), AER-V01), so a single long text
made it refuse the whole execution (``adapter_defect``). After its redaction and lone-surrogate passes a mapper hands its
finished records to :func:`not_inlined`, which replaces every such string by ``{"not_inlined": {sha256, bytes}}`` of its
UTF-8 bytes:

- a ``{"$utf16": ...}`` value (a string holding a lone surrogate, C.11.3) is such a string as a whole (AU-RC-2): it is
  replaced when its decoded text exceeds 1 MiB or its base64, which the writer measures, does, and the digest is of the
  decoded text's UTF-8 (``surrogatepass``), never of the base64 and never inside the wrapper; a member named ``$utf16``
  inside a ``$lit`` body is a source key, never such a value; a wrapper that is not the encoder's base64 is left for the
  writer to judge;
- a typed text field cannot hold the digest object: a ``tool_result`` part's ``text`` becomes the part's ``value``, and a
  part holding only ``t`` and ``text`` (``text``, ``reasoning``, ``refusal``) becomes an ``other`` part of its source type
  whose ``value`` is the digest;
- a tool call's ``args_raw`` (a typed, optional string: the verbatim arguments text) is not copied: it leaves the part and
  its digest stands at ``ext.<ns>.args_raw_not_inlined.<k>`` for part *k* (AU-NC-307; the decoded ``args``, a ``Json``
  position, keep their own digests in place); a family that passes no namespace keeps ``args_raw`` where it is;
- any other typed position keeps the object and the writer refuses it as before: nothing is dropped to make it fit (a
  ``reasoning`` part with a ``signature``, say, is not turned into an ``other`` part);
- any ``Json`` position keeps the digest in place.

Everything that names a moved pointer follows it (UC-38, AU-RC-1): the ``evf`` and ``unk`` keys, every scoped rule
citation (the lone-surrogate pass's, a redaction's, a mapper's own) and the entries of the family's redaction listing
(``ext.<listing>.redacted``); otherwise the citation dangles and AER-V14 refuses the record. Each digest pointer is ``D``
(``I`` in an ``I`` record or where it already was, never above the record: C.6.5 rule 1) and cites the family's
``<ns>.content_not_inlined@1`` through ``cite``, as given: a transformation by AgentPROV, independent of the code that
wrote the log. The caller raises one info issue ``<ns>.content_not_inlined`` naming the records returned. The string
stays in the raw artefact the record's locator names. Pure.

``dtap`` keeps its own copy (D-934, UC-38), which this module follows; the AgentDojo family's pass
(``adapters/agentdojo/not_inlined.py``) uses the pieces here with its own record order and no ``args_raw`` move.
"""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Final

from agentprov.aer.canon import json_pointer

__all__ = ["META_FIELDS", "MIB", "cited", "move_listing", "moved_pointer", "not_inlined", "relink", "retype", "slim"]

MIB: Final = 1 << 20
#: Record fields that are AER metadata, never source content: the pass does not search them.
META_FIELDS: Final = frozenset({"k", "id", "ev", "by", "evf", "rule", "src", "unk", "after"})
#: Parts whose only content member is ``text``: an ``other`` part of the same type holds the digest instead.
_TEXT_ONLY: Final = frozenset({"t", "text"})


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def slim(node: Any, tokens: tuple[str, ...], found: list[str], literal: bool = False) -> Any:
    """``node`` with every string whose UTF-8 encoding exceeds 1 MiB replaced by its digest object; ``found`` collects
    the replaced pointers. A ``$utf16`` value counts as a whole, by its decoded text and by its base64 (module
    docstring)."""
    if isinstance(node, str):
        if len(node) <= MIB // 4:  # at most 4 UTF-8 bytes per code point
            return node
        return _digest_over_mib(node, tokens, found)
    if isinstance(node, dict):
        if not literal and set(node) == {"$utf16"} and isinstance(node["$utf16"], str):
            if len(node["$utf16"]) <= MIB * 8 // 9:  # at most 3/8 of a code unit per base64 digit, 3 UTF-8 bytes per unit
                return node
            try:
                text = base64.b64decode(node["$utf16"], validate=True).decode("utf-16-be", "surrogatepass")
            except (ValueError, UnicodeDecodeError):  # not the encoder's form: left for the writer to judge
                return node
            # the writer measures the base64 itself (AER-V01): a wrapper whose base64 exceeds 1 MiB is never kept, even
            # when its decoded text is shorter (about 2.67 base64 digits per code unit)
            return _digest_over_mib(text, tokens, found, node, force=len(node["$utf16"]) > MIB)
        wrapper = not literal and len(node) == 1 and "$lit" in node
        return {k: slim(v, (*tokens, str(k)), found, wrapper) for k, v in node.items()}
    if isinstance(node, list):
        return [slim(v, (*tokens, str(i)), found) for i, v in enumerate(node)]
    return node


def _digest_over_mib(text: str, tokens: tuple[str, ...], found: list[str], keep: Any = None, *,
                     force: bool = False) -> Any:
    """The digest object of ``text`` when its UTF-8 encoding exceeds 1 MiB (or ``force``), else ``keep`` (``text``
    when ``None``)."""
    raw = text.encode("utf-8", "surrogatepass")
    if len(raw) <= MIB and not force:
        return text if keep is None else keep
    found.append(json_pointer(*tokens))
    return {"not_inlined": {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}}


def moved_pointer(pointer: str, moved: Mapping[str, str]) -> str:
    """``pointer`` after the retyping ``moved`` (old pointer -> new): the pointer itself or one below it."""
    for old, new in moved.items():
        if old != new and (pointer == old or pointer.startswith(old + "/")):
            return new + pointer[len(old):]
    return pointer


def cited(ref: str, moved: Mapping[str, str]) -> str:
    """A scoped rule citation ``<rule>#<pointer>`` after the retyping ``moved``."""
    rule, sep, pointer = ref.partition("#")
    return rule + sep + moved_pointer(pointer, moved) if sep else ref


def _part(record: dict[str, Any], pointer: str, member: str) -> tuple[int, dict[str, Any]] | None:
    """Part *k* and its index when ``pointer`` is ``/parts/<k>/<member>`` of an existing part, else ``None``."""
    tokens = pointer.split("/")[1:]
    if len(tokens) != 3 or tokens[0] != "parts" or tokens[2] != member or not tokens[1].isdigit():
        return None
    parts = record.get("parts")
    k = int(tokens[1])
    if not isinstance(parts, list) or k >= len(parts) or not isinstance(parts[k], dict):
        return None
    return k, parts[k]


def retype(record: dict[str, Any], pointer: str, namespace: str | None) -> str:
    """Move a digest out of a typed string field it cannot stay in (module docstring); return the digest's pointer
    (``pointer`` itself for a ``Json`` position, or for a typed position it cannot take). ``namespace`` names the
    ``ext`` member that receives an ``args_raw`` digest; ``None`` leaves ``args_raw`` in place."""
    found = _part(record, pointer, "text")
    if found is not None:
        k, part = found
        if part.get("t") == "tool_result" and "value" not in part:
            part["value"] = part.pop("text")
        elif set(part) == _TEXT_ONLY and isinstance(part.get("t"), str):
            record["parts"][k] = {"t": "other", "type": part["t"], "value": part["text"]}
        else:  # a typed position the digest cannot take: left for the writer to refuse, as before
            return pointer
        return f"/parts/{k}/value"
    found = _part(record, pointer, "args_raw")
    if namespace is not None and found is not None and found[1].get("t") == "tool_call":
        k, part = found
        own = record.setdefault("ext", {}).setdefault(namespace, {})
        own.setdefault("args_raw_not_inlined", {})[str(k)] = part.pop("args_raw")
        return json_pointer("ext", namespace, "args_raw_not_inlined", str(k))
    return pointer


def move_listing(record: dict[str, Any], listing: str, moved: Mapping[str, str]) -> None:
    """The entries of the redaction listing ``ext.<listing>.redacted`` follow the retyping ``moved``."""
    entries = _dict(_dict(record.get("ext")).get(listing)).get("redacted")
    for entry in entries if isinstance(entries, list) else []:
        if isinstance(entry, dict) and isinstance(entry.get("p"), str):
            entry["p"] = moved_pointer(entry["p"], moved)


def relink(record: dict[str, Any], moved: Mapping[str, str], listing: str, cite: Callable[[str], str]) -> None:
    """After the retyping ``moved`` (every replaced pointer -> its digest's pointer) of ``record``: everything that names
    a moved pointer follows it, and each digest pointer is tagged and cites the rule (module docstring)."""
    evf = {moved_pointer(k, moved): v for k, v in (record.get("evf") or {}).items()}
    if isinstance(record.get("unk"), dict):
        record["unk"] = {moved_pointer(k, moved): v for k, v in record["unk"].items()}
    rules = [cited(r, moved) if isinstance(r, str) else r for r in record.get("rule", [])]
    move_listing(record, listing, moved)
    floor = "I" if record.get("ev") == "I" else "D"  # never stronger than the record (C.6.5 rule 1)
    for pointer in moved.values():
        evf[pointer] = "I" if evf.get(pointer) == "I" else floor
        ref = cite(pointer)
        if ref not in rules:
            rules.append(ref)
    record["evf"] = evf
    record["rule"] = rules


def not_inlined(records: Sequence[dict[str, Any]], namespace: str, cite: Callable[[str], str]) -> list[str]:
    """Apply the pass to finished ``records`` in place (module docstring); ``namespace`` names the family's ``ext``
    member (its redaction listing and the ``args_raw`` digests) and ``cite(pointer)`` is its scoped citation of
    ``<namespace>.content_not_inlined@1``. Returns the ids of the changed records, sorted and distinct (the family's one
    info issue names them)."""
    ids: list[str] = []
    for record in records:
        found: list[str] = []
        for key in [k for k in record if k not in META_FIELDS]:
            record[key] = slim(record[key], (key,), found)
        if not found:
            continue
        relink(record, {f: retype(record, f, namespace) for f in found}, namespace, cite)
        ids.append(str(record["id"]))
    return sorted(set(ids))
