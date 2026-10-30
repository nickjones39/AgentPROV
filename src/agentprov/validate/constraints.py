"""A faithful PROV-CONSTRAINTS subset over ``agentprov-prov/0.1`` output (D8 tier 4; EF E.1.4 "PROV checks", E.1.6
item 7; K.10 ``test_prov_constraints.py``).

Each check runs per container (the top level and every bundle on its own) and on the application view of every
inference bundle (core ∪ the bundle ∪ the inference bundles of its proper method subsets; E.1.6 item 1):

* ``pv.constraints.typing`` - Constraint 50 typing (each argument position types its node, together with the
  declared sections) and Constraint 55 entity/activity disjointness; Constraint 56 (no member of an
  ``prov:EmptyCollection``);
* ``pv.constraints.unique_generation`` - Constraint 24: one generation per (entity, activity);
* ``pv.constraints.single_generator`` - the profile rule on C39: at most one generating activity per entity per
  bundle;
* ``pv.constraints.self_communication`` - no ``wasInformedBy(a, a)`` (E.1.6 item 7);
* ``pv.constraints.identifiers`` - Constraints 52-54: specialization is irreflexive and an identifier denotes one
  statement kind within a view;
* ``pv.constraints.ordering`` - the event-ordering constraints (33, 36, 37, 38, 42 and the starter/trigger reading of
  44, with Inferences 9 and 11): every relation names its events, so the constraints are instantiable without any
  time. The event graph's "precedes" edges are built from the relations; a strongly connected component holding a
  *strict* edge (Constraint 42: the used entity's generation strictly precedes the generated entity's) is unsatisfiable;
* ``pv.constraints.derivation_parts`` - Constraint 51: a derivation that names a generation or a usage names its
  activity;
* ``pv.constraints.unique_start`` - Constraint 26: one ``wasStartedBy`` identifier per (activity, starter);
* ``pv.constraints.cycles`` - profile lints: no used/generated dependency cycle, no ``wasInformedBy`` cycle and no
  ``specializationOf`` ∪ ``mentionOf`` cycle (a cycle of length two or more makes specialization reflexive through
  its transitivity, Constraint 52; ``mentionOf`` is a specialization, PROV-LINKS).

The ordering, C26 and cycle checks also run on the assessment bundle's application view (core, inference bundles and
the assessment bundle), since an assessment's mentions specialise core and inference nodes.

No relation carries a time in this profile (E.5.3 item 7); ordering is checked from the relations alone (regeneration
batch item 10, examination 2 b1, A3 PI-04). The activity-time checks are "MAY flag" diagnostics (A5): they are
returned apart and never fail a check.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Hashable, Iterable, Iterator, Mapping, Sequence
from datetime import datetime
from typing import Final

from agentprov.validate._provdoc import ProvView, St
from agentprov.validate.prov_structure import ARG_KIND
from agentprov.validate.tiers import CheckOutcome, Finding, outcome

__all__ = ["check"]

M: Final = "pv.constraints"
DIAG: Final = "pv.constraints.time"


def _views(view: ProvView) -> Iterator[tuple[str, list[St]]]:
    """(label, statements) for the top level, each bundle on its own, and each inference bundle's application view."""
    yield "top", list(view.top)
    for b in view.bundles.values():
        yield f"bundle:{b.iri}", list(b.statements)
    for b in view.inference():
        statements = [s for v in view.visible(b.iri) for s in v.statements]
        yield f"view:{b.iri}", statements


def _assessment_views(view: ProvView) -> Iterator[tuple[str, list[St]]]:
    """(label, statements) of each assessment bundle's application view (core, inference bundles, the bundle)."""
    for b in view.assessment():
        yield f"view:{b.iri}", [s for v in view.visible(b.iri) for s in v.statements]


def check(view: ProvView) -> tuple[list[CheckOutcome], list[Finding]]:
    typing: list[Finding] = []
    unique: list[Finding] = []
    single: list[Finding] = []
    selfcomm: list[Finding] = []
    idents: list[Finding] = []
    ordering: list[Finding] = []
    parts: list[Finding] = []
    starts: list[Finding] = []
    cycles: list[Finding] = []
    for label, statements in _views(view):
        typing += _typing(label, statements, view)
        unique += _unique_generation(label, statements)
        idents += _identifiers(label, statements)
        if label.startswith("bundle:") or label == "top":
            single += _single_generator(label, statements)
            selfcomm += _self_communication(statements)
            parts += _derivation_parts(label, statements)
        ordering += _ordering(label, statements)
        starts += _unique_start(label, statements)
        cycles += _cycles(label, statements)
    for label, statements in _assessment_views(view):
        ordering += _ordering(label, statements)
        starts += _unique_start(label, statements)
        cycles += _cycles(label, statements)
    outcomes = [
        outcome(f"{M}.typing", typing),
        outcome(f"{M}.unique_generation", unique),
        outcome(f"{M}.single_generator", single),
        outcome(f"{M}.self_communication", selfcomm),
        outcome(f"{M}.identifiers", idents),
        outcome(f"{M}.ordering", ordering),
        outcome(f"{M}.derivation_parts", parts),
        outcome(f"{M}.unique_start", starts),
        outcome(f"{M}.cycles", cycles),
    ]
    return outcomes, list(_time_diagnostics(view))


def _typing(label: str, statements: Iterable[St], view: ProvView) -> Iterator[Finding]:
    types: dict[str, set[str]] = {}
    empty: set[str] = set()
    for s in statements:
        if s.is_element:
            types.setdefault(s.key, set()).add(s.section)
            if "prov:EmptyCollection" in s.types:
                empty.add(s.key)
            continue
        for k, v in s.args().items():
            kind = ARG_KIND.get(k)
            if kind is None:
                continue
            if k == "prov:bundle":
                continue  # a bundle entity of the top level, typed there
            types.setdefault(v, set()).add(kind)
        if s.section == "hadMember":
            c = s.arg("prov:collection")
            if c is not None and c in empty:
                yield Finding(f"{M}.empty_collection_member", f"{label}:{s.key}", "Constraint 56")
    for key, kinds in types.items():
        if {"entity", "activity"} <= kinds:
            yield Finding(f"{M}.disjoint", f"{label}:{key}", "typed both entity and activity (Constraints 50, 55)")


def _unique_generation(label: str, statements: Iterable[St]) -> Iterator[Finding]:
    seen: dict[tuple[str, str], str] = {}
    for s in statements:
        if s.section != "wasGeneratedBy":
            continue
        e, a = s.arg("prov:entity"), s.arg("prov:activity")
        if e is None or a is None:
            continue
        prev = seen.setdefault((e, a), s.key)
        if prev != s.key:
            yield Finding(f"{M}.generation_not_unique", f"{label}:{s.key}", f"also {prev} for ({e}, {a}) (Constraint 24)")


def _single_generator(label: str, statements: Iterable[St]) -> Iterator[Finding]:
    gens: dict[str, set[str]] = {}
    for s in statements:
        if s.section == "wasGeneratedBy" and (e := s.arg("prov:entity")) and (a := s.arg("prov:activity")):
            gens.setdefault(e, set()).add(a)
    for e, acts in sorted(gens.items()):
        if len(acts) > 1:
            yield Finding(f"{M}.multiple_generators", f"{label}:{e}", f"{len(acts)} generating activities (C39 rule)")


def _self_communication(statements: Iterable[St]) -> Iterator[Finding]:
    for s in statements:
        if s.section == "wasInformedBy" and s.arg("prov:informed") is not None:
            if s.arg("prov:informed") == s.arg("prov:informant"):
                yield Finding(f"{M}.self_communication", s.where, "an activity informed by itself (E.1.6 item 7)")


def _identifiers(label: str, statements: Iterable[St]) -> Iterator[Finding]:
    kinds: dict[str, set[str]] = {}
    for s in statements:
        if s.is_identified:
            kinds.setdefault(s.key, set()).add("element" if s.is_element else s.section)
        # mentionOf is a specialization (PROV-LINKS; the cycle lint above), so a reflexive one breaks Constraint 52 too
        # (D-621, pre-round review #25)
        if s.section in ("specializationOf", "mentionOf") and s.arg("prov:specificEntity") is not None \
                and s.arg("prov:specificEntity") == s.arg("prov:generalEntity"):
            yield Finding(f"{M}.specialization_reflexive", f"{label}:{s.key}", "Constraint 52")
    for key, ks in kinds.items():
        if len(ks) > 1:
            yield Finding(f"{M}.identifier_overlap", f"{label}:{key}", f"{sorted(ks)} (Constraints 53, 54)")


# ============================================================================================================ ordering
type _Event = tuple[str, ...]


def _sccs(nodes: Sequence[Hashable], adj: Mapping[Hashable, list[Hashable]]) -> list[list[Hashable]]:
    """Tarjan's strongly connected components, iterative (no recursion limit on long chains)."""
    index: dict[Hashable, int] = {}
    low: dict[Hashable, int] = {}
    on_stack: set[Hashable] = set()
    stack: list[Hashable] = []
    out: list[list[Hashable]] = []
    counter = 0
    for root in nodes:
        if root in index:
            continue
        work: list[tuple[Hashable, int]] = [(root, 0)]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, i = work[-1]
            succ = adj.get(node, [])
            if i < len(succ):
                work[-1] = (node, i + 1)
                nxt = succ[i]
                if nxt not in index:
                    index[nxt] = low[nxt] = counter
                    counter += 1
                    stack.append(nxt)
                    on_stack.add(nxt)
                    work.append((nxt, 0))
                elif nxt in on_stack:
                    low[node] = min(low[node], index[nxt])
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                comp: list[Hashable] = []
                while True:
                    top = stack.pop()
                    on_stack.discard(top)
                    comp.append(top)
                    if top == node:
                        break
                out.append(comp)
    return out


def _event_edges(statements: Iterable[St]) -> list[tuple[_Event, _Event, bool, str]]:
    """The "precedes" edges ``(before, after, strict, statement key)`` of the PROV-CONSTRAINTS event graph.

    Events: ``("s", a)`` start and ``("e", a)`` end of an activity, ``("g", e)`` generation of an entity, ``("u", a, e)``
    the usage of ``e`` by ``a``. Edges: C36 (usage within its activity) and C40 (generation before usage) for ``used``;
    C37 for ``wasGeneratedBy``; C38 for ``wasInformedBy``; for ``wasStartedBy`` the trigger's generation precedes the
    start (C44 with Inference 9: the trigger generated by the starter); for ``wasDerivedFrom`` the used entity's
    generation strictly precedes the generated one's (C42), and with an activity Inference 11's usage and generation;
    ``specializationOf``/``mentionOf``: the general entity's generation precedes the specific one's (C46); C33 for every
    activity named."""
    edges: list[tuple[_Event, _Event, bool, str]] = []
    acts: set[str] = set()

    def use(act: str, ent: str, key: str) -> None:
        u = ("u", act, ent)
        edges.extend(((("s", act), u, False, key), (u, ("e", act), False, key), (("g", ent), u, False, key)))
        acts.add(act)

    def gen(ent: str, act: str, key: str) -> None:
        edges.extend(((("s", act), ("g", ent), False, key), (("g", ent), ("e", act), False, key)))
        acts.add(act)

    for s in statements:
        sec = s.section
        if sec == "used":
            act, ent = s.arg("prov:activity"), s.arg("prov:entity")
            if act and ent:
                use(act, ent, s.key)
        elif sec == "wasGeneratedBy":
            act, ent = s.arg("prov:activity"), s.arg("prov:entity")
            if act and ent:
                gen(ent, act, s.key)
        elif sec == "wasInformedBy":
            a2, a1 = s.arg("prov:informed"), s.arg("prov:informant")
            if a1 and a2:
                edges.append((("s", a1), ("e", a2), False, s.key))
                acts.update((a1, a2))
        elif sec == "wasStartedBy":
            act, trig, starter = s.arg("prov:activity"), s.arg("prov:trigger"), s.arg("prov:starter")
            if act and trig:
                edges.append((("g", trig), ("s", act), False, s.key))
                acts.add(act)
            if trig and starter:
                gen(trig, starter, s.key)
        elif sec == "wasDerivedFrom":
            e2, e1, act = s.arg("prov:generatedEntity"), s.arg("prov:usedEntity"), s.arg("prov:activity")
            if e2 and e1:
                edges.append((("g", e1), ("g", e2), True, s.key))
                if act:
                    use(act, e1, s.key)
                    gen(e2, act, s.key)
                    edges.append((("u", act, e1), ("g", e2), False, s.key))
        elif sec in ("specializationOf", "mentionOf"):
            specific, general = s.arg("prov:specificEntity"), s.arg("prov:generalEntity")
            if specific and general:
                edges.append((("g", general), ("g", specific), False, s.key))
    for act in sorted(acts):
        edges.append((("s", act), ("e", act), False, ""))
    return edges


def _ordering(label: str, statements: Iterable[St]) -> Iterator[Finding]:
    """An SCC of the event graph that holds a strict edge: its events would have to precede themselves strictly."""
    edges = _event_edges(statements)
    adj: dict[Hashable, list[Hashable]] = defaultdict(list)
    nodes: dict[Hashable, None] = {}
    for x, y, _strict, _key in edges:
        adj[x].append(y)
        nodes.setdefault(x)
        nodes.setdefault(y)
    member: dict[Hashable, int] = {}
    for i, comp in enumerate(_sccs(list(nodes), adj)):
        for event in comp:
            member[event] = i
    reported: set[int] = set()
    for x, y, strict, key in edges:
        if strict and member[x] == member[y] and member[x] not in reported:
            reported.add(member[x])
            yield Finding(f"{M}.strict_cycle", f"{label}:{key}",
                          "an event would strictly precede itself (Constraint 42 with the ordering constraints)")


def _derivation_parts(label: str, statements: Iterable[St]) -> Iterator[Finding]:
    for s in statements:
        if s.section != "wasDerivedFrom" or s.arg("prov:activity") is not None:
            continue
        if s.arg("prov:generation") is not None or s.arg("prov:usage") is not None:
            yield Finding(f"{M}.derivation_parts", f"{label}:{s.key}",
                          "generation or usage without an activity (Constraint 51)")


def _unique_start(label: str, statements: Iterable[St]) -> Iterator[Finding]:
    seen: dict[tuple[str, str], str] = {}
    for s in statements:
        if s.section != "wasStartedBy":
            continue
        act, starter = s.arg("prov:activity"), s.arg("prov:starter")
        if act is None or starter is None:
            continue
        prev = seen.setdefault((act, starter), s.key)
        if prev != s.key:
            yield Finding(f"{M}.start_not_unique", f"{label}:{s.key}",
                          f"also {prev} for ({act}, {starter}) (Constraint 26)")


def _cycle_findings(label: str, code: str, pairs: Iterable[tuple[str, str]], what: str) -> Iterator[Finding]:
    adj: dict[Hashable, list[Hashable]] = defaultdict(list)
    nodes: dict[Hashable, None] = {}
    for x, y in pairs:
        if x == y:
            continue  # self-loops are reported by the checks that own them (self-communication, C52)
        adj[x].append(y)
        nodes.setdefault(x)
        nodes.setdefault(y)
    for comp in _sccs(list(nodes), adj):
        if len(comp) > 1:
            yield Finding(f"{M}.{code}", f"{label}:{min(str(c) for c in comp)}", f"{what} ({len(comp)} nodes)")


def _cycles(label: str, statements: Iterable[St]) -> Iterator[Finding]:
    statements = list(statements)
    generators: dict[str, list[str]] = defaultdict(list)
    for s in statements:
        if s.section == "wasGeneratedBy" and (e := s.arg("prov:entity")) and (a := s.arg("prov:activity")):
            generators[e].append(a)
    depends = [(a, g) for s in statements if s.section == "used"
               and (a := s.arg("prov:activity")) and (e := s.arg("prov:entity")) for g in generators.get(e, ())]
    yield from _cycle_findings(label, "dependency_cycle", depends, "used/generated dependency cycle")
    informed = [(a2, a1) for s in statements if s.section == "wasInformedBy"
                and (a2 := s.arg("prov:informed")) and (a1 := s.arg("prov:informant"))]
    yield from _cycle_findings(label, "communication_cycle", informed, "wasInformedBy cycle")
    special = [(x, y) for s in statements if s.section in ("specializationOf", "mentionOf")
               and (x := s.arg("prov:specificEntity")) and (y := s.arg("prov:generalEntity"))]
    yield from _cycle_findings(label, "specialization_cycle", special, "specializationOf/mentionOf cycle (Constraint 52)")


# ============================================================================================================ times (A5)
def _instant(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _time_diagnostics(view: ProvView) -> Iterator[Finding]:
    times: dict[str, tuple[datetime | None, datetime | None]] = {}
    for s in view.all_statements():
        if s.section == "activity":
            times[s.key] = (_instant(s.attrs.get("prov:startTime")), _instant(s.attrs.get("prov:endTime")))
    for key, (start, end) in sorted(times.items()):
        if start is not None and end is not None and start > end:
            yield Finding(f"{DIAG}.start_after_end", key, "MAY flag: startTime after endTime")
    gens: dict[str, list[str]] = {}
    for s in view.bundle_statements():
        if s.section == "wasGeneratedBy" and (e := s.arg("prov:entity")) and (a := s.arg("prov:activity")):
            gens.setdefault(e, []).append(a)
    for s in view.bundle_statements():
        if s.section == "wasInformedBy":
            a2, a1 = s.arg("prov:informed"), s.arg("prov:informant")
            if a1 and a2 and (s1 := times.get(a1, (None, None))[0]) and (e2 := times.get(a2, (None, None))[1]):
                if s1 > e2:
                    yield Finding(f"{DIAG}.informant_after_informed", s.where, "MAY flag: informant starts after informed ends")
        elif s.section == "used":
            a2, e = s.arg("prov:activity"), s.arg("prov:entity")
            end2 = times.get(a2 or "", (None, None))[1]
            for a1 in gens.get(e or "", ()):
                start1 = times.get(a1, (None, None))[0]
                if end2 is not None and start1 is not None and start1 > end2:
                    yield Finding(f"{DIAG}.generation_after_use", s.where, "MAY flag: generator starts after the user ends")
