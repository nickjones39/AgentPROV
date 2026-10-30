"""T0's check of an Inspect worker's ``catalogue_ok.catalogue`` (``agentprov-inspect-catalogue/0.1``; D-663, D-652 peer).

The worker is T2: its reply is untrusted output. :func:`checked_inspect_catalogue` rebuilds the document from its
checked members only, with the rules of the AgentDojo-shaped ``checked_catalogue`` (D-652, ``cli/run.py`` on the GUI
branch): bounded lists, names that are labels (never paths or text), counts that are non-negative integers, unknown
members dropped, nothing passed through. ``run --catalogue`` dispatches on ``format`` to this function or the AgentDojo
one (wired when D-652 is on the base; orchestrator ruling (c), 2026-10-22).
"""

from __future__ import annotations

import math
import re
from typing import Any, Final

from agentprov.errors import AgentProvError

__all__ = ["INSPECT_CATALOGUE_FORMAT", "checked_inspect_catalogue"]

INSPECT_CATALOGUE_FORMAT: Final = "agentprov-inspect-catalogue/0.1"
_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.:@+/\-]{0,199}")  # task names are registry names ("inspect_evals/agentharm")
_LABEL = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.:@+\-]{0,99}")  # parameter, split, solver, scorer and role names; no "/"
_HF_REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-]{0,95}/[A-Za-z0-9][A-Za-z0-9_.\-]{0,95}")
_VERSION = re.compile(r"[0-9][0-9A-Za-z.+\-]{0,63}")
_TYPES: Final = frozenset({"str", "int", "bool|null"})
MAX_ITEMS: Final = 1000
MAX_COUNT: Final = 2**31


class CatalogueError(AgentProvError):
    """A malformed worker catalogue (exit 3, as a backend protocol fault)."""

    code = "backend.protocol"
    exit_code = 3


def _bad(what: str) -> CatalogueError:
    return CatalogueError(f"the backend worker sent a malformed Inspect catalogue ({what})")


def _list(value: Any, what: str, limit: int = MAX_ITEMS) -> list[Any]:
    if not isinstance(value, list) or len(value) > limit:
        raise _bad(what)
    return value


def _name(value: Any, what: str, pattern: re.Pattern[str] = _LABEL) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value) or ".." in value.split("/"):
        raise _bad(what)
    return value


def _count(value: Any, what: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value < MAX_COUNT:
        raise _bad(what)
    return value


def _scalar(value: Any, kind: str, what: str) -> Any:
    """A parameter default or choice of the declared type (a bounded label for strings)."""
    if kind == "str":
        return _name(value, what)
    if kind == "int":
        return _count(value, what)
    if value is None or isinstance(value, bool):
        return value
    raise _bad(what)


def _param(p: Any) -> dict[str, Any]:
    if not isinstance(p, dict):
        raise _bad("param")
    kind = p.get("type")
    if kind not in _TYPES:
        raise _bad("param.type")
    out: dict[str, Any] = {"name": _name(p.get("name"), "param.name"), "type": kind,
                           "default": _scalar(p.get("default"), kind, "param.default")}
    if "choices" in p:
        out["choices"] = [_scalar(c, kind, "param.choices") for c in _list(p["choices"], "param.choices", 64)]
    for bound in ("minimum", "maximum"):
        if bound in p:
            out[bound] = _count(p[bound], f"param.{bound}")
    if "maps_to" in p:
        out["maps_to"] = _name(p["maps_to"], "param.maps_to")
    return out


def _scorer(s: Any) -> dict[str, Any]:
    if not isinstance(s, dict):
        raise _bad("scorer")
    roles = []
    for r in _list(s.get("judge_roles"), "scorer.judge_roles", 16):
        if not isinstance(r, dict):
            raise _bad("judge_role")
        calls = r.get("calls_per_sample")
        if calls != "varies":
            calls = _count(calls, "judge_role.calls_per_sample")
        roles.append({"role": _name(r.get("role"), "judge_role.role"),
                      "default_model": _name(r.get("default_model"), "judge_role.default_model", _NAME),
                      "calls_per_sample": calls})
    return {"name": _name(s.get("name"), "scorer.name"), "judge_roles": roles}


def _split(s: Any) -> dict[str, Any]:
    if not isinstance(s, dict):
        raise _bad("split")
    chars = s.get("tool_definition_chars")
    if not isinstance(chars, dict):
        raise _bad("split.tool_definition_chars")
    return {"name": _name(s.get("name"), "split.name"), "samples": _count(s.get("samples"), "split.samples"),
            "tool_definition_chars": {"mean": _count(chars.get("mean"), "tool_definition_chars.mean"),
                                      "max": _count(chars.get("max"), "tool_definition_chars.max")}}


def checked_inspect_catalogue(document: Any, backend: str) -> dict[str, Any]:
    """The worker's catalogue, rebuilt from its checked members only (raises :class:`CatalogueError`)."""
    if not isinstance(document, dict) or document.get("format") != INSPECT_CATALOGUE_FORMAT:
        raise _bad("format")
    if document.get("backend") != backend:
        raise _bad("backend")
    dataset = document.get("dataset")
    if not isinstance(dataset, dict) or not isinstance(dataset.get("repo"), str) or not _HF_REPO.fullmatch(dataset["repo"]) \
            or not isinstance(dataset.get("revision"), str) or not re.fullmatch(r"[0-9a-f]{40}", dataset["revision"]):
        raise _bad("dataset")
    version = document.get("inspect_ai")
    if not isinstance(version, str) or not _VERSION.fullmatch(version):
        raise _bad("inspect_ai")
    tasks = []
    for t in _list(document.get("tasks"), "tasks", 200):
        if not isinstance(t, dict):
            raise _bad("task")
        raw_fixed = t.get("fixed")
        fixed: dict[Any, Any] = raw_fixed if isinstance(raw_fixed, dict) else {}
        tasks.append({
            "name": _name(t.get("name"), "task.name", _NAME),
            "splits": [_split(s) for s in _list(t.get("splits"), "task.splits", 64)],
            "params": [_param(p) for p in _list(t.get("params"), "task.params", 64)],
            "solvers": [_name(v, "task.solvers") for v in _list(t.get("solvers"), "task.solvers", 64)],
            "default_solver": _name(t.get("default_solver"), "task.default_solver"),
            "fixed": {_name(k, "task.fixed"): v for k, v in fixed.items()
                      if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)},
            "scorers": [_scorer(s) for s in _list(t.get("scorers"), "task.scorers", 16)],
        })
    return {"format": INSPECT_CATALOGUE_FORMAT, "backend": backend, "benchmark": _name(document.get("benchmark"), "benchmark"),
            "inspect_ai": version, "dataset": {"repo": dataset["repo"], "revision": dataset["revision"]}, "tasks": tasks}
