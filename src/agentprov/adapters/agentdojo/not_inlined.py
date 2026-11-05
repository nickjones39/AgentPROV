"""Strings over 1 MiB in the AgentDojo family's AERs (D-1063, review UC-41; the D-934 pattern of ``dtap``, ``agentops``).

C.2.1(6) (AER-V01, enforced for ``aer/0.2``) keeps a string whose UTF-8 encoding exceeds 1 MiB out of the AER, so before
this a single long tool output in a TraceLogger, DRIFT, results-container or capture message made the writer refuse the
whole execution (``adapter_defect``). The family's mappers now run :func:`not_inlined` over their finished records, after
the redaction and lone-surrogate passes and before C.6.5 weakening:

* every such string becomes ``{"not_inlined": {"sha256", "bytes"}}`` of its UTF-8 bytes; a ``{"$utf16": ...}`` value (a
  string with a lone surrogate, C.11.3) is replaced as a whole, by the digest of its decoded text, when that text or its
  base64 (which the writer measures, AER-V01) exceeds 1 MiB (regen-batch row 186, the AU-RC-2 rule), and a member named
  ``$utf16`` inside a ``$lit`` body is a source key, never such a value;
* a typed text field cannot hold the digest object, so a ``tool_result`` part's ``text`` becomes the part's ``value``
  and a part holding only ``t`` and ``text`` (a ``text``, ``reasoning`` or ``refusal`` part) becomes an ``other`` part
  of its source type whose ``value`` is the digest; any other typed position (``args_raw`` among them) keeps the object
  and is refused by the writer as before (nothing is dropped to make it fit);
* everything that names a moved pointer follows it (``evf`` and ``unk`` keys, scoped rule citations, the
  ``ext.rescont.redacted`` listing);
* each replaced pointer is tagged ``D`` (``I`` in an ``I`` record, never above it) and cites
  ``agentdojo.content_not_inlined@1`` scoped to it, as given: the rule is a transformation by AgentPROV, independent of
  the code that wrote the log, so it is never an ``_unverified`` twin;
* one info issue ``agentdojo.content_not_inlined`` names the records, in record order.

The pieces are the shared pass's (:mod:`agentprov.adapters.not_inlined`, row 186). The string stays in the raw artefact
the record's locator names. Pure.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, Final

from agentprov.adapters.not_inlined import META_FIELDS, MIB, relink, retype, slim

__all__ = ["ISSUE", "MIB", "RULE", "not_inlined"]

RULE: Final = "agentdojo.content_not_inlined@1"
ISSUE: Final = "agentdojo.content_not_inlined"


def not_inlined(records: Iterable[dict[str, Any]], cite: Callable[[str], str]) -> list[str]:
    """Replace, in place, every string over 1 MiB of the finished ``records`` (module docstring); return the ids of the
    records changed, in order. ``cite(pointer)`` is the mapper's scoped citation of :data:`RULE`, as given."""
    ids: list[str] = []
    for record in records:
        found: list[str] = []
        for key in [k for k in record if k not in META_FIELDS]:
            record[key] = slim(record[key], (key,), found)
        if not found:
            continue
        relink(record, {f: retype(record, f, None) for f in found}, "rescont", cite)
        ids.append(str(record["id"]))
    return ids
