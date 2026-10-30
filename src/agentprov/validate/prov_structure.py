"""Generic PROV-JSON structure of an ``agentprov-prov/0.1`` document (D8 tier 4; EF E.3.1-E.3.2, E.4.1-E.4.2, E.5.1,
E.5.3, E.5.5; K.10 ``test_prov_structure.py``).

The checks are total: a relation section that is ``null``, a number or a boolean, an unknown or misspelt section, an
undeclared prefix or a non-canonical value is a finding, never an exception (baseline V1, V2). Checks:

* ``pv.prov_structure.document`` - top-level members, section and statement shapes, empty sections;
* ``pv.prov_structure.prefixes`` - ``prov``/``xsd`` never declared, bundles carry no ``prefix`` and do not nest;
* ``pv.prov_structure.bundles`` - exactly one core bundle, no empty inference bundle, bundle IRIs and their top-level
  bundle entities (kind type, derivation key, method-set slug; for assessment bundles the profile and its slug);
* ``pv.prov_structure.relations`` - relation arguments present and typed per PROV-JSON, no foreign ``prov:`` keys,
  unidentified relations carry only their arguments and sit where E.5.1 item 3 puts them (D-621): ``specializationOf``
  only at the top level, exactly ``specializationOf(<bundle>, xd:provenance)`` once per bundle of the document
  (``aprov.t_spec@1``, with the top-level entity ``xd:provenance``); ``hadMember`` only inside a bundle (its form is
  ``pv.profiles.membership``); ``mentionOf`` only inside inference and assessment bundles; ``alternateOf`` never;
* ``pv.prov_structure.qnames`` - QNames well formed and under declared prefixes (keys, arguments, values);
* ``pv.prov_structure.values`` - canonical value forms; multi-valued attributes sorted by JCS bytes, duplicate free, a
  single value a scalar (E.5.3 item 4);
* ``pv.prov_structure.identifiers`` - node names (E.1.2), statement ids ``<rule-name>.<h16>`` (E.4.2), blank nodes
  only as ``_:`` keys of unidentified relations;
* ``pv.prov_structure.references`` - every argument resolves in its application view (an assessment bundle also sees
  the top-level engine agent and plans its association names, E.7.2 item 2), the core declares every node it
  references (R-21, R-22);
* ``PV-NE-19`` - no ``used`` whose object is an activity, every ``mentionOf`` supra/infra is an entity.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from typing import Any, Final

from agentprov.io.canonical import jcs_bytes
from agentprov.prov.iri import method_slug, rule_name, rule_slug
from agentprov.validate._provdoc import (
    ASSESS_RE,
    CORE_RE,
    ELEMENT_SECTIONS,
    INF_RE,
    RELATION_ARGS,
    REQUIRED_ARGS,
    UNIDENTIFIED,
    ProvView,
    as_list,
    qname_value,
    qname_values,
)
from agentprov.validate.tiers import CheckOutcome, Finding, outcome

__all__ = ["NODE_NAME_RE", "QNAME_RE", "check"]

M: Final = "pv.prov_structure"
QNAME_RE: Final = re.compile(r"([A-Za-z_][A-Za-z0-9_.\-]*):([A-Za-z0-9_][A-Za-z0-9_.\-]*)")
H16: Final = r"[a-z2-7]{16}"
STATEMENT_RE: Final = re.compile(rf"(?P<prefix>x|xd|_):(?P<name>[a-z][a-z0-9_]*)\.(?P<h>{H16})")
#: E.1.2 node local names: ``L(id)``, derived ``L(id).<q>``, gaps, mentions, assessments and the reserved names
#: (``assess.<profile-slug>`` is an assessment bundle's evaluation activity, E.7.2 item 2).
NODE_NAME_RE: Final = re.compile(
    r"x:(?:capture-profile|exec|as-[a-z2-7]{16}|assess\.[a-z0-9_\-]+|"
    r"[a-z][a-z0-9_]{0,31}(?:-[0-9]+)?(?:\.(?:model|svc|check|rule|out|pre|before|after|ctx))?"
    r"(?:\.gap-[0-9]+)?(?:\.mn-[a-z2-7]{12})?)"
)
TOP_ELEMENT_RE: Final = re.compile(r"(?:raw|xd|sw|rules):[A-Za-z0-9_][A-Za-z0-9_.\-]*")
RESERVED_PREFIXES: Final = frozenset({"prov", "xsd"})
ELEMENT_PROV_ATTRS: Final = frozenset({"prov:type", "prov:label", "prov:value", "prov:location"})
ACTIVITY_PROV_ATTRS: Final = ELEMENT_PROV_ATTRS | {"prov:startTime", "prov:endTime"}
RELATION_PROV_ATTRS: Final = frozenset({"prov:type", "prov:label", "prov:role", "prov:value", "prov:location"})
MAX_SAFE_INT: Final = 2**53 - 1
#: The PROV class each argument position requires (C50 typing), used by the NE-19 and reference checks.
ARG_KIND: Final = {
    "prov:entity": "entity", "prov:activity": "activity", "prov:informed": "activity", "prov:informant": "activity",
    "prov:trigger": "entity", "prov:starter": "activity", "prov:ender": "activity", "prov:generatedEntity": "entity",
    "prov:usedEntity": "entity", "prov:agent": "agent", "prov:plan": "entity", "prov:delegate": "agent",
    "prov:responsible": "agent", "prov:specificEntity": "entity", "prov:generalEntity": "entity",
    "prov:bundle": "entity", "prov:collection": "entity", "prov:alternate1": "entity", "prov:alternate2": "entity",
}  # fmt: skip


def check(doc: Any) -> list[CheckOutcome]:
    """Run every structure check over a decoded PROV-JSON document."""
    view = ProvView.parse(doc)
    return [
        outcome(f"{M}.document", _document(doc)),
        outcome(f"{M}.prefixes", _prefixes(doc)),
        outcome(f"{M}.bundles", _bundles(doc, view)),
        outcome(f"{M}.relations", _relations(view)),
        outcome(f"{M}.qnames", _qnames(view)),
        outcome(f"{M}.values", _values(view)),
        outcome(f"{M}.identifiers", _identifiers(view)),
        outcome(f"{M}.references", _references(view)),
        outcome("PV-NE-19", _ne19(view)),
    ]


# ============================================================================================================ document
def _container_members(container: dict[str, Any], where: str, *, top: bool) -> Iterator[Finding]:
    for member, value in container.items():
        if member == "prefix":
            if not top:
                yield Finding(f"{M}.bundle_prefix", where, "a bundle declares prefixes")
            continue
        if member == "bundle":
            if not top:
                yield Finding(f"{M}.nested_bundle", where, "a bundle contains bundles")
            elif not isinstance(value, dict):
                yield Finding(f"{M}.section_not_object", f"{where}:bundle", type(value).__name__)
            continue
        if member not in ELEMENT_SECTIONS and member not in RELATION_ARGS:
            yield Finding(f"{M}.top_member", where, f"unknown member {_label(member)}")
            continue
        if not isinstance(value, dict):
            yield Finding(f"{M}.section_not_object", f"{where}:{member}", type(value).__name__)
            continue
        if not value:
            yield Finding(f"{M}.empty_section", f"{where}:{member}", "empty sections are omitted (E.5.3 item 2)")
        for key, body in value.items():
            if not isinstance(body, dict):
                yield Finding(f"{M}.statement_not_object", f"{where}:{member}:{_label(key)}", type(body).__name__)


def _document(doc: Any) -> Iterator[Finding]:
    if not isinstance(doc, dict):
        yield Finding(f"{M}.not_object", "document", type(doc).__name__)
        return
    yield from _container_members(doc, "top", top=True)
    bundles = doc.get("bundle")
    if isinstance(bundles, dict):
        for iri, body in bundles.items():
            if not isinstance(body, dict):
                yield Finding(f"{M}.section_not_object", f"bundle:{_label(iri)}", type(body).__name__)
            else:
                yield from _container_members(body, str(iri), top=False)


def _prefixes(doc: Any) -> Iterator[Finding]:
    if not isinstance(doc, dict):
        return
    prefix = doc.get("prefix")
    if not isinstance(prefix, dict):
        yield Finding(f"{M}.prefix_missing", "top", "no prefix object")
        return
    for name, iri in prefix.items():
        if name in RESERVED_PREFIXES:
            yield Finding(f"{M}.reserved_prefix", f"prefix:{name}", "prov and xsd are never declared (E.4.1)")
        if not isinstance(iri, str) or not iri:
            yield Finding(f"{M}.prefix_value", f"prefix:{_label(name)}", "not an IRI string")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.\-]*", str(name)):
            yield Finding(f"{M}.prefix_name", f"prefix:{_label(name)}", "not a prefix name")


def _bundles(doc: Any, view: ProvView) -> Iterator[Finding]:
    if not isinstance(doc, dict):
        return
    cores = [b for b in view.bundles.values() if b.kind == "core"]
    if len(cores) != 1:
        yield Finding(f"{M}.core_count", "bundle", f"{len(cores)} core bundles (exactly one, E.3.1)")
    for b in view.bundles.values():
        core = CORE_RE.fullmatch(b.iri)
        inf = INF_RE.fullmatch(b.iri)
        assess = ASSESS_RE.fullmatch(b.iri)
        if core is None and inf is None and assess is None:
            yield Finding(f"{M}.bundle_iri", b.iri,
                          "not xd:bundle.core.<dk>, xd:bundle.inf.<slug>.<dk> or xd:bundle.assess.<slug>.<dk>")
            continue
        if b.kind in ("inference", "assessment") and not b.statements:
            yield Finding(f"{M}.empty_bundle", b.iri, f"empty {b.kind} bundles are not emitted (E.3.1)")
        entity = view.top_elements.get(b.iri)
        if entity is None or entity.section != "entity":
            yield Finding(f"{M}.bundle_entity", b.iri, "no top-level bundle entity")
            continue
        want = "apv:CoreBundle" if core else "apv:InferenceBundle" if inf else "apv:AssessmentBundle"
        if not {"prov:Bundle", want} <= entity.types:
            yield Finding(f"{M}.bundle_entity", b.iri, f"bundle entity is not typed prov:Bundle and {want}")
        match = core or inf or assess
        assert match is not None
        dk = match.group(1) if core is not None else match.group(2)
        if entity.attrs.get("apv:derivationKey") != dk:
            yield Finding(f"{M}.bundle_entity", b.iri, "apv:derivationKey differs from the IRI's key")
        if inf is not None:
            if b.methods is None:
                yield Finding(f"{M}.bundle_entity", b.iri, "inference bundle entity has no apv:method")
            elif method_slug(b.methods) != inf.group(1):
                yield Finding(f"{M}.bundle_entity", b.iri, "method-set slug differs from apv:method")
        elif "apv:method" in entity.attrs:
            yield Finding(f"{M}.bundle_entity", b.iri, f"{b.kind} bundle entity carries apv:method")
        if assess is not None:
            if b.profile is None:
                yield Finding(f"{M}.bundle_entity", b.iri, "assessment bundle entity has no apv:profile")
            elif rule_slug(b.profile) != assess.group(1):
                yield Finding(f"{M}.bundle_entity", b.iri, "profile slug differs from apv:profile")
        elif "apv:profile" in entity.attrs:
            yield Finding(f"{M}.bundle_entity", b.iri, f"{b.kind} bundle entity carries apv:profile")
    for key, s in view.top_elements.items():
        if "prov:Bundle" in s.types and key not in view.bundles:
            yield Finding(f"{M}.bundle_entity", key, "bundle entity without a bundle")


# ============================================================================================================ relations
def _relations(view: ProvView) -> Iterator[Finding]:
    for s in view.all_statements():
        if s.is_element:
            allowed = ACTIVITY_PROV_ATTRS if s.section == "activity" else ELEMENT_PROV_ATTRS
            for k in s.attrs:
                if k.startswith("prov:") and k not in allowed:
                    yield Finding(f"{M}.unknown_attribute", s.where, f"{k} on an {s.section}")
            continue
        args = RELATION_ARGS[s.section]
        for k in REQUIRED_ARGS[s.section]:
            if k not in s.attrs:
                yield Finding(f"{M}.missing_argument", s.where, k)
        for k, v in s.attrs.items():
            if k in args:
                if not isinstance(v, str):
                    yield Finding(f"{M}.argument_type", s.where, f"{k} is not a QName string")
            elif k.startswith("prov:") and k not in RELATION_PROV_ATTRS:
                yield Finding(f"{M}.unknown_attribute", s.where, f"{k} in {s.section}")
        if s.section in UNIDENTIFIED:
            extra = sorted(k for k in s.attrs if k not in args)
            if extra:
                yield Finding(f"{M}.unidentified_attribute", s.where, ", ".join(_label(k) for k in extra[:5]))
    yield from _placement(view)


#: The general entity of every top-level ``specializationOf`` (``aprov.t_spec@1``, E.3; E.5.1 item 3).
EXECUTION_PROVENANCE: Final = "xd:provenance"


def _placement(view: ProvView) -> Iterator[Finding]:
    """E.5.1 item 3 (D-621): where the unidentified relations may sit, and the one ``specializationOf`` per bundle."""
    code = f"{M}.unidentified_placement"
    for s in view.all_statements():
        if s.section not in UNIDENTIFIED:
            continue
        bundle = view.bundles.get(s.bundle) if s.bundle is not None else None
        if s.section == "alternateOf":
            yield Finding(code, s.where, "alternateOf is never emitted (E.5.1 item 3)")
        elif s.section == "specializationOf" and s.bundle is not None:
            yield Finding(code, s.where, "specializationOf only at the top level")
        elif s.section == "hadMember" and s.bundle is None:
            yield Finding(code, s.where, "hadMember only inside a bundle (tool-call requests)")
        elif s.section == "mentionOf" and (bundle is None or bundle.kind not in ("inference", "assessment")):
            yield Finding(code, s.where, "mentionOf only inside inference and assessment bundles")
    seen: dict[str, int] = {}
    for s in view.top:
        if s.section != "specializationOf":
            continue
        specific, general = s.arg("prov:specificEntity"), s.arg("prov:generalEntity")
        if general != EXECUTION_PROVENANCE or specific not in view.bundles:
            yield Finding(code, s.where, f"a top-level specializationOf is (<bundle>, {EXECUTION_PROVENANCE}) only")
            continue
        seen[specific] = seen.get(specific, 0) + 1
    for iri in view.bundles:
        if seen.get(iri, 0) != 1:
            yield Finding(code, iri, f"{seen.get(iri, 0)} specializationOf({iri}, {EXECUTION_PROVENANCE}) (exactly one)")
    if view.bundles:
        entity = view.top_elements.get(EXECUTION_PROVENANCE)
        if entity is None or entity.section != "entity" or "apv:ExecutionProvenance" not in entity.types:
            yield Finding(code, EXECUTION_PROVENANCE, "the top-level entity xd:provenance (apv:ExecutionProvenance) is missing")


# ============================================================================================================ qnames
def _qname_ok(text: Any, prefixes: dict[str, str], *, allow_prov: bool = True) -> str | None:
    """``None`` when ``text`` is a well-formed QName under a declared prefix, else the finding code suffix."""
    if not isinstance(text, str):
        return "qname"
    m = QNAME_RE.fullmatch(text)
    if m is None:
        return "qname"
    prefix = m.group(1)
    if prefix in prefixes or (allow_prov and prefix in RESERVED_PREFIXES):
        return None
    return "undeclared_prefix"


def _qnames(view: ProvView) -> Iterator[Finding]:
    prefixes = view.prefixes
    for s in view.all_statements():
        if s.is_identified and (bad := _qname_ok(s.key, prefixes, allow_prov=False)):
            yield Finding(f"{M}.{bad}", s.where, "statement identifier")
        for k, v in s.attrs.items():
            if (bad := _qname_ok(k, prefixes)) is not None:
                yield Finding(f"{M}.{bad}", s.where, f"attribute key {_label(k)}")
            if not s.is_element and k in RELATION_ARGS[s.section] and k != "prov:time":
                if isinstance(v, str) and (bad := _qname_ok(v, prefixes, allow_prov=False)) is not None:
                    yield Finding(f"{M}.{bad}", s.where, f"argument {k}")
                continue
            for item in as_list(v):
                if isinstance(item, dict):
                    t = item.get("type")
                    if t is not None and (bad := _qname_ok(t, prefixes)) is not None:
                        yield Finding(f"{M}.{bad}", s.where, f"{_label(k)} value type")
                    q = qname_value(item)
                    if q is not None and (bad := _qname_ok(q, prefixes)) is not None:
                        yield Finding(f"{M}.{bad}", s.where, f"{_label(k)} QName value")
    for iri in view.bundles:
        if (bad := _qname_ok(iri, prefixes, allow_prov=False)) is not None:
            yield Finding(f"{M}.{bad}", "bundle", "bundle identifier")


# ============================================================================================================ values
def _value_form(v: Any) -> str | None:
    if isinstance(v, bool | str):
        return None
    if isinstance(v, int):
        return None if abs(v) <= MAX_SAFE_INT else "integer outside I-JSON"
    if isinstance(v, float):
        return "plain JSON number; xsd:double uses the typed form (E.5.3 item 3)"
    if isinstance(v, dict):
        if not isinstance(v.get("$"), str) or not isinstance(v.get("type"), str):
            return "typed value without string $ and type"
        if set(v) - {"$", "type", "lang"}:
            return "typed value with extra members"
        if v["type"] == "xsd:double":
            try:
                if repr(float(v["$"])) != v["$"]:
                    return "xsd:double not in shortest round-trip form"
            except ValueError:
                return "xsd:double lexical form invalid"
        return None
    return f"value of type {type(v).__name__}"


def _values(view: ProvView) -> Iterator[Finding]:
    for s in view.all_statements():
        for k, v in s.attrs.items():
            if not s.is_element and k in RELATION_ARGS[s.section]:
                continue
            if isinstance(v, list):
                if len(v) < 2:
                    yield Finding(f"{M}.singleton_array", s.where, f"{_label(k)}: a single value is a scalar")
                keys: list[bytes] = []
                for item in v:
                    if (bad := _value_form(item)) is not None:
                        yield Finding(f"{M}.value_form", s.where, f"{_label(k)}: {bad}")
                        break
                    keys.append(jcs_bytes(item))
                else:
                    if len(set(keys)) != len(keys):
                        yield Finding(f"{M}.multi_value_duplicate", s.where, _label(k))
                    elif keys != sorted(keys) and k != "apv:sourcePointer":  # E.1.5 item 6 orders those by
                        # record position, then pointer; pv.linkage.source_pointer checks that order
                        yield Finding(f"{M}.multi_value_order", s.where, f"{_label(k)} not sorted by JCS bytes")
            elif (bad := _value_form(v)) is not None:
                yield Finding(f"{M}.value_form", s.where, f"{_label(k)}: {bad}")


# ============================================================================================================ identifiers
def _identifiers(view: ProvView) -> Iterator[Finding]:
    seen: dict[str, str] = {}
    for s in view.all_statements():
        prev = seen.setdefault(s.key, s.where)
        if prev != s.where and s.is_identified:
            yield Finding(f"{M}.duplicate_identifier", s.where, f"also {prev}")
        if s.is_element:
            if s.bundle is None:
                if TOP_ELEMENT_RE.fullmatch(s.key) is None:
                    yield Finding(f"{M}.node_name", s.where, "top-level elements are raw:, xd:, sw: or rules: names")
            elif NODE_NAME_RE.fullmatch(s.key) is None:
                yield Finding(f"{M}.node_name", s.where, "not an E.1.2 node name")
            continue
        m = STATEMENT_RE.fullmatch(s.key)
        if s.section in UNIDENTIFIED:
            if m is None or m.group("prefix") != "_":
                yield Finding(f"{M}.statement_id", s.where, "unidentified relations are keyed _:<rule-name>.<h16>")
            continue
        if s.key.startswith("_:"):
            yield Finding(f"{M}.blank_node", s.where, "an identified relation keyed by a blank node")
            continue
        if m is None:
            yield Finding(f"{M}.statement_id", s.where, "not <rule-name>.<h16> (E.4.2)")
            continue
        want = "xd" if s.bundle is None else "x"
        if m.group("prefix") != want:
            yield Finding(f"{M}.statement_id", s.where, f"statement ids here are {want}: names")
        rule = s.rule
        if rule is not None and m.group("name") != rule_name(rule):
            yield Finding(f"{M}.statement_id", s.where, f"rule name does not match apv:rule {_label(rule)}")
    for s in view.all_statements():
        for k, v in s.attrs.items():
            for item in as_list(v):
                text = item if isinstance(item, str) and not s.is_element and k in RELATION_ARGS[s.section] else qname_value(item)
                if isinstance(text, str) and text.startswith("_:"):
                    yield Finding(f"{M}.blank_node", s.where, f"{_label(k)} references a blank node")


# ============================================================================================================ references
def _declared_in(view: ProvView, bundle: str | None) -> dict[str, str]:
    """Element key -> section for the application view of ``bundle`` (top level: the top-level elements)."""
    if bundle is None:
        return {k: s.section for k, s in view.top_elements.items()}
    out: dict[str, str] = {}
    for b in view.visible(bundle):
        for s in b.statements:
            if s.is_element:
                out.setdefault(s.key, s.section)
    mine = view.bundles.get(bundle)
    if mine is not None and mine.kind == "assessment":  # the engine agent and the profile plan (E.7.2 item 2)
        for key, s in view.top_elements.items():
            if s.section == "agent" or "prov:Plan" in s.types:
                out.setdefault(key, s.section)
    return out


def _references(view: ProvView) -> Iterator[Finding]:
    declared: dict[str | None, dict[str, str]] = {None: _declared_in(view, None)}
    core = view.core
    core_nodes = {s.key for s in core.statements if s.is_element} if core is not None else set()
    core_keys = {s.key for s in core.statements} if core is not None else set()
    for s in view.all_statements():
        if s.bundle not in declared:
            declared[s.bundle] = _declared_in(view, s.bundle)
        scope = declared[s.bundle]
        if not s.is_element:
            for k, v in s.args().items():
                if k == "prov:bundle":
                    if v not in view.bundles:
                        yield Finding(f"{M}.unresolved_argument", s.where, f"{k} is not a bundle of the document")
                    else:
                        general = s.arg("prov:generalEntity")
                        members = {t.key for t in view.bundles[v].statements if t.is_element}
                        if general is not None and general not in members:
                            yield Finding(f"{M}.unresolved_argument", s.where, "prov:generalEntity is not declared in prov:bundle")
                    continue
                if s.bundle is not None and k in ("prov:generation", "prov:usage"):
                    continue
                if s.bundle is None and k in ("prov:generation", "prov:usage"):
                    if v not in view.by_key:
                        yield Finding(f"{M}.unresolved_argument", s.where, f"{k} is not a statement")
                    continue
                if v not in scope:
                    code = "core_undeclared" if core is not None and s.bundle == core.iri else "unresolved_argument"
                    yield Finding(f"{M}.{code}", s.where, f"{k} {_label(v)} is not declared in the application view")
        if core is not None and s.bundle == core.iri:
            for k, v in s.attrs.items():
                for q in qname_values(v):
                    if not q.startswith("x:"):
                        continue
                    target_ok = q in core_keys if k == "apv:premise" else q in core_nodes
                    if not target_ok:
                        yield Finding(f"{M}.core_undeclared", s.where, f"{k} references {_label(q)} outside the core")


def _ne19(view: ProvView) -> Iterator[Finding]:
    kinds = {k: s.section for k, s in view.top_elements.items()}
    for k, s in view.elements.items():
        kinds.setdefault(k, s.section)
    for s in view.all_statements():
        if s.section == "used":
            e = s.arg("prov:entity")
            if e is not None and kinds.get(e) in ("activity", "agent"):
                yield Finding(f"{M}.used_activity", s.where, f"used object {_label(e)} is an {kinds.get(e)}")
        elif s.section == "mentionOf":
            for k in ("prov:specificEntity", "prov:generalEntity"):
                v = s.arg(k)
                if v is None or kinds.get(v) != "entity":
                    yield Finding(f"{M}.mention_not_entity", s.where, f"{k} is not a declared entity")
            supra = s.arg("prov:specificEntity")
            if supra is not None and s.bundle is not None:
                local = {t.key for t in view.bundles[s.bundle].statements if t.is_element}
                if supra not in local:
                    yield Finding(f"{M}.mention_not_entity", s.where, "the mention entity is not declared in its bundle")


def _label(value: Any) -> str:
    """A short, safe label for keys from the document (ids and QNames are printable ASCII by construction; anything
    else is replaced)."""
    text = str(value)
    if len(text) > 80 or not text.isascii() or not text.isprintable():
        return f"<{len(text)} chars>"
    return text


def labels(values: Iterable[Any]) -> str:
    return ", ".join(_label(v) for v in values)
