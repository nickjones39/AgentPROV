"""A premise on an earlier annotation whose ``ev`` is not ``O``/``D``/``I`` is a finding, not a crash (CA-9)."""

from __future__ import annotations

import hashlib
from typing import Any

import pytest
from sem_support import ann, example_registry, syn_sem, synthetic_aer

from agentprov.aer.canon import dumps_line
from agentprov.sem.reader import load_sem_bytes
from agentprov.sem.validate import validate_sem_document


def _read_back(*records: dict[str, Any]) -> Any:
    """``records`` after a synthetic header, sealed and read back through the reader."""
    header = syn_sem(ann("te0", "role", ["neutral"])).header
    body = b"".join(dumps_line(r) for r in [header, *records])
    seal = {"k": "seal", "id": "seal", "n_records": len(records) + 2, "records_sha256": hashlib.sha256(body).hexdigest()}
    return load_sem_bytes(body + dumps_line(seal))


@pytest.mark.parametrize("ev", ["X", "", "O:"], ids=["unknown", "empty", "bad-party"])
def test_premise_on_annotation_with_invalid_ev_is_a_finding(ev: str) -> None:
    a0 = {"k": "ann", "id": "a0", "target": "te0", "type": "role", "value": ["neutral"], "ev": ev,
          "rule": ["tst.d@1"], "premises": [{"id": "te0", "p": ""}]}
    a1 = {"k": "ann", "id": "a1", "target": "te0", "type": "tst.x", "value": 1, "ev": "D",
          "rule": ["tst.d@1"], "premises": [{"id": "a0", "p": ""}]}
    report = validate_sem_document(_read_back(a0, a1), synthetic_aer(), catalogues=example_registry())
    assert not report.passed
    assert ("sem.schema", "/ev") in {(f.code, f.pointer) for f in report.errors}
