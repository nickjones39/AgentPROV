"""Builders for the artefact-layer tests: a small clean sealed AER (as records) and a catalogue from TOML text.

The records are plain dicts shaped like a sealed ``aer/0.1`` file (header first, seal last). They are not written to disk:
``agentprov.artefacts.scan`` takes records, and these tests exercise the detectors, not the AER reader or validator.
"""

from __future__ import annotations

import copy
from typing import Any

from agentprov.artefacts import ArtefactCatalogue, parse_catalogue

PROFILE = "tst-profile"
EX = "ex_aaaaaaaaaaaaaaaaaaaaaaaaaa"


def header(**changes: Any) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "k": "execution", "id": "exec", "ex": EX, "aer": "0.1", "mode": "import", "unit": "agent_execution",
        "profile": {"id": PROFILE, "version": 1, "sha256": "0" * 64}, "rules": {"aer": 1},
    }  # fmt: skip
    rec.update(changes)
    return rec


def seal(*, issues: list[dict[str, Any]] | None = None, checks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    checks = checks or []
    status = (
        "inconsistent"
        if any(c["verdict"] == "inconsistent" for c in checks)
        else "unverifiable"
        if any(c["verdict"] == "unverifiable" for c in checks)
        else "consistent"
    )
    return {
        "k": "seal", "id": "seal", "n_records": 0, "records_sha256": "0" * 64,
        "accounting": {"status": status, "checks": checks}, "issues": issues or [],
    }  # fmt: skip


def clean() -> list[dict[str, Any]]:
    """One tool round trip, nothing anomalous: the scan of this execution is empty."""
    return [
        header(),
        {"k": "actor", "id": "agent", "kind": "llm_agent", "ev": "D"},
        {"k": "actor", "id": "env", "kind": "tool_runtime", "ev": "D"},
        {"k": "scope", "id": "run", "kind": "run", "ev": "D"},
        {"k": "scope", "id": "att0", "kind": "attempt", "parent": "run", "scored": True, "ev": "D"},
        {"k": "message", "id": "m0", "scope": "att0", "role": "user", "ev": "O",
         "parts": [{"t": "text", "text": "hello"}]},
        {"k": "model_call", "id": "mc0", "actor": "agent", "role": "agent", "scope": "att0", "status": "kept",
         "finish_reason": "tool_calls", "ev": "D"},
        {"k": "message", "id": "m1", "scope": "att0", "role": "assistant", "generated_by": "mc0", "ev": "O",
         "parts": [{"t": "text", "text": None},
                   {"t": "tool_call", "name": "lookup", "args": {"q": "x"}, "provider_call_id": "call_1"}]},
        {"k": "tool_execution", "id": "te0", "actor": "env", "scope": "att0", "call": "m1#1", "name": "lookup",
         "status": "ok", "ev": "D"},
        {"k": "message", "id": "m2", "scope": "att0", "role": "tool", "generated_by": "te0", "ev": "O",
         "parts": [{"t": "tool_result", "responds_to": "m1#1", "text": "result"}]},
        {"k": "model_call", "id": "mc1", "actor": "agent", "role": "agent", "scope": "att0", "status": "kept",
         "finish_reason": "stop", "ev": "D"},
        {"k": "message", "id": "m3", "scope": "att0", "role": "assistant", "generated_by": "mc1", "ev": "O",
         "parts": [{"t": "text", "text": "done"}]},
        seal(),
    ]  # fmt: skip


def without_seal(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in records if r["k"] != "seal"]


def with_records(
    base: list[dict[str, Any]], *extra: dict[str, Any], seal_record: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """``base`` with ``extra`` before the seal and the seal optionally replaced; the input is not touched."""
    out = copy.deepcopy(without_seal(base))
    out.extend(copy.deepcopy(list(extra)))
    out.append(seal_record if seal_record is not None else seal())
    return out


def replaced(records: list[dict[str, Any]], record_id: str, **changes: Any) -> list[dict[str, Any]]:
    out = copy.deepcopy(records)
    for rec in out:
        if rec["id"] == record_id:
            rec.update(changes)
            return out
    raise KeyError(record_id)


def catalogue(*entries: str, family: str = "tst", namespaces: str = '["tst"]') -> ArtefactCatalogue:
    """A catalogue built from entry TOML snippets (each a ``[[artefact]]`` block)."""
    text = f'version = 1\nfamily = "{family}"\nnamespaces = {namespaces}\n\n' + "\n".join(entries)
    return parse_catalogue(text.encode(), source="<test>", family=family)


def entry(
    name: str,
    *,
    detector: str = "artefact.generic.empty_execution",
    cls: str = "O",
    handling: str = "FO",
    extra: str = "",
    handling_rule: str = "",
) -> str:
    """One ``[[artefact]]`` block with the required fields; ``extra`` is appended verbatim."""
    rule = f', rule = "{handling_rule}"' if handling_rule else ""
    return (
        f'[[artefact]]\nid = "tst.art.{name}"\ntitle = "{name}"\ndescription = "test entry {name}"\n'
        f'cause = "unknown"\ndetector = {{ rule = "{detector}", class = "{cls}" }}\n'
        f'handling = {{ class = "{handling}"{rule} }}\n{extra}\n'
    )


def attacked(records: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """``records`` (default :func:`clean`) with an ``attack_id`` in the header task, i.e. an attacked execution."""
    out = copy.deepcopy(records if records is not None else clean())
    out[0]["task"] = {"task_id": "t0", "attack_id": "tst_attack"}
    return out


def sem_records(*statuses: str, ex: str = EX, extra: tuple[dict[str, Any], ...] = ()) -> list[dict[str, Any]]:
    """The records of a SEM file (header, then annotations, then the seal): one ``injection_marker`` per status on m2#0
    and one unrelated annotation. Shaped like ``agentprov.sem.reader.load_sem(...).records`` plus the seal."""
    out: list[dict[str, Any]] = [{"k": "sem", "id": "sem", "sem": "0.1", "ex": ex, "profile": {"id": "tst.sem", "version": 1}}]
    out.append({"k": "ann", "id": "a0", "target": "m2#0", "type": "integrity", "value": "untrusted", "ev": "I", "rule": ["tst.r@1"]})
    for k, status in enumerate(statuses, start=1):
        out.append({"k": "ann", "id": f"a{k}", "target": "m2#0", "type": "injection_marker", "ev": "D", "rule": ["tst.m@1"],
                    "value": {"fixture": f"fx{k}", "status": status, "normaliser": "tst.norm@1"}})
    out.extend(extra)
    out.append({"k": "seal", "id": "seal", "n_records": len(out), "records_sha256": "0" * 64})
    return out
