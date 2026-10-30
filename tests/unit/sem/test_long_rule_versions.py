"""A rule reference whose version is too long for ``int`` is a ``sem.rule.missing`` finding, not a crash (CA-4)."""

from __future__ import annotations

import hashlib
from typing import Any

import pytest
from sem_support import ann, example_registry, syn_sem, synthetic_aer

from agentprov.aer.canon import dumps_line
from agentprov.aer.rules import RULE_REF_RE
from agentprov.sem.reader import load_sem_bytes
from agentprov.sem.validate import validate_sem_document

LONG = "tst.d@" + "1" * 5000  # matches the unbounded C.6.4 grammar; past int's 4300-digit string limit


def _read_back(record: dict[str, Any]) -> Any:
    """``record`` replacing the first annotation of a synthetic document, sealed and read back through the reader."""
    doc = syn_sem(ann("m0#3", "integrity", "untrusted"))
    records = [record, *(dict(r) for r in doc.annotations[1:])]
    body = b"".join(dumps_line(r) for r in [doc.header, *records])
    seal = {"k": "seal", "id": "seal", "n_records": len(records) + 2, "records_sha256": hashlib.sha256(body).hexdigest()}
    return load_sem_bytes(body + dumps_line(seal))


def _base() -> dict[str, Any]:
    return dict(syn_sem(ann("m0#3", "integrity", "untrusted")).annotations[0])


@pytest.mark.parametrize("ref", [LONG, LONG + "#/value"], ids=["bare", "scoped"])
def test_long_rule_version_in_rule_is_missing(ref: str) -> None:
    assert RULE_REF_RE.fullmatch(ref) is not None
    report = validate_sem_document(_read_back({**_base(), "rule": [ref]}), synthetic_aer(), catalogues=example_registry())
    assert not report.passed
    assert [(f.code, f.pointer) for f in report.errors] == [("sem.rule.missing", "/rule/0")]


def test_long_rule_version_as_normaliser_is_missing() -> None:
    value = {"fixture": "fx0", "status": "absent", "normaliser": LONG}
    record = {**_base(), "type": "injection_marker", "value": value}
    report = validate_sem_document(_read_back(record), synthetic_aer(), catalogues=example_registry())
    assert [(f.code, f.pointer) for f in report.errors] == [("sem.rule.missing", "/value/normaliser")]
