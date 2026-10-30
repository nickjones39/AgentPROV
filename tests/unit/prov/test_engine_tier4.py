"""The synthetic generic-kind derivations pass every tier-4 check (PQ phase 5 exit; EF E.2, E.5.5; D8 tier 4).

The golden set has no generic records, no INFERRED attribute splits and no assumption-driven rules, so these variants
exercise the routing that the golden gate cannot reach.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import prov_support as ps  # noqa: E402

from agentprov.prov.engine import derive  # noqa: E402
from agentprov.validate.prov import validate_prov  # noqa: E402


def _record(records: list[dict[str, Any]], rid: str) -> dict[str, Any]:
    return next(r for r in records if r["id"] == rid)


def inferred_input(records: list[dict[str, Any]]) -> None:
    _record(records, "ac2").update(evf={"/inputs/0": "I"}, rule=["tst.d@1", "tst.i@1#/inputs/0"])


def inferred_label(records: list[dict[str, Any]]) -> None:
    _record(records, "ac0").update(evf={"/label": "I"}, rule=["tst.d@1", "tst.i@1#/label"])


def inferred_time(records: list[dict[str, Any]]) -> None:
    """D-28 addendum: a D start and an I end on one activity; the I end is not a PROV time."""
    _record(records, "ac0").update(t={"start": START, "end": END}, evf={"/t/end": "I"},
                                   rule=["tst.d@1", "tst.i@1#/t/end"])


START, END = "2026-10-08T12:00:00Z", "2026-10-08T12:00:05Z"


def auto_execution(records: list[dict[str, Any]]) -> None:
    te0 = _record(records, "te0")
    del te0["authorised_by"]
    te0["rule"] = ["tst.d@1", "tst.auto@1"]


VARIANTS: dict[str, Callable[[list[dict[str, Any]]], None]] = {
    "base": lambda records: None,
    "inferred_input": inferred_input,
    "inferred_label": inferred_label,
    "auto_execution": auto_execution,
    "inferred_time": inferred_time,
}


@pytest.mark.parametrize("name", sorted(VARIANTS))
def test_generic_derivation_passes_tier4(tmp_path: Path, name: str) -> None:
    records = ps.generic_records()
    VARIANTS[name](records)
    doc = ps.write_aer(records, tmp_path / "g.aer.jsonl")
    registry = ps.registry()
    report = validate_prov(derive(doc, registry=registry).prov_json, doc, registry=registry)
    failures = [(o.id, [f.code for f in o.findings]) for o in report.outcomes if o.status == "fail"]
    assert failures == [] and report.passed


def test_an_inferred_time_is_never_a_prov_time(tmp_path: Path) -> None:
    """D-28 addendum: the engine emits ``prov:startTime``/``prov:endTime`` only from O- or D-class times. An I-class
    ``/t/end`` gives no attribute (nor a lexical form) in any bundle and a disclosure; the D ``/t/start`` stays; tier 4
    passes (before the fix the I end became an inference-bundle entity with ``prov:endTime``, refused by PV-NE-6)."""
    import json

    records = ps.generic_records()
    inferred_time(records)
    doc = ps.write_aer(records, tmp_path / "t.aer.jsonl")
    registry = ps.registry()
    assert ps.check_valid(doc, registry) == []
    result = derive(doc, registry=registry)
    from agentprov.prov.serialise.time import prov_time

    text = result.prov_json.decode("utf-8")
    assert END not in text and prov_time(END) not in text and "apv:endTimeLexical" not in text
    starts = [b for b, body in json.loads(text)["bundle"].items()
              for st in body.get("activity", {}).values() if st.get("prov:startTime") == prov_time(START)]
    assert starts and all(".core." in b for b in starts)
    assert {"code": "inferred_time_omitted", "id": "ac0/t/end",
            "detail": "an I-class time is not a PROV time (D-28 addendum)"} in result.report.disclosed
    report = validate_prov(result.prov_json, doc, registry=registry)
    assert report.passed, [(o.id, [f.code for f in o.findings]) for o in report.outcomes if o.status == "fail"]
