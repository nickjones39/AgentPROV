"""Synthetic, builder-independent inputs for the tier-4 validator unit tests (K.10; audit/validation.md §3.10)."""

from __future__ import annotations

from typing import Any

from agentprov.aer.reader import AerDocument

EX = "ex_unit"
BASE = "https://w3id.org/agentprov/"
PREFIX = {
    "apv": BASE + "ns#",
    "raw": BASE + "raw/",
    "rules": BASE + "rules/",
    "sw": BASE + "sw/",
    "x": f"{BASE}exec/{EX}#",
    "xd": f"{BASE}exec/{EX}/",
}
CORE = "xd:bundle.core." + "a" * 26


def q(name: str) -> dict[str, str]:
    return {"$": name, "type": "prov:QUALIFIED_NAME"}


def ev(cls: str = "Observed", rule: str = "aprov.n_tool_execution@1", **extra: Any) -> dict[str, Any]:
    return {"apv:evidenceClass": q(f"apv:{cls}"), "apv:rule": rule, **extra}


def minimal_doc(core: dict[str, Any] | None = None) -> dict[str, Any]:
    """A one-bundle document: the core bundle, its top-level bundle entity and its ``aprov.t_spec@1`` statements."""
    return t_spec({
        "prefix": dict(PREFIX),
        "entity": {CORE: {"prov:type": [q("apv:CoreBundle"), q("prov:Bundle")], "apv:derivationKey": "a" * 26,
                          **ev(rule="aprov.t_derive@1")}},
        "bundle": {CORE: core if core is not None else {"entity": {"x:m0": ev(rule="aprov.n_message@1")}}},
    })


def t_spec(doc: dict[str, Any]) -> dict[str, Any]:
    """Add what E.5.1 item 3 requires at the top level (D-621): the entity ``xd:provenance`` and exactly one
    ``specializationOf(<bundle>, xd:provenance)`` per bundle of ``doc`` (replacing any present). Returns ``doc``."""
    doc.setdefault("entity", {})["xd:provenance"] = {"prov:type": q("apv:ExecutionProvenance"), **ev(rule="aprov.t_spec@1")}
    doc["specializationOf"] = {
        f"_:t_spec.{chr(ord('a') + n) * 16}": {"prov:specificEntity": iri, "prov:generalEntity": "xd:provenance"}
        for n, iri in enumerate(sorted(doc.get("bundle", {})))
    }
    return doc


def minimal_aer(*records: dict[str, Any]) -> AerDocument:
    header = {"k": "execution", "id": "exec", "ex": EX, "ev": "O", "rules": {}, "artifacts": []}
    body = [header, *records]
    seal = {"k": "seal", "id": "seal", "n_records": len(body), "records_sha256": "0" * 64}
    index = {str(r["id"]): r for r in body}
    return AerDocument(header=header, records=body, seal=seal, execution_digest="0" * 64, file_sha256="0" * 64,
                       _index=index)
