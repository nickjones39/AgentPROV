"""The PROV-CONSTRAINTS subset (K.10 ``test_prov_constraints.py``): typing and disjointness (C50, C55), generation
uniqueness (C24) and the C39 profile rule, self-communication, identifier overlap, and time checks as "MAY flag"
diagnostics reported apart (A5)."""

from __future__ import annotations

from typing import Any

from agentprov.validate import constraints
from agentprov.validate._provdoc import ProvView

from validate_support import ev, minimal_doc


def _run(core: dict[str, Any]) -> tuple[dict[str, set[str]], list[str]]:
    outcomes, diagnostics = constraints.check(ProvView.parse(minimal_doc(core)))
    return {o.id: o.codes() for o in outcomes}, [d.code for d in diagnostics]


def _gen(key: str, entity: str, activity: str) -> dict[str, Any]:
    return {key: {"prov:entity": entity, "prov:activity": activity, **ev(rule="aprov.gen_message@1")}}


def test_clean() -> None:
    codes, diags = _run({"entity": {"x:m0": ev()}, "activity": {"x:mc0": ev()},
                         "wasGeneratedBy": _gen("x:gen_message.aaaaaaaaaaaaaaaa", "x:m0", "x:mc0")})
    assert not any(codes.values()) and diags == []


def test_entity_activity_disjointness() -> None:
    codes, _ = _run({"activity": {"x:mc0": ev(), "x:te0": ev()},
                     "used": {"x:use_request.aaaaaaaaaaaaaaaa": {"prov:activity": "x:te0", "prov:entity": "x:mc0",
                                                                 **ev(rule="aprov.use_request@1")}}})
    assert codes["pv.constraints.typing"] == {"pv.constraints.disjoint"}


def test_generation_uniqueness_and_single_generator() -> None:
    gens = {**_gen("x:gen_message.aaaaaaaaaaaaaaaa", "x:m0", "x:mc0"),
            **_gen("x:gen_message.bbbbbbbbbbbbbbbb", "x:m0", "x:mc0"),
            **_gen("x:gen_message.cccccccccccccccc", "x:m0", "x:mc1")}
    codes, _ = _run({"entity": {"x:m0": ev()}, "activity": {"x:mc0": ev(), "x:mc1": ev()}, "wasGeneratedBy": gens})
    assert codes["pv.constraints.unique_generation"] == {"pv.constraints.generation_not_unique"}
    assert codes["pv.constraints.single_generator"] == {"pv.constraints.multiple_generators"}


def test_self_communication() -> None:
    codes, _ = _run({"activity": {"x:mc0": ev()},
                     "wasInformedBy": {"x:comm.aaaaaaaaaaaaaaaa": {"prov:informed": "x:mc0", "prov:informant": "x:mc0",
                                                                   **ev("Derived", "aprov.comm@1")}}})
    assert codes["pv.constraints.self_communication"] == {"pv.constraints.self_communication"}


def test_identifier_overlap_and_reflexive_specialization() -> None:
    codes, _ = _run({"entity": {"x:m0": ev()},
                     "specializationOf": {"_:t_spec.aaaaaaaaaaaaaaaa": {"prov:specificEntity": "x:m0",
                                                                        "prov:generalEntity": "x:m0"}},
                     "activity": {"x:gen_message.aaaaaaaaaaaaaaaa": ev()},
                     "wasGeneratedBy": _gen("x:gen_message.aaaaaaaaaaaaaaaa", "x:m0", "x:mc0")})
    assert {"pv.constraints.identifier_overlap", "pv.constraints.specialization_reflexive"} <= codes[
        "pv.constraints.identifiers"]


def test_times_are_diagnostics_only() -> None:
    codes, diags = _run({"activity": {"x:mc0": ev(**{"prov:startTime": "2026-10-08T10:00:00+00:00",
                                                     "prov:endTime": "2026-10-08T09:00:00+00:00"})}})
    assert not any(codes.values())
    assert diags == ["pv.constraints.time.start_after_end"]


# ------------------------------------------------------------------------------------------------ item 10 (E2-b1)
def _der(key: str, generated: str, used: str, **extra: Any) -> dict[str, Any]:
    return {key: {"prov:generatedEntity": generated, "prov:usedEntity": used, **extra,
                  **ev("Derived", "aprov.t_map@1")}}


def test_new_checks_pass_on_a_clean_document() -> None:
    codes, _ = _run({"entity": {"x:m0": ev(), "x:m1": ev()}, "activity": {"x:mc0": ev()},
                     "wasGeneratedBy": _gen("x:gen_message.aaaaaaaaaaaaaaaa", "x:m1", "x:mc0"),
                     "used": {"x:use_context.aaaaaaaaaaaaaaaa": {"prov:activity": "x:mc0", "prov:entity": "x:m0",
                                                                 **ev(rule="aprov.use_context@1")}},
                     "wasDerivedFrom": _der("x:d.aaaaaaaaaaaaaaaa", "x:m1", "x:m0")})
    for check in ("ordering", "derivation_parts", "unique_start", "cycles"):
        assert codes[f"pv.constraints.{check}"] == set(), check


def test_a_derivation_cycle_is_a_strict_ordering_violation() -> None:
    """Constraint 42: generation(m0) < generation(m1) < generation(m0) cannot hold."""
    codes, _ = _run({"entity": {"x:m0": ev(), "x:m1": ev()},
                     "wasDerivedFrom": {**_der("x:d.aaaaaaaaaaaaaaaa", "x:m1", "x:m0"),
                                        **_der("x:d.bbbbbbbbbbbbbbbb", "x:m0", "x:m1")}})
    assert codes["pv.constraints.ordering"] == {"pv.constraints.strict_cycle"}


def test_derivation_against_start_and_generation_order() -> None:
    """m1 derived from m0 (C42: g(m0) < g(m1)), while m0 is generated by an activity that m1 triggered (C37, C44:
    g(m1) <= start(b) <= g(m0)): the strict edge closes a cycle through non-strict ones, though no relation alone is a
    cycle."""
    codes, _ = _run({"entity": {"x:m0": ev(), "x:m1": ev()}, "activity": {"x:b": ev()},
                     "wasStartedBy": {"x:st.aaaaaaaaaaaaaaaa": {"prov:activity": "x:b", "prov:trigger": "x:m1",
                                                                **ev("Derived", "aprov.spawn@1")}},
                     "wasGeneratedBy": _gen("x:g.aaaaaaaaaaaaaaaa", "x:m0", "x:b"),
                     "wasDerivedFrom": _der("x:d.aaaaaaaaaaaaaaaa", "x:m1", "x:m0")})
    assert codes["pv.constraints.ordering"] == {"pv.constraints.strict_cycle"}
    assert codes["pv.constraints.cycles"] == set()


def test_satisfiable_derivation_with_usage_is_not_flagged() -> None:
    """The same entities in a satisfiable order: b generates m0, m1 is derived from m0 later, b uses m1 after that."""
    codes, _ = _run({"entity": {"x:m0": ev(), "x:m1": ev()}, "activity": {"x:b": ev()},
                     "used": {"x:u.aaaaaaaaaaaaaaaa": {"prov:activity": "x:b", "prov:entity": "x:m1",
                                                       **ev(rule="aprov.use_context@1")}},
                     "wasGeneratedBy": _gen("x:g.aaaaaaaaaaaaaaaa", "x:m0", "x:b"),
                     "wasDerivedFrom": _der("x:d.aaaaaaaaaaaaaaaa", "x:m1", "x:m0")})
    assert codes["pv.constraints.ordering"] == set()


def test_non_strict_cycles_are_satisfiable() -> None:
    """Two activities informing each other force equal events, which PROV allows (only the lint fires)."""
    codes, _ = _run({"activity": {"x:a": ev(), "x:b": ev()},
                     "wasInformedBy": {"x:c.aaaaaaaaaaaaaaaa": {"prov:informed": "x:a", "prov:informant": "x:b",
                                                                **ev("Derived", "aprov.comm@1")},
                                       "x:c.bbbbbbbbbbbbbbbb": {"prov:informed": "x:b", "prov:informant": "x:a",
                                                                **ev("Derived", "aprov.comm@1")}}})
    assert codes["pv.constraints.ordering"] == set()
    assert codes["pv.constraints.cycles"] == {"pv.constraints.communication_cycle"}


def test_c51_derivation_parts_need_an_activity() -> None:
    codes, _ = _run({"entity": {"x:m0": ev(), "x:m1": ev()},
                     "wasDerivedFrom": _der("x:d.aaaaaaaaaaaaaaaa", "x:m1", "x:m0",
                                            **{"prov:generation": "x:g.aaaaaaaaaaaaaaaa"})})
    assert codes["pv.constraints.derivation_parts"] == {"pv.constraints.derivation_parts"}


def test_c26_one_start_per_activity_and_starter() -> None:
    start = {"prov:activity": "x:a", "prov:trigger": "x:t", "prov:starter": "x:s", **ev("Derived", "aprov.spawn@1")}
    codes, _ = _run({"activity": {"x:a": ev(), "x:s": ev()}, "entity": {"x:t": ev()},
                     "wasStartedBy": {"x:st.aaaaaaaaaaaaaaaa": start, "x:st.bbbbbbbbbbbbbbbb": dict(start)}})
    assert codes["pv.constraints.unique_start"] == {"pv.constraints.start_not_unique"}


def test_dependency_and_specialization_cycles_are_flagged() -> None:
    codes, _ = _run({"entity": {"x:m0": ev(), "x:m1": ev()}, "activity": {"x:a": ev(), "x:b": ev()},
                     "wasGeneratedBy": {**_gen("x:g.aaaaaaaaaaaaaaaa", "x:m0", "x:a"),
                                        **_gen("x:g.bbbbbbbbbbbbbbbb", "x:m1", "x:b")},
                     "used": {"x:u.aaaaaaaaaaaaaaaa": {"prov:activity": "x:a", "prov:entity": "x:m1",
                                                       **ev(rule="aprov.use_context@1")},
                              "x:u.bbbbbbbbbbbbbbbb": {"prov:activity": "x:b", "prov:entity": "x:m0",
                                                       **ev(rule="aprov.use_context@1")}},
                     "specializationOf": {"_:s1": {"prov:specificEntity": "x:m0", "prov:generalEntity": "x:m1"},
                                          "_:s2": {"prov:specificEntity": "x:m1", "prov:generalEntity": "x:m0"}}})
    assert codes["pv.constraints.cycles"] == {"pv.constraints.dependency_cycle", "pv.constraints.specialization_cycle"}
