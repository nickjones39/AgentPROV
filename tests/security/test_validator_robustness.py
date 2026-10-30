"""SEC-01/SEC-21 (T-01, T-19): the tier-2 AER validator reports hostile AER lines, it never crashes on them.

An AER read back from a corpus or a downloaded deposit is untrusted (G.1.3). Phase-12 fuzzing (``tests/fuzz/
test_aer_validator_fuzz.py``) found type-confused fields that raised ``TypeError``/``ValueError``/``AttributeError``
out of the validator: a scalar where a list belongs (``rule``, ``parts``, ``input``, ``inputs``, ``after``, seal issue
``ids``), an unhashable ``unk`` reason, a non-string origin pointer, and a 4,301-digit array index in an ``unk`` key.
Each is replayed here; each must end in findings.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest
from aer_support import example_records, insert_after, make_registry

from agentprov.aer.canon import dumps_line
from agentprov.aer.validate import AerValidator

SCALARS = [5, True, 1.5, "abc", {"a": 1}, None]
ACTIVITY = {"k": "activity", "id": "ac0", "ev": "D", "rule": ["tst.d@1"], "type": "tst:plan", "actor": "agent",
            "scope": "att0", "inputs": ["m0"], "status": "ok", "label": "plan"}


def findings(records: list[dict[str, Any]]) -> set[str]:
    v = AerValidator(store=None, catalogues=make_registry(), mode="release")
    for record in records:
        v.feed(dumps_line(record))
    return {f.code for f in v.finish().findings}


def _with(rid: str, field: str, value: Any, records: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    records = copy.deepcopy(records or example_records())
    target = next(r for r in records if r["id"] == rid)
    target[field] = value
    return records


@pytest.mark.parametrize("value", SCALARS)
@pytest.mark.parametrize(("rid", "field"), [("agent", "rule"), ("m0", "parts"), ("mc0", "input"), ("te0", "after"),
                                            ("mc0", "after")])
def test_a_scalar_where_a_list_belongs_is_a_finding(rid: str, field: str, value: Any) -> None:
    assert findings(_with(rid, field, value))


@pytest.mark.parametrize("value", SCALARS)
def test_scalar_activity_inputs_are_a_finding(value: Any) -> None:
    records = insert_after(example_records(), "m0", dict(ACTIVITY, inputs=value))
    assert findings(records)


@pytest.mark.parametrize("reason", [{"$blob": "x"}, ["lost"], 5, None])
def test_an_unhashable_or_non_string_unk_reason_is_a_finding(reason: Any) -> None:
    assert findings(_with("mc0", "unk", {"/model": reason}))


@pytest.mark.parametrize("pointer", [None, 5, ["/x"], {"p": "/x"}, "/" + "9" * 5000])
def test_a_hostile_origin_pointer_is_a_finding(pointer: Any) -> None:
    records = copy.deepcopy(example_records())
    target = next(r for r in records if r.get("src"))
    target["src"] = [{"a": "a0", "o": pointer}]
    assert findings(records)


@pytest.mark.parametrize("ids", [5, "m0", [{"a": 1}], [["m0"]]])
def test_hostile_seal_issue_ids_are_findings(ids: Any) -> None:
    from aer_support import seal_record

    records = example_records()
    seal = seal_record(records, None)
    seal = copy.deepcopy(seal)
    seal.setdefault("issues", []).append({"code": "x", "rule": "tst.d@1", "ids": ids})
    assert findings([*records, seal])
