"""The CLI's machine outputs the Run live form reads (no Qt): ``agentprov estimate --format json`` (D-701),
``agentprov prices list --format json`` (D-701), ``run --catalogue`` (D-652), ``info --format json`` (live status) and
the checkout's ``endpoints.toml``.

Everything is parsed strictly and bounded (``agentprov.ingest``). Names and ids come from the backend worker or the
price tables through the CLI: they are labels, shown only through ``text.line`` (escaped), never used as paths. The
estimate's numbers and wording are the CLI's; the GUI computes none of them.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Final

from agentprov.errors import IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

__all__ = [
    "Attack",
    "Catalogue",
    "Endpoint",
    "EstimateView",
    "InspectCatalogue",
    "InspectParam",
    "InspectSplit",
    "InspectTask",
    "JudgeRole",
    "PlanError",
    "PriceRow",
    "PriceTable",
    "Quote",
    "QuoteBasis",
    "SuggestedCaps",
    "SuiteEntry",
    "live_status",
    "load_endpoints",
    "parse_any_catalogue",
    "parse_caps",
    "parse_catalogue",
    "parse_estimate",
    "parse_inspect_catalogue",
    "parse_prices",
    "parse_quote",
]

ESTIMATE_FORMAT: Final = "agentprov-estimate/0.1"
PRICES_FORMAT: Final = "agentprov-prices-list/0.1"
CATALOGUE_FORMAT: Final = "agentprov-backend-catalogue/0.1"
_LIMITS: Final = IngestLimits().replace(max_json_bytes=64 * 1024 * 1024, max_json_depth=16)
_NAME: Final = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.:@+-]{0,199}")
_VAR: Final = re.compile(r"[A-Z][A-Z0-9_]{0,63}")
_OPTION: Final = re.compile(r"--[a-z][a-z0-9-]{0,62}")
ENDPOINTS_REL: Final = Path("capture/src/agentprov_capture/endpoints.toml")


class PlanError(ValueError):
    """A CLI document the form cannot use (the message names the problem, never data)."""


def _load(data: bytes) -> dict[str, Any]:
    try:
        doc = strict_json_loads(data.strip(), _LIMITS)
    except IngestError as exc:
        raise PlanError(f"not strict JSON ({exc.code})") from None
    if not isinstance(doc, dict):
        raise PlanError("not a JSON object")
    return doc


def _int(value: Any, what: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise PlanError(f"{what} is not a count")
    return value


def _money(value: Any, what: str) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 40:
        raise PlanError(f"{what} is not a decimal string")
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise PlanError(f"{what} is not a decimal string") from None
    if not number.is_finite() or number < 0:
        raise PlanError(f"{what} is not a non-negative decimal")
    return number


def _float(value: Any, what: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool) or not 0 <= value < 1e15:
        raise PlanError(f"{what} is not a non-negative number")
    return float(value)


def _label(value: Any, limit: int = 300) -> str:
    return value[:limit] if isinstance(value, str) else ""


@dataclass(frozen=True, slots=True)
class PriceRow:
    model: str
    provider: str
    input: Decimal
    output: Decimal
    cached_input: Decimal | None
    cache_write: Decimal | None
    source: str
    as_of: str
    stale: bool
    note: str = ""

    @classmethod
    def from_json(cls, row: Any) -> PriceRow:
        if not isinstance(row, dict) or not isinstance(row.get("model"), str):
            raise PlanError("a malformed price")
        pin, pout = _money(row.get("input"), "input"), _money(row.get("output"), "output")
        if pin is None or pout is None:
            raise PlanError("a price without input or output")
        return cls(row["model"][:200], _label(row.get("provider"), 20), pin, pout,
                   _money(row.get("cached_input"), "cached_input"), _money(row.get("cache_write"), "cache_write"),
                   _label(row.get("source")), _label(row.get("as_of"), 10), row.get("stale") is True,
                   _label(row.get("note")))

    def text(self) -> str:
        cached = f", cached input ${self.cached_input}" if self.cached_input is not None else ""
        return (f"input ${self.input}, output ${self.output}{cached} per million tokens; {self.source}, "
                f"as of {self.as_of}" + (" (more than 60 days old)" if self.stale else ""))


@dataclass(frozen=True, slots=True)
class PriceTable:
    """``prices list``: the priced models per endpoint (for completion and the price line) and the sources."""

    models: Mapping[str, Mapping[str, PriceRow]]
    local: frozenset[str]
    shipped_rows: int
    shipped_as_of: str
    refreshed_rows: int
    refreshed_as_of: str | None
    overrides: Mapping[str, PriceRow]  # "<endpoint>:<model>" → its override

    def lookup(self, endpoint: str, model: str) -> PriceRow | None:
        return self.models.get(endpoint, {}).get(model)


def parse_prices(data: bytes) -> PriceTable:
    doc = _load(data)
    if doc.get("format") != PRICES_FORMAT or not isinstance(doc.get("endpoints"), list):
        raise PlanError("not a prices list")
    models: dict[str, dict[str, PriceRow]] = {}
    local = set()
    for e in doc["endpoints"]:
        if not isinstance(e, dict) or not isinstance(e.get("name"), str) or not re.fullmatch(r"[a-z0-9_-]{1,40}",
                                                                                              e["name"]):
            raise PlanError("a malformed endpoint")
        if e.get("local") is True:
            local.add(e["name"])
        raw_rows = e.get("models")
        rows: list[Any] = raw_rows if isinstance(raw_rows, list) else []
        models[e["name"]] = {str(r.get("id"))[:200]: PriceRow.from_json(r) for r in rows if isinstance(r, dict)}
    raw_shipped, raw_refreshed = doc.get("shipped"), doc.get("refreshed")
    shipped: dict[str, Any] = raw_shipped if isinstance(raw_shipped, dict) else {}
    refreshed: dict[str, Any] = raw_refreshed if isinstance(raw_refreshed, dict) else {}
    overrides = {str(o.get("key"))[:240]: PriceRow.from_json(o) for o in doc.get("overrides") or []
                 if isinstance(o, dict)}
    return PriceTable(models, frozenset(local), _int(shipped.get("rows", 0), "shipped rows"),
                      _label(shipped.get("as_of"), 10), _int(refreshed.get("rows", 0), "refreshed rows"),
                      _label(refreshed.get("as_of"), 10) or None, overrides)


@dataclass(frozen=True, slots=True)
class EstimateView:
    """``agentprov estimate --format json`` as the dialog uses it: the numbers its gates need and the CLI's lines."""

    units: int
    attempts_due: int
    cost_p50: Decimal | None
    cost_p90: Decimal | None
    cost_worst: Decimal | None
    seconds_p50: float
    seconds_p90: float
    price: PriceRow | None
    planned_with: str  # model | stand-in
    plan_sha256: str
    warnings: tuple[str, ...]
    text: tuple[str, ...]
    calls_p50: float | None = None
    calls_p90: float | None = None
    quote: Quote | None = None  # the CLI's ``quote`` object, when this CLI gives one (read defensively)


@dataclass(frozen=True, slots=True)
class QuoteBasis:
    """What the quote's figures rest on, as the CLI states it (``quote.basis``). Every field may be missing (an older
    CLI): ``None`` then, and the dialog says it does not know rather than guessing."""

    priors: str | None = None  # local (the user's sealed corpora) | shipped (the shipped table) | mixed
    family_specific: bool | None = None  # True only when the figures are this model family's own
    family: str | None = None
    executions: int | None = None  # recorded executions behind the per-call figures
    corpora: int | None = None  # the sealed corpora they come from
    token_basis: str | None = None  # e.g. chars/4, usage, mixed
    price_source: str | None = None  # direct | openrouter | override | local
    price_as_of: str | None = None
    discounts_assumed: bool | None = None  # batch or cache discounts
    estimate_only: bool | None = None


@dataclass(frozen=True, slots=True)
class SuggestedCaps:
    """The D-725 caps the CLI suggests for this run (``quote.caps``, D-1090), read defensively. ``available`` is true
    only when both caps and both prices are present; otherwise ``reason`` says why (``None``: an older CLI gave no
    suggestion). The GUI shows these figures and fills the cap fields with them; it computes none."""

    available: bool = False
    reason: str | None = None
    max_calls: int | None = None
    max_cost_usd: Decimal | None = None
    price_in: Decimal | None = None
    price_out: Decimal | None = None
    margin_pct: Decimal | None = None
    margin_from: str | None = None  # setting | default
    reserved_cells: int | None = None
    cell_calls: int | None = None
    cell_usd: Decimal | None = None
    probe_calls: int | None = None
    resumed_units: int | None = None


def parse_caps(raw: Any) -> SuggestedCaps | None:
    """``quote.caps`` (D-1090), or ``None`` when the CLI gave none."""
    if not isinstance(raw, dict):
        return None

    def dec(key: str) -> Decimal | None:
        value: Decimal | None = _opt(_money, _decimal_text(raw.get(key)))
        return value

    calls = _opt(_int, raw.get("max_calls"))
    cost, p_in, p_out = dec("max_cost_usd"), dec("price_in"), dec("price_out")
    complete = calls is not None and calls >= 1 and cost is not None and cost > 0 and p_in is not None \
        and p_out is not None
    available = raw.get("available") is True and complete
    reason = _label(raw.get("reason"), 400) or None
    if raw.get("available") is True and not complete:
        reason = "the CLI's suggestion is incomplete"
    margin_from = _label(raw.get("margin_from"), 20)
    return SuggestedCaps(available=available, reason=None if available else reason or "no reason given",
                         max_calls=calls if available else None, max_cost_usd=cost if available else None,
                         price_in=p_in if available else None, price_out=p_out if available else None,
                         margin_pct=dec("margin_pct"),
                         margin_from=margin_from if margin_from in ("setting", "default") else None,
                         reserved_cells=_opt(_int, raw.get("reserved_cells")),
                         cell_calls=_opt(_int, raw.get("cell_calls")), cell_usd=dec("cell_usd"),
                         probe_calls=_opt(_int, raw.get("probe_calls")),
                         resumed_units=_opt(_int, raw.get("resumed_units")))


@dataclass(frozen=True, slots=True)
class Quote:
    """The USD quote for a real model's run (``agentprov estimate``'s ``quote`` object). A missing figure is ``None``;
    the dialog then falls back to the estimate's own fields or shows a dash."""

    usd_p50: Decimal | None = None
    usd_p90: Decimal | None = None
    calls_p50: float | None = None
    calls_p90: float | None = None
    tokens_in_p50: float | None = None
    tokens_in_p90: float | None = None
    tokens_out_p50: float | None = None
    tokens_out_p90: float | None = None
    seconds_p50: float | None = None
    seconds_p90: float | None = None
    cells: int | None = None
    basis: QuoteBasis = QuoteBasis()
    jobs: int | None = None  # the concurrency the time is given at
    p50_aggregation: str | None = None  # how the run's figures add up ("sum of per-cell medians")
    p90_aggregation: str | None = None  # "upper (sum of per-cell 90th percentiles)": not the run's own 90th percentile
    caps: SuggestedCaps | None = None  # D-1090: the suggested caps (``None``: an older CLI)


def _opt(convert: Any, value: Any) -> Any:
    """``convert(value, "quote")``, or ``None`` when the value is missing or malformed (a defensive read)."""
    if value is None:
        return None
    try:
        return convert(value, "quote")
    except PlanError:
        return None


def _flag(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _count(value: Any) -> int | None:
    """A count, or the length of a list (``corpora`` may be the corpora themselves)."""
    return len(value) if isinstance(value, list) else _opt(_int, value)


def _decimal_text(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, int | float) and not isinstance(value, bool):
        return str(value)
    return None


def parse_quote(raw: Any) -> Quote | None:
    """The ``quote`` object, read defensively: a field that is missing or of the wrong type is ``None``, never an
    error (the estimate itself stays usable)."""
    if not isinstance(raw, dict):
        return None
    b: dict[str, Any] = raw["basis"] if isinstance(raw.get("basis"), dict) else {}
    priors = _label(b.get("priors"), 20)
    basis = QuoteBasis(
        priors=priors if priors in ("local", "shipped", "mixed") else None, family_specific=_flag(b.get("family_specific")),
        family=_label(b.get("family"), 120) or None, executions=_count(b.get("executions")),
        corpora=_count(b.get("corpora")), token_basis=_label(b.get("token_basis"), 40) or None,
        price_source=_label(b.get("price_source"), 200) or None, price_as_of=_label(b.get("price_as_of"), 25) or None,
        discounts_assumed=_flag(b.get("discounts_assumed")), estimate_only=_flag(b.get("estimate_only")))
    return Quote(
        usd_p50=_opt(_money, _decimal_text(raw.get("usd_p50"))), usd_p90=_opt(_money, _decimal_text(raw.get("usd_p90"))),
        calls_p50=_opt(_float, raw.get("calls_p50")), calls_p90=_opt(_float, raw.get("calls_p90")),
        tokens_in_p50=_opt(_float, raw.get("tokens_in_p50")), tokens_in_p90=_opt(_float, raw.get("tokens_in_p90")),
        tokens_out_p50=_opt(_float, raw.get("tokens_out_p50")), tokens_out_p90=_opt(_float, raw.get("tokens_out_p90")),
        seconds_p50=_opt(_float, raw.get("seconds_p50")), seconds_p90=_opt(_float, raw.get("seconds_p90")),
        cells=_count(raw.get("cells")), basis=basis, jobs=_count(raw.get("jobs")),
        p50_aggregation=_label(raw.get("p50_aggregation"), 120) or None,
        p90_aggregation=_label(raw.get("p90_aggregation"), 120) or None, caps=parse_caps(raw.get("caps")))


def parse_estimate(data: bytes) -> EstimateView:
    doc = _load(data)
    if doc.get("format") != ESTIMATE_FORMAT:
        raise PlanError("not an estimate")
    raw_plan = doc.get("plan")
    plan: dict[str, Any] = raw_plan if isinstance(raw_plan, dict) else {}
    lines = doc.get("text")
    warnings = doc.get("warnings")
    if not isinstance(lines, list) or not isinstance(warnings, list) or len(lines) > 10_000:
        raise PlanError("an estimate without its lines")
    price = doc.get("price")
    return EstimateView(
        _int(doc.get("units"), "units"), _int(doc.get("attempts_due"), "attempts_due"),
        _money(doc.get("cost_p50"), "cost_p50"), _money(doc.get("cost_p90"), "cost_p90"),
        _money(doc.get("cost_worst"), "cost_worst"), _float(doc.get("seconds_p50"), "seconds_p50"),
        _float(doc.get("seconds_p90"), "seconds_p90"), None if price is None else PriceRow.from_json(price),
        "stand-in" if doc.get("planned_with") == "stand-in" else "model", _label(plan.get("plan_sha256"), 64),
        tuple(_label(w, 600) for w in warnings), tuple(_label(x, 600) for x in lines),
        _opt(_float, doc.get("calls_p50")), _opt(_float, doc.get("calls_p90")), parse_quote(doc.get("quote")))


@dataclass(frozen=True, slots=True)
class SuiteEntry:
    name: str
    user_tasks: tuple[str, ...]
    injection_tasks: tuple[str, ...]
    tool_definition_chars: int | None


@dataclass(frozen=True, slots=True)
class Attack:
    name: str
    dos: bool
    refused: str | None
    needs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Catalogue:
    backend: str
    benchmark_version: str
    benchmark_versions: tuple[str, ...]
    suites: tuple[SuiteEntry, ...]
    attacks: tuple[Attack, ...]

    def suite(self, name: str) -> SuiteEntry | None:
        return next((s for s in self.suites if s.name == name), None)


def _names(value: Any, what: str) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > 10_000 or not all(isinstance(v, str) and _NAME.fullmatch(v)
                                                                     for v in value):
        raise PlanError(f"malformed {what}")
    return tuple(value)


def parse_catalogue(data: bytes) -> Catalogue:
    doc = _load(data)
    if doc.get("format") != CATALOGUE_FORMAT or not isinstance(doc.get("backend"), str):
        raise PlanError("not a backend catalogue")
    suites = []
    for s in doc.get("suites") or []:
        if not isinstance(s, dict) or not isinstance(s.get("name"), str) or not _NAME.fullmatch(s["name"]):
            raise PlanError("malformed suite")
        chars = s.get("tool_definition_chars")
        suites.append(SuiteEntry(s["name"], _names(s.get("user_tasks"), "user tasks"),
                                 _names(s.get("injection_tasks"), "injection tasks"),
                                 chars if isinstance(chars, int) and not isinstance(chars, bool) and chars >= 0
                                 else None))
    attacks = []
    for a in doc.get("attacks") or []:
        if not isinstance(a, dict) or not isinstance(a.get("name"), str) or not _NAME.fullmatch(a["name"]):
            raise PlanError("malformed attack")
        refused = a.get("refused")
        needs = a.get("needs") or []
        if not isinstance(needs, list) or not all(isinstance(n, str) and _OPTION.fullmatch(n) for n in needs):
            raise PlanError("malformed attack needs")
        attacks.append(Attack(a["name"], a.get("dos") is True, refused[:400] if isinstance(refused, str) else None,
                              tuple(needs)))
    version = doc.get("benchmark_version")
    if not isinstance(version, str) or not _NAME.fullmatch(version):
        raise PlanError("malformed benchmark version")
    return Catalogue(doc["backend"][:40], version, _names(doc.get("benchmark_versions") or [], "versions"),
                     tuple(suites), tuple(attacks))


# ------------------------------------------------------------------------------- Inspect catalogues (D-663, D-1120)
INSPECT_CATALOGUE_FORMAT: Final = "agentprov-inspect-catalogue/0.1"
#: an Inspect task is a registry name (``inspect_evals/agentharm``); parameter, split, solver and role names are labels
#: without ``/`` (the CLI's ``cli/live/inspect_catalogue.py`` patterns, pinned by a test)
_TASK: Final = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.:@+/\-]{0,199}")
_ILABEL: Final = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.:@+\-]{0,99}")
_PARAM_TYPES: Final = frozenset({"str", "int", "bool|null"})
#: the largest whole number a parameter may take (a Qt spin box's range)
MAX_PARAM_INT: Final = 2**31 - 2


@dataclass(frozen=True, slots=True)
class InspectParam:
    """A task parameter the catalogue declares (``--task-param NAME=VALUE``): its type, default, choices and bounds."""

    name: str
    type: str  # str | int | bool|null
    default: str | int | bool | None
    choices: tuple[str | int | bool | None, ...] = ()
    minimum: int | None = None
    maximum: int | None = None


@dataclass(frozen=True, slots=True)
class InspectSplit:
    name: str
    samples: int


@dataclass(frozen=True, slots=True)
class JudgeRole:
    """A judge role of the task's scorer (``--judge ROLE=MODEL``; every role is required, D-667)."""

    role: str
    default_model: str
    calls_per_sample: int | None  # None: "varies"


@dataclass(frozen=True, slots=True)
class InspectTask:
    name: str
    default_solver: str
    solvers: tuple[str, ...]
    params: tuple[InspectParam, ...]
    splits: tuple[InspectSplit, ...]
    judges: tuple[JudgeRole, ...]
    fixed: tuple[tuple[str, int | float], ...]  # set by the task, reported only (max_messages, seed, ...)

    def param(self, name: str) -> InspectParam | None:
        return next((p for p in self.params if p.name == name), None)

    def split(self, name: str) -> InspectSplit | None:
        return next((s for s in self.splits if s.name == name), None)


@dataclass(frozen=True, slots=True)
class InspectCatalogue:
    """``run SOURCE --catalogue`` of an Inspect backend (``agentprov-inspect-catalogue/0.1``)."""

    backend: str
    benchmark: str
    inspect_ai: str
    dataset_repo: str
    dataset_revision: str
    tasks: tuple[InspectTask, ...]

    def task(self, name: str) -> InspectTask | None:
        return next((t for t in self.tasks if t.name == name), None)


def _ilabel(value: Any, what: str, pattern: re.Pattern[str] = _ILABEL) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value) or ".." in value.split("/"):
        raise PlanError(f"malformed {what}")
    return value


def _ilist(value: Any, what: str, limit: int) -> list[Any]:
    if not isinstance(value, list) or len(value) > limit:
        raise PlanError(f"malformed {what}")
    return value


def _icount(value: Any, what: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= MAX_PARAM_INT:
        raise PlanError(f"{what} is not a count")
    return value


def _iscalar(value: Any, kind: str, what: str) -> str | int | bool | None:
    if kind == "str":
        return _ilabel(value, what)
    if kind == "int":
        return _icount(value, what)
    if value is None or isinstance(value, bool):
        return value
    raise PlanError(f"malformed {what}")


def _iparam(p: Any) -> InspectParam:
    if not isinstance(p, dict) or p.get("type") not in _PARAM_TYPES:
        raise PlanError("malformed task parameter")
    kind = str(p["type"])
    choices = tuple(_iscalar(c, kind, "parameter choice") for c in _ilist(p.get("choices", []), "choices", 64))
    if len(set(choices)) != len(choices):
        raise PlanError("duplicate parameter choices")
    lo = _icount(p["minimum"], "minimum") if "minimum" in p else None
    hi = _icount(p["maximum"], "maximum") if "maximum" in p else None
    if kind != "int" and (lo is not None or hi is not None):
        raise PlanError("bounds on a parameter that is not a whole number")
    default = _iscalar(p.get("default"), kind, "parameter default")
    if isinstance(default, int) and not isinstance(default, bool) and not (
            (lo is None or default >= lo) and (hi is None or default <= hi)):
        raise PlanError("a parameter default outside its bounds")
    if lo is not None and hi is not None and lo > hi:
        raise PlanError("parameter bounds the wrong way round")
    return InspectParam(_ilabel(p.get("name"), "parameter name"), kind, default, choices, lo, hi)


def parse_inspect_catalogue(data: bytes) -> InspectCatalogue:
    """The Inspect catalogue, read as strictly as the AgentDojo one: bounded lists, names that are labels (never paths
    or text), counts that are whole numbers; unknown members are dropped. Every name is shown through ``text.line``."""
    doc = _load(data)
    if doc.get("format") != INSPECT_CATALOGUE_FORMAT or not isinstance(doc.get("backend"), str):
        raise PlanError("not an Inspect catalogue")
    raw_dataset = doc.get("dataset")
    dataset: dict[str, Any] = raw_dataset if isinstance(raw_dataset, dict) else {}
    revision = dataset.get("revision")
    tasks: list[InspectTask] = []
    for t in _ilist(doc.get("tasks"), "tasks", 200):
        if not isinstance(t, dict):
            raise PlanError("malformed task")
        params = tuple(_iparam(p) for p in _ilist(t.get("params", []), "task parameters", 64))
        if len({p.name for p in params}) != len(params):
            raise PlanError("duplicate task parameters")
        splits = []
        for s in _ilist(t.get("splits", []), "splits", 64):
            if not isinstance(s, dict):
                raise PlanError("malformed split")
            splits.append(InspectSplit(_ilabel(s.get("name"), "split name"), _icount(s.get("samples"), "samples")))
        judges: dict[str, JudgeRole] = {}
        for scorer in _ilist(t.get("scorers", []), "scorers", 16):
            if not isinstance(scorer, dict):
                raise PlanError("malformed scorer")
            for r in _ilist(scorer.get("judge_roles", []), "judge roles", 16):
                if not isinstance(r, dict) or not isinstance(r.get("role"), str) or not re.fullmatch(
                        r"[a-z][a-z0-9_]{0,63}", r["role"]):  # what --judge ROLE=MODEL takes (cli/run.py _judge)
                    raise PlanError("malformed judge role")
                calls = r.get("calls_per_sample")
                judges.setdefault(r["role"], JudgeRole(
                    r["role"], _ilabel(r.get("default_model"), "judge model", _TASK),
                    None if calls == "varies" else _icount(calls, "judge calls")))
        raw_fixed = t.get("fixed")
        fixed = tuple(sorted((_ilabel(k, "fixed setting"), v) for k, v in (
            raw_fixed.items() if isinstance(raw_fixed, dict) else ())
            if isinstance(v, int | float) and not isinstance(v, bool) and abs(v) < 1e15 and v == v))
        solvers = tuple(_ilabel(v, "solver") for v in _ilist(t.get("solvers", []), "solvers", 64))
        default_solver = t.get("default_solver")
        tasks.append(InspectTask(_ilabel(t.get("name"), "task name", _TASK),
                                 _ilabel(default_solver, "solver") if default_solver is not None else "", solvers,
                                 params, tuple(splits), tuple(judges.values()), fixed[:32]))
    if len({t.name for t in tasks}) != len(tasks):
        raise PlanError("duplicate tasks")
    version = doc.get("inspect_ai")
    return InspectCatalogue(
        doc["backend"][:40], _ilabel(doc.get("benchmark"), "benchmark"),
        version[:64] if isinstance(version, str) and re.fullmatch(r"[0-9][0-9A-Za-z.+\-]{0,63}", version) else "",
        _label(dataset.get("repo"), 200) if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.\-]{0,95}/[A-Za-z0-9][A-Za-z0-9_.\-]{0,95}",
                                                         str(dataset.get("repo"))) else "",
        revision if isinstance(revision, str) and re.fullmatch(r"[0-9a-f]{40}", revision) else "", tuple(tasks))


def parse_any_catalogue(data: bytes) -> Catalogue | InspectCatalogue:
    """``run SOURCE --catalogue``'s document by its ``format``: an AgentDojo-family or an Inspect catalogue."""
    doc = _load(data)
    if doc.get("format") == INSPECT_CATALOGUE_FORMAT:
        return parse_inspect_catalogue(data)
    return parse_catalogue(data)


@dataclass(frozen=True, slots=True)
class Endpoint:
    name: str
    base_url: str
    api_key_env: str | None
    model_env: str | None
    base_url_env: str | None
    local: bool
    api: str = "openai_chat"  # D-656: "anthropic_messages" for a direct Anthropic endpoint

def load_endpoints(checkout: Path | None) -> dict[str, Endpoint]:
    """The checkout's ``endpoints.toml`` (trusted repository data, read bounded; never imported: the GUI does not
    import ``agentprov_capture``). Empty without a checkout."""
    if checkout is None:
        return {}
    path = checkout / ENDPOINTS_REL
    try:
        with open(path, "rb") as fh:
            data = fh.read(256 * 1024 + 1)
        doc = tomllib.loads(data[: 256 * 1024].decode("utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return {}
    out: dict[str, Endpoint] = {}
    table = doc.get("endpoints")
    for name, e in (table.items() if isinstance(table, dict) else []):
        if not isinstance(e, dict) or not re.fullmatch(r"[a-z0-9_-]{1,40}", name):
            continue

        def var(key: str, e: Mapping[str, Any] = e) -> str | None:
            v = e.get(key)
            return v if isinstance(v, str) and _VAR.fullmatch(v) else None

        api = e.get("api")
        out[name] = Endpoint(name, str(e.get("base_url", ""))[:300], var("api_key_env"), var("model_env"),
                             var("base_url_env"), e.get("local") is True,
                             api if isinstance(api, str) and re.fullmatch(r"[a-z_]{1,40}", api) else "openai_chat")
    return out


def live_status(info: bytes, source: str) -> tuple[str | None, str | None]:
    """``(live status, backend)`` of ``source``'s live part from ``agentprov info SOURCE --format json``."""
    try:
        doc = _load(info)
    except PlanError:
        return None, None
    parts = doc.get("parts") if doc.get("source_id") == source else None
    for part in parts if isinstance(parts, list) else []:
        if isinstance(part, dict) and isinstance(part.get("live"), str):
            backend = part.get("backend")
            return part["live"][:40], backend[:40] if isinstance(backend, str) else None
    return None, None


def unknown_names(chosen: Sequence[str], offered: Sequence[str]) -> list[str]:
    known = set(offered)
    return [c for c in chosen if c not in known]
