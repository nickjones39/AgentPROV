"""Finding AU-RA-6 (2026-11-05; 0.2.0 change batch D-1063, regen-batch row 179): the results-container model call's
``/input`` is inferred (the request is not logged), so the rule that justifies it is class I:
``rescont.request_built_from_messages@2`` (catalogue ``rescont`` 3), ``@1`` (class D) superseded (AD-18). All content is
synthetic."""

from __future__ import annotations

from test_rescont import container, ok, one

from agentprov.adapters.agentdojo import citation
from agentprov.adapters.code_verification import Citations, VerifiedCode, rule_class
from agentprov.aer.rules import load_catalogue


def test_the_request_reading_is_class_i_even_for_verified_code():
    """A profile that verified the cited script commit (7c331d97) would have cited the class-D @1 at D."""
    catalogue = load_catalogue("rescont")
    assert catalogue.get("rescont.request_built_from_messages@2").cls == "I"
    assert catalogue.get("rescont.request_built_from_messages@1").status == "superseded"
    assert load_catalogue("rescont", 2).get("rescont.request_built_from_messages@1").status == "active"  # archived v2
    verified = Citations([VerifiedCode("7c331d978acca38534a3d42951f28a25ba26901b")], {}, namespaces=citation.NAMESPACES,
                         independent=citation.INDEPENDENT)
    assert rule_class(verified.cite("rescont.request_built_from_messages@2")) == "I"
    m = one(container())
    ok(m)
    calls = [r for r in m.records if r.get("k") == "model_call"]
    assert calls
    for call in calls:
        assert "rescont.request_built_from_messages@2#/input" in call["rule"] and call["evf"]["/input"] == "I"
    assert [i["rule"] for i in m.info.issues if i["code"] == "rescont.request_not_recorded"] == \
        ["rescont.request_built_from_messages@2"]
