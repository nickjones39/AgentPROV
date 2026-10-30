"""Regen item 62 (CA-3, C.4.2): a part id whose ordinal has more than 18 digits addresses no part.

Such an id still matches the part-id grammar (no aer/0.1 change), but no message has that many parts, and an ordinal
past CPython's 4300-digit ``int()`` limit raised a bare ``ValueError`` from the validator, the reader and the SEM
validator. It is out of range: ``split_part_id`` raises its documented error and every caller treats the reference as
dangling.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from aer_support import codes_of, edit, example_records, validate_example

from agentprov.aer.ids import is_part_id, split_part_id
from agentprov.aer.reader import AerDocument
from agentprov.views import transcript_v1

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sem"))
from sem_support import ann, example_registry, syn_sem, synthetic_aer  # noqa: E402

from agentprov.sem.validate import validate_sem_document  # noqa: E402

HUGE = "m1#" + "1" * 5000  # past CPython's int() digit limit
LONG = "m1#" + "1" * 19  # one digit past the range; int() would accept it
LONGEST = "m1#" + "9" * 18  # still in range: parses, addresses nothing


@pytest.mark.parametrize("ref", [HUGE, LONG], ids=["5000-digits", "19-digits"])
def test_split_part_id_rejects_long_ordinal(ref: str) -> None:
    assert is_part_id(ref)
    with pytest.raises(ValueError, match="^not a part id$"):
        split_part_id(ref)


def test_split_part_id_keeps_18_digits() -> None:
    assert split_part_id(LONGEST) == ("m1", 10**18 - 1)


@pytest.mark.parametrize("ref", [HUGE, LONG], ids=["5000-digits", "19-digits"])
def test_validator_reports_long_ordinal_as_dangling(ref: str) -> None:
    assert "aer.ref.dangling" in codes_of(validate_example(edit(example_records(), "te0", call=ref)))


@pytest.mark.parametrize("ref", [HUGE, LONG], ids=["5000-digits", "19-digits"])
def test_reader_and_view_part_return_none(ref: str) -> None:
    message = {"k": "message", "id": "m1", "parts": [{"t": "text", "text": "x"}]}
    doc = AerDocument(header={}, records=[], seal={}, execution_digest="", file_sha256="", _index={"m1": message})
    assert doc.part(ref) is None
    view = transcript_v1._Aer([{"k": "execution", "id": "exec"}, message])
    assert view.part(ref) is None


@pytest.mark.parametrize("ordinal", ["1" * 5000, "1" * 19], ids=["5000-digits", "19-digits"])
def test_sem_target_with_long_ordinal_is_dangling(ordinal: str) -> None:
    report = validate_sem_document(syn_sem(ann(f"m0#{ordinal}", "integrity", "untrusted", premises=())),
                                   synthetic_aer(), catalogues=example_registry())
    assert {f.code for f in report.errors} == {"sem.target.dangling"}
