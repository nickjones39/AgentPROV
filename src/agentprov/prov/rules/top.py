"""Top-level conversion provenance ``aprov.t_*@1`` (EF E.3.3).

These statements describe AgentPROV's own processing: raw artefacts, the AER and its mapping, the derive activity, the
bundles it generated, the plans (rule catalogues) and the software agents. The engine agent is ``sw:agentprov``
without a version: the document is a function of the AER, the spec, the catalogues and the options only (E.9), and
the software version and code digest of the run are recorded in the corpus ``derivation.json`` (H.8.2; DECISIONS
D-13). They carry ``apv:evidenceClass`` and
``apv:rule`` only, and live at the document's top level, never in a bundle. ``hadPrimarySource`` is stated only for
artefacts whose ``prov_primary`` is ``native`` or ``byte_derived`` (NE-20).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Final

from agentprov.aer.rules import CatalogueUnavailableError
from agentprov.io.canonical import jcs_bytes
from agentprov.prov import iri
from agentprov.prov._ir import ARG_ORDER, q

if TYPE_CHECKING:
    from agentprov.prov.engine import BundleInfo, Ctx
    from agentprov.sem.types import SemanticsProfile, SemDocument

__all__ = ["build"]

PRIMARY: Final = frozenset({"native", "byte_derived"})
ORIGIN_ATTRS: Final[dict[str, tuple[tuple[str, str], ...]]] = {
    "git": (("repo", "apv:originRepository"), ("commit", "apv:originRevision"), ("path", "apv:originPath"),
            ("blob_sha1", "apv:originBlob")),
    "hf": (("repo", "apv:originRepository"), ("revision", "apv:originRevision"), ("path", "apv:originPath")),
    "zenodo": (("doi", "apv:originRepository"), ("file", "apv:originPath")),
    "url": (("url", "apv:originPath"),),
    "corpus": (("corpus", "apv:originRepository"), ("version", "apv:originRevision"), ("path", "apv:originPath")),
    "capture": (("session", "apv:originLabel"),),
    "member": (("container", "apv:originContainer"), ("label", "apv:originLabel")),
    "local": (("path", "apv:originPath"),),
}


class _Top:
    def __init__(self, dk: str) -> None:
        self.dk = dk
        self.doc: dict[str, dict[str, Any]] = {}

    def element(self, section: str, ident: str, rule: str, attrs: dict[str, Any]) -> None:
        body = dict(attrs)
        body["apv:evidenceClass"] = q("apv:Observed")
        body["apv:rule"] = rule
        self.doc.setdefault(section, {})[ident] = body

    def relation(self, section: str, rule: str, args: dict[str, str], attrs: dict[str, Any] | None = None,
                 disc: str = "") -> str:
        argv = [args.get(k, "-") for k in ARG_ORDER[section]]
        name = iri.statement_name(self.dk, rule, argv, disc)
        if section in ("specializationOf", "hadMember", "mentionOf"):
            self.doc.setdefault(section, {})["_:" + name] = dict(args)
            return "_:" + name
        ident = "xd:" + name
        body = {**(attrs or {}), **args, "apv:evidenceClass": q("apv:Observed"), "apv:rule": rule}
        sec = self.doc.setdefault(section, {})
        if ident in sec:
            raise ValueError(f"top-level collision {ident}")
        sec[ident] = body
        return ident


def _types(*names: str) -> Any:
    values = sorted((q(n) for n in names), key=jcs_bytes)
    return values[0] if len(values) == 1 else values


def build(ctx: Ctx, bundles: Sequence[BundleInfo], dk_core: str,
          sems: Sequence[tuple[SemDocument, SemanticsProfile, BundleInfo]] = ()) -> dict[str, dict[str, Any]]:
    """The top level. ``sems`` pairs each SEM document with its profile and its assessment bundle: ``aprov.t_annotate@1``
    states the document and its annotation, ``aprov.t_plans@1`` the profile as an ``apv:SemanticsProfile`` plan, and
    ``aprov.t_derive@1`` the derive activity's use of it and each assessment bundle's derivation from it (E.3.3)."""
    header, seal = ctx.header, ctx.seal
    top = _Top(dk_core)
    digest = str(seal.get("records_sha256", ""))
    aer = f"xd:aer.{digest}"
    adapter = header.get("adapter") or {}
    adapter_agent = f"sw:{adapter.get('id')}.{adapter.get('version')}"
    engine_agent = "sw:agentprov"  # version-free (D-13): the run's software identity is in derivation.json
    # t_raw: one entity per content digest (D-621 #18, user decision 2026-10-22). Artifacts with identical bytes share
    # it; their per-artifact attributes become multi-valued (sorted, E.5.3 item 4) and their pairing stays in the AER
    # header. A digest stated once also states t_map, t_primary and t_capture once.
    by_digest: dict[str, list[dict[str, Any]]] = {}
    for art in header.get("artifacts", []):
        by_digest.setdefault(str(art["sha256"]), []).append(art)
    raws: list[tuple[str, list[dict[str, Any]]]] = []
    for sha, arts in by_digest.items():
        raw = f"raw:sha256-{sha}"
        values: dict[str, list[Any]] = {}
        for art in arts:
            origin = art.get("origin") or {}
            attrs: dict[str, Any] = {
                "prov:type": q("apv:RawSourceArtefact"),
                "apv:sha256": art["sha256"],
                "apv:bytes": art["bytes"],
                "apv:mediaType": art["media"],
                "apv:artefactRole": art["role"],
                "apv:provPrimary": art["prov_primary"],
                "apv:originKind": origin.get("kind"),
            }
            for key, prop in ORIGIN_ATTRS.get(str(origin.get("kind")), ()):
                if isinstance(origin.get(key), str | int):
                    attrs[prop] = origin[key]
            for k, v in attrs.items():
                if v is not None:
                    values.setdefault(k, []).append(v)
        body = {}
        for k, vs in values.items():
            unique = sorted({jcs_bytes(v): v for v in vs}.items())
            body[k] = unique[0][1] if len(unique) == 1 else [v for _, v in unique]
        top.element("entity", raw, "aprov.t_raw@1", body)
        raws.append((raw, arts))
    # t_capture (live mode): the session and the capture artefacts it generated
    if header.get("mode") == "live" and isinstance(header.get("capture"), dict):
        capture = "xd:capture"
        top.element("activity", capture, "aprov.t_capture@1", {"prov:type": q("apv:CaptureSession")})
        for raw, arts in raws:
            if any(art.get("role") == "capture_log" for art in arts):
                top.relation("wasGeneratedBy", "aprov.t_capture@1", {"prov:entity": raw, "prov:activity": capture})
        ctx.disclose("capture_software_unversioned", "exec", "capture and backend versions are not in aer/0.1")
    # t_agents and t_plans
    top.element("agent", engine_agent, "aprov.t_agents@1", {
        "prov:type": _types("prov:SoftwareAgent", "apv:ProvEngine"),
        "apv:softwareName": "agentprov",
    })
    top.element("agent", adapter_agent, "aprov.t_agents@1", {
        "prov:type": _types("prov:SoftwareAgent", "apv:Adapter"),
        "apv:softwareName": str(adapter.get("id")),
        "apv:softwareVersion": str(adapter.get("version")),
    })
    top.element("entity", ctx.spec.plan, "aprov.t_plans@1", {
        "prov:type": _types("prov:Plan", "apv:RuleCatalogue"),
        "apv:catalogueId": ctx.spec.catalogue_id,
        "apv:sha256": ctx.spec.catalogue_sha256,
    })
    plans: dict[str, str] = {}
    for ns, version in sorted(ctx.declared.items()):
        plan = f"rules:{ns}.{version}"
        plans[ns] = plan
        attrs = {"prov:type": _types("prov:Plan", "apv:RuleCatalogue"), "apv:catalogueId": ns}
        try:
            attrs["apv:sha256"] = ctx.registry.get(ns, int(version)).digest
        except CatalogueUnavailableError:
            ctx.disclose("catalogue_unavailable", "exec", f"{ns} {version}")
        top.element("entity", plan, "aprov.t_plans@1", attrs)
    profile_plans: dict[str, str] = {}
    for sem, profile, _ in sems:
        plan = f"rules:{profile.id}.{profile.version}"
        profile_plans[sem.digest] = plan
        top.element("entity", plan, "aprov.t_plans@1", {
            "prov:type": _types("prov:Plan", "apv:SemanticsProfile"),
            "apv:sha256": profile.sha256,
        })
    # t_map
    accounting = seal.get("accounting") or {}
    aer_attrs: dict[str, Any] = {
        "prov:type": q("apv:ExecutionRecord"),
        "apv:aerVersion": "aer/" + str(header.get("aer")),
        "apv:sha256": digest,
        "apv:executionId": ctx.doc.ex,
        "apv:sourceKey": "sha256:" + str(header["source_key"]["sha256"]) + "#"
        + jcs_bytes(header["source_key"].get("loc", {})).decode("utf-8"),
    }
    if isinstance(accounting.get("status"), str):
        aer_attrs["apv:accounting"] = accounting["status"]
    issues = sorted({str(i["code"]) for i in seal.get("issues", []) if isinstance(i, dict) and "code" in i})
    if issues:
        aer_attrs["apv:issue"] = issues[0] if len(issues) == 1 else issues
    top.element("entity", aer, "aprov.t_map@1", aer_attrs)
    mapping = f"xd:map.{iri.h('aprov-map/1' + chr(10) + digest, 16)}"
    top.element("activity", mapping, "aprov.t_map@1", {"prov:type": q("apv:Mapping")})
    gen_aer = top.relation("wasGeneratedBy", "aprov.t_map@1", {"prov:entity": aer, "prov:activity": mapping})
    for raw, _ in raws:
        use = top.relation("used", "aprov.t_map@1", {"prov:activity": mapping, "prov:entity": raw})
        top.relation("wasDerivedFrom", "aprov.t_map@1", {"prov:generatedEntity": aer, "prov:usedEntity": raw,
                     "prov:activity": mapping, "prov:generation": gen_aer, "prov:usage": use})
    for plan in plans.values():
        top.relation("wasAssociatedWith", "aprov.t_map@1", {"prov:activity": mapping, "prov:agent": adapter_agent,
                     "prov:plan": plan})
    # t_annotate: each SEM document, hashed separately (D6)
    sem_entities: dict[str, str] = {}
    for sem, profile, _ in sems:
        entity = f"xd:sem.{iri.profile_slug(profile.id, profile.version)}.{sem.digest}"
        sem_entities[sem.digest] = entity
        top.element("entity", entity, "aprov.t_annotate@1", {
            "prov:type": q("apv:SemanticAnnotationSet"),
            "apv:semVersion": "sem/" + str(sem.header.get("sem")),
            "apv:sha256": sem.digest,
        })
        annotate = f"xd:annotate.{iri.h('aprov-annotate/1' + chr(10) + sem.digest, 16)}"
        top.element("activity", annotate, "aprov.t_annotate@1", {"prov:type": q("apv:Annotation")})
        use = top.relation("used", "aprov.t_annotate@1", {"prov:activity": annotate, "prov:entity": aer})
        gen = top.relation("wasGeneratedBy", "aprov.t_annotate@1", {"prov:entity": entity, "prov:activity": annotate})
        top.relation("wasAssociatedWith", "aprov.t_annotate@1", {"prov:activity": annotate, "prov:agent": engine_agent,
                     "prov:plan": profile_plans[sem.digest]})
        top.relation("wasDerivedFrom", "aprov.t_annotate@1", {"prov:generatedEntity": entity, "prov:usedEntity": aer,
                     "prov:activity": annotate, "prov:generation": gen, "prov:usage": use})
    # t_derive, t_primary, t_spec
    derive = f"xd:derive.{dk_core}"
    top.element("activity", derive, "aprov.t_derive@1", {
        "prov:type": q("apv:ProvDerivation"),
        "apv:contextEncoding": ctx.options.context_encoding,
        "apv:profileOptions": jcs_bytes(ctx.options.as_json()).decode("utf-8"),
        "apv:vocabularyVersion": ctx.spec.vocabulary_version,
    })
    use_aer = top.relation("used", "aprov.t_derive@1", {"prov:activity": derive, "prov:entity": aer})
    use_sem = {digest: top.relation("used", "aprov.t_derive@1", {"prov:activity": derive, "prov:entity": entity})
               for digest, entity in sem_entities.items()}
    sem_of = {info.iri: sem.digest for sem, _, info in sems}
    top.relation("wasAssociatedWith", "aprov.t_derive@1", {"prov:activity": derive, "prov:agent": engine_agent,
                 "prov:plan": ctx.spec.plan})
    top.element("entity", "xd:provenance", "aprov.t_spec@1", {"prov:type": q("apv:ExecutionProvenance")})
    method_plans: set[str] = set()
    for b in bundles:
        kind_type = {"core": "apv:CoreBundle", "assessment": "apv:AssessmentBundle"}.get(b.kind, "apv:InferenceBundle")
        attrs = {"prov:type": _types("prov:Bundle", kind_type), "apv:derivationKey": b.derivation_key}
        if b.profile:
            attrs["apv:profile"] = b.profile
        if b.methods:
            attrs["apv:method"] = list(b.methods) if len(b.methods) > 1 else b.methods[0]
            method_plans |= {plans[m.split(".", 1)[0]] for m in b.methods if m.split(".", 1)[0] in plans}
        top.element("entity", b.iri, "aprov.t_derive@1", attrs)
        gen_b = top.relation("wasGeneratedBy", "aprov.t_derive@1", {"prov:entity": b.iri, "prov:activity": derive})
        top.relation("wasDerivedFrom", "aprov.t_derive@1", {"prov:generatedEntity": b.iri, "prov:usedEntity": aer,
                     "prov:activity": derive, "prov:generation": gen_b, "prov:usage": use_aer})
        if b.iri in sem_of:
            digest = sem_of[b.iri]
            top.relation("wasDerivedFrom", "aprov.t_derive@1", {"prov:generatedEntity": b.iri,
                         "prov:usedEntity": sem_entities[digest], "prov:activity": derive, "prov:generation": gen_b,
                         "prov:usage": use_sem[digest]})
        for raw, arts in raws:
            top.relation("wasDerivedFrom", "aprov.t_primary@1", {"prov:generatedEntity": b.iri, "prov:usedEntity": raw})
            if any(art.get("prov_primary") in PRIMARY for art in arts):
                top.relation("wasDerivedFrom", "aprov.t_primary@1", {"prov:generatedEntity": b.iri, "prov:usedEntity": raw},
                             {"prov:type": q("prov:PrimarySource")}, disc="primary")
        top.relation("specializationOf", "aprov.t_spec@1", {"prov:specificEntity": b.iri,
                     "prov:generalEntity": "xd:provenance"})
    for plan in sorted(method_plans):
        top.relation("wasAssociatedWith", "aprov.t_derive@1", {"prov:activity": derive, "prov:agent": adapter_agent,
                     "prov:plan": plan}, {"prov:role": q("apv:MethodProvider")})
    return top.doc
