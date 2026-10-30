"""Run plans of an Inspect backend (``agentprov-run-plan/0.1`` with an ``[inspect]`` table; D-663, D-667).

::

    [plan]
    format = "agentprov-run-plan/0.1"           # inside [plan], as every run plan (D.10.1)
    backend = "inspect-agentharm"
    [inspect]
    task = "inspect_evals/agentharm"
    params = { split = "test_public", agent = "default" }   # only declared parameters, checked by type and choices
    samples = { ids = ["1-1", "2-3"] }                      # or { limit = 4 }: an explicit count is mandatory
    epochs = 1
    limits = { message_limit = 20, token_limit = 60000, time_limit_s = 600 }   # all three mandatory (D-667)
    max_connections = 4
    cell_size = 25
    [agent]                      # T0's agent: model_requested, endpoint, transport ("http" | "scripted"), base_url,
                                 # api_key_env, script, provider, params, llm_element, allow_lan (D-698)
    [judges.refusal_judge]       # one table per judge role the task's scorer declares (D-667): no silent default;
    [judges.semantic_judge]      # the same shape as [agent]

``plan_ok.plan`` carries ``backend_config`` (:meth:`InspectPlan.backend_config`): everything a ``run_cell`` needs
besides the cell and the agent, which the campaign sends with it (``agentprov.cli.live.campaign``). The worker checks a
``run_cell`` with :func:`run_spec` (the cell key is re-derived from the cell's content).

A plan expands to cells of at most ``cell_size`` samples, in plan order: each cell is one Inspect ``eval()`` (its
samples run concurrently up to ``max_connections``), one staged session and one ``.eval`` log. A ``limit`` selects
the first ``limit`` ids of the split in dataset order. Unknown keys anywhere are refused.
"""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any

import rfc8785

__all__ = ["PLAN_FORMAT", "InspectCell", "InspectPlan", "ModelSpec", "PlanError", "load_plan", "model_spec"]

PLAN_FORMAT = "agentprov-run-plan/0.1"
_ID = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.:\-]{0,127}")
_MODEL = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.:/@+\-]{0,199}")
#: The members of T0's agent table (``agentprov.cli.run._real_agent`` and ``_scripted_agent``).
_AGENT_KEYS = frozenset({"model", "model_requested", "endpoint", "transport", "base_url", "api_key_env", "script",
                         "provider", "params", "llm_element", "allow_lan"})
_ENDPOINT = re.compile(r"[a-z][a-z0-9_\-]{0,63}")
_ENV = re.compile(r"[A-Z][A-Z0-9_]{0,127}")
MAX_SAMPLES = 10_000
MAX_LIMITS = {"message_limit": 500, "token_limit": 10_000_000, "time_limit_s": 86_400}


class PlanError(ValueError):
    """A plan this backend refuses."""


def _require(cond: bool, message: str) -> None:
    if not cond:
        raise PlanError(message)


def _closed(table: Any, what: str, allowed: set[str], required: set[str] = frozenset()) -> Mapping[str, Any]:
    _require(isinstance(table, Mapping), f"{what} must be a table")
    unknown = sorted(set(table) - allowed)
    _require(not unknown, f"{what}: unknown key(s) {', '.join(unknown)}")
    missing = sorted(required - set(table))
    _require(not missing, f"{what}: missing key(s) {', '.join(missing)}")
    return table


@dataclass(frozen=True)
class ModelSpec:
    """A model the run calls (the agent or a judge role): no secret, the key variable's name only."""

    model: str
    endpoint: str
    transport: str
    base_url: str | None = None
    api_key_env: str | None = None
    script: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {"model": self.model, "endpoint": self.endpoint, "transport": self.transport,
                "base_url": self.base_url, "api_key_env": self.api_key_env, "script": self.script}


def model_spec(table: Any, what: str) -> ModelSpec:
    """A :class:`ModelSpec` from a T0 agent table (``run_cell``'s or ``probe``'s ``agent``), checked as in a plan."""
    return _model(table, what)


def _model(table: Any, what: str) -> ModelSpec:
    t = dict(_closed(table, what, set(_AGENT_KEYS), {"endpoint", "transport"}))
    _require(("model" in t) != ("model_requested" in t), f"{what} names its model as model_requested")
    t["model"] = t.pop("model_requested", t.get("model"))
    _require(isinstance(t["model"], str) and bool(_MODEL.fullmatch(t["model"])), f"{what}.model is not a model id")
    _require(isinstance(t["endpoint"], str) and bool(_ENDPOINT.fullmatch(t["endpoint"])), f"{what}.endpoint is invalid")
    _require(t["transport"] in ("http", "scripted"), f"{what}.transport must be http or scripted")
    if t["transport"] == "http":
        _require(isinstance(t.get("base_url"), str) and t["base_url"].startswith(("https://", "http://")),
                 f"{what}.base_url is required for http")
        key = t.get("api_key_env")
        _require(key is None or (isinstance(key, str) and bool(_ENV.fullmatch(key))),
                 f"{what}.api_key_env must name a variable")
        _require(key is not None or t.get("allow_lan") is True, f"{what}: a keyless endpoint must be a LAN endpoint")
        _require(t.get("script") is None, f"{what}.script is for scripted transport only")
    else:
        _require(isinstance(t.get("script"), str) and bool(_ID.fullmatch(t["script"])),
                 f"{what}.script must name the staged script file")
    return ModelSpec(model=t["model"], endpoint=t["endpoint"], transport=t["transport"], base_url=t.get("base_url"),
                     api_key_env=t.get("api_key_env"), script=t.get("script"))


def model_json(spec: ModelSpec) -> dict[str, Any]:
    """A :class:`ModelSpec` in T0's agent-table shape (for ``backend_config.judges``)."""
    out = {"model_requested": spec.model, "endpoint": spec.endpoint, "transport": spec.transport}
    for key in ("base_url", "api_key_env", "script"):
        if getattr(spec, key) is not None:
            out[key] = getattr(spec, key)
    return out


@dataclass(frozen=True)
class InspectCell:
    cell_key: str
    task: str
    params: dict[str, Any]
    sample_ids: tuple[str, ...]

    def to_json(self) -> dict[str, Any]:
        return {"cell_key": self.cell_key, "task": self.task, "params": dict(self.params),
                "sample_ids": list(self.sample_ids)}


@dataclass(frozen=True)
class InspectPlan:
    backend: str
    task: str
    params: dict[str, Any]
    epochs: int
    limits: dict[str, int]
    max_connections: int
    agent: ModelSpec
    judges: dict[str, ModelSpec]
    cells: tuple[InspectCell, ...]
    plan_sha256: str = field(default="")

    def backend_config(self) -> dict[str, Any]:
        """What every ``run_cell`` of this plan carries (``plan_ok.plan.backend_config``; D.10.10 item 19)."""
        return {"task": self.task, "params": dict(self.params), "epochs": self.epochs, "limits": dict(self.limits),
                "max_connections": self.max_connections,
                "judges": {k: model_json(v) for k, v in sorted(self.judges.items())}}

    def to_json(self) -> dict[str, Any]:
        return {"format": PLAN_FORMAT, "backend": self.backend, "plan_sha256": self.plan_sha256,
                "backend_config": self.backend_config(), "task": self.task,
                "params": dict(self.params), "epochs": self.epochs, "limits": dict(self.limits),
                "max_connections": self.max_connections, "agent": self.agent.to_json(),
                "judges": {k: v.to_json() for k, v in sorted(self.judges.items())},
                "cells": [c.to_json() for c in self.cells]}


def _check_param(spec: Mapping[str, Any], value: Any) -> Any:
    name, kind = spec["name"], spec["type"]
    if kind == "str":
        _require(isinstance(value, str), f"parameter {name} must be a string")
    elif kind == "int":
        _require(isinstance(value, int) and not isinstance(value, bool), f"parameter {name} must be an integer")
        _require(spec.get("minimum", value) <= value <= spec.get("maximum", value), f"parameter {name} out of range")
    elif kind == "bool|null":
        _require(value is None or isinstance(value, bool), f"parameter {name} must be true, false or absent")
    else:  # pragma: no cover - descriptor error
        raise PlanError(f"parameter {name} has an unknown type")
    if "choices" in spec:
        _require(value in spec["choices"], f"parameter {name} must be one of {', '.join(map(str, spec['choices']))}")
    return value


def load_plan(text: str, bench: ModuleType, backend_id: str, split_ids: Mapping[str, Sequence[str]]) -> InspectPlan:
    """Parse and check a plan; ``split_ids`` maps ``"<task>/<split>"`` to the split's sample ids in dataset order."""
    try:
        doc = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise PlanError(f"the plan is not TOML ({exc})") from None
    return _load_document(doc, bench, backend_id, split_ids)


def _load_document(doc: Any, bench: ModuleType, backend_id: str, split_ids: Mapping[str, Sequence[str]]) -> InspectPlan:
    _closed(doc, "plan file", {"plan", "inspect", "agent", "judges"}, {"plan", "inspect", "agent"})
    plan = _closed(doc["plan"], "[plan]", {"format", "backend"}, {"format", "backend"})
    _require(plan["format"] == PLAN_FORMAT, f"the plan format must be {PLAN_FORMAT}")
    _require(plan["backend"] == backend_id, f"the plan is for backend {plan['backend']!r}, not {backend_id!r}")
    ins = _closed(doc["inspect"], "[inspect]",
                  {"task", "params", "samples", "epochs", "limits", "max_connections", "cell_size"},
                  {"task", "samples", "limits"})
    task = ins["task"]
    _require(task in bench.TASKS, f"unknown task {task!r} (the catalogue lists the tasks)")
    declared = {p["name"]: p for p in bench.PARAMS}
    raw_params = ins.get("params", {})
    _closed(raw_params, "[inspect].params", set(declared))
    params = {name: _check_param(declared[name], value) for name, value in sorted(raw_params.items())}
    split = params.get("split", declared["split"]["default"])
    _require(split in bench.TASKS[task]["splits"], f"task {task} has no split {split!r}")
    ids = list(split_ids.get(f"{task}/{split}", ()))
    samples = _closed(ins["samples"], "[inspect].samples", {"ids", "limit"})
    _require(len(samples) == 1, "[inspect].samples takes exactly one of ids or limit")
    if "ids" in samples:
        chosen = samples["ids"]
        _require(isinstance(chosen, list) and 0 < len(chosen) <= MAX_SAMPLES, "samples.ids must be a non-empty list")
        _require(all(isinstance(i, str) and _ID.fullmatch(i) for i in chosen), "samples.ids must be sample ids")
        _require(len(set(chosen)) == len(chosen), "samples.ids has duplicates")
        unknown = [i for i in chosen if i not in set(ids)]
        _require(not unknown, f"{len(unknown)} sample id(s) are not in {task} split {split}")
    else:
        limit = samples["limit"]
        _require(isinstance(limit, int) and not isinstance(limit, bool) and 0 < limit <= len(ids),
                 f"samples.limit must be in 1-{len(ids)}")
        chosen = ids[:limit]
    epochs = ins.get("epochs", 1)
    _require(isinstance(epochs, int) and not isinstance(epochs, bool) and 1 <= epochs <= 10, "epochs must be in 1-10")
    limits = _closed(ins["limits"], "[inspect].limits", set(MAX_LIMITS), set(MAX_LIMITS))
    for name, bound in MAX_LIMITS.items():
        value = limits[name]
        _require(isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= bound,
                 f"limits.{name} must be in 1-{bound}")
    max_connections = ins.get("max_connections", 4)
    _require(isinstance(max_connections, int) and not isinstance(max_connections, bool) and 1 <= max_connections <= 64,
             "max_connections must be in 1-64")
    cell_size = ins.get("cell_size", 25)
    _require(isinstance(cell_size, int) and not isinstance(cell_size, bool) and 1 <= cell_size <= 500,
             "cell_size must be in 1-500")
    agent = _model(doc["agent"], "[agent]")
    roles = [r["role"] for s in bench.SCORERS for r in s["judge_roles"]]
    judges_raw = doc.get("judges", {})
    _closed(judges_raw, "[judges]", set(roles), set(roles))
    judges = {role: _model(judges_raw[role], f"[judges.{role}]") for role in roles}
    transports = {agent.transport} | {j.transport for j in judges.values()}
    _require(len(transports) == 1, "the agent and every judge use the same transport (scripted and real never mix)")
    cells = []
    for start in range(0, len(chosen), cell_size):
        chunk = tuple(chosen[start:start + cell_size])
        key = _cell_key(task, params, chunk)
        cells.append(InspectCell(cell_key=key, task=task, params=params, sample_ids=chunk))
    out = InspectPlan(backend=backend_id, task=task, params=params, epochs=epochs, limits=dict(limits),
                      max_connections=max_connections, agent=agent, judges=judges, cells=tuple(cells))
    digest = hashlib.sha256(rfc8785.dumps({k: v for k, v in out.to_json().items()
                                                       if k != "plan_sha256"})).hexdigest()
    return InspectPlan(**{**out.__dict__, "plan_sha256": digest})


def _cell_key(task: str, params: Mapping[str, Any], samples: Sequence[str]) -> str:
    return hashlib.sha256(rfc8785.dumps({"task": task, "params": dict(params), "samples": list(samples)})).hexdigest()[:16]


def run_spec(bench: ModuleType, backend_id: str, backend_config: Any, agent: Any, cell: Any,
             split_ids: Mapping[str, Sequence[str]]) -> tuple[InspectPlan, InspectCell]:
    """Check a ``run_cell`` of the campaign: ``backend_config`` (as :meth:`InspectPlan.backend_config` made it), T0's
    agent table and one cell. The cell key is re-derived from the cell's task, parameters and samples; the samples must
    be ids of the cell's split. Raises :class:`PlanError`."""
    cfg = _closed(backend_config, "backend_config", {"task", "params", "epochs", "limits", "max_connections", "judges"},
                  {"task", "params", "epochs", "limits", "max_connections", "judges"})
    c = _closed(cell, "cell", {"cell_key", "task", "params", "sample_ids"}, {"cell_key", "task", "params", "sample_ids"})
    _require(c["task"] == cfg["task"] and c["params"] == cfg["params"], "the cell is not of this plan")
    toml_doc = {"plan": {"format": PLAN_FORMAT, "backend": backend_id},
                "inspect": {"task": cfg["task"], "params": cfg["params"], "samples": {"ids": list(c["sample_ids"])},
                            "epochs": cfg["epochs"], "limits": cfg["limits"], "max_connections": cfg["max_connections"],
                            "cell_size": max(1, len(c["sample_ids"]))},
                "agent": agent, "judges": cfg["judges"]}
    plan = _load_document(toml_doc, bench, backend_id, split_ids)
    (only,) = plan.cells
    _require(only.cell_key == c["cell_key"] == _cell_key(c["task"], c["params"], c["sample_ids"]),
             "the cell key does not match the cell's content")
    return plan, only


def split_ids_from_dataset(bench: ModuleType, root: Any) -> dict[str, list[str]]:
    """``{"<task>/<split>": [sample ids in dataset order]}`` from the provisioned dataset (ids only)."""
    out: dict[str, list[str]] = {}
    for task, spec in bench.TASKS.items():
        for split, rel in spec["splits"].items():
            behaviours = json.loads((root / rel).read_bytes())["behaviors"]
            out[f"{task}/{split}"] = [str(b["id"]) for b in behaviours]
    return out
