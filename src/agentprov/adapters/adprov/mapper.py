"""Mapper ``adprov.transcript_v1``: AgentDojo-PROV transcript/v1 -> AER ``aer/0.1`` (docs/architecture D.7.3; C.15.3).

The mapping follows the normative worked example C.16.2 record for record, and generalises it to every variant and
flag of D.7.2. Its inverse is the view :func:`agentprov.views.transcript_v1.render`: for every frozen-baseline file,
``serialise(render(map(file)))`` equals the file bytes (gates A1 and A2, J.3.2). What makes that possible:

* every object and number copied from the transcript goes through :func:`agentprov.aer.canon.encode_value`, which
  writes the sparse ``ext.lex`` hints (member order, integral floats; C.11.4) at the pointer where the value lands;
* the member order of ``meta``, ``meta.model_config`` and its ``usage`` is the layout record ``ext.adprov.v1``;
  turn-level order is a constant of the view unless a message records ``ext.adprov.keys`` (C.15.3, J.3.2);
* the few transcript members with no core slot are kept verbatim under ``ext.adprov`` / ``ext.agentdojo`` (C.10).

Evidence (C.6): context membership is INFERRED (``adprov.context_is_prefix@1``, AD-05); reasoning and refusal attached by
position are I; the converted tree's ``"0"`` tool timing is ``t.raw`` plus ``unk`` (C.7.3); unknowns are declared with
the closed reasons, never filled. A D rule is cited at D only where the profile's ``verified_code`` lists a commit its
catalogue ``code`` cites for the transcript's tree (released or converted), else through its ``_unverified`` twin, and
every record is weakened to the class of the rules that justify it (D.5.4, D-24, D-27 c6; C.6.5 rule 1). Seal issues are reported through the context, never swallowed (D.2.8).

Pure (A-2): the output is a function of the unit's bytes, this code, the profile and the catalogues only.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator, Mapping, Sequence
from typing import Any, Final

from agentprov.adapters.adprov.dialect import (
    DIALECT_ID,
    FLAG_CONVERTED,
    FLAG_NULL_AS_EMPTY,
    FLAG_STUBBED,
    VARIANT,
)
from agentprov.adapters.code_verification import Citations, parse_verified_code, weaken_to_rule_class
from agentprov.adapters.surrogates import scrub_keys, surrogates
from agentprov.adapters.protocols import AerRecord, MappingContext
from agentprov.adapters.types import ExecutionUnit
from agentprov.aer.canon import LexHints, encode_value, json_pointer
from agentprov.aer.ids import part_id
from agentprov.errors import MalformedArtefact
from agentprov.io.canonical import jcs_bytes
from agentprov.views.transcript_v1 import BENIGN_LABEL, layout, usage_map

__all__ = ["ADAPTER_ID", "ADAPTER_VERSION", "CATALOGUES", "NAMESPACES", "TranscriptV1Mapper"]

ADAPTER_ID: Final = "adprov.transcript_v1"
ADAPTER_VERSION: Final = "0.1.0"
#: Catalogues this mapper cites; the header lists them at the shipped versions (C.3.1 ``rules``).
CATALOGUES: Final = ("adprov", "aer", "agentdojo")
#: The catalogues whose D rules are cited at D only for verified code (D.5.4 "Citation of D rules", D-24).
CITED_NAMESPACES: Final = frozenset({"adprov", "agentdojo"})
NAMESPACES: Final = {
    "adprov": "https://w3id.org/agentprov/ns/adprov#",
    "agentdojo": "https://w3id.org/agentprov/ns/agentdojo#",
}
_UTC_SUFFIX: Final = "+00:00"
_RFC3339_UTC: Final = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?\+00:00")
_INVALID_PREFIXES: Final = ("Empty function name provided", "Invalid tool ")
_MODEL_CALL_UNKNOWN: Final = ("/params", "/request", "/response", "/t", "/tools", "/usage")


def _p(*tokens: str | int) -> str:
    return json_pointer(*tokens)


def _loc(pointer: str) -> dict[str, Any]:
    return {"a": "a0", "p": pointer}


def _to_z(value: object) -> str | None:
    """``…+00:00`` -> ``…Z`` (a lossless re-encoding, C.8.3); ``None`` for anything else."""
    if isinstance(value, str) and _RFC3339_UTC.fullmatch(value):
        return value[: -len(_UTC_SUFFIX)] + "Z"
    return None


def _tool_status(error: object) -> str:
    """``agentdojo.tool_status_from_error@1``."""
    if error is None:
        return "ok"
    text = str(error)
    if text.startswith("ValidationError") or text.startswith(_INVALID_PREFIXES):
        return "invalid"
    return "error"


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _jcs_equal(a: object, b: object) -> bool:
    try:
        return jcs_bytes(a) == jcs_bytes(b)
    except (TypeError, ValueError):
        return False


def check_order(observed: Sequence[str], template: Sequence[tuple[str, bool]]) -> tuple[list[str], bool]:
    """``(unknown members, order allowed)`` of an object's member list against a J.3.2 layout template."""
    names = [m for m, _ in template]
    unknown = [k for k in observed if k not in names]
    known = [k for k in observed if k in names]
    positions = [names.index(k) for k in known]
    required = {m for m, optional in template if not optional}
    ok = positions == sorted(positions) and len(set(known)) == len(known) and required <= set(known)
    return unknown, ok


class _Rec:
    """A record under construction: fields plus its lexical hints."""

    def __init__(self, **fields: Any) -> None:
        self.data: dict[str, Any] = dict(fields)
        self.lex = LexHints()

    def enc(self, value: object, pointer: str) -> Any:
        return encode_value(value, at=pointer, lex=self.lex)

    def set(self, field: str, value: object) -> None:
        self.data[field] = self.enc(value, "/" + field)

    def done(self) -> dict[str, Any]:
        out = dict(self.data)
        if self.lex:
            ext = dict(out.get("ext") or {})
            ext["lex"] = self.lex.as_dict()
            out["ext"] = ext
        return out


class TranscriptV1Mapper:
    """``Mapper`` for ``adprov.transcript_v1`` (D.2.4)."""

    mapper_id: Final = ADAPTER_ID
    version: Final = ADAPTER_VERSION
    accepts: Final = frozenset({(DIALECT_ID, VARIANT)})
    namespaces: Final = NAMESPACES
    catalogues: Final = CATALOGUES

    def map(self, unit: ExecutionUnit, ctx: MappingContext) -> Iterator[AerRecord]:
        yield from _Build(unit, ctx).run()

    @staticmethod
    def prov_primary(flags: frozenset[str]) -> str:
        """``native`` for released transcripts (the generating harness wrote them), ``secondary`` for converted ones (a
        derived conversion of an upstream log, D.7.3; R-22)."""
        return "secondary" if FLAG_CONVERTED in flags else "native"

    def degenerate_header(self, unit: ExecutionUnit, ctx: MappingContext, *, issue_code: str, detail: str) -> dict[str, Any]:
        """The header of a degenerate AER (D.2.8 case 3), with its error issue reported through ``ctx``."""
        meta = _dict(_dict(unit.primary.value).get("meta"))
        task: dict[str, Any] = {"benchmark": "agentdojo"}
        unk = {"/instrumentation": "not_recorded"}
        header: dict[str, Any] = {
            "k": "execution",
            "id": "exec",
            "aer": "0.1",
            "ex": ctx.ex,
            "mode": unit.mode,
            "unit": "agent_execution",
            "source_key": {"sha256": unit.primary.artefact.sha256, "loc": unit.primary.locator.key()},
            "artifacts": [unit.primary.artefact.to_json()],
            "adapter": {"id": ADAPTER_ID, "version": ADAPTER_VERSION},
            "dialect": {"id": DIALECT_ID, "variant": VARIANT},
            "profile": ctx.profile.header(),
            "rules": ctx.catalogue_versions(CATALOGUES),
            "ns": dict(NAMESPACES),
            "canon": "jcs-rfc8785",
            "hash": "sha256",
            "task": task,
            "ev": "D",
            "rule": [ctx.rule("adprov.v1_benchmark_is_agentdojo@1")],
            "unk": unk,
        }
        task_id = meta.get("user_task_id")
        if isinstance(task_id, str):
            task["task_id"] = task_id
            header.update(ev="O", by="config", evf={"/task/benchmark": "D"},
                          rule=[ctx.rule("adprov.v1_benchmark_is_agentdojo@1", "/task/benchmark")],
                          src=[_loc("/meta/user_task_id")])
        else:  # D-219: a map job that failed before reading the value did not capture it
            unk["/task/task_id"] = "not_captured" if unit.primary.value is None else "not_recorded"
        ctx.issue(issue_code, ids=["exec"], rule=ctx.rule("adprov.v1_writer_layout@1"), severity="error", detail=detail)
        return header


class _Build:
    """One mapping run. Records are built in full first, because the header depends on facts found later."""

    def __init__(self, unit: ExecutionUnit, ctx: MappingContext) -> None:
        item = unit.primary
        if not isinstance(item.value, dict):
            raise MalformedArtefact("the located item is not a transcript/v1 object")
        self.unit = unit
        self.ctx = ctx
        self.item = item
        self.doc: dict[str, Any] = item.value
        self.doc, self.surrogate_keys = scrub_keys(self.doc)  # item 7 (F-01, D-378): keys cannot be $utf16-wrapped
        self.meta: dict[str, Any] = self.doc["meta"]
        self.flags = item.flags
        self.converted = FLAG_CONVERTED in self.flags
        self.family = ctx.profile.family_table()
        # D.5.4, D-24: a D rule or its _unverified twin, by the profile's verified_code and this transcript's tree
        self.cite = Citations(parse_verified_code(self.family.get("verified_code", ()), f"profile {ctx.profile.id!r}"),
                              {"transcript": "converted" if self.converted else "released"}, namespaces=CITED_NAMESPACES)
        self.records: list[dict[str, Any]] = []
        self.header = _Rec()
        self.header_ext_agentdojo: dict[str, Any] = {}
        self.n_mc = 0
        self.n_te = 0
        self.n_dc = 0
        self.n_st = 0
        self.agent_calls: list[_Rec] = []  # every agent model_call in id order (finish-reason alignment)
        self.attack_id: str | None = None
        self.has_def0 = False
        self.plan: dict[str, Any] = {}

    # ---------------------------------------------------------------------------------------------- helpers
    def R(self, rule_id: str, pointer: str | None = None) -> str:  # noqa: N802 - mirrors MappingContext.rule
        """A statement's rule citation: the D rule or its ``_unverified`` twin (D.5.4), with an optional pointer."""
        return self.ctx.rule(self.cite.cite(rule_id), pointer)

    def issue(self, code: str, ids: Sequence[str], rule: str, *, severity: str = "warning", detail: str | None = None) -> None:
        """A seal issue citing ``rule`` as given (pass ``self.cite.cite(rule)`` to cite a statement's reading)."""
        self.ctx.issue(code, ids=list(ids), rule=self.ctx.rule(rule), severity=severity, detail=detail)  # type: ignore[arg-type]

    def _str(self, value: object, where: str, *, nullable: bool = False) -> Any:
        if isinstance(value, str) or (nullable and value is None):
            return value
        raise MalformedArtefact(f"{where}: unexpected value type")

    # ---------------------------------------------------------------------------------------------- run
    def run(self) -> Iterator[dict[str, Any]]:
        self._check_top()
        body: list[dict[str, Any]] = []
        self._actors(body)
        attempts = self._attempt_plan()
        self._scopes(body, attempts)
        self._fixtures(body)
        self._lost_calls(body, attempts)
        for plan in attempts["passes"]:
            self._pass(body, plan)
        self._align_finish_reasons()
        self._judgements(body)
        header = self._header(attempts)
        records = [header, *(record.done() if isinstance(record, _Rec) else record for record in body)]
        surrogates(self, records, "adprov")
        for record in records:  # C.6.5 rule 1: no field stronger than an I rule (a twin) that justifies it
            weaken_to_rule_class(record)
        yield from records

    # ---------------------------------------------------------------------------------------------- layout checks
    def _check_top(self) -> None:
        unknown, ok = check_order(list(self.doc), layout("top"))
        if unknown:
            raise MalformedArtefact("transcript/v1 object has an unknown top-level member")
        if not ok:
            self.issue("adprov.v1_layout_unexpected_order", ["exec"], "adprov.v1_writer_layout@1", detail="top")
        unknown, ok = check_order(list(self.meta), layout("meta"))
        if unknown:
            self.issue("adprov.v1_layout_unknown_member", ["exec"], "adprov.v1_writer_layout@1", detail="meta")
        if not ok:
            self.issue("adprov.v1_layout_unexpected_order", ["exec"], "adprov.v1_writer_layout@1", detail="meta")

    # ---------------------------------------------------------------------------------------------- header
    def _header(self, attempts: Mapping[str, Any]) -> dict[str, Any]:
        meta = self.meta
        h = self.header
        art = self.item.artefact
        attack_raw = self._str(meta.get("attack_type"), "meta.attack_type")
        task: dict[str, Any] = {
            "benchmark": "agentdojo",
            "suite": self._str(meta.get("suite"), "meta.suite"),
            "task_id": self._str(meta.get("user_task_id"), "meta.user_task_id"),
            "attack_id": self.attack_id,
            "attack_target_id": self._str(meta.get("injection_task_id"), "meta.injection_task_id", nullable=True),
        }
        evf: dict[str, str] = {"/task/benchmark": "D"}
        rules = [self.R("adprov.v1_benchmark_is_agentdojo@1", "/task/benchmark")]
        unk: dict[str, str] = {}
        if not self.converted:
            task["defense_id"] = None
            evf["/task/defense_id"] = "D"
            rules.append(self.R("adprov.release_undefended@1", "/task/defense_id"))
            items = self.family.get("instrumentation", ())
            h.data["instrumentation"] = [dict(i) for i in items]
            evf["/instrumentation"] = "I"
            rules.append(self.R("adprov.v1_capture_code_semantics@1", "/instrumentation"))
        else:
            unk["/task/defense_id"] = "ambiguous"
            rules.append(self.R("agentdojo.defence_suffix@1", "/task/defense_id"))
            unk["/instrumentation"] = "not_recorded"
        if attack_raw == BENIGN_LABEL:
            evf["/task/attack_id"] = "D"
            rules.append(self.R("adprov.v1_benign_label@1", "/task/attack_id"))
        h.data["task"] = task
        src = [_loc("/meta/suite"), _loc("/meta/user_task_id"), _loc("/meta/attack_type"), _loc("/meta/injection_task_id")]

        ext_adprov: dict[str, Any] = {"model": h.enc(self._str(meta.get("model"), "meta.model"), "/ext/adprov/model")}
        v1: dict[str, Any] = {"variant": "converted" if self.converted else "released", "meta_keys": list(meta)}
        model_config = meta.get("model_config")
        if isinstance(model_config, dict):
            v1["model_config_keys"] = list(model_config)
            usage = model_config.get("usage")
            if isinstance(usage, dict):
                v1["usage_keys"] = list(usage)
        elif "model_config" in meta:
            raise MalformedArtefact("meta.model_config is not an object")
        if attempts.get("finish_reasons_verbatim_set"):
            v1["finish_reasons"] = h.enc(attempts["finish_reasons_verbatim"], "/ext/adprov/v1/finish_reasons")
        if self.doc.get("discarded_attempts") == []:  # present but empty: no attempt scope carries it (CA-17)
            v1["discarded_attempts_empty"] = True
        ext_adprov["v1"] = v1
        # C.15.3 Import direction (regen item 74, CA-16): kept whenever present, not only in the converted variant
        for key in ("source", "timing_stubbed", "run_error"):
            if key in meta:
                ext_adprov[key] = h.enc(meta[key], _p("ext", "adprov", key))
                src.append(_loc(_p("meta", key)))
        if self.converted or "pipeline_name" in meta:
            self.header_ext_agentdojo["pipeline_name"] = self._str(meta.get("pipeline_name"), "meta.pipeline_name",
                                                                   nullable=not self.converted)
            src.append(_loc("/meta/pipeline_name"))
        if self.converted:
            ext_adprov["model_id"] = h.enc(self._str(meta.get("model_id"), "meta.model_id"), "/ext/adprov/model_id")
            link = self._upstream_link()
            if link is not None:
                ext_adprov["derived_from_upstream"] = link
                evf["/ext/adprov/derived_from_upstream"] = "D"
                rules.append(self.R("adprov.converted_stem_to_upstream_path@1", "/ext/adprov/derived_from_upstream"))
        for key, slot in (("reasoning_alignment", "reasoning_alignment"), ("n_attempts", "n_attempts"),
                          ("capture", "capture_block")):
            if key in meta:
                ext_adprov[slot] = h.enc(meta[key], _p("ext", "adprov", slot))
                src.append(_loc(_p("meta", key)))
        known = {m for m, _ in layout("meta")}
        extra = {k: h.enc(v, _p("ext", "adprov", "meta_extra", k)) for k, v in meta.items() if k not in known}
        if extra:
            ext_adprov["meta_extra"] = extra
        if isinstance(model_config, dict):
            mc_extra = {
                k: h.enc(v, _p("ext", "adprov", "model_config_extra", k))
                for k, v in model_config.items()
                if k not in ("temperature", "usage", "finish_reasons")
            }
            if mc_extra:
                ext_adprov["model_config_extra"] = mc_extra
                src.append(_loc("/meta/model_config"))
        task_id = task["task_id"]
        if self.attack_id is None and isinstance(task_id, str) and task_id.startswith("injection_task_"):
            self.header_ext_agentdojo["task_kind"] = "injection_task_as_user_task"
            evf["/ext/agentdojo/task_kind"] = "D"
            rules.append(self.R("agentdojo.injection_task_as_user_task@1", "/ext/agentdojo/task_kind"))
        ext: dict[str, Any] = {"adprov": ext_adprov}
        if self.header_ext_agentdojo:
            ext["agentdojo"] = dict(self.header_ext_agentdojo)
        h.data.update(
            {
                "k": "execution",
                "id": "exec",
                "aer": "0.1",
                "ex": self.ctx.ex,
                "mode": "import",
                "unit": attempts["unit"],
                "source_key": {"sha256": art.sha256, "loc": {"p": ""}},
                "artifacts": [art.to_json()],
                "adapter": {"id": ADAPTER_ID, "version": ADAPTER_VERSION},
                "dialect": {"id": DIALECT_ID, "variant": VARIANT},
                "profile": self.ctx.profile.header(),
                "rules": self.ctx.catalogue_versions(CATALOGUES),
                "ns": dict(NAMESPACES),
                "canon": "jcs-rfc8785",
                "hash": "sha256",
                "ev": "O",
                "by": "config",
                "evf": evf,
                "rule": rules,
                "src": src,
                "ext": ext,
            }
        )
        if unk:
            h.data["unk"] = unk
        return h.done()

    def _upstream_link(self) -> dict[str, Any] | None:
        """``adprov.converted_stem_to_upstream_path@1``: the upstream log behind a converted transcript."""
        meta = self.meta
        pipeline, suite, user = meta.get("pipeline_name"), meta.get("suite"), meta.get("user_task_id")
        attack, inj = meta.get("attack_type"), meta.get("injection_task_id")
        repo, commit = self.family.get("upstream_repo"), self.family.get("upstream_commit")
        parts_ok = all(isinstance(x, str) and x and "/" not in x for x in (pipeline, suite, user, attack))
        benign = attack == BENIGN_LABEL
        if not parts_ok or not (benign or (isinstance(inj, str) and inj and "/" not in inj)) or not repo or not commit:
            self.issue("adprov.upstream_link_unresolved", ["exec"], "adprov.converted_stem_to_upstream_path@1")
            return None
        attack_dir = "none" if benign else attack
        inj_name = inj if isinstance(inj, str) and inj else "none"
        if benign and inj is not None:
            self.issue("adprov.upstream_link_unresolved", ["exec"], "adprov.converted_stem_to_upstream_path@1")
            return None
        return {"commit": commit, "path": f"runs/{pipeline}/{suite}/{user}/{attack_dir}/{inj_name}.json", "repo": repo}

    # ---------------------------------------------------------------------------------------------- actors
    def _actors(self, body: list[Any]) -> None:
        meta = self.meta
        attack = self._str(meta.get("attack_type"), "meta.attack_type")
        self.attack_id = None if attack == BENIGN_LABEL else attack
        body.append({"k": "actor", "id": "user", "kind": "simulated_user", "ev": "D", "rule": [self.R("agentdojo.user_is_simulated@1")]})
        body.append(self._agent())
        body.append(
            {
                "k": "actor",
                "id": "env",
                "kind": "tool_runtime",
                "name": "agentdojo.FunctionsRuntime",
                "on_behalf_of": "agent",
                "ev": "D",
                # acting for the agent without confirmation rests on an asserted assumption (EF E.10 item 21)
                "evf": {"/on_behalf_of": "I"},
                "rule": [self.R("agentdojo.functions_runtime@1"), self.R("agentdojo.auto_execution_unverified@1", "/on_behalf_of")],
            }
        )
        if self.attack_id is not None:
            body.append({"k": "actor", "id": "att", "kind": "attacker", "name": self.attack_id, "ev": "O", "by": "config",
                         "src": [_loc("/meta/attack_type")]})
        body.append(self._bench())
        body.append(
            {
                "k": "actor",
                "id": "harness",
                "kind": "harness",
                "name": "agentdojo-prov",
                "ev": "O",
                "by": "source",
                "src": [_loc("/adprov_schema")],
                "unk": {"/code": "not_recorded", "/version": "not_recorded"},
            }
        )
        if self.converted and self._has_pi_sentinel():
            self.has_def0 = True
            body.append({"k": "actor", "id": "def0", "kind": "defense", "ev": "I", "rule": [self.R("agentdojo.pi_detector_sentinel@1")],
                         "unk": {"/model": "not_recorded", "/version": "not_recorded"}})

    def _has_pi_sentinel(self) -> bool:
        sentinel = self.family.get("pi_detector_sentinel")
        if not isinstance(sentinel, str):
            return False
        return any(isinstance(t, dict) and t.get("role") == "tool" and t.get("content") == sentinel and t.get("error") is None
                   for t in self._all_turns())

    def _all_turns(self) -> Iterator[Any]:
        yield from self.doc["turns"]
        for attempt in self.doc.get("discarded_attempts") or ():
            if isinstance(attempt, dict):
                yield from attempt.get("turns") or ()

    def _agent(self) -> dict[str, Any]:
        meta = self.meta
        rec = _Rec(k="actor", id="agent", kind="llm_agent", on_behalf_of="user")
        unk = {"/model/provider": "not_recorded", "/model/served": "not_recorded"}
        model_config = meta.get("model_config") if isinstance(meta.get("model_config"), dict) else None
        if self.converted:
            rec.data.update(ev="D", rule=[self.R("agentdojo.user_is_simulated@1"),
                                          self.R("agentdojo.pipeline_dir_is_model_identity@1", "/model/requested")])
            rec.data["src"] = [_loc("/meta/model_id")]
            unk["/model/requested"] = "ambiguous"
            if model_config is not None and "temperature" in model_config:  # as the released variant (CA-16)
                rec.data["params"] = {"temperature": rec.enc(model_config["temperature"], "/params/temperature")}
                rec.data["src"].append(_loc("/meta/model_config/temperature"))
            else:
                unk["/params"] = "not_recorded"
            rec.data["unk"] = unk
            return rec.done()
        src = []
        model_id = meta.get("model_id")
        if isinstance(model_id, str):
            rec.data["model"] = {"requested": model_id}
            src.append(_loc("/meta/model_id"))
        else:
            unk["/model/requested"] = "not_recorded"
        if model_config is not None and "temperature" in model_config:
            rec.data["params"] = {"temperature": rec.enc(model_config["temperature"], "/params/temperature")}
            src.append(_loc("/meta/model_config/temperature"))
        else:
            unk["/params"] = "not_recorded"
        if src:
            rec.data.update(ev="O", by="config", evf={"/on_behalf_of": "D"},
                            rule=[self.R("agentdojo.user_is_simulated@1", "/on_behalf_of")], src=src)
        else:
            rec.data.update(ev="D", rule=[self.R("agentdojo.user_is_simulated@1")])
        rec.data["unk"] = unk
        return rec.done()

    def _bench(self) -> dict[str, Any]:
        meta = self.meta
        dist_version, label = meta.get("agentdojo_version"), meta.get("benchmark_version")
        rec = _Rec(k="actor", id="bench", kind="benchmark", name="agentdojo")
        if not isinstance(dist_version, str) and not isinstance(label, str):
            rec.data.update(ev="D", rule=[self.R("adprov.v1_benchmark_is_agentdojo@1")],
                            unk={"/code": "not_recorded", "/version": "not_recorded"})
            return rec.done()
        unk: dict[str, str] = {}
        src = []
        if isinstance(label, str):
            rec.data["version"] = label
            src.append(_loc("/meta/benchmark_version"))
        else:
            unk["/version"] = "not_recorded"
        if isinstance(dist_version, str):
            rec.data["code"] = {"dist": "agentdojo", "dist_version": dist_version}
            src.append(_loc("/meta/agentdojo_version"))
            unk["/code/commit"] = "not_recorded"
        else:
            unk["/code"] = "not_recorded"
        rec.data.update(ev="O", by="source", src=src, unk=unk)
        return rec.done()

    # ---------------------------------------------------------------------------------------------- attempts
    def _attempt_plan(self) -> dict[str, Any]:
        """Scopes, passes and the call-count reading (C.7.4; adprov.single_attempt_from_call_count / lost_calls)."""
        turns = self.doc["turns"]
        discarded = self.doc.get("discarded_attempts")
        if discarded is not None and not isinstance(discarded, list):
            raise MalformedArtefact("discarded_attempts is not an array")
        discarded = discarded or []
        passes: list[dict[str, Any]] = []
        for i, attempt in enumerate(discarded):
            if not isinstance(attempt, dict) or not isinstance(attempt.get("turns"), list):
                raise MalformedArtefact("a discarded attempt is not an object with turns")
            unknown, ok = check_order(list(attempt), layout("discarded_attempt"))
            if unknown:
                raise MalformedArtefact("a discarded attempt has an unknown member")
            if not ok:
                self.issue("adprov.v1_layout_unexpected_order", ["exec"], "adprov.v1_writer_layout@1", detail="discarded_attempt")
            passes.append({"scope": f"att{i}", "turns": attempt["turns"], "src": _p("discarded_attempts", i, "turns"),
                           "prefix": f"d{i}m", "entry": attempt, "entry_src": _p("discarded_attempts", i)})
        held = sum(1 for t in self._all_turns() if isinstance(t, dict) and t.get("role") == "assistant")
        model_config = _dict(self.meta.get("model_config"))
        usage = _dict(model_config.get("usage"))
        reported = usage.get("n_llm_calls")
        if isinstance(reported, bool) or not isinstance(reported, int):
            reported = None
        # an explicit null or a non-list is not alignable: kept verbatim at ext.adprov.v1.finish_reasons (CA-16)
        verbatim = "finish_reasons" in model_config and not isinstance(model_config["finish_reasons"], list)
        finish = model_config.get("finish_reasons") if "finish_reasons" in model_config and not verbatim else None
        lost = 0
        if reported is not None and reported > held and not discarded and (finish is None or len(finish) == reported):
            lost = reported - held
        plan: dict[str, Any] = {"unit": "agent_execution", "lost": lost, "reported": reported, "finish": finish,
                                "finish_reasons_verbatim": model_config.get("finish_reasons") if verbatim else None,
                                "finish_reasons_verbatim_set": verbatim, "scopes": []}
        if not turns and not discarded:
            plan["unit"] = "outcome_only"
            plan["passes"] = []
            return plan
        n = len(discarded)
        scopes: list[dict[str, Any]] = []
        for i in range(n):
            scopes.append({"k": "scope", "id": f"att{i}", "kind": "attempt", "parent": "run", "actor": "agent", "index": i,
                           "scored": False, "ev": "D", "rule": [self.R("adprov.discarded_attempts_in_order@1")],
                           "src": [_loc(_p("discarded_attempts", i))]})
        if n:
            scored_id = f"att{n}"
            scopes.append({"k": "scope", "id": scored_id, "kind": "attempt", "parent": "run", "actor": "agent", "index": n,
                           "scored": True, "ev": "D", "rule": [self.R("adprov.discarded_attempts_in_order@1")],
                           "src": [_loc("/discarded_attempts")]})
        elif lost:
            scopes.append({"k": "scope", "id": "att0", "kind": "attempt", "parent": "run", "actor": "agent", "scored": False,
                           "ev": "D", "rule": [self.R("adprov.lost_calls_from_count@1")],
                           "src": [_loc("/meta/model_config/usage/n_llm_calls")], "unk": {"/index": "lost"}})
            scored_id = "att1"
            scopes.append({"k": "scope", "id": "att1", "kind": "attempt", "parent": "run", "actor": "agent", "scored": True,
                           "ev": "D", "rule": [self.R("adprov.lost_calls_from_count@1")],
                           "src": [_loc("/meta/model_config/usage/n_llm_calls")], "unk": {"/index": "lost"}})
            self.issue("earlier_attempts_unobservable", ["att0"], self.cite.cite("adprov.lost_calls_from_count@1"))
        elif reported is not None and reported == held:
            scored_id = "att0"
            scopes.append({"k": "scope", "id": "att0", "kind": "attempt", "parent": "run", "actor": "agent", "index": 0,
                           "scored": True, "ev": "D", "rule": [self.R("adprov.single_attempt_from_call_count@1")],
                           "src": [_loc("/meta/model_config/usage/n_llm_calls")]})
        else:
            scored_id = "att0"
            scopes.append({"k": "scope", "id": "att0", "kind": "attempt", "parent": "run", "actor": "agent", "scored": True,
                           "ev": "D", "rule": [self.R("adprov.turns_hold_last_pass@1")], "src": [_loc("/turns")],
                           "unk": {"/index": "lost"}})
            self.issue("earlier_attempts_unobservable", ["att0"], "adprov.turns_hold_last_pass@1")
        passes.append({"scope": scored_id, "turns": turns, "src": "/turns", "prefix": "m", "entry": None, "entry_src": None})
        plan["scopes"] = scopes
        plan["passes"] = passes
        plan["held"] = held
        return plan

    def _scopes(self, body: list[Any], plan: dict[str, Any]) -> None:
        body.append(self._run_scope())
        for scope in plan["scopes"]:
            rec = _Rec(**scope)
            for p in plan["passes"]:
                entry = p["entry"]
                if p["scope"] == scope["id"] and entry is not None and "reasoning_alignment" in entry:
                    rec.data["ext"] = {"adprov": {"reasoning_alignment": rec.enc(entry["reasoning_alignment"],
                                                                                 "/ext/adprov/reasoning_alignment")}}
            body.append(rec)
        self.plan = plan

    def _run_scope(self) -> _Rec:
        meta = self.meta
        rec = _Rec(k="scope", id="run", kind="run", actor="agent", ev="O", by="source")
        t: dict[str, Any] = {}
        raw: dict[str, Any] = {}
        unk: dict[str, str] = {"/status": "not_recorded"}
        src = []
        for key, slot in (("started_at", "start"), ("ended_at", "end")):
            value = meta.get(key)
            if isinstance(value, str):
                raw[slot] = value
                z = _to_z(value)
                if z is None:
                    raise MalformedArtefact(f"meta.{key} is not an RFC 3339 UTC instant")
                t[slot] = z
                src.append(_loc(_p("meta", key)))
            elif value is None:
                unk[f"/t/{slot}"] = "not_recorded"
            else:
                raise MalformedArtefact(f"meta.{key}: unexpected value type")
        wall = meta.get("wall_clock_s")
        if isinstance(wall, int | float) and not isinstance(wall, bool):
            t["dur_s"] = rec.enc(wall, "/t/dur_s")
            t["dur_clock"] = "wall" if self.converted else "monotonic"
            src.append(_loc("/meta/wall_clock_s"))
        elif wall is None:
            unk["/t/dur_s"] = "not_recorded"
        else:
            raise MalformedArtefact("meta.wall_clock_s: unexpected value type")
        if raw:
            t["raw"] = raw
        if t:
            rec.data["t"] = t
        model_config = _dict(meta.get("model_config"))
        usage = model_config.get("usage")
        if usage is not None and not isinstance(usage, dict):
            raise MalformedArtefact("meta.model_config.usage is not an object")
        if isinstance(usage, dict):
            mapping = usage_map()
            typed: dict[str, Any] = {}
            extra: dict[str, Any] = {}
            for key, value in usage.items():
                if key in mapping and isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                    typed[mapping[key]] = rec.enc(value, "/usage/" + mapping[key])
                else:
                    extra[key] = value
            if typed:
                rec.data["usage"] = typed
                evf = {"/usage": "O:provider"}
                if "calls" in typed:
                    evf["/usage/calls"] = "O"
                rec.data["evf"] = evf
            if extra:
                rec.data["ext"] = {"adprov": {"usage_extra": {
                    k: rec.enc(v, _p("ext", "adprov", "usage_extra", k)) for k, v in extra.items()}}}
            src.append(_loc("/meta/model_config/usage"))
        else:
            unk["/usage"] = "not_recorded"
        rec.data["src"] = src
        rec.data["unk"] = unk
        if not src:
            rec.data["ev"] = "D"
            del rec.data["by"]
            rec.data["rule"] = [self.R("adprov.turns_hold_last_pass@1")]
        return rec

    # ---------------------------------------------------------------------------------------------- fixtures
    def _fixtures(self, body: list[Any]) -> None:
        injections = self.meta.get("injections")
        if not isinstance(injections, dict):
            raise MalformedArtefact("meta.injections is not an object")
        for i, (vector, payload) in enumerate(injections.items()):
            rec = _Rec(k="fixture", id=f"fx{i}", kind="injection_payload", vector=vector, ev="O", by="benchmark",
                       src=[_loc(_p("meta", "injections", vector))])
            rec.data["content"] = rec.enc(payload, "/content")
            if self.attack_id is not None:
                rec.data.update(actor="att", evf={"/actor": "I"},
                                rule=[self.R("agentdojo.payload_attributed_to_attacker@1", "/actor")])
            body.append(rec)

    # ---------------------------------------------------------------------------------------------- model calls
    def _new_call(self, scope: str, *, lost: bool) -> _Rec:
        rec = _Rec(k="model_call", id=f"mc{self.n_mc}", actor="agent", role="agent", scope=scope, ev="D")
        self.n_mc += 1
        self.agent_calls.append(rec)
        rec.data["_lost"] = lost
        return rec

    def _lost_calls(self, body: list[Any], plan: Mapping[str, Any]) -> None:
        for _ in range(plan["lost"]):
            rec = self._new_call("att0", lost=True)
            rec.data["rule"] = [self.R("adprov.lost_calls_from_count@1")]
            rec.data["src"] = [_loc("/meta/model_config/usage/n_llm_calls")]
            rec.data["unk"] = {"/input": "lost", "/status": "lost", "/t": "lost"}
            body.append(rec)

    def _align_finish_reasons(self) -> None:
        """``adprov.finish_reason_positional@1``: one entry per agent call (lost calls first), else verbatim."""
        plan = self.plan
        finish: list[Any] | None = plan["finish"]
        calls = self.agent_calls
        aligned = finish is not None and len(finish) == len(calls) and all(isinstance(x, str) or x is None for x in finish)
        for i, rec in enumerate(calls):
            lost = rec.data.pop("_lost")
            unk = rec.data.setdefault("unk", {})
            rules = rec.data["rule"]
            if finish is None:
                if not lost:
                    unk["/finish_reason"] = "not_recorded"
                continue
            rules.append(self.R("adprov.finish_reason_positional@1", "/finish_reason"))
            if aligned:
                rec.data.setdefault("src", []).append(_loc(_p("meta", "model_config", "finish_reasons", i)))
                if isinstance(finish[i], str):
                    rec.data["finish_reason"] = finish[i]
                else:
                    unk["/finish_reason"] = "not_recorded"
            else:
                unk["/finish_reason"] = "ambiguous"
                rec.data.setdefault("src", []).append(_loc("/meta/model_config/finish_reasons"))
            if not unk:
                del rec.data["unk"]
        if finish is not None and not aligned:
            plan["finish_reasons_verbatim"] = list(finish)
            plan["finish_reasons_verbatim_set"] = True
        for rec in calls:
            if not rec.data.get("src"):
                rec.data.pop("src", None)

    # ---------------------------------------------------------------------------------------------- passes
    def _pass(self, body: list[Any], plan: Mapping[str, Any]) -> None:
        scope, turns, base, prefix = plan["scope"], plan["turns"], plan["src"], plan["prefix"]
        timing_overwritten = self._overwritten_timings(turns)
        inputs: list[str] = []
        prev: str | None = None
        users = 0
        batch: dict[str, Any] | None = None  # {"msg": id, "calls": [(part id, call)], "results": int}
        assistants: list[dict[str, Any]] = []
        for i, turn in enumerate(turns):
            if not isinstance(turn, dict):
                raise MalformedArtefact("a turn is not an object")
            role = turn.get("role")
            mid = f"{prefix}{i}"
            tsrc = f"{base}/{i}"
            if role == "tool":
                if batch is None:
                    raise MalformedArtefact("a tool turn precedes every assistant turn")
                te_id, out_id = self._tool_turn(body, turn, i, mid, tsrc, scope, batch, timing_overwritten)
                inputs.append(out_id)
                prev = out_id
                continue
            if role == "assistant":
                mc = self._new_call(scope, lost=False)
                mc.data["input"] = list(inputs)
                rules: list[str] = [self.R("adprov.assistant_turn_one_call@1")]
                if prev is not None:
                    mc.data["after"] = [{"b": "pos", "id": prev}]
                    rules.append(self.R("agentdojo.messages_append_ordered@1", "/after"))
                rules.append(self.R("adprov.context_is_prefix@1", "/input"))
                mc.data.update(evf={"/input": "I"}, rule=rules, status="kept",
                               unk={key: "not_recorded" for key in _MODEL_CALL_UNKNOWN})
                body.append(mc)
                calls = self._assistant(body, turn, mid, tsrc, scope, str(mc.data["id"]))
                batch = {"msg": mid, "calls": calls, "results": 0}
                assistants.append(batch)
                inputs.append(mid)
                prev = mid
                continue
            batch = None
            rec = _Rec(k="message", id=mid, scope=scope, role=role, ev="O", by="source", src=[_loc(tsrc)])
            self._check_turn_layout(rec, turn, "system_turn" if role == "system" else "user_turn" if role == "user" else "other_turn")
            content = self._str(turn.get("content"), f"turn {i} content")
            rec.data["parts"] = [{"t": "text", "text": rec.enc(content, "/parts/0/text")}]
            evf: dict[str, str] = {}
            rules = []
            if role == "system":
                rec.data["actor"] = "bench"
                evf["/actor"] = "D"
                rules.append(self.R("agentdojo.system_prompt_from_harness@1", "/actor"))
            elif role == "user":
                rec.data["actor"] = "user"
                if users == 0:
                    evf["/actor"] = "D"
                    rules.append(self.R("agentdojo.user_is_simulated@1", "/actor"))
                else:
                    evf["/actor"] = "I"
                    rules.append(self.R("adprov.additional_user_turn_unattributed@1", "/actor"))
                    self.issue("unattributed_additional_user_message", [mid], "adprov.additional_user_turn_unattributed@1")
                users += 1
            else:
                rec.data.setdefault("unk", {})["/actor"] = "not_recorded"
            if prev is not None:
                rec.data["after"] = [{"b": "pos", "id": prev}]
                evf["/after"] = "D"
                rules.append(self.R("agentdojo.messages_append_ordered@1", "/after"))
            if evf:
                rec.data["evf"] = evf
            if rules:
                rec.data["rule"] = rules
            body.append(rec)
            inputs.append(mid)
            prev = mid
        self._trailing_calls(assistants)
        if plan["entry"] is None:  # the scored pass closes the run: the capture block's environment records follow it
            self._state_changes(body)

    def _trailing_calls(self, assistants: Sequence[Mapping[str, Any]]) -> None:
        for n, batch in enumerate(assistants):
            # only calls after the last tool turn of the batch are undispatched; a call skipped by a link problem is
            # covered by that problem's issue (and the accounting verdict), never claimed unexecuted
            pending = [pid for k, (pid, _call, linked) in enumerate(batch["calls"]) if not linked and k >= batch["results"]]
            if not pending:
                continue
            if n == len(assistants) - 1:
                self.issue("unexecuted_tool_call", pending, "agentdojo.unexecuted_trailing_calls@1")
            else:
                self.issue("missing_tool_result", pending, "agentdojo.unexecuted_trailing_calls@1", severity="error")

    def _check_turn_layout(self, rec: _Rec, turn: Mapping[str, Any], template: str) -> None:
        """J.3.2: record a non-canonical member order (``ext.adprov.keys``) and unknown members (``ext.adprov.extra``)."""
        observed = list(turn)
        unknown, ok = check_order(observed, layout(template))
        alternative = template == "assistant_turn" and not unknown and check_order(observed, layout("assistant_turn_log_reasoning"))[1]
        canonical = [m for m, _ in layout(template) if m in turn]
        adprov: dict[str, Any] = {}
        if unknown:
            adprov["extra"] = {k: rec.enc(turn[k], _p("ext", "adprov", "extra", k)) for k in unknown}
            self.issue("adprov.v1_layout_unknown_member", [str(rec.data["id"])], "adprov.v1_writer_layout@1", detail=template)
        # J.3.2 writes tool_calls only with >= 1 call: a present-but-empty array is kept through the key list, which
        # the view honours (regen item 75, CA-17)
        empty_calls = template == "assistant_turn" and turn.get("tool_calls") == []
        if observed != canonical or empty_calls:
            adprov["keys"] = observed
            if not ok and not alternative:
                self.issue("adprov.v1_layout_unexpected_order", [str(rec.data["id"])], "adprov.v1_writer_layout@1",
                           detail=template)
        if adprov:
            ext = rec.data.setdefault("ext", {})
            ext.setdefault("adprov", {}).update(adprov)

    def _assistant(self, body: list[Any], turn: Mapping[str, Any], mid: str, tsrc: str, scope: str, mc_id: str) -> list[Any]:
        rec = _Rec(k="message", id=mid, scope=scope, role="assistant", actor="agent", generated_by=mc_id,
                   after=[{"b": "causal", "id": mc_id}], ev="O", by="source", evf={"/after": "D", "/generated_by": "D"},
                   src=[_loc(tsrc)])
        self._check_turn_layout(rec, turn, "assistant_turn")
        rules = [self.R("adprov.assistant_turn_one_call@1", "/generated_by"), self.R("aer.output_after_generator@1", "/after")]
        text = self._str(turn.get("text"), "assistant text", nullable=True)
        parts: list[dict[str, Any]] = [{"t": "text", "text": rec.enc(text, "/parts/0/text")}]
        unk: dict[str, str] = {}
        if text == "":
            unk["/parts/0/text"] = "ambiguous"
            if not self.converted and FLAG_NULL_AS_EMPTY in self.flags:
                rules.append(self.R("adprov.release_null_as_empty@1", "/parts/0/text"))
            else:
                rules.append(self.R("adprov.empty_assistant_text_ambiguous@1", "/parts/0/text"))
        evf = rec.data["evf"]
        for key, kind, rule in (("reasoning", "reasoning", "adprov.reasoning_log_alignment@1"),
                                ("refusal", "refusal", "adprov.refusal_log_alignment@1")):
            if key in turn:
                k = len(parts)
                value = self._str(turn[key], f"assistant {key}")
                parts.append({"t": kind, "text": rec.enc(value, f"/parts/{k}/text")})
                evf[f"/parts/{k}"] = "I"
                rules.append(self.R(rule, f"/parts/{k}"))
        calls: list[Any] = []
        tool_calls = turn.get("tool_calls")
        if "tool_calls" in turn and not isinstance(tool_calls, list):
            raise MalformedArtefact("assistant tool_calls is not an array")
        placeholders: dict[str, Any] = {}
        for call in tool_calls or ():
            if not isinstance(call, dict):
                raise MalformedArtefact("a tool call is not an object")
            unknown, ok = check_order(list(call), layout("tool_call"))
            if unknown or not ok:
                raise MalformedArtefact("a tool call has unknown members or an unexpected order")
            k = len(parts)
            name = self._str(call.get("function"), "tool call function")
            cid = self._str(call.get("id"), "tool call id", nullable=True)
            parts.append({"t": "tool_call", "name": name, "args": rec.enc(call.get("args"), f"/parts/{k}/args"),
                          "provider_call_id": cid})
            if "placeholder_args" in call:
                placeholders[str(k)] = rec.enc(call["placeholder_args"], f"/ext/adprov/placeholder_args/{k}")
            calls.append([part_id(mid, k), call, False])
        if placeholders:
            rec.data.setdefault("ext", {}).setdefault("adprov", {})["placeholder_args"] = placeholders
        rec.data["parts"] = parts
        rec.data["rule"] = rules
        if unk:
            rec.data["unk"] = unk
        body.append(rec)
        return calls

    # ---------------------------------------------------------------------------------------------- tool turns
    def _overwritten_timings(self, turns: Sequence[Any]) -> set[int]:
        """``adprov.timing_keyed_by_call_id@1``: indices of tool turns whose timing a later same-id turn overwrote."""
        if FLAG_STUBBED in self.flags:
            return set()
        groups: dict[str, list[int]] = {}
        for i, turn in enumerate(turns):
            if isinstance(turn, dict) and turn.get("role") == "tool":
                cid = turn.get("tool_call_id")
                if isinstance(cid, str) and cid and "started_at" in turn:
                    groups.setdefault(cid, []).append(i)
        out: set[int] = set()
        for indices in groups.values():
            if len(indices) < 2:
                continue
            pairs = {(turns[i].get("started_at"), turns[i].get("ended_at")) for i in indices}
            if len(pairs) == 1:
                out.update(indices[:-1])
        return out

    def _link(self, turn: Mapping[str, Any], batch: dict[str, Any]) -> tuple[int | None, str, str | None]:
        """``(index of the linked call, evidence tag, issue code)`` (adprov.call_id_unique_match / positional_match)."""
        calls = batch["calls"]
        j = batch["results"]
        batch["results"] += 1
        tcid = turn.get("tool_call_id")
        ids = [c[1].get("id") for c in calls]
        unique_ids = all(isinstance(x, str) and x for x in ids) and len(set(ids)) == len(ids)
        if unique_ids:
            if isinstance(tcid, str) and tcid in ids:
                return ids.index(tcid), "D", None
            return None, "D", "adprov.tool_call_id_mismatch"
        if j >= len(calls):
            return None, "I", "orphan_tool_result"
        call = calls[j][1]
        if tcid != call.get("id"):
            return None, "I", "adprov.tool_call_id_mismatch"
        if turn.get("function") != call.get("function") or not _jcs_equal(turn.get("args"), call.get("args")):
            return None, "I", "call_result_link_conflict"
        return j, "I", None

    def _tool_turn(self, body: list[Any], turn: Mapping[str, Any], i: int, mid: str, tsrc: str, scope: str,
                   batch: dict[str, Any], overwritten: set[int]) -> tuple[str, str]:
        index, tag, problem = self._link(turn, batch)
        link_rule = "adprov.call_id_unique_match@1" if tag == "D" else "agentdojo.positional_match@1"
        call_part = None
        if index is not None:
            call_part = batch["calls"][index][0]
            if batch["calls"][index][2]:
                index, call_part, problem = None, None, "call_result_link_conflict"
            else:
                batch["calls"][index][2] = True
        te_id = f"te{self.n_te}"
        self.n_te += 1
        te = _Rec(k="tool_execution", id=te_id, actor="env", scope=scope, ev="O", by="source")
        name = self._str(turn.get("function"), "tool turn function")
        error = self._str(turn.get("error"), "tool turn error", nullable=True)
        content = self._str(turn.get("content"), "tool turn content")
        te.data["name"] = name
        te.data["args"] = te.enc(turn.get("args"), "/args")
        te.data["status"] = _tool_status(error)
        evf = {"/status": "D"}
        rules: list[str] = []
        unk = {"/args_effective": "not_recorded"}
        if call_part is not None:
            te.data["call"] = call_part
            te.data["after"] = [{"b": "causal", "id": batch["msg"]}]
            evf["/call"] = tag
            evf["/after"] = "D"
            rules.append(self.R(link_rule, "/call"))
        else:
            unk["/call"] = "ambiguous"
            rules.append(self.R(link_rule, "/call"))
        rules.append(self.R("agentdojo.tool_status_from_error@1", "/status"))
        if call_part is not None:
            rules.append(self.R("aer.execution_after_call@1", "/after"))
        src = [_loc(f"{tsrc}/function"), _loc(f"{tsrc}/args"), _loc(f"{tsrc}/error")]
        has_start, has_end = "started_at" in turn, "ended_at" in turn
        if has_start != has_end:
            raise MalformedArtefact("a tool turn has only one of started_at and ended_at")
        if has_start:
            start = self._str(turn["started_at"], "tool started_at")
            end = self._str(turn["ended_at"], "tool ended_at")
            src += [_loc(f"{tsrc}/started_at"), _loc(f"{tsrc}/ended_at")]
            t: dict[str, Any] = {"raw": {"end": end, "start": start}}
            if FLAG_STUBBED in self.flags:
                unk["/t/end"] = "not_recorded"
                unk["/t/start"] = "not_recorded"
                rules += [self.R("adprov.timing_stub_is_unknown@1", "/t/end"),
                          self.R("adprov.timing_stub_is_unknown@1", "/t/start")]
            elif i in overwritten:
                unk["/t/end"] = "overwritten"
                unk["/t/start"] = "overwritten"
                rules += [self.R("adprov.timing_keyed_by_call_id@1", "/t/end"),
                          self.R("adprov.timing_keyed_by_call_id@1", "/t/start")]
                self.issue("adprov.tool_timing_overwritten", [te_id], "adprov.timing_keyed_by_call_id@1")
            else:
                zs, ze = _to_z(start), _to_z(end)
                if zs is None or ze is None:
                    raise MalformedArtefact("a tool timing is not an RFC 3339 UTC instant")
                t["start"], t["end"] = zs, ze
            te.data["t"] = t
        else:
            unk["/t"] = "not_recorded"
        te.data.update(evf=evf, rule=rules, src=src, unk=unk)
        body.append(te)

        sentinel = self.family.get("pi_detector_sentinel")
        redacted = self.has_def0 and content == sentinel and error is None
        generator = te_id
        if redacted:
            dc_id = f"dc{self.n_dc}"
            self.n_dc += 1
            body.append({"k": "decision", "id": dc_id, "actor": "def0", "scope": scope, "subject": te_id, "verdict": "redact",
                         "after": [{"b": "causal", "id": te_id}], "ev": "I",
                         "rule": [self.R("agentdojo.pi_detector_sentinel@1"), self.R("aer.decision_after_subject@1", "/after")],
                         "src": [_loc(f"{tsrc}/content")],
                         "unk": {"/original": "overwritten", "/reason": "not_recorded", "/t": "not_recorded"}})
            generator = dc_id

        msg = _Rec(k="message", id=mid, scope=scope, role="tool", generated_by=generator,
                   after=[{"b": "causal", "id": generator}], ev="O", by="source", src=[_loc(tsrc)])
        self._check_turn_layout(msg, turn, "tool_turn")
        part: dict[str, Any] = {"t": "tool_result", "text": msg.enc(content, "/parts/0/text"), "error": error}
        mevf: dict[str, str] = {}
        mrules: list[str] = []
        munk: dict[str, str] = {}
        if redacted:
            msg.data["actor"] = "def0"
            mevf.update({"/actor": "I", "/after": "I", "/generated_by": "I"})
            mrules += [self.R("agentdojo.pi_detector_sentinel@1", "/actor"),
                       self.R("agentdojo.pi_detector_sentinel@1", "/generated_by")]
        else:
            msg.data["actor"] = "env"
            mevf.update({"/after": "D", "/generated_by": "D"})
            mrules.append(self.R("adprov.tool_turn_is_one_execution@1", "/generated_by"))
        if call_part is not None:
            part["responds_to"] = call_part
            mevf["/parts/0/responds_to"] = tag
        else:
            munk["/parts/0/responds_to"] = "ambiguous"
            msg.data.setdefault("ext", {}).setdefault("adprov", {})["tool_call_id"] = msg.enc(
                turn.get("tool_call_id"), "/ext/adprov/tool_call_id")
        mrules.append(self.R(link_rule, "/parts/0/responds_to"))
        mrules.append(self.R("aer.output_after_generator@1", "/after"))
        digest = turn.get("content_sha256")
        if digest != "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest():
            msg.data.setdefault("ext", {}).setdefault("adprov", {})["content_sha256"] = msg.enc(
                digest, "/ext/adprov/content_sha256")
            self.issue("adprov.content_hash_mismatch", [mid], "adprov.v1_writer_layout@1")
        msg.data["parts"] = [part]
        msg.data.update(evf=mevf, rule=mrules)
        if munk:
            msg.data["unk"] = munk
        body.append(msg)
        if problem is not None:
            rule = "adprov.call_id_unique_match@1" if problem == "adprov.tool_call_id_mismatch" else "agentdojo.positional_match@1"
            self.issue(problem, [te_id, mid], rule)
        return te_id, mid

    # ---------------------------------------------------------------------------------------------- state changes
    def _state_changes(self, body: list[Any]) -> None:
        """``adprov.capture_environment_record@1``: one state_change per capture pass with an environment record."""
        capture = self.meta.get("capture")
        if not isinstance(capture, dict) or not isinstance(capture.get("passes"), list):
            return
        passes = capture["passes"]
        scopes = [s for s in self.plan["scopes"] if "index" in s]
        if len(passes) != len(scopes):
            return
        for k, (entry, scope) in enumerate(zip(passes, scopes, strict=True)):
            env = entry.get("environment") if isinstance(entry, dict) else None
            if not isinstance(env, dict):
                continue
            before, after, changed = env.get("before_sha256"), env.get("after_sha256"), env.get("changed")
            if not all(isinstance(x, str) and re.fullmatch(r"[0-9a-f]{64}", x) for x in (before, after)):
                continue
            rec = _Rec(k="state_change", id=f"st{self.n_st}", scope=scope["id"], cause=scope["id"], target="environment",
                       canon="adprov.envstate@1", before_sha256=before, after_sha256=after, ev="O", by="source",
                       src=[_loc(_p("meta", "capture", "passes", k, "environment"))])
            self.n_st += 1
            evf = {"/cause": "D"}
            rules = [self.R("adprov.capture_environment_record@1", "/cause")]
            if isinstance(changed, bool):
                rec.data["changed"] = changed
            diff = env.get("diff")
            if isinstance(diff, dict):
                rec.data["diff"] = {"format": "adprov.envstate_diff", "truncated": bool(diff.get("truncated")),
                                    "value": rec.enc(diff, "/diff/value")}
                evf["/diff"] = "D"
                rules.append(self.R("adprov.capture_environment_record@1", "/diff"))
            rec.data.update(evf=evf, rule=rules, unk={"/t": "not_recorded"})
            body.append(rec)

    # ---------------------------------------------------------------------------------------------- judgements
    def _judgements(self, body: list[Any]) -> None:
        meta = self.meta
        dos = set(self.family.get("dos_attacks", ()))
        run_error = meta.get("run_error") if self.converted else None
        for n, name in enumerate(("utility", "security")):
            value = meta.get(name)
            if value is not None and not isinstance(value, bool):
                raise MalformedArtefact(f"meta.{name}: unexpected value type")
            src = [_loc(_p("meta", name))]
            if name == "security":
                src.append(_loc("/meta/attack_type"))
            if self.converted:
                if run_error is not None:
                    origin, rule = "harness_default", "agentdojo.run_error_imposed_outcome@1"
                    src.append(_loc("/meta/run_error"))
                elif name == "security" and self.attack_id is None:
                    origin, rule = "harness_default", "agentdojo.benign_security_constant@1"
                elif name == "security" and self.attack_id in dos:
                    origin, rule = "harness_rule", "agentdojo.dos_security_rule@1"
                else:
                    origin, rule = "checker", "agentdojo.checker_outcome@1"
            elif name == "security" and self.attack_id is None:
                origin, rule = "harness_default", "adprov.benign_security_normalised@1"
            else:
                origin, rule = "checker", "adprov.checker_outcome@1"
            rules = [self.R(rule, "/origin")]
            record: dict[str, Any] = {"k": "judgement", "id": f"j{n}", "actor": "bench", "subject": "run", "name": name,
                                      "value": value, "origin": origin, "ev": "O", "by": "benchmark",
                                      "evf": {"/origin": "D"}, "rule": rules, "src": src}
            if origin == "checker":  # what the checker read is not recorded; the suite's checker inputs are asserted
                record["unk"] = {"/inputs": "not_recorded"}
                rules.append(self.R("agentdojo.checker_inputs_unverified@1", "/inputs"))
            body.append(record)
        if self.converted and run_error is not None:
            self.issue("outcome_imposed_by_runner", ["j0", "j1"], self.cite.cite("agentdojo.run_error_imposed_outcome@1"))
        if self.plan["unit"] == "outcome_only":
            self.issue("no_execution_observed", ["exec"], "agentdojo.no_execution_observed@1")
