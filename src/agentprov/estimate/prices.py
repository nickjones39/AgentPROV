"""Model prices for the live-run estimate (design §8.3 as amended by D-650; moved into the core by D-701). No network
here except :func:`fetch_openrouter`, which goes through the core's fetch transport (``agentprov.raw.fetch``) and runs
only for ``agentprov prices refresh --allow-network``.

Three sources, in this order of precedence for one ``(endpoint, model id)``:

1. a **per-model override** (``agentprov prices set``; ``$AGENTPROV_HOME/prices/overrides.json``, with the date
   entered);
2. the newest **refreshed OpenRouter snapshot** ``$AGENTPROV_HOME/prices/openrouter-<date>.json`` (written by a
   confirmed ``agentprov prices refresh``; never automatic), for the endpoints that route through OpenRouter, and for an
   OpenAI or DeepSeek model the shipped direct table does not list;
3. the **shipped table** ``data/prices.json`` (built by ``tools/estimate/build_price_table.py`` from a dated OpenRouter
   snapshot and the direct-provider rows in ``tools/estimate/price_direct.toml``).

Every price carries its source and its "as of" date; :func:`stale` is true past :data:`STALE_DAYS`. Local endpoints
(``endpoints.toml`` ``local = true``: ollama, omlx) cost nothing per token.

**The OpenRouter response is untrusted.** :func:`parse_openrouter` reads it only through ``agentprov.ingest`` (bounded,
strict JSON), keeps a model only when its id matches :data:`MODEL_ID` and every price is a finite, non-negative decimal
below :data:`MAX_PER_M`, and keeps no text (no names, no descriptions). The raw response is never stored; the snapshot
records its sha256.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Final

from agentprov.errors import AgentProvError, IngestError
from agentprov.ingest.limits import IngestLimits
from agentprov.ingest.loaders import strict_json_loads

__all__ = [
    "MODEL_ID",
    "OPENROUTER_URL",
    "OVERRIDES_FORMAT",
    "PRICES_FORMAT",
    "STALE_DAYS",
    "Price",
    "PriceBook",
    "PriceError",
    "fetch_openrouter",
    "import_response",
    "load_overrides",
    "load_table",
    "parse_openrouter",
    "prices_dir",
    "set_override",
    "stale",
    "unset_override",
    "write_snapshot",
]

PRICES_FORMAT: Final = "agentprov-prices/0.1"
OVERRIDES_FORMAT: Final = "agentprov-price-overrides/0.1"
OPENROUTER_URL: Final = "https://openrouter.ai/api/v1/models"
OPENROUTER_HOST: Final = "openrouter.ai"
#: D-650: a price older than this many days is shown with a warning on every estimate.
STALE_DAYS: Final = 60
#: An OpenRouter or provider model id (a label, never a path): ``vendor/model[:variant]`` or a bare id.
MODEL_ID: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.@+-]{0,99}(/[A-Za-z0-9][A-Za-z0-9_.@+-]{0,99})?(:[a-z0-9-]{1,30})?")
ENDPOINT: Final = re.compile(r"[a-z0-9_-]{1,40}")
#: USD per million tokens above this is refused as implausible (the dearest listed model is well below it).
MAX_PER_M: Final = Decimal(10_000)
MAX_RESPONSE_BYTES: Final = 16 * 1024 * 1024
MAX_MODELS: Final = 20_000
MAX_OVERRIDES: Final = 1000
FETCH_TIMEOUT_S: Final = 60.0
SHIPPED: Final = Path(__file__).resolve().parent / "data" / "prices.json"
#: The endpoints that route through OpenRouter (endpoints.toml: one OpenRouter key and base URL serve them).
OPENROUTER_ENDPOINTS: Final = ("openrouter", "gemini", "llama", "qwen", "glm")
#: Direct-provider endpoints and the OpenRouter vendor prefix their ids fall back to.
DIRECT_VENDOR: Final[Mapping[str, str | None]] = {"openai": "openai", "deepseek": "deepseek", "anthropic": None}
#: (``None``: no OpenRouter fallback; OpenRouter spells Anthropic ids differently, ``anthropic/claude-opus-5.5`` for the
#: API's ``claude-opus-5-5``, so a fallback would offer ids the provider's own API refuses.)
#: A dated snapshot id of a provider whose prices are per model, not per snapshot (Anthropic:
#: ``claude-haiku-4-5-20251001`` is the model ``claude-haiku-4-5``): the date suffix the alias lookup strips.
SNAPSHOT_SUFFIX: Final = re.compile(r"-20\d{6}$")
#: The direct providers whose dated ids are priced by their alias (D-701 follow-up, 2026-10-22).
ALIAS_PRICED: Final = frozenset({"anthropic"})
_PER_M: Final = Decimal(1_000_000)
_LIMITS: Final = IngestLimits().replace(max_json_bytes=MAX_RESPONSE_BYTES, max_json_depth=32)


class PriceError(AgentProvError):
    """A price document or value that cannot be used (the message names the problem, never data). Exit 1; the CLI
    reports a refused value as a usage error (exit 2)."""

    code = "prices.invalid"
    exit_code = 1


@dataclass(frozen=True, slots=True)
class Price:
    """USD per million tokens. ``cached_input`` is ``None`` where the provider does not price cached input."""

    provider: str  # openrouter | openai | deepseek | anthropic | override | local
    model: str
    input: Decimal
    output: Decimal
    cached_input: Decimal | None
    source: str
    as_of: dt.date
    note: str = ""
    cache_write: Decimal | None = None  # 5-minute cache writes, where the provider prices them (Anthropic)

    def to_json(self) -> dict[str, Any]:
        out = {"provider": self.provider, "model": self.model, "input": plain(self.input),
               "output": plain(self.output),
               "cached_input": None if self.cached_input is None else plain(self.cached_input), "source": self.source,
               "as_of": self.as_of.isoformat(), "note": self.note}
        if self.cache_write is not None:
            out["cache_write"] = plain(self.cache_write)
        return out


def plain(value: Decimal) -> str:
    """A decimal in plain notation (``10``, not ``1E+1``)."""
    text = format(value.normalize(), "f")
    return text if text != "-0" else "0"


def stale(price: Price, today: dt.date | None = None) -> bool:
    return ((today or dt.date.today()) - price.as_of).days > STALE_DAYS


def _decimal(value: Any, *, per_token: bool) -> Decimal | None:
    """A price string as USD per million tokens; ``None`` when it is missing, malformed, negative or implausible."""
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        return None
    text = str(value)
    if len(text) > 40:
        return None
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    if not number.is_finite() or number < 0:
        return None
    per_m = (number * _PER_M).normalize() if per_token else number.normalize()
    if per_m > MAX_PER_M:
        return None
    return per_m if per_m != 0 else Decimal(0)


def parse_openrouter(data: bytes, *, fetched: dt.date, source: str = OPENROUTER_URL) -> list[Price]:
    """The text models of an OpenRouter ``/api/v1/models`` response (``pricing.prompt``, ``pricing.completion`` and
    ``pricing.input_cache_read``, USD per token, as decimal strings). Batch variants (``:batch``) are left out: a live
    run is not a batch job. A model with a malformed id or price is skipped, never repaired."""
    if len(data) > MAX_RESPONSE_BYTES:
        raise PriceError("the response is larger than 16 MiB")
    try:
        doc = strict_json_loads(data, _LIMITS)
    except IngestError as exc:
        raise PriceError(f"the response is not strict JSON ({exc.code})") from None
    models = doc.get("data") if isinstance(doc, dict) else None
    if not isinstance(models, list) or len(models) > MAX_MODELS:
        raise PriceError("the response has no model list")
    out: dict[str, Price] = {}
    for m in models:
        if not isinstance(m, dict) or not isinstance(m.get("id"), str) or not MODEL_ID.fullmatch(m["id"]):
            continue
        if m["id"].endswith(":batch"):
            continue
        arch = m.get("architecture")
        outputs = arch.get("output_modalities") if isinstance(arch, dict) else None
        if isinstance(outputs, list) and "text" not in outputs:
            continue
        pricing = m.get("pricing")
        if not isinstance(pricing, dict):
            continue
        pin, pout = _decimal(pricing.get("prompt"), per_token=True), _decimal(pricing.get("completion"), per_token=True)
        if pin is None or pout is None:
            continue
        cache = pricing.get("input_cache_read")
        cached = None if cache is None else _decimal(cache, per_token=True)
        if cache is not None and cached is None:
            continue
        out[m["id"]] = Price("openrouter", m["id"], pin, pout, cached, source, fetched)
    return [out[k] for k in sorted(out)]


def _price_from_json(row: Any, fallback_source: str) -> Price | None:
    if not isinstance(row, dict):
        return None
    model, provider = row.get("model"), row.get("provider")
    if not isinstance(model, str) or not MODEL_ID.fullmatch(model) or provider not in (
            "openrouter", "openai", "deepseek", "anthropic", "override"):
        return None
    pin, pout = _decimal(row.get("input"), per_token=False), _decimal(row.get("output"), per_token=False)
    cache = row.get("cached_input")
    cached = None if cache is None else _decimal(cache, per_token=False)
    try:
        as_of = dt.date.fromisoformat(str(row.get("as_of")))
    except ValueError:
        return None
    if pin is None or pout is None or (cache is not None and cached is None):
        return None
    source = row.get("source") if isinstance(row.get("source"), str) else fallback_source
    note = row.get("note") if isinstance(row.get("note"), str) else ""
    write_raw = row.get("cache_write")
    write = None if write_raw is None else _decimal(write_raw, per_token=False)
    if write_raw is not None and write is None:
        return None
    return Price(str(provider), model, pin, pout, cached, str(source)[:300], as_of, str(note)[:300], write)


def load_table(path: Path) -> tuple[dict[str, Any], list[Price]]:
    """A price document (the shipped table or a refreshed snapshot): its header and its usable rows."""
    try:
        with open(path, "rb") as fh:
            data = fh.read(MAX_RESPONSE_BYTES + 1)
    except OSError:
        return {}, []
    if len(data) > MAX_RESPONSE_BYTES:
        return {}, []
    try:
        doc = strict_json_loads(data.rstrip(b"\n"), _LIMITS)
    except IngestError:
        return {}, []
    if not isinstance(doc, dict) or doc.get("format") != PRICES_FORMAT or not isinstance(doc.get("rows"), list):
        return {}, []
    source = str(doc.get("source", ""))[:300]
    rows = [p for p in (_price_from_json(r, source) for r in doc["rows"]) if p is not None]
    return {k: v for k, v in doc.items() if k != "rows"}, rows


def prices_dir(home: Path) -> Path:
    """``$AGENTPROV_HOME/prices``: refreshed snapshots and the overrides file."""
    return Path(home) / "prices"


def _dump(doc: Mapping[str, Any]) -> bytes:
    return json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"


def write_snapshot(directory: Path, rows: Sequence[Price], *, fetched: dt.date, raw_sha256: str) -> Path:
    """A refreshed OpenRouter snapshot ``openrouter-<date>.json`` (atomic; the raw response is not kept)."""
    from agentprov.io.atomic import atomic_write_bytes

    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"openrouter-{fetched.isoformat()}.json"
    doc = {"format": PRICES_FORMAT, "source": OPENROUTER_URL, "as_of": fetched.isoformat(),
           "raw_sha256": raw_sha256, "rows": [r.to_json() for r in rows]}
    atomic_write_bytes(path, _dump(doc))
    return path


def import_response(home: Path, data: bytes, *, fetched: dt.date) -> tuple[Path, int]:
    """Parse an OpenRouter response (strictly) into ``prices/openrouter-<date>.json``: the path and the row count."""
    rows = parse_openrouter(data, fetched=fetched)
    if not rows:
        raise PriceError("the response holds no usable prices")
    return write_snapshot(prices_dir(home), rows, fetched=fetched, raw_sha256=hashlib.sha256(data).hexdigest()), \
        len(rows)


def fetch_openrouter(transport: Any = None, *, url: str = OPENROUTER_URL,
                     opener: Callable[..., Any] | None = None) -> bytes:
    """GET OpenRouter's public model list (no key, no cookie): https only, redirects only to the same host, HTTP 200,
    at most 16 MiB. ``transport`` is an ``agentprov.raw.fetch.Transport`` (the default: ``UrllibTransport``);
    the tests pass a fake. The caller has checked ``--allow-network``."""
    from agentprov.raw.fetch import FetchError, UrllibTransport

    if url != OPENROUTER_URL:
        raise PriceError("only OpenRouter's model list is fetched")
    transport = transport if transport is not None else UrllibTransport()
    response = transport.open(url, headers={"Accept": "application/json", "User-Agent": "agentprov"},
                              unredirected={}, timeout=FETCH_TIMEOUT_S, allowed_hosts=frozenset({OPENROUTER_HOST}))
    try:
        if getattr(response, "status", 200) != 200:
            raise FetchError(f"the server answered HTTP {response.status}", code="raw.fetch.http_status")
        data = response.read(MAX_RESPONSE_BYTES + 1)
    finally:
        response.close()
    if len(data) > MAX_RESPONSE_BYTES:
        raise PriceError("the response is larger than 16 MiB")
    return bytes(data)


def _newest_snapshot(directory: Path) -> Path | None:
    try:
        names = sorted(p for p in directory.glob("openrouter-*.json") if re.fullmatch(
            r"openrouter-\d{4}-\d{2}-\d{2}\.json", p.name))
    except OSError:
        return None
    return names[-1] if names else None


class PriceBook:
    """The prices one estimate reads: overrides, the newest refreshed snapshot and the shipped table."""

    def __init__(self, shipped: Iterable[Price], refreshed: Iterable[Price] = (), overrides: Iterable[Price] = (),
                 *, local_endpoints: Iterable[str] = ("ollama", "omlx"), shipped_header: Mapping[str, Any] | None = None
                 ) -> None:
        self.shipped = {(p.provider, p.model): p for p in shipped}
        self.refreshed = {p.model: p for p in refreshed}
        self.overrides = {p.model: p for p in overrides}
        self.local = frozenset(local_endpoints)
        self.shipped_header = dict(shipped_header or {})
        self.refreshed_as_of = max((p.as_of for p in self.refreshed.values()), default=None)

    @classmethod
    def load(cls, home: Path, overrides: Iterable[Price] | None = None, *,
             local_endpoints: Iterable[str] = ("ollama", "omlx"), shipped: Path = SHIPPED) -> PriceBook:
        """The book of ``home``: its stored overrides (unless given), its newest snapshot and the shipped table."""
        header, rows = load_table(shipped)
        if overrides is None:
            overrides = override_rows(load_overrides(home))
        snap = _newest_snapshot(prices_dir(home))
        refreshed = load_table(snap)[1] if snap is not None else []
        return cls(rows, refreshed, overrides, local_endpoints=local_endpoints, shipped_header=header)

    @property
    def filled(self) -> bool:
        """False while the shipped table holds no rows (it was built before the prices were fetched)."""
        return bool(self.shipped)

    def lookup(self, endpoint: str, model: str) -> Price | None:
        """The price of ``model`` on ``endpoint``, or ``None`` (the estimate then asks for one in Settings)."""
        if endpoint in self.local:
            return Price("local", model, Decimal(0), Decimal(0), None, "local endpoint: no per-token cost",
                         dt.date.today(), "time only")
        key = f"{endpoint}:{model}"
        if key in self.overrides:
            return self.overrides[key]
        if endpoint in DIRECT_VENDOR:
            direct = self.shipped.get((endpoint, model))
            if direct is None and endpoint in ALIAS_PRICED and SNAPSHOT_SUFFIX.search(model):
                alias = SNAPSHOT_SUFFIX.sub("", model)
                found = self.overrides.get(f"{endpoint}:{alias}") or self.shipped.get((endpoint, alias))
                if found is not None:  # Price.model stays the alias: the row the price came from
                    return replace(found, note="; ".join(x for x in (found.note, f"{model} priced as {alias}") if x))
            vendor = DIRECT_VENDOR[endpoint]
            if vendor is None:
                return direct
            routed = f"{vendor}/{model}"
            via = self.refreshed.get(routed) or self.shipped.get(("openrouter", routed))
            if direct is not None and (via is None or direct.as_of >= via.as_of):
                return direct
            if via is not None:
                note = f"OpenRouter's price for {routed}; {endpoint}'s own price may differ"
                return Price(via.provider, via.model, via.input, via.output, via.cached_input, via.source, via.as_of,
                             note)
            return direct
        if endpoint in OPENROUTER_ENDPOINTS:
            fresh, ship = self.refreshed.get(model), self.shipped.get(("openrouter", model))
            if fresh is not None and (ship is None or fresh.as_of >= ship.as_of):
                return fresh
            return ship
        return None

    def models_for(self, endpoint: str) -> list[str]:
        """Model ids the table prices for ``endpoint`` (a completion list for the form; never a default)."""
        if endpoint in DIRECT_VENDOR:
            ids = {m for (p, m) in self.shipped if p == endpoint}
            vendor = DIRECT_VENDOR[endpoint]
            if vendor is None:
                return sorted(ids)
            prefix = vendor + "/"
            ids |= {m[len(prefix):] for m in (*self.refreshed, *(m for (p, m) in self.shipped if p == "openrouter"))
                    if m.startswith(prefix)}
            return sorted(ids)
        if endpoint in OPENROUTER_ENDPOINTS:
            vendor = {"gemini": "google/", "llama": "meta-llama/", "qwen": "qwen/", "glm": "z-ai/"}.get(endpoint, "")
            ids = {m for (p, m) in self.shipped if p == "openrouter"} | set(self.refreshed)
            return sorted(m for m in ids if m.startswith(vendor))
        return []


def override_rows(stored: Mapping[str, Any]) -> list[Price]:
    """The stored overrides: ``{"<endpoint>:<model>": {input, output, cached_input?, as_of}}`` (strictly read)."""
    out = []
    for key, row in stored.items():
        if not isinstance(key, str) or ":" not in key or not isinstance(row, dict):
            continue
        endpoint, model = key.split(":", 1)
        price = _price_from_json({**row, "provider": "override", "model": model,
                                  "source": "your override (agentprov prices set)"}, "")
        if price is not None and re.fullmatch(r"[a-z0-9_-]{1,40}", endpoint):
            out.append(Price("override", key, price.input, price.output, price.cached_input, price.source,
                             price.as_of, cache_write=price.cache_write))
    return out


# ---------------------------------------------------------------------------------------------- the overrides file
def _overrides_path(home: Path) -> Path:
    return prices_dir(home) / "overrides.json"


def load_overrides(home: Path) -> dict[str, Any]:
    """The stored overrides ``{"<endpoint>:<model>": {input, output, cached_input?, cache_write?, as_of}}``, strictly
    read; an unusable file reads as none (``agentprov prices list`` says so)."""
    try:
        with open(_overrides_path(home), "rb") as fh:
            data = fh.read(1024 * 1024 + 1)
    except OSError:
        return {}
    try:
        doc = strict_json_loads(data.rstrip(b"\n"), _LIMITS)
    except IngestError:
        return {}
    if not isinstance(doc, dict) or doc.get("format") != OVERRIDES_FORMAT or not isinstance(doc.get("overrides"), dict):
        return {}
    return dict(doc["overrides"])


def check_override(endpoint: str, model: str, row: Mapping[str, Any]) -> Price:
    """The override ``endpoint:model`` as a price, or :class:`PriceError` naming the refused part."""
    if not ENDPOINT.fullmatch(endpoint):
        raise PriceError("the endpoint is not a registry name")
    if not MODEL_ID.fullmatch(model):
        raise PriceError("the model id is not a plain label")
    for name in ("input", "output", "cached_input", "cache_write"):
        value = row.get(name)
        if (value is not None or name in ("input", "output")) and _decimal(value, per_token=False) is None:
            raise PriceError(f"{name} is not a non-negative decimal below {MAX_PER_M} USD per million tokens")
    prices = override_rows({f"{endpoint}:{model}": dict(row)})
    if not prices:
        raise PriceError("as_of is not a date (YYYY-MM-DD)")
    return prices[0]


def _write_overrides(home: Path, change: Callable[[dict[str, Any]], None]) -> None:
    from agentprov.io.atomic import atomic_write_bytes
    from agentprov.io.locks import ResourceLock

    path = _overrides_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    with ResourceLock(path.with_name("overrides.json.lock"), what="the price overrides", command="prices"):
        values = load_overrides(home)
        change(values)
        if len(values) > MAX_OVERRIDES:
            raise PriceError(f"more than {MAX_OVERRIDES} overrides")
        atomic_write_bytes(path, _dump({"format": OVERRIDES_FORMAT, "overrides": dict(sorted(values.items()))}))


def set_override(home: Path, endpoint: str, model: str, *, input: str, output: str,  # noqa: A002 - the field name
                 cached_input: str | None = None, cache_write: str | None = None,
                 as_of: dt.date | None = None) -> Price:
    row: dict[str, Any] = {"input": input, "output": output, "as_of": (as_of or dt.date.today()).isoformat()}
    if cached_input is not None:
        row["cached_input"] = cached_input
    if cache_write is not None:
        row["cache_write"] = cache_write
    price = check_override(endpoint, model, row)
    _write_overrides(home, lambda values: values.__setitem__(f"{endpoint}:{model}", row))
    return price


def unset_override(home: Path, endpoint: str, model: str) -> bool:
    found = [False]

    def change(values: dict[str, Any]) -> None:
        found[0] = values.pop(f"{endpoint}:{model}", None) is not None

    _write_overrides(home, change)
    return found[0]
