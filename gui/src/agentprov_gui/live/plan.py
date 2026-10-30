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
    "PlanError",
    "PriceRow",
    "PriceTable",
    "SuiteEntry",
    "live_status",
    "load_endpoints",
    "parse_catalogue",
    "parse_estimate",
    "parse_prices",
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
        tuple(_label(w, 600) for w in warnings), tuple(_label(x, 600) for x in lines))


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
