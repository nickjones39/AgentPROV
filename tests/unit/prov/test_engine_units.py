"""Units of the provenance engine: local names, statement ids and derivation keys (E.1.2, E.3.4, E.4.2), evidence
arithmetic (E.0.4, C.6.3-C.6.4), the time predicate (E.5.3 item 7) and the ``aprov`` catalogue (E.0.3)."""

from __future__ import annotations

import re

import pytest

from agentprov.prov import iri
from agentprov.prov.evidence import EvidenceClass, applicable_refs, cls, existence, weakest
from agentprov.prov.serialise.time import prov_time
from agentprov.prov.specs import load_spec


O, D, I = EvidenceClass.OBSERVED, EvidenceClass.DERIVED, EvidenceClass.INFERRED  # noqa: E741


def test_local_names_are_injective_on_part_ids() -> None:
    assert iri.local("m2#1") == "m2-1" and iri.local("mc0") == "mc0"
    ids = ["m2#1", "m21", "m2", "m2#10", "m21#0"]
    assert len({iri.local(i) for i in ids}) == len(ids)


def test_slugs_and_rule_names() -> None:
    assert iri.rule_slug("adprov.context_is_prefix@1") == "adprov-context_is_prefix-v1"
    assert iri.method_slug(["b.y@1", "a.x@2"]) == "a-x-v2--b-y-v1"
    assert iri.rule_name("aprov.use_context@1") == "use_context"


def test_statement_names_depend_on_every_input() -> None:
    base = iri.statement_name("dk", "aprov.use_context@1", ["x:mc0", "x:m1"])
    assert re.fullmatch(r"use_context\.[a-z2-7]{16}", base)
    assert base == iri.statement_name("dk", "aprov.use_context@1", ["x:mc0", "x:m1"])
    for other in (
        iri.statement_name("dk2", "aprov.use_context@1", ["x:mc0", "x:m1"]),
        iri.statement_name("dk", "aprov.use_context@1", ["x:m1", "x:mc0"]),
        iri.statement_name("dk", "aprov.use_context@1", ["x:mc0", "x:m1"], "contextIndex=1"),
    ):
        assert other != base


def test_derivation_key_changes_with_any_input() -> None:
    kw = dict(spec_id="agentprov-prov/0.1", catalogue_sha256="c" * 64, aer_digest="a" * 64, sem_digest=None,
              kind="core", key=None, options={"context_encoding": "members", "emit_content": False})
    dk = iri.derivation_key(**kw)
    assert re.fullmatch(r"[a-z2-7]{26}", dk)
    for change in ({"aer_digest": "b" * 64}, {"kind": "inference"}, {"key": "x"}, {"catalogue_sha256": "d" * 64},
                   {"options": {"context_encoding": "members", "emit_content": True}}):
        assert iri.derivation_key(**(kw | change)) != dk


def test_prefixes_never_declare_prov_or_xsd() -> None:
    prefixes = iri.prefixes_for("ex_abc")
    assert "prov" not in prefixes and "xsd" not in prefixes
    assert prefixes["x"].endswith("/exec/ex_abc#") and prefixes["xd"].endswith("/exec/ex_abc/")


def test_weakest_never_raises_a_class() -> None:
    assert weakest(O, D) == D and weakest(D, I) == I and weakest(O) == O
    with pytest.raises(ValueError):
        weakest()


def test_longest_prefix_class_and_applicable_rules() -> None:
    rec = {"ev": "D", "evf": {"/input": "I", "/input/2": "D", "/after": "O:source"},
           "rule": ["x.a@1", "x.b@1#/input", "x.c@1#/input/2"]}
    assert existence(rec) == D
    assert cls(rec, "/input/1") == I and cls(rec, "/input/2") == D and cls(rec, "/after") == O
    assert cls(rec, "/inputx") == D  # not a token-boundary prefix
    assert applicable_refs(rec, "/input/1") == ["x.b@1#/input"]
    assert applicable_refs(rec, "/input/2/sent") == ["x.c@1#/input/2"]
    assert applicable_refs(rec, "") == ["x.a@1"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-06-05T09:13:00.501241Z", "2026-06-05T09:13:00.501241+00:00"),
        ("2026-06-05T09:13:00Z", "2026-06-05T09:13:00+00:00"),
        ("2026-06-05T09:13:00.5Z", "2026-06-05T09:13:00.500000+00:00"),
        ("2026-06-05T10:13:00+01:00", "2026-06-05T09:13:00+00:00"),
        ("2026-06-05T09:13:00.1234567Z", None),  # more than 6 fractional digits: lexical only
        ("2026-06-05T09:13:00", None),  # naive
        ("0", None),
        ("", None),
        (0, None),
        ("2026-06-05T09:13:00Z\n", None),  # a trailing newline is not an instant
        ("\u0662\u0660\u0662\u0666-06-05T09:13:00Z", None),  # Arabic-Indic digits: lexical only (escaping audit F-12)
        ("2026-06-05T09:13:\uff10\uff10Z", None),  # fullwidth digits
    ],
)
def test_time_predicate(value: object, expected: str | None) -> None:
    assert prov_time(value) == expected


def test_catalogue_ceilings_follow_e15() -> None:
    spec = load_spec()
    assert spec.id == "agentprov-prov/0.1" and spec.vocabulary_version == "0.2.0"
    structural = ["aprov.n_message@1", "aprov.gen_part@1", "aprov.member_request@1", "aprov.use_request@1",
                  "aprov.assoc_model_call@1", "aprov.g_act@1", "aprov.g_use@1", "aprov.g_gen@1", "aprov.g_assoc@1"]
    assert all(spec.rule(r).ceiling == O for r in structural)
    assert spec.rule("aprov.comm@1").ceiling == D and spec.rule("aprov.start_tool@1").ceiling == D
    assert spec.rule("aprov.use_model@1").cap("per_actor") == D
    assert spec.rule("aprov.a_sent_transform@1").ceiling == I
    assert re.fullmatch(r"[0-9a-f]{64}", spec.catalogue_sha256)
