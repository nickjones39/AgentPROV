"""Helpers shared by the SEC-17/SEC-18 tests and the never-emit properties: derive a synthetic AER and reduce its PROV to
the relations it states (what a claimed value must never change)."""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

_TESTS = Path(__file__).resolve().parents[1]
for _path in (_TESTS / "unit" / "aer", _TESTS / "unit" / "prov"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import prov_support as ps  # noqa: E402

from agentprov.prov.engine import derive  # noqa: E402

NODE_SECTIONS = frozenset({"activity", "agent", "entity", "prefix", "bundle"})
TIME_PROPS = frozenset({"prov:startTime", "prov:endTime", "prov:time", "apv:startTimeLexical", "apv:endTimeLexical",
                        "apv:durationSeconds", "apv:startTimeStatus", "apv:endTimeStatus"})


def derive_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    reg = ps.registry()
    with tempfile.TemporaryDirectory() as tmp:
        doc = ps.write_aer(records, Path(tmp) / "x.aer.jsonl")
        assert ps.check_valid(doc, reg) == []
        result = derive(doc, registry=reg)
    data = result.prov_json
    return json.loads(data) if isinstance(data, bytes | str) else data


#: Conversion-provenance ids (``xd:map.<b32>``, ``xd:aer.<hex>``, ``xd:bundle.core.<b32>``) and qualified-statement ids
#: (``x:use_context.<b32>``) are digests over the AER: any edit of a claimed value changes them, so they are compared by
#: kind only. Raw-object ids (``raw:sha256-<hex>``) likewise, for comparisons across different source bytes.
_DIGEST_ID = re.compile(r"(xd?:[a-z0-9_.-]+?\.)(?:[a-z2-7]{16,}|[0-9a-f]{64})\b")


_RAW_ID = re.compile(r"raw:sha256-[0-9a-f]{64}")
_MENTION_ID = re.compile(r"(\.mn-|x:as-)[a-z2-7]{8,}\b")  # assessment mention and assessment entities (E.7)


def _normal(text: str) -> str:
    return _MENTION_ID.sub(r"\1*", _RAW_ID.sub("raw:*", _DIGEST_ID.sub(r"\1*", text)))


def _bundle_kind(name: str) -> str:
    return name.rsplit(".", 1)[0]  # "xd:bundle.core.<digest>" -> "xd:bundle.core"


def relations(prov: dict[str, Any], *, assessment: bool = True) -> dict[str, list[str]]:
    """``{"<bundle kind>/<relation>": sorted JSON of each statement}``: everything except node descriptions (and, with
    ``assessment=False``, except the assessment bundles, which hold claims, not provenance; E.7)."""
    out: dict[str, list[str]] = {}

    def add(prefix: str, doc: dict[str, Any]) -> None:
        for section, items in doc.items():
            if section in NODE_SECTIONS or not isinstance(items, dict):
                continue
            out.setdefault(f"{prefix}/{section}", []).extend(_normal(json.dumps(v, sort_keys=True)) for v in items.values())

    add("top", prov)
    for name, body in (prov.get("bundle") or {}).items():
        if assessment or ".assess." not in name:
            add(_bundle_kind(name), body)
    return {k: sorted(v) for k, v in out.items()}


def time_attribute_holders(prov: dict[str, Any]) -> set[str]:
    """The sections in which any time attribute appears (expected: ``activity`` only)."""
    found: set[str] = set()

    def walk(doc: dict[str, Any]) -> None:
        for section, items in doc.items():
            if section == "bundle" and isinstance(items, dict):
                for body in items.values():
                    walk(body)
            elif isinstance(items, dict):
                for value in items.values():
                    if isinstance(value, dict) and TIME_PROPS & set(value):
                        found.add(section)

    walk(prov)
    return found
