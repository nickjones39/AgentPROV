"""A malformed :class:`Annotation` is a profile defect: :func:`annotate` raises ``SemAnnotationError``, never a raw
``IndexError``, ``TypeError`` or ``ValueError`` (module docstring of :mod:`agentprov.sem.engine`; regen item 70, CA-12).
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sem_support import ann, p, syn_sem

from agentprov.errors import AgentProvError
from agentprov.sem.engine import SemAnnotationError
from agentprov.sem.types import Annotation

#: name -> (annotation factory, expected ``sem.*`` code)
CASES: dict[str, tuple[Callable[[], Annotation], str]] = {
    "span_one_member": (lambda: ann("m0#0", "integrity", "trusted", at="/text", span=(1,)), "sem.schema"),
    "span_three_members": (lambda: ann("m0#0", "integrity", "trusted", at="/text", span=(1, 2, 3)), "sem.schema"),
    "premises_none": (
        lambda: Annotation("te0", "role", ["neutral"], "D", ("tst.d@1",), None),  # type: ignore[arg-type]
        "sem.schema",
    ),
    "rule_none": (
        lambda: Annotation("te0", "role", ["neutral"], "D", None, (p("te0"),)),  # type: ignore[arg-type]
        "sem.schema",
    ),
    # An id with more digits than int() accepts (sys.int_info.str_digits_check_threshold) still names a later annotation.
    "huge_ann_id_target": (lambda: ann("a" + "9" * 5000, "role", ["neutral"], premises=(p("te0"),)),
                           "sem.target.forward"),
    "huge_ann_id_premise": (lambda: ann("te0", "role", ["neutral"], premises=(p("a" + "9" * 5000),)),
                            "sem.premise.forward"),
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_malformed_annotation_is_sem_annotation_error(name: str) -> None:
    factory, code = CASES[name]
    with pytest.raises(SemAnnotationError) as info:
        syn_sem(factory())
    assert info.value.code == code
    assert info.value.index == 0
    assert isinstance(info.value, AgentProvError)  # what the derive job catches to record a sem error


def test_earlier_annotation_reference_still_accepted() -> None:
    doc = syn_sem(ann("te0", "role", ["neutral"]), ann("te0", "role", ["neutral"], premises=(p("a0"),)))
    assert [r["id"] for r in doc.records[1:]] == ["a0", "a1"]
