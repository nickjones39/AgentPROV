"""``agentprov.prov.diff.diff_documents`` (HL H.8.4(3); HL-T6) and the on-demand TriG writer
``agentprov.prov.serialise.trig.to_trig`` (EF E.5.4)."""

from __future__ import annotations

import json

import pytest

from agentprov.prov.diff import diff_documents, same_value
from agentprov.prov.serialise.trig import TrigError, _literal_text, serialiser_versions, to_trig

DOC = {
    "prefix": {"ex": "https://example.org/x#", "b": "https://example.org/b/"},
    "entity": {"ex:e1": {"ex:size": 3}, "ex:e2": {}},
    "activity": {"ex:a1": {}},
    "used": {"ex:u1": {"prov:activity": "ex:a1", "prov:entity": "ex:e1"}},
    "bundle": {
        "b:one": {
            "prefix": {"ex": "https://example.org/x#"},
            "entity": {"ex:e3": {"ex:flag": True, "ex:text": "line\nwith \"quotes\" and \\"}},
            "activity": {"ex:a2": {}},
            "wasGeneratedBy": {"ex:g1": {"prov:entity": "ex:e3", "prov:activity": "ex:a2"}},
            "wasDerivedFrom": {"ex:d1": {"prov:generatedEntity": "ex:e3", "prov:usedEntity": "ex:e4",
                                         "prov:type": {"$": "prov:Quotation", "type": "prov:QUALIFIED_NAME"}}},
        }
    },
}


# ------------------------------------------------------------------------------------------------ diff
def test_identical_documents_have_no_diff_and_order_does_not_matter():
    reordered = json.loads(json.dumps(DOC, sort_keys=True))
    assert diff_documents(DOC, reordered) == []


def test_additions_removals_and_attribute_changes_are_listed():
    new = json.loads(json.dumps(DOC))
    del new["entity"]["ex:e2"]
    new["entity"]["ex:e9"] = {}
    new["entity"]["ex:e1"]["ex:size"] = 4
    lines = diff_documents(DOC, new)
    assert "-entity/ex:e2" in lines and "+entity/ex:e9" in lines
    assert "~entity/ex:e1.ex:size: 3 -> 4" in lines


@pytest.mark.parametrize(("old", "new"), [(True, 1), (3, 3.0), (1, "1"), (0.0, -0.0), ([1], [True])])
def test_type_only_changes_are_reported(old, new):
    """Baseline R2 / HL-T6: Python ``==`` would call these equal; the diff does not."""
    a = json.loads(json.dumps(DOC))
    b = json.loads(json.dumps(DOC))
    a["entity"]["ex:e1"]["ex:size"] = old
    b["entity"]["ex:e1"]["ex:size"] = new
    assert not same_value(old, new)
    assert diff_documents(a, b) == [f"~entity/ex:e1.ex:size: {old!r} -> {new!r}"]


def test_bundles_are_diffed_inside():
    new = json.loads(json.dumps(DOC))
    new["bundle"]["b:one"]["entity"]["ex:e3"]["ex:flag"] = 1
    assert diff_documents(DOC, new) == ["~bundle/b:one/entity/ex:e3.ex:flag: True -> 1"]
    new["bundle"]["b:two"] = {}
    assert "+bundle/b:two" in diff_documents(DOC, new)


def test_an_attribute_that_appears_with_null_is_a_change():
    new = json.loads(json.dumps(DOC))
    new["entity"]["ex:e2"]["ex:x"] = None
    assert diff_documents(DOC, new) == ["~entity/ex:e2.ex:x: None -> None"]


# ------------------------------------------------------------------------------------------------ TriG
def test_trig_is_canonical_and_deterministic():
    data = to_trig(json.dumps(DOC).encode("utf-8"))
    assert data == to_trig(json.dumps(DOC, sort_keys=True, indent=3))
    text = data.decode("utf-8")
    assert text.endswith("}\n") and "@prefix" not in text and "_:" not in text
    assert text.startswith("{\n")  # the default graph comes first
    graphs = [line for line in text.splitlines() if line.endswith("{")]
    assert graphs == ["{", "<https://example.org/b/one> {"]
    for block in text.split("}\n")[:-1]:
        lines = block.splitlines()[1:]
        assert lines == sorted(lines)


def test_trig_has_the_unqualified_layer_in_the_statement_graph():
    text = to_trig(json.dumps(DOC)).decode("utf-8")
    default, bundle = text.split("}\n")[:2]
    used = "<https://example.org/x#a1> <http://www.w3.org/ns/prov#used> <https://example.org/x#e1> ."
    generated = "<https://example.org/x#e3> <http://www.w3.org/ns/prov#wasGeneratedBy> <https://example.org/x#a2> ."
    quoted = "<https://example.org/x#e3> <http://www.w3.org/ns/prov#wasQuotedFrom> <https://example.org/x#e4> ."
    assert used in default.splitlines() and generated in bundle.splitlines() and quoted in bundle.splitlines()
    assert "prov#wasDerivedFrom> <https://example.org/x#e4>" not in bundle  # the most specific property only


def test_trig_literals_use_canonical_escaping():
    text = to_trig(json.dumps(DOC)).decode("utf-8")
    assert '"line\\nwith \\"quotes\\" and \\\\"' in text
    assert _literal_text("a\tb\x01\x7f") == "a\\tb\\u0001\\u007F"


def test_trig_refuses_an_unreadable_document():
    with pytest.raises(TrigError):
        to_trig(b"{not json")


def test_serialiser_versions_are_reported():
    versions = serialiser_versions()
    assert set(versions) == {"prov", "rdflib"} and all(versions.values())


def test_trig_and_the_tier4_round_trip_share_one_encode_and_parse(monkeypatch):
    """D-131: ``to_trig`` reads the PROV-O image through the N-Quads encode and parse that ``pv.roundtrip`` checks (one
    function each, in ``prov.serialise.nquads``; neither module keeps a copy), so the path TriG is produced from is the
    path tier 4 validates per execution."""
    from agentprov.prov.serialise import nquads, trig
    from agentprov.validate import roundtrip
    from agentprov.validate._provdoc import ProvView

    seen: list[str] = []
    encode, parse = nquads.encode_nquads, nquads.parse_nquads
    monkeypatch.setattr(nquads, "encode_nquads", lambda document: (seen.append("encode"), encode(document))[1])
    monkeypatch.setattr(nquads, "parse_nquads", lambda text, bindings: (seen.append("parse"), parse(text, bindings))[1])
    to_trig(json.dumps(DOC))
    assert seen == ["encode", "parse"]
    seen.clear()
    roundtrip.check(DOC, ProvView.parse(DOC))
    assert seen == ["encode", "parse", "encode"]  # the second model is compared as text, not parsed (D-89 step 2)
    assert not any(hasattr(m, n) for m in (roundtrip, trig) for n in ("_serialise", "_parse", "encode_nquads", "parse_nquads"))
