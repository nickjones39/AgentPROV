"""The results-container build of the ``agentdojo.tracelogger`` mapper: rows of ``agentdojo.results_container`` -> AER
``aer/0.1`` (docs/architecture D.6.20; D-470..D-479; ``docs/reports/phase10q/``).

memo-ozdincer/agentdojo's evaluation scripts write one container per evaluation call with the call's settings at top level
and one row per (user task, injection task) pair (:mod:`~agentprov.adapters.agentdojo.results_reader`). Each row is one
execution; :class:`ResultsBuild` maps it in the D.6.5 record order of the generic mapper: the ``execution`` header, the
actors, the ``run`` and ``att0`` scopes, no fixtures (the rows record no injection map), the messages with the activities
that generate them, and the two judgements. It is entered from ``TraceLoggerMapper.map`` by a dispatch on the item's
dialect (D-471, routed edit R-10q-1), so the adapter id, version and execution-id prefix are the family's. What differs
from the TraceLogger build:

- **Settings at container level** (``rescont.container_fields_apply_to_rows@1``): suite, attack, defence and the served
  model name come from the container; the row adds the task ids, outcomes, duration and messages. The served name stays
  verbatim in ``ext.rescont.container.model`` (redacted, D-476); the model it denotes, a LoRA adapter served under its
  own name (a defence actor) and, for containers that record no attack, the attack come from the profile's container
  identity table, each with the document that states it (D-92, D-474), never from a code default.
- **What the scripts do not log** stays unknown: call ids (results link positionally, ``agentdojo.positional_match@1``),
  the model requests (built from the messages and possibly trimmed client-side, so ``input`` is inferred), times, the
  injection map, MELON's own model and embedding calls. The attempt index is lost: up to three passes ran and a null
  final content is serialised as the empty string.
- **Rows with no messages** are the scripts' exception path (D-475): ``outcome_only`` executions whose two outcomes are
  ``harness_default``.
- **Defence-authored messages**: a MELON block (the detector's fixed assistant text) is a ``terminate`` decision of the
  defence and the message it generated; a repeated task prompt is the repeating defence's copy; spotlighted tool outputs
  are post-defence.
- **The script's own summaries** (``classification``, ``turns``, ``failure_mode``, …) stay verbatim in ``ext.rescont`` with
  their meaning rule; they are not judgements.

Every D rule of ``rescont`` cites the scripts at the pin; the profile verifies none (D-472), so each is cited through its
``_unverified`` twin and every harness reading is class I; logged values stay O. Pure (A-2).
"""

from __future__ import annotations

import fnmatch
import hashlib
import tomllib
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import Any, Final

from agentprov.adapters.agentdojo.citation import citations
from agentprov.adapters.agentdojo.mapper import (
    ADAPTER_ID,
    ADAPTER_VERSION,
    _artefact_json,
    _lexical,
    _loc,
    _Rec,
    declared_variants,
    tool_status,
)
from agentprov.adapters.agentdojo.profile import FamilyTable, family_table
from agentprov.adapters.agentdojo.redact import NAMESPACE_IRI, RULE as R_REDACTED, Redactor, parse_redact_rules
from agentprov.adapters.agentdojo.results_reader import DIALECT_ID, FLAG_N_MISMATCH, MAPPED_VARIANTS
from agentprov.adapters.code_verification import weaken_to_rule_class
from agentprov.adapters.protocols import MappingContext
from agentprov.adapters.surrogates import scrub_keys, surrogates
from agentprov.adapters.types import ExecutionUnit
from agentprov.aer.canon import LexHints, encode_value, json_pointer
from agentprov.aer.ids import part_id
from agentprov.errors import MalformedArtefact, ProfileError, UnsupportedVariant
from agentprov.io.canonical import sha256_hex

__all__ = ["CATALOGUES", "NAMESPACES", "ContainerRow", "ResultsBuild", "container_table", "results_degenerate_header"]

CATALOGUES: Final = ("aer", "agentdojo", "rescont")
NAMESPACES: Final = {"agentdojo": "https://w3id.org/agentprov/ns/agentdojo#", "rescont": NAMESPACE_IRI}
#: MELONDetector's block text (``eval_lorra_multiturn.py`` l. 1177-1183 at the pin).
MELON_BLOCK: Final = "Potential prompt injection detected, stopping execution."
MELON_DEFENCES: Final = frozenset({"melon", "melon_aug"})
REPEAT_DEFENCES: Final = frozenset({"repeat_user_prompt", "secalign_sandwich", "melon_aug"})
SPOTLIGHT: Final = "spotlighting_with_delimiting"
_MODEL_CALL_UNKNOWN: Final = ("/finish_reason", "/request", "/response", "/t", "/tools", "/usage")
_CONTAINER_EXT: Final = ("label", "model", "adapter", "mode", "base_url", "port", "elapsed_seconds", "n_results")
_DERIVED: Final = ("classification", "failure_mode", "any_garbled", "n_assistant_turns", "n_total_tool_calls", "turns")
_SHAPES: Final = {
    "system": (frozenset({"role", "content"}), frozenset()),
    "user": (frozenset({"role", "content"}), frozenset()),
    "assistant": (frozenset({"role", "content"}), frozenset({"tool_calls"})),
    "tool": (frozenset({"role", "content", "tool_call", "error"}), frozenset({"raw_output"})),
}
_CALL_KEYS: Final = frozenset({"function", "args"})
_TABLE_KEYS: Final = frozenset({"glob", "served", "model", "basis", "conflict", "attack", "attack_basis", "defence",
                                "defence_basis", "note"})

# quirk ids (D.6.4; the profile declares them, R-38 namespacing)
Q_EXCEPTION: Final = "agentdojo.rescont_exception_row_defaults"
Q_BENIGN: Final = "agentdojo.rescont_benign_security_constant"
Q_EMPTY_TEXT: Final = "agentdojo.rescont_null_content_as_empty"
Q_MELON: Final = "agentdojo.rescont_melon_block"
Q_REPEAT: Final = "agentdojo.rescont_repeat_prompt_copy"
Q_SPOT: Final = "agentdojo.rescont_spotlighting_delimiters"
Q_RAW: Final = "agentdojo.rescont_raw_output"
Q_ARGS: Final = "agentdojo.args_mutated_in_place"
Q_IDS: Final = "agentdojo.provider_call_id_anomalies"
Q_TRAILING: Final = "agentdojo.unexecuted_trailing_calls"

# rules
R_FIELDS: Final = "rescont.container_fields_apply_to_rows@1"
R_SERIAL: Final = "rescont.messages_serialised@1"
R_NULL_EMPTY: Final = "rescont.null_content_serialised_empty@1"
R_EXCEPTION: Final = "rescont.exception_imposes_outcome@1"
R_BENIGN: Final = "rescont.benign_security_constant@1"
R_DURATION: Final = "rescont.duration_scope@1"
R_LAST_PASS: Final = "rescont.last_pass_kept@1"
R_SUITE_V1: Final = "rescont.suite_version_v1@1"
R_SYSTEM: Final = "rescont.system_prompt_from_eval_script@1"
R_REQUEST: Final = "rescont.request_built_from_messages@1"
R_MELON: Final = "rescont.melon_block_message@1"
R_REPEAT: Final = "rescont.repeat_prompt_copy@1"
R_SPOT: Final = "rescont.spotlighting_delimiters@1"
R_RAW: Final = "rescont.raw_output_is_return_value@1"
R_DERIVED: Final = "rescont.derived_fields_meaning@1"
R_NO_INJECTIONS: Final = "rescont.no_injection_map@1"
R_MODEL: Final = "rescont.model_from_identity_table@1"
R_LORA: Final = "rescont.lora_adapter_is_defence@1"
R_ATTACK: Final = "rescont.attack_from_identity_table@1"
R_CHECKER: Final = "rescont.checker_is_agentdojo_suites@1"
#: The rule a detected quirk's ``agentdojo.undeclared_quirk`` issue cites.
_QUIRK_RULES: Final = {
    Q_EXCEPTION: R_EXCEPTION, Q_BENIGN: R_BENIGN, Q_EMPTY_TEXT: R_NULL_EMPTY, Q_MELON: R_MELON, Q_REPEAT: R_REPEAT,
    Q_SPOT: R_SPOT, Q_RAW: R_RAW, Q_ARGS: "agentdojo.args_are_effective@1", Q_IDS: "agentdojo.positional_match@1",
    Q_TRAILING: "agentdojo.unexecuted_trailing_calls@1",
}  # fmt: skip


# ------------------------------------------------------------------------------------------------ the container table
@dataclass(frozen=True, slots=True)
class ContainerRow:
    """One row of a container identity table (D-474): a glob over container paths and the (redacted) served name."""

    glob: str
    served: str
    model: str | None
    basis: str
    conflict: str | None
    attack: str | None
    attack_basis: str | None
    defence: str | None
    defence_basis: str | None


@cache
def _load_table(path: str, sha256: str) -> tuple[ContainerRow, ...]:
    node = resources.files("agentprov.adapters.agentdojo").joinpath(*path.split("/"))
    if not node.is_file():
        raise ProfileError(f"container table {path!r} is not shipped in the package")
    data = node.read_bytes()
    if sha256_hex(data) != sha256:
        raise ProfileError(f"container table {path!r}: its sha256 differs from the one the profile pins")
    try:
        doc = tomllib.loads(data.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise ProfileError(f"container table {path!r}: not valid TOML/UTF-8") from exc
    if set(doc) != {"row"} or not isinstance(doc["row"], list):
        raise ProfileError(f"container table {path!r}: a table holds [[row]] rows only")
    rows: list[ContainerRow] = []
    for row in doc["row"]:
        if not isinstance(row, dict) or set(row) - _TABLE_KEYS or not {"glob", "served", "model", "basis"} <= set(row) \
                or not all(isinstance(v, str) and v for v in row.values()):
            raise ProfileError(f"container table {path!r}: a row is {{glob, served, model, basis, conflict?, attack?, "
                               "attack_basis?, defence?, defence_basis?, note?}} of non-empty strings")
        if ("attack" in row) != ("attack_basis" in row) or ("defence" in row) != ("defence_basis" in row):
            raise ProfileError(f"container table {path!r}: an attack or defence row cites its document")
        model = None if row["model"] == "not_recorded" else row["model"]
        rows.append(ContainerRow(row["glob"], row["served"], model, row["basis"], row.get("conflict"), row.get("attack"),
                                 row.get("attack_basis"), row.get("defence"), row.get("defence_basis")))
    return tuple(rows)


def container_table(fam: FamilyTable) -> tuple[ContainerRow, ...]:
    """The profile's container table (``[family.agentdojo.identity] container_table``), digest-checked; empty if none."""
    declared = fam.identity.get("container_table")
    if not isinstance(declared, Mapping):
        return ()
    return _load_table(str(declared["path"]), str(declared["sha256"]))


def _row_for(rows: Sequence[ContainerRow], path: str, served: str) -> ContainerRow | None:
    return next((r for r in rows if r.served == served and fnmatch.fnmatchcase(path, r.glob)), None)


def _row_index(item: Any) -> int:
    pointer = item.locator.p
    head, _, tail = pointer.rpartition("/")
    if head != "/results" or not tail.isdigit() or (tail != "0" and tail.startswith("0")):
        raise MalformedArtefact("the row locator is not /results/<i>")
    return int(tail)


# ------------------------------------------------------------------------------------------------ the build
class ResultsBuild:
    """One mapping run of a results-container row."""

    def __init__(self, unit: ExecutionUnit, ctx: MappingContext) -> None:
        item = unit.primary
        if item.dialect != DIALECT_ID:
            raise UnsupportedVariant(f"not a {DIALECT_ID} item")
        if item.variant not in MAPPED_VARIANTS or item.variant not in declared_variants(ctx.profile):
            raise UnsupportedVariant(f"results-container variant {item.variant} is recognised; the profile does not map it")
        container = item.value
        if not isinstance(container, dict) or not isinstance(container.get("results"), list):
            raise MalformedArtefact("the located item is not a results container")
        self.index = _row_index(item)
        if self.index >= len(container["results"]):
            raise MalformedArtefact("the row locator does not name a row of the container")
        self.unit, self.ctx, self.item = unit, ctx, item
        # D-378 (regen item 7, F-01; regen item 119, NF-13): a key cannot be $utf16-wrapped, so the keys of this row and
        # of the container's fields are scrubbed before mapping (the other rows are not read); disclosed by surrogates()
        fields, fields_changed = scrub_keys({k: v for k, v in container.items() if k != "results"})
        self.container: dict[str, Any] = {**fields, "results": container["results"]} if fields_changed else container
        self.row: dict[str, Any]
        self.row, row_changed = scrub_keys(container["results"][self.index])
        self.surrogate_keys = fields_changed or row_changed
        self.base = f"/results/{self.index}"
        self.fam: FamilyTable = family_table(ctx.profile)
        self.detected: set[str] = set()
        self._read_fields()
        self.facets: dict[str, str | None] = {"variant": item.variant, "suite": self.suite}
        self.cite = citations(self.fam, self.facets)
        self.r_ordered = self.cite.cite("agentdojo.messages_append_ordered@1")
        self.r_one_call = self.cite.cite("agentdojo.assistant_msg_has_one_call@1")
        self.r_one_exec = self.cite.cite("agentdojo.tool_msg_is_one_execution@1")
        self.benchmark = self.fam.benchmark_of(self.suite)
        origin = item.artefact.origin.data
        self.path = str(origin.get("path") or origin.get("label") or "")
        rules = parse_redact_rules(self.fam.data.get("redact", ()), f"profile {ctx.profile.id!r}")
        self.redactor = Redactor(ctx.profile.id, ctx.profile.version, rules, {"model_id": [self.served]})
        self.ident = _row_for(container_table(self.fam), self.path, self.redactor.label(self.served))
        # defences: the container's defence (O by config) and a LoRA adapter the identity table names (I), never doubled
        self.defences: dict[str, str] = {}
        if self.defense is not None:
            self.defences[self.defense] = "config"
        if self.ident is not None and self.ident.defence is not None:
            self.defences.setdefault(self.ident.defence, "table")
        self.def_ids: dict[str, str] = {name: f"def{n}" for n, name in enumerate(sorted(self.defences))}
        self.n_mc = self.n_te = self.n_dc = 0

    # ---------------------------------------------------------------------------------------------- helpers
    def R(self, rule_id: str, pointer: str | None = None) -> str:  # noqa: N802 - mirrors the generic mapper
        return self.ctx.rule(self.cite.cite(rule_id), pointer)

    def C(self, rule_id: str) -> str:  # noqa: N802
        return self.cite.cls(rule_id)

    def issue(self, code: str, ids: Sequence[str], rule: str, *, severity: str = "warning", detail: str | None = None) -> None:
        self.ctx.issue(code, ids=list(ids), rule=self.ctx.rule(rule), severity=severity, detail=detail)  # type: ignore[arg-type]

    def quirk_on(self, quirk_id: str) -> bool:
        return self.fam.applies(quirk_id, self.facets)

    def detect(self, quirk_id: str) -> bool:
        """Note a quirk seen in the data; ``True`` when the profile declares it for this row (then it is applied)."""
        self.detected.add(quirk_id)
        return self.quirk_on(quirk_id)

    def at(self, *tokens: str | int) -> dict[str, Any]:
        """A source locator under this row."""
        return _loc(self.base + json_pointer(*(str(t) for t in tokens)) if tokens else self.base)

    def msg_at(self, i: int, *tokens: str) -> dict[str, Any]:
        return self.at("messages", i, *tokens)

    def _read_fields(self) -> None:
        c, r = self.container, self.row

        def text(where: Mapping[str, Any], key: str, *, nullable: bool = False) -> Any:
            value = where.get(key)
            if (isinstance(value, str) and value) or (nullable and value is None):
                return value
            raise MalformedArtefact(f"{key}: empty" if value == "" else f"{key}: unexpected value type")

        self.served = text(c, "model")
        self.suite = text(c, "suite") if "suite" in c else text(r, "suite")
        self.defense = text(c, "defense", nullable=True) if "defense" in c else None
        self.attack_logged = text(c, "attack", nullable=True) if "attack" in c else None
        self.task_id = text(r, "user_task_id")
        self.target = text(r, "injection_task_id", nullable=True)
        for name in ("utility", "security"):
            if not isinstance(r.get(name), bool):
                raise MalformedArtefact(f"{name}: unexpected value type")
        duration = r.get("duration")
        if isinstance(duration, bool) or not isinstance(duration, int | float):
            raise MalformedArtefact("duration: unexpected value type")
        if not isinstance(r.get("messages"), list):
            raise MalformedArtefact("messages: unexpected value type")
        self.messages: list[Any] = r["messages"]

    # ---------------------------------------------------------------------------------------------- run
    def run(self) -> Iterator[dict[str, Any]]:
        body: list[Any] = []
        header = self._header()
        self._identity_issues()
        self._actors(body)
        self._scopes(body)
        self._no_fixtures()
        self._messages(body)
        self._judgements(body)
        if FLAG_N_MISMATCH in self.item.flags:
            self.issue("rescont.n_results_mismatch", ["exec"], R_FIELDS)
        for quirk_id in sorted(self.detected):
            if not self.quirk_on(quirk_id):
                self.issue("agentdojo.undeclared_quirk", ["exec"], _QUIRK_RULES[quirk_id], detail=quirk_id)
        records = [record.done() if isinstance(record, _Rec) else record for record in body]
        head = header.done()
        surrogates(self, (head, *records), "agentdojo")  # D-378, before the redaction pass (regen item 119, NF-13)
        redacted = 0
        for record in (head, *records):
            redacted += len(self.redactor.apply(record, lambda p: self.ctx.rule(R_REDACTED, p)))
        if redacted:
            self.ctx.issue("rescont.value_redacted", ids=["exec"], rule=self.ctx.rule(R_REDACTED), severity="info",
                           detail=str(redacted))
        for record in (head, *records):  # C.6.5 rule 1
            weaken_to_rule_class(record)
        cited = {str(ref).split(".", 1)[0] for r in (head, *records) for ref in r.get("rule", ())}
        cited |= {str(i.get("rule", "")).split(".", 1)[0] for i in getattr(self.ctx, "issues", ()) if i.get("rule")}
        head["rules"] = self.ctx.catalogue_versions(sorted(set(CATALOGUES) | cited))
        yield head
        yield from records

    # ---------------------------------------------------------------------------------------------- header
    def _attack(self) -> tuple[str | None, str | None]:
        """``(attack, source)``: the container's (``config``), the table's (``table``), or none recorded (``None``)."""
        if self.target is None:
            return None, "benign"
        if isinstance(self.attack_logged, str):
            return self.attack_logged, "config"
        if self.ident is not None and self.ident.attack is not None:
            return self.ident.attack, "table"
        return None, None

    def _header(self) -> _Rec:
        h = _Rec()
        attack, attack_src = self._attack()
        self.attack, self.attack_src = attack, attack_src
        task: dict[str, Any] = {
            "benchmark": self.benchmark,
            "suite": h.enc(self.suite, "/task/suite"),
            "task_id": h.enc(self.task_id, "/task/task_id"),
            "attack_target_id": h.enc(self.target, "/task/attack_target_id"),
        }
        evf: dict[str, str] = {"/task/benchmark": self.C(R_CHECKER), "/task/suite": self.C(R_FIELDS)}
        rules = [self.R(R_CHECKER, "/task/benchmark"), self.R(R_FIELDS, "/task/suite")]
        unk: dict[str, str] = {"/instrumentation": "not_recorded"}
        suite_src = _loc("/suite") if "suite" in self.container else self.at("suite")
        src = [suite_src, self.at("user_task_id"), self.at("injection_task_id")]
        if attack_src in ("benign", "config"):
            task["attack_id"] = h.enc(attack, "/task/attack_id")
            evf["/task/attack_id"] = self.C(R_FIELDS)
            rules.append(self.R(R_FIELDS, "/task/attack_id"))
            if attack_src == "config":
                src.append(_loc("/attack"))
        elif attack_src == "table":
            task["attack_id"] = h.enc(attack, "/task/attack_id")
            evf["/task/attack_id"] = "I"
            rules.append(self.R(R_ATTACK, "/task/attack_id"))
            src.append(_loc(""))
        else:
            unk["/task/attack_id"] = "not_recorded"
        names = sorted(self.def_ids)
        if len(names) > 1:
            unk["/task/defense_id"] = "ambiguous"
        elif not names and "defense" not in self.container:
            # no `defense` key and no table defence: nothing logged says "no defence" (invariant 2; regen item 116, NF-6),
            # so the field is unrecorded, as an unrecorded attack is; `rescont.defence_unrecorded` is raised below
            unk["/task/defense_id"] = "not_recorded"
        else:
            task["defense_id"] = names[0] if names else None
            if names and self.defences[names[0]] == "table":
                evf["/task/defense_id"] = "I"
                rules.append(self.R(R_LORA, "/task/defense_id"))
            else:
                evf["/task/defense_id"] = self.C(R_FIELDS)
                rules.append(self.R(R_FIELDS, "/task/defense_id"))
                if "defense" in self.container:
                    src.append(_loc("/defense"))
        ext = h.data.setdefault("ext", {}).setdefault("rescont", {})
        ext["container"] = {k: h.enc(self.container[k], f"/ext/rescont/container/{k}") for k in _CONTAINER_EXT
                            if k in self.container}
        src += [_loc(f"/{k}") for k in _CONTAINER_EXT if k in self.container]
        derived = {k: h.enc(self.row[k], f"/ext/rescont/derived/{k}") for k in _DERIVED if k in self.row}
        if derived:
            ext["derived"] = derived
            src += [self.at(k) for k in _DERIVED if k in self.row]
            rules.append(self.R(R_DERIVED))  # unscoped: the values are O by source (C.6.4)
        if self.ident is not None and self.ident.attack is not None and attack_src == "table":
            ext["attack_basis"] = self.ident.attack_basis
            evf["/ext/rescont/attack_basis"] = "I"
            rules.append(self.R(R_ATTACK, "/ext/rescont/attack_basis"))
        rules.append(self.R(R_SERIAL))
        h.data.update({
            "k": "execution", "id": "exec", "aer": "0.1", "ex": self.ctx.ex, "mode": "import",
            "unit": "agent_execution" if self.messages else "outcome_only",
            "source_key": {"sha256": self.item.artefact.sha256, "loc": self.item.locator.key()},
            "artifacts": [_artefact_json(self.unit, self.ctx)],
            "adapter": {"id": ADAPTER_ID, "version": ADAPTER_VERSION},
            "dialect": {"id": DIALECT_ID, "variant": self.item.variant},
            "profile": self.ctx.profile.header(),
            "rules": self.ctx.catalogue_versions(CATALOGUES),
            "ns": dict(sorted(NAMESPACES.items())),
            "canon": "jcs-rfc8785", "hash": "sha256", "task": task, "ev": "O", "by": "config",
            "evf": dict(sorted(evf.items())), "rule": rules, "src": src, "unk": unk,
        })
        return h

    def _identity_issues(self) -> None:
        if self.ident is None or self.ident.model is None:
            if not self._provider_id():
                self.issue("identity_unresolved", ["agent"], R_MODEL)
        elif self.ident.conflict is not None:
            self.issue("identity_conflict", ["agent"], R_MODEL, severity="info", detail=self.ident.conflict)
        if self.target is not None and self.attack_src is None:
            self.issue("rescont.attack_unrecorded", ["exec"], R_ATTACK, severity="info")
        if not self.def_ids and "defense" not in self.container:  # regen item 116 (NF-6): the container's field is absent
            self.issue("rescont.defence_unrecorded", ["exec"], self.cite.cite(R_FIELDS), severity="info")

    def _provider_id(self) -> bool:
        """The served name is a provider model id the client requested (no path, no table row): logged, O."""
        return self.ident is None and "/" in self.served and not self.served.startswith("/")

    # ---------------------------------------------------------------------------------------------- actors, scopes
    def _actors(self, body: list[Any]) -> None:
        bench = _Rec(k="actor", id="bench", kind="benchmark", name=self.benchmark, ev="D", version="v1",
                     evf={"/version": self.C(R_SUITE_V1)},
                     rule=[self.R(R_CHECKER), self.R(R_SUITE_V1, "/version")],
                     unk={"/code": "not_recorded"})
        body.append(bench)
        body.append({"k": "actor", "id": "user", "kind": "simulated_user", "ev": "D",
                     "rule": [self.R("agentdojo.user_is_simulated@1")]})
        agent: dict[str, Any] = {"k": "actor", "id": "agent", "kind": "llm_agent", "on_behalf_of": "user", "ev": "D"}
        model_unk = {"/model/provider": "not_recorded", "/model/served": "not_recorded", "/params": "not_recorded"}
        if self._provider_id():
            agent.update(model={"requested": self.served}, by="config",
                         evf={"/model": "O"}, rule=[self.R("agentdojo.user_is_simulated@1"), self.R(R_FIELDS, "/model")],
                         src=[_loc("/model")], unk=model_unk)
        elif self.ident is not None and self.ident.model is not None:
            agent.update(model={"requested": self.ident.model}, evf={"/model": "I"},
                         rule=[self.R("agentdojo.user_is_simulated@1"), self.R(R_MODEL, "/model")],
                         src=[_loc("/model")], unk=model_unk)
        else:
            agent.update(rule=[self.R("agentdojo.user_is_simulated@1")], unk={"/model": "not_recorded", "/params": "not_recorded"})
        body.append(agent)
        body.append({"k": "actor", "id": "env", "kind": "tool_runtime", "name": "agentdojo.FunctionsRuntime", "on_behalf_of": "agent",
                     "ev": "D", "evf": {"/on_behalf_of": "I"},
                     "rule": [self.R("agentdojo.functions_runtime@1"), self.R("agentdojo.auto_execution_unverified@1", "/on_behalf_of")]})
        if self.attack is not None:
            if self.attack_src == "config":
                att = _Rec(k="actor", id="att", kind="attacker", ev="O", by="config", src=[_loc("/attack")])
            else:
                att = _Rec(k="actor", id="att", kind="attacker", ev="I", rule=[self.R(R_ATTACK)], src=[_loc("")])
            att.data["name"] = att.enc(self.attack, "/name")
            body.append(att)
        for name, did in self.def_ids.items():
            if self.defences[name] == "config":
                rec: dict[str, Any] = {"k": "actor", "id": did, "kind": "defense", "name": name, "ev": "O", "by": "config",
                                       "src": [_loc("/defense")], "unk": {"/model": "not_recorded", "/version": "not_recorded"}}
            else:
                assert self.ident is not None
                rec = {"k": "actor", "id": did, "kind": "defense", "name": name, "ev": "I", "rule": [self.R(R_LORA)],
                       "src": [_loc("/model")], "unk": {"/version": "not_recorded"},
                       "ext": {"rescont": {"defence_basis": self.ident.defence_basis}}}
            body.append(rec)

    def _scopes(self, body: list[Any]) -> None:
        run = _Rec(k="scope", id="run", kind="run", actor="agent", ev="O", by="source", src=[self.at("duration")],
                   rule=[self.R(R_DURATION)],
                   unk={"/status": "not_recorded", "/t/end": "not_recorded", "/t/start": "not_recorded"})
        run.data["t"] = {"dur_s": run.enc(self.row["duration"], "/t/dur_s"), "dur_clock": "wall"}
        body.append(run)
        if not self.messages:
            return
        body.append({"k": "scope", "id": "att0", "kind": "attempt", "parent": "run", "actor": "agent", "scored": True,
                     "ev": self.C(R_LAST_PASS), "rule": [self.R(R_LAST_PASS), self.R(R_LAST_PASS, "/index")],
                     "unk": {"/index": "lost"}})

    def _no_fixtures(self) -> None:
        """D.6.5 Step 4: the rows record no injection map, so there are no payload fixtures."""
        if self.target is not None:
            self.issue("rescont.injection_map_not_recorded", ["exec"], R_NO_INJECTIONS, severity="info")

    # ---------------------------------------------------------------------------------------------- messages
    def _shape(self, message: object) -> str | None:
        if not isinstance(message, dict):
            return None
        role = message.get("role")
        spec = _SHAPES.get(role) if isinstance(role, str) else None
        if spec is None or not (spec[0] <= set(message) <= spec[0] | spec[1]) or not isinstance(message.get("content"), str):
            return None
        if role == "assistant" and "tool_calls" in message:
            calls = message["tool_calls"]
            if not (isinstance(calls, list) and calls and all(self._call_ok(c) for c in calls)):
                return None
        if role == "tool":
            if not self._call_ok(message.get("tool_call")) or not (message.get("error") is None or isinstance(message.get("error"), str)):
                return None
        return str(role)

    @staticmethod
    def _call_ok(call: object) -> bool:
        return (isinstance(call, dict) and set(call) == _CALL_KEYS and isinstance(call["function"], str)
                and isinstance(call["args"], dict))

    def _messages(self, body: list[Any]) -> None:
        msgs = self.messages
        self.prev: str | None = None
        self.ids: list[str] = []
        self.first_user: tuple[str, str] | None = None
        self.last_assistant: str | None = None
        self.last_te: str | None = None
        self.batches: list[dict[str, Any]] = []
        self.request_issue = False
        i = 0
        while i < len(msgs):
            message = msgs[i]
            role = self._shape(message)
            if role == "assistant":
                j = i + 1
                tools: list[int] = []
                while j < len(msgs) and self._shape(msgs[j]) == "tool":
                    tools.append(j)
                    j += 1
                self._assistant(body, i, message, tools)
                i = j
                continue
            if role in ("system", "user"):
                self._plain(body, i, message, role)
            elif role == "tool":
                self._tool(body, i, message, None, None, 0)
            else:
                self._unknown(body, i, message)
            i += 1
        self._trailing_calls()

    def _push(self, mid: str) -> None:
        self.prev = mid
        self.ids.append(mid)

    def _after_pos(self, rec: _Rec, evf: dict[str, str], rules: list[str]) -> None:
        if self.prev is not None:
            rec.data["after"] = [{"b": "pos", "id": self.prev}]
            evf["/after"] = self.C(self.r_ordered)
            rules.append(self.R(self.r_ordered, "/after"))

    def _plain(self, body: list[Any], i: int, message: Mapping[str, Any], role: str) -> None:
        mid = f"m{i}"
        content: str = message["content"]
        rec = _Rec(k="message", id=mid, scope="att0", role=role, ev="O", by="source", src=[self.msg_at(i)])
        rec.data["parts"] = [{"t": "text", "text": rec.enc(content, "/parts/0/text")}]
        evf: dict[str, str] = {}
        rules: list[str] = []
        if role == "system":
            rec.data["actor"] = "bench"
            evf["/actor"] = self.C(R_SYSTEM)
            rules.append(self.R(R_SYSTEM, "/actor"))
            self._prompt_variant(rec, content, evf, rules)
        elif self.first_user is None:
            rec.data["actor"] = "user"
            evf["/actor"] = self.C("agentdojo.user_is_simulated@1")
            rules.append(self.R("agentdojo.user_is_simulated@1", "/actor"))
            self.first_user = (mid, content)
        else:
            repeater = next((d for d in sorted(self.def_ids) if d in REPEAT_DEFENCES), None)
            if repeater is not None and content == self.first_user[1] and self.detect(Q_REPEAT):
                rec.data["actor"] = self.def_ids[repeater]
                rec.data.setdefault("ext", {})["rescont"] = {"copy_of": self.first_user[0]}
                evf["/actor"] = self.C(R_REPEAT)
                evf["/ext/rescont/copy_of"] = self.C(R_REPEAT)
                rules += [self.R(R_REPEAT, "/actor"), self.R(R_REPEAT, "/ext/rescont/copy_of")]
            else:
                rec.data["actor"] = "user"
                evf["/actor"] = "I"
                rules.append(self.R("agentdojo.additional_user_message_unattributed@1", "/actor"))
                self.issue("unattributed_additional_user_message", [mid], "agentdojo.additional_user_message_unattributed@1")
        self._after_pos(rec, evf, rules)
        rec.data.update(evf=evf, rule=rules)
        body.append(rec)
        self._push(mid)

    def _prompt_variant(self, rec: _Rec, content: str, evf: dict[str, str], rules: list[str]) -> None:
        """The system prompt's variant label by SHA-256 against the profile's pinned variants (D.6.6 system row)."""
        variants = [v for v in self.fam.prompt_variants if v.matches(self.facets)]
        if not variants:
            return
        digest = hashlib.sha256(content.encode("utf-8", "surrogatepass")).hexdigest()
        found = next((v for v in variants if v.sha256 == digest), None)
        rule = "agentdojo.system_prompt_variant_digest@1"
        if found is None:
            self.ctx.issue("agentdojo.system_prompt_unrecognised", ids=[str(rec.data["id"])], rule=self.ctx.rule(rule),
                           severity="info")
            return
        rec.data.setdefault("ext", {}).setdefault("rescont", {})["system_prompt_variant"] = found.label
        evf["/ext/rescont/system_prompt_variant"] = "D"
        rules.append(self.ctx.rule(rule, "/ext/rescont/system_prompt_variant"))

    def _unknown(self, body: list[Any], i: int, message: object) -> None:
        mid = f"m{i}"
        role = message.get("role") if isinstance(message, dict) else None
        rec = _Rec(k="message", id=mid, scope="att0", ev="O", by="source", src=[self.msg_at(i)])
        rec.data["role"] = rec.enc(role, "/role") if isinstance(role, str) and role else "agentdojo.unknown"
        rec.data["parts"] = [{"t": "other", "type": "agentdojo.unknown_message", "value": rec.enc(message, "/parts/0/value")}]
        rec.data["unk"] = {"/actor": "not_recorded"}
        evf: dict[str, str] = {}
        rules: list[str] = []
        self._after_pos(rec, evf, rules)
        if evf:
            rec.data.update(evf=evf, rule=rules)
        body.append(rec)
        self.ctx.issue("agentdojo.unknown_message_shape", ids=[mid], rule=self.ctx.rule("agentdojo.tracelogger_record_shape@1"))
        self._push(mid)

    # ---------------------------------------------------------------------------------------------- assistant
    def _melon_block(self, message: Mapping[str, Any]) -> str | None:
        """The MELON defence actor whose block this assistant message is, else ``None``."""
        if message["content"] != MELON_BLOCK or "tool_calls" in message or not self.ids:
            return None
        melon = next((d for d in sorted(self.def_ids) if d in MELON_DEFENCES), None)
        before = self.messages[len(self.ids) - 1] if self.ids else None
        if melon is None or self.last_te is None or not (isinstance(before, dict) and before.get("role") == "tool") \
                or not self.detect(Q_MELON):
            return None
        return self.def_ids[melon]

    def _assistant(self, body: list[Any], i: int, message: Mapping[str, Any], tools: Sequence[int]) -> None:
        if not self.request_issue:
            self.request_issue = True
            self.issue("rescont.request_not_recorded", ["exec"], R_REQUEST, severity="info")
        mid = f"m{i}"
        content: str = message["content"]
        melon = self._melon_block(message)
        if melon is not None:
            self._melon(body, i, mid, content, melon)
            return
        mc_id = f"mc{self.n_mc}"
        self.n_mc += 1
        mc = _Rec(k="model_call", id=mc_id, actor="agent", role="agent", scope="att0", status="kept", ev=self.C(self.r_one_call),
                  input=list(self.ids), evf={"/input": "I"})
        mc_rules = [self.R(self.r_one_call), self.R(R_REQUEST, "/input")]
        if self.prev is not None:
            mc.data["after"] = [{"b": "pos", "id": self.prev}]
            mc_rules.append(self.R(self.r_ordered, "/after"))
        mc.data["rule"] = mc_rules
        mc.data["unk"] = {key: "not_recorded" for key in _MODEL_CALL_UNKNOWN}
        body.append(mc)

        rec = _Rec(k="message", id=mid, scope="att0", role="assistant", actor="agent", generated_by=mc_id,
                   after=[{"b": "causal", "id": mc_id}], ev="O", by="source", src=[self.msg_at(i)])
        parts: list[dict[str, Any]] = [{"t": "text", "text": rec.enc(content, "/parts/0/text")}]
        cls = self.C(self.r_one_call)
        evf = {"/after": cls, "/generated_by": cls}
        rules = [self.R(self.r_one_call, "/generated_by"), self.R("aer.output_after_generator@1", "/after")]
        unk: dict[str, str] = {}
        if content == "" and self.detect(Q_EMPTY_TEXT):
            unk["/parts/0/text"] = "ambiguous"
            rules.append(self.R(R_NULL_EMPTY, "/parts/0/text"))
        calls: list[list[Any]] = []
        for call in message.get("tool_calls", ()):
            k = len(parts)
            parts.append({"t": "tool_call", "name": rec.enc(call["function"], f"/parts/{k}/name"),
                          "args": rec.enc(call["args"], f"/parts/{k}/args")})
            unk[f"/parts/{k}/provider_call_id"] = "not_recorded"
            unk[f"/parts/{k}/args_raw"] = "not_recorded"
            calls.append([part_id(mid, k), call, False])
        if calls:
            self.detected.add(Q_IDS)
            if self.detect(Q_ARGS):
                rules.append(self.R("agentdojo.args_are_effective@1"))  # unscoped: args are O by source (D.6.11 item 7)
        rec.data.update(parts=parts, evf=evf, rule=rules)
        if unk:
            rec.data["unk"] = unk
        body.append(rec)
        self._push(mid)
        self.last_assistant = mid
        batch = {"msg": mid, "calls": calls, "results": 0}
        if calls:
            self.batches.append(batch)
        links = self._link(batch, [self.messages[t] for t in tools])
        for position, t in enumerate(tools):
            self._tool(body, t, self.messages[t], batch, links[position], position)

    def _melon(self, body: list[Any], i: int, mid: str, content: str, actor: str) -> None:
        """MELON's block (``rescont.melon_block_message@1``): a ``terminate`` decision about the last tool execution, and
        the defence-written assistant message it generated. The dropped model turn, the masked call and the embedding
        calls are not logged and get no records."""
        assert self.last_te is not None
        dc_id = f"dc{self.n_dc}"
        self.n_dc += 1
        cls = self.C(R_MELON)
        body.append({"k": "decision", "id": dc_id, "actor": actor, "scope": "att0", "subject": self.last_te,
                     "verdict": "terminate", "after": [{"b": "causal", "id": self.last_te}], "ev": cls,
                     "rule": [self.R(R_MELON), self.R("aer.decision_after_subject@1", "/after")],
                     "src": [self.msg_at(i, "content")], "unk": {"/reason": "not_recorded", "/t": "not_recorded"}})
        self.issue("rescont.melon_calls_not_recorded", [dc_id], R_MELON, severity="info")
        rec = _Rec(k="message", id=mid, scope="att0", role="assistant", actor=actor, generated_by=dc_id,
                   after=[{"b": "causal", "id": dc_id}], ev="O", by="source", src=[self.msg_at(i)])
        rec.data["parts"] = [{"t": "text", "text": rec.enc(content, "/parts/0/text")}]
        rec.data.update(evf={"/actor": cls, "/after": cls, "/generated_by": cls},
                        rule=[self.R(R_MELON, "/actor"), self.R(R_MELON, "/generated_by"),
                              self.R("aer.output_after_generator@1", "/after")])
        body.append(rec)
        self._push(mid)
        self.last_assistant = mid

    def _link(self, batch: Mapping[str, Any], results: Sequence[Mapping[str, Any]]) -> list[tuple[int | None, str | None]]:
        """D.6.6.1 rule 2 (no call ids are logged): ``(call index, problem issue)`` per tool message of the batch."""
        calls = batch["calls"]
        out: list[tuple[int | None, str | None]] = []
        for p, result in enumerate(results):
            if p >= len(calls):
                out.append((None, "orphan_tool_result"))
                continue
            echo, call = result.get("tool_call") or {}, calls[p][1]
            if echo.get("function") == call.get("function") and _lexical(echo.get("args")) == _lexical(call.get("args")):
                out.append((p, None))
            else:
                out.append((None, "call_result_link_conflict"))
        return out

    # ---------------------------------------------------------------------------------------------- tool messages
    def _tool(self, body: list[Any], i: int, message: Mapping[str, Any], batch: dict[str, Any] | None,
              link: tuple[int | None, str | None] | None, position: int) -> None:
        index, problem = link if link is not None else (None, "orphan_tool_result")
        link_rule = "agentdojo.positional_match@1"
        call_part: str | None = None
        if batch is not None and index is not None:
            call_part = batch["calls"][index][0]
            batch["calls"][index][2] = True
        if batch is not None:
            batch["results"] += 1
        echo = message["tool_call"]
        error = message.get("error")
        te_id = f"te{self.n_te}"
        self.n_te += 1
        te = _Rec(k="tool_execution", id=te_id, actor="env", scope="att0", ev=self.C(self.r_one_exec), by="source")
        te.data["name"] = te.enc(echo["function"], "/name")
        te.data["args"] = te.enc(echo["args"], "/args")
        te.data["status"] = tool_status(error)
        evf: dict[str, str] = {"/args": "O", "/name": "O"}
        rules = [self.R(self.r_one_exec), self.R(link_rule, "/call"), self.R("agentdojo.tool_status_from_error@1", "/status")]
        unk = {"/args_effective": "not_recorded", "/returned": "not_recorded", "/t": "not_recorded"}
        src = [self.msg_at(i, "tool_call"), self.msg_at(i, "error")]
        if self.quirk_on(Q_ARGS):
            te.data["args_effective"] = te.enc(echo["args"], "/args_effective")
            evf["/args_effective"] = self.C("agentdojo.args_are_effective@1")
            rules.append(self.R("agentdojo.args_are_effective@1", "/args_effective"))
            del unk["/args_effective"]
        if "raw_output" in message and self.detect(Q_RAW):
            raw = message["raw_output"]
            if isinstance(raw, str):  # a string return value or str() of an object: which one is not recorded
                unk["/returned"] = "ambiguous"
                te.data.setdefault("ext", {})["rescont"] = {"raw_output": te.enc(raw, "/ext/rescont/raw_output")}
                rules.append(self.R(R_RAW, "/returned"))
            else:
                te.data["returned"] = te.enc(raw, "/returned")
                del unk["/returned"]
                evf["/returned"] = "O"
                rules.append(self.R(R_RAW))  # unscoped: the value is O by source; the rule gives its meaning
            src.append(self.msg_at(i, "raw_output"))
        after: list[dict[str, str]] = []
        if call_part is not None and batch is not None:
            te.data["call"] = call_part
            after.append({"b": "causal", "id": batch["msg"]})
            evf["/call"] = "I"
            rules.append(self.R("aer.execution_after_call@1", "/after"))
        else:
            unk["/call"] = "ambiguous"
        if position > 0 and self.prev is not None:
            after.append({"b": "pos", "id": self.prev})
            rules.append(self.R("agentdojo.tools_executed_sequentially@1", "/after"))
        if after:
            te.data["after"] = after
        te.data.update(evf=dict(sorted(evf.items())), rule=rules, src=src, unk=unk)
        body.append(te)
        self.last_te = te_id

        mid = f"m{i}"
        msg = _Rec(k="message", id=mid, scope="att0", role="tool", actor="env", generated_by=te_id,
                   after=[{"b": "causal", "id": te_id}], ev="O", by="source", src=[self.msg_at(i)])
        part: dict[str, Any] = {"t": "tool_result", "text": msg.enc(message["content"], "/parts/0/text"),
                                "error": msg.enc(error, "/parts/0/error")}
        cls = self.C(self.r_one_exec)
        mevf: dict[str, str] = {"/after": cls, "/generated_by": cls}
        mrules = [self.R(self.r_one_exec, "/generated_by")]
        munk: dict[str, str] = {}
        if call_part is not None:
            part["responds_to"] = call_part
            mevf["/parts/0/responds_to"] = "I"
        else:
            munk["/parts/0/responds_to"] = "ambiguous"
        mrules += [self.R(link_rule, "/parts/0/responds_to"), self.R("aer.output_after_generator@1", "/after")]
        if SPOTLIGHT in self.def_ids and self.detect(Q_SPOT):
            msg.data.setdefault("ext", {})["rescont"] = {"content_state": "post_defence"}
            mevf["/ext/rescont/content_state"] = self.C(R_SPOT)
            mrules.append(self.R(R_SPOT, "/ext/rescont/content_state"))
        msg.data.update(parts=[part], evf=mevf, rule=mrules)
        if munk:
            msg.data["unk"] = munk
        body.append(msg)
        self._push(mid)
        if problem is not None:
            self.issue(problem, [te_id, mid], link_rule)

    def _trailing_calls(self) -> None:
        """Calls with no tool message: ``unexecuted_tool_call`` in the last assistant message, else ``missing_tool_result``."""
        for batch in self.batches:
            pending = [pid for k, (pid, _call, linked) in enumerate(batch["calls"]) if not linked and k >= batch["results"]]
            if not pending:
                continue
            if batch["msg"] == self.last_assistant:
                self.detect(Q_TRAILING)
                self.issue("unexecuted_tool_call", pending, "agentdojo.unexecuted_trailing_calls@1")
            else:
                self.issue("missing_tool_result", pending, "agentdojo.unexecuted_trailing_calls@1", severity="error")

    # ---------------------------------------------------------------------------------------------- judgements
    def _judgements(self, body: list[Any]) -> None:
        exception = not self.messages and self.detect(Q_EXCEPTION)
        quirk = self.fam.quirk(Q_EXCEPTION) if exception else None
        ids: list[str] = []
        imposed: list[str] = []
        for spec in self.fam.outcomes.get("judgements", ()):
            name, field = str(spec["name"]), str(spec["field"])
            jid = f"j{len(ids)}"
            src = [self.at(field)]
            # an exception row imposes only the values the quirk declares; another logged value keeps its checker origin
            # and is reported (as capture_mapper's run_error_imposes_outcome does; regen item 118, NF-8)
            expected = quirk.params.get(name) if quirk is not None else None
            declared = isinstance(expected, bool) and self.row[field] is expected
            if quirk is not None and not declared:
                self.issue("rescont.exception_row_values_differ", [jid], self.cite.cite(R_EXCEPTION),
                           detail=f"logged {name} differs from the profile's {Q_EXCEPTION} value")
            if declared:
                origin, rule = "harness_default", R_EXCEPTION
                src.append(self.at("messages"))
                imposed.append(jid)
            elif name == "security" and self.target is None and self.detect(Q_BENIGN):
                origin, rule = "harness_default", R_BENIGN
                src.append(self.at("injection_task_id"))
            else:
                origin, rule = "checker", "agentdojo.checker_outcome@1"
            record: dict[str, Any] = {"k": "judgement", "id": jid, "actor": "bench", "subject": "run", "name": name,
                                      "value": self.row[field], "origin": origin, "ev": "O", "by": "benchmark",
                                      "evf": {"/origin": self.C(rule)}, "rule": [self.R(rule, "/origin")], "src": src}
            if origin == "checker":
                record["unk"] = {"/inputs": "not_recorded"}
                record["rule"].append(self.R("agentdojo.checker_inputs_unverified@1", "/inputs"))
            body.append(record)
            ids.append(jid)
        if imposed:  # the judgements' reading (the twin under D-472), as the generic mapper cites it (regen item 115, NF-5)
            self.issue("outcome_imposed_by_runner", imposed, self.cite.cite(R_EXCEPTION))
        if not self.messages:
            self.issue("no_execution_observed", ["exec"], "agentdojo.no_execution_observed@1")


def results_degenerate_header(unit: ExecutionUnit, ctx: MappingContext, *, issue_code: str, detail: str) -> dict[str, Any]:
    """The header of a degenerate AER for a results-container item (D.2.8 case 3), with its error issue reported through
    ``ctx``: the family's TraceLogger header shape under this dialect's id, its row locator and the row's task ids."""
    value = unit.primary.value if isinstance(unit.primary.value, dict) else {}
    fam = family_table(ctx.profile)
    cite = citations(fam, {"variant": unit.primary.variant})
    bench_rule = cite.cite(R_CHECKER)
    row: Mapping[str, Any] = {}
    try:
        index = _row_index(unit.primary)
        rows = value.get("results")
        if isinstance(rows, list) and index < len(rows) and isinstance(rows[index], dict):
            row = rows[index]
    except MalformedArtefact:
        index = None
    suite = value.get("suite") if isinstance(value.get("suite"), str) else row.get("suite")
    task: dict[str, Any] = {"benchmark": fam.benchmark_of(suite) if isinstance(suite, str) and suite
                            else str(fam.benchmark.get("benchmark", "agentdojo"))}
    header: dict[str, Any] = {
        "k": "execution", "id": "exec", "aer": "0.1", "ex": ctx.ex, "mode": unit.mode, "unit": "agent_execution",
        "source_key": {"sha256": unit.primary.artefact.sha256, "loc": unit.primary.locator.key()},
        "artifacts": [_artefact_json(unit, ctx)],
        "adapter": {"id": ADAPTER_ID, "version": ADAPTER_VERSION},
        "dialect": {"id": DIALECT_ID, "variant": unit.primary.variant},
        "profile": ctx.profile.header(),
        "rules": ctx.catalogue_versions(CATALOGUES),
        "ns": dict(sorted(NAMESPACES.items())),
        "canon": "jcs-rfc8785", "hash": "sha256", "task": task, "ev": "D",
        "rule": [ctx.rule(bench_rule)], "unk": {"/instrumentation": "not_recorded"},
    }
    task_id = row.get("user_task_id")
    if isinstance(task_id, str) and task_id and index is not None:
        lex = LexHints()
        usable_suite = isinstance(suite, str) and bool(suite)
        if usable_suite:
            task["suite"] = encode_value(suite, at="/task/suite", lex=lex)
        task["task_id"] = encode_value(task_id, at="/task/task_id", lex=lex)
        # the suite's locator is where it was read: the container's, else the row's (smoke rows; regen item 117, NF-7)
        suite_src = [] if not usable_suite else [_loc("/suite")] if isinstance(value.get("suite"), str) \
            else [_loc(f"/results/{index}/suite")]
        header.update(ev="O", by="config", evf={"/task/benchmark": cite.cls(R_CHECKER)},
                      rule=[ctx.rule(bench_rule, "/task/benchmark")],
                      src=[*suite_src, _loc(f"/results/{index}/user_task_id")])
    else:  # D-219: a map job that failed before reading the value did not capture it
        header["unk"]["/task/task_id"] = "not_captured" if unit.primary.value is None else "not_recorded"
    ctx.issue(issue_code, ids=["exec"], rule=ctx.rule("agentdojo.tracelogger_record_shape@1"), severity="error",
              detail=detail)
    weaken_to_rule_class(header)
    return header
