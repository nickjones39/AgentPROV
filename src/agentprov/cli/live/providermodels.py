"""API providers' model lists: fetch (opt-in), a dated cache, and the join with the price table (D-730..D-735).

``agentprov models --endpoint <remote>`` shows the models a provider lists, so the GUI's picker always offers a working
list. Listing models costs no tokens; it is still network egress, so it happens only with ``--allow-network`` (R2) or,
under the user's standing consent (the setting ``models.auto_refresh``, D-733), with ``--refresh-if-stale`` when the
cached list is older than 24 h. Otherwise the dated cache is shown, marked stale when old; nothing is invented.

**Network.** One provider, its registry host only (never a base URL from ``.env``): ``http.client`` over HTTPS with
the default TLS context (certificate and host name verified), no proxy (``http.client`` reads no proxy variables), no
redirect (anything but HTTP 200 is a failure), 20 s timeouts, bodies bounded at 16 MiB, at most 10 pages. The key, when
the provider needs one, travels only in its header; it comes from ``--keychain``, ``--env-stdin`` or ``--env-file``
(never argv) and is registered for redaction before any request.

**Untrusted data.** Each body is parsed by ``agentprov.ingest`` (strict JSON under ``IngestLimits``); only checked
members are kept: ids are labels (:data:`_ID`), names bounded printable text, numbers non-negative integers, OpenRouter
prices decimal strings. Each response's sha256 is kept in the cache and the document.

**Cache.** ``$AGENTPROV_HOME/models-cache/<endpoint>.json`` (``agentprov-provider-models/0.1``), written atomically:
the endpoint, host, ``fetched_at`` (ISO UTC, this machine's clock at the fetch), the responses' digests and the rows.
gemini, llama, qwen and glm are OpenRouter shorthands: their list is OpenRouter's, filtered by vendor prefix.
"""

from __future__ import annotations

import hashlib
import http.client
import re
import ssl
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlencode, urlsplit

from agentprov.errors import AgentProvError, IngestError

__all__ = [
    "CACHE_FORMAT",
    "OPENROUTER_PREFIXES",
    "PROVIDER_ENDPOINTS",
    "STALE_AFTER",
    "ProviderModelError",
    "cache_path",
    "document",
    "fetch",
    "key_variable",
    "listed_ids",
    "read_cache",
    "write_cache",
]

CACHE_FORMAT: Final = "agentprov-provider-models/0.1"
STALE_AFTER: Final = timedelta(hours=24)
MAX_BODY_BYTES: Final = 16 * 1024 * 1024
MAX_PAGES: Final = 10
MAX_MODELS: Final = 10_000
TIMEOUT_S: Final = 20.0
ANTHROPIC_VERSION: Final = "2023-06-01"
#: The remote endpoints with a model list (the registry's non-local names; a test keeps this equal to the registry).
PROVIDER_ENDPOINTS: Final = ("anthropic", "deepseek", "gemini", "glm", "llama", "openai", "openrouter", "qwen")
#: OpenRouter shorthands: the vendor prefixes of their model ids (OpenRouter's own id scheme).
OPENROUTER_PREFIXES: Final[Mapping[str, tuple[str, ...]]] = {
    "gemini": ("google/",), "llama": ("meta-llama/",), "qwen": ("qwen/",), "glm": ("z-ai/", "thudm/"),
}
_ID = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.:@+/ -]{0,199}")
_DECIMAL = re.compile(r"-?[0-9]{1,12}(\.[0-9]{1,20})?([eE]-?[0-9]{1,3})?")
_STAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,9})?Z")


class ProviderModelError(AgentProvError):
    """A provider-list condition: exit 3 (unreachable, refused, malformed) or 2 (usage). No response text is quoted."""

    code = "models.provider"
    exit_code = 3


def _fail(code: str, message: str, exit_code: int = 3) -> ProviderModelError:
    return ProviderModelError(message, code=f"models.provider.{code}", exit_code=exit_code)


# ---------------------------------------------------------------------------------------------------------- checks


def _label(value: Any) -> str | None:
    return value if isinstance(value, str) and _ID.fullmatch(value) and ".." not in value.split("/") else None


def _text(value: Any, limit: int = 160) -> str | None:
    return value if isinstance(value, str) and value and len(value) <= limit and value.isprintable() else None


def _count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 2**53 else None


def _decimal(value: Any) -> str | None:
    return value if isinstance(value, str) and _DECIMAL.fullmatch(value) else None


def _stamp(value: Any) -> str | None:
    return value if isinstance(value, str) and len(value) <= 40 and _STAMP.fullmatch(value) else None


def _drop_none(d: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}


def _strict(body: bytes) -> Any:
    from agentprov.ingest.limits import IngestLimits
    from agentprov.ingest.loaders import strict_json_loads

    try:
        return strict_json_loads(body, IngestLimits())
    except IngestError:
        return None


# ---------------------------------------------------------------------------------------------------------- fetch


@dataclass(frozen=True)
class Fetched:
    path: str
    status: int
    sha256: str
    body: bytes

    def cite(self) -> dict[str, Any]:
        return {"path": self.path, "status": self.status, "sha256": self.sha256}


Connection = Callable[[str, int, float], http.client.HTTPConnection]


def _https(host: str, port: int, timeout: float) -> http.client.HTTPConnection:
    return http.client.HTTPSConnection(host, port, timeout=timeout, context=ssl.create_default_context())


def _target(endpoint: str) -> tuple[Any, str, int, str]:
    """``(registry entry, host, port, base path)``: always the registry's base URL (egress to that host only)."""
    from agentprov_capture.endpoints import EndpointError, get_endpoint

    try:
        entry = get_endpoint(endpoint)
    except EndpointError:
        raise _fail("unknown", "unknown endpoint", exit_code=2) from None
    if entry.local or endpoint not in PROVIDER_ENDPOINTS:
        raise _fail("not_provider", "not an API provider endpoint (local servers are listed by discovery)", exit_code=2)
    parts = urlsplit(entry.base_url)
    if parts.scheme != "https" or not parts.hostname:
        raise _fail("url", "the registry base URL is not https")
    return entry, parts.hostname, parts.port or 443, parts.path.rstrip("/")


def key_variable(endpoint: str) -> tuple[str | None, bool]:
    """``(key variable, required)``. OpenRouter documents its list as public, so its key is optional: sent only when
    the caller supplied one explicitly; the other providers require theirs."""
    entry, _host, _port, _base = _target(endpoint)
    variable = entry.api_key_env if isinstance(entry.api_key_env, str) else None
    return variable, not (endpoint == "openrouter" or endpoint in OPENROUTER_PREFIXES)


def _get(conn_factory: Connection, host: str, port: int, path: str, headers: Mapping[str, str]) -> Fetched:
    conn = conn_factory(host, port, TIMEOUT_S)
    try:
        try:
            conn.request("GET", path, headers={"Accept": "application/json", "User-Agent": "agentprov-models",
                                               **headers})
            resp = conn.getresponse()
            status = resp.status
            body = resp.read(MAX_BODY_BYTES + 1)
        except (OSError, http.client.HTTPException, ValueError):
            raise _fail("unreachable", "the provider did not answer") from None
    finally:
        conn.close()
    if len(body) > MAX_BODY_BYTES:
        raise _fail("too_large", "the model list is larger than the limit")
    if status != 200:  # a redirect is never followed; an auth failure is a status, never a body quoted here
        raise _fail("http_status", f"the provider answered HTTP {status}")
    return Fetched(path, status, "sha256:" + hashlib.sha256(body).hexdigest(), bytes(body))


def _openai_rows(doc: Any) -> list[dict[str, Any]] | None:
    data = doc.get("data") if isinstance(doc, Mapping) else None
    if not isinstance(data, list):
        return None
    rows = []
    for item in data[:MAX_MODELS]:
        if not isinstance(item, Mapping) or (ident := _label(item.get("id"))) is None:
            continue
        rows.append(_drop_none({"id": ident, "display_name": _text(item.get("name")), "owned_by": _text(item.get("owned_by"), 80),
                                "created": _count(item.get("created")),
                                "context_length": _count(item.get("context_length")) or _count(item.get("context_window"))}))
    return rows


def _openrouter_rows(doc: Any) -> list[dict[str, Any]] | None:
    data = doc.get("data") if isinstance(doc, Mapping) else None
    if not isinstance(data, list):
        return None
    rows = []
    for item in data[:MAX_MODELS]:
        if not isinstance(item, Mapping) or (ident := _label(item.get("id"))) is None:
            continue
        raw_pricing = item.get("pricing")
        pricing: Mapping[str, Any] = raw_pricing if isinstance(raw_pricing, Mapping) else {}
        listed_price = _drop_none({"prompt": _decimal(pricing.get("prompt")),
                                   "completion": _decimal(pricing.get("completion"))})
        rows.append(_drop_none({"id": ident, "display_name": _text(item.get("name")), "created": _count(item.get("created")),
                                "context_length": _count(item.get("context_length")),
                                "listed_price_per_token": listed_price or None}))
    return rows


def _anthropic_rows(doc: Any) -> tuple[list[dict[str, Any]], str | None] | None:
    data = doc.get("data") if isinstance(doc, Mapping) else None
    if not isinstance(data, list):
        return None
    rows = []
    for item in data[:MAX_MODELS]:
        if not isinstance(item, Mapping) or (ident := _label(item.get("id"))) is None:
            continue
        lifecycle = item.get("lifecycle") if item.get("lifecycle") in ("active", "deprecated", "retired") else None
        rows.append(_drop_none({"id": ident, "display_name": _text(item.get("display_name")),
                                "created_at": _stamp(item.get("created_at")), "lifecycle": lifecycle,
                                "context_length": _count(item.get("max_input_tokens")),
                                "max_tokens": _count(item.get("max_tokens"))}))
    nxt = _label(doc.get("last_id")) if doc.get("has_more") is True else None
    return rows, nxt


def fetch(endpoint: str, keys: Mapping[str, str], *, connection: Connection | None = None,
          now: datetime | None = None) -> dict[str, Any]:
    """The provider's model list now, as the cache document (not yet written). Exit 3 on any failure."""
    entry, host, port, base = _target(endpoint)
    factory = connection or _https
    key = keys.get(entry.api_key_env) if entry.api_key_env else None
    source = "openrouter" if endpoint in OPENROUTER_PREFIXES or endpoint == "openrouter" else endpoint
    fetched: list[Fetched] = []
    rows: list[dict[str, Any]] = []
    if source == "anthropic":
        if not key:
            raise _fail("credential", f"the key variable {entry.api_key_env} is needed to list Anthropic's models",
                        exit_code=3)
        after: str | None = None
        for _page in range(MAX_PAGES):
            query = {"limit": "1000", **({"after_id": after} if after else {})}
            got = _get(factory, host, port, f"{base}/v1/models?{urlencode(query)}",
                       {"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION})
            fetched.append(got)
            parsed = _anthropic_rows(_strict(got.body))
            if parsed is None:
                raise _fail("bad_list", "the model list is not the documented shape")
            page_rows, after = parsed
            rows += page_rows
            if after is None:
                break
    else:
        headers: dict[str, str] = {}
        if source in ("openai", "deepseek") and not key:
            raise _fail("credential", f"the key variable {entry.api_key_env} is needed to list this provider's models")
        if key:  # required for OpenAI and DeepSeek; optional for OpenRouter (given only when the caller supplied it)
            headers["Authorization"] = f"Bearer {key}"
        path = "/models" if source == "deepseek" else f"{base}/models"  # DeepSeek documents GET /models at the host root
        got = _get(factory, host, port, path, headers)
        fetched.append(got)
        parsed_rows = (_openrouter_rows if source == "openrouter" else _openai_rows)(_strict(got.body))
        if parsed_rows is None:
            raise _fail("bad_list", "the model list is not the documented shape")
        rows = parsed_rows
        if endpoint in OPENROUTER_PREFIXES:
            rows = [r for r in rows if r["id"].startswith(OPENROUTER_PREFIXES[endpoint])]
    unique = {r["id"]: r for r in rows}
    return {"format": CACHE_FORMAT, "endpoint": endpoint, "host": host,
            "fetched_at": (now or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "responses": [f.cite() for f in fetched], "models": [unique[k] for k in sorted(unique)]}


# ---------------------------------------------------------------------------------------------------------- cache


def cache_path(home: Path, endpoint: str) -> Path:
    return home / "models-cache" / f"{endpoint}.json"


def write_cache(home: Path, doc: Mapping[str, Any]) -> Path:
    from agentprov.io.atomic import atomic_write_bytes
    from agentprov.io.canonical import jcs_bytes

    path = cache_path(home, str(doc["endpoint"]))
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_write_bytes(path, jcs_bytes(dict(doc)) + b"\n", mode=0o600)
    return path


def read_cache(home: Path, endpoint: str) -> dict[str, Any] | None:
    """The cached list, or ``None`` (absent or not a valid cache document: a damaged cache is never half-read)."""
    path = cache_path(home, endpoint)
    try:
        if not path.is_file() or path.stat().st_size > MAX_BODY_BYTES:
            return None
        doc = _strict(path.read_bytes())
    except OSError:
        return None
    if not isinstance(doc, dict) or doc.get("format") != CACHE_FORMAT or doc.get("endpoint") != endpoint:
        return None
    if _stamp(doc.get("fetched_at")) is None or not isinstance(doc.get("models"), list):
        return None
    if not all(isinstance(m, dict) and _label(m.get("id")) for m in doc["models"]):
        return None
    return doc


def age(doc: Mapping[str, Any], now: datetime | None = None) -> timedelta:
    fetched = datetime.strptime(str(doc["fetched_at"])[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=UTC)
    return (now or datetime.now(UTC)) - fetched


def listed_ids(doc: Mapping[str, Any] | None) -> set[str]:
    return {str(m["id"]) for m in (doc or {}).get("models", ()) if isinstance(m, Mapping)}


# ---------------------------------------------------------------------------------------------------------- output


def document(endpoint: str, cache: Mapping[str, Any] | None, *, source: str, price_book: Any = None,
             now: datetime | None = None, refresh_error: str | None = None) -> dict[str, Any]:
    """The ``models`` output for a provider: the cached (or just fetched) list, its age, and each model's price status
    from the price table (D-701): ``priced`` or ``no_price``; priced models the provider no longer lists are
    ``not_listed``. ``source`` is ``network``, ``cache`` or ``none``."""
    models: list[dict[str, Any]] = []
    covered: set[str] = set()  # the price-table names the listed models are priced under (an alias, for a dated id)
    for row in (cache or {}).get("models", ()):
        price = price_book.lookup(endpoint, row["id"]) if price_book is not None else None
        entry = {**row, "listed": True, "price_status": "priced" if price is not None else "no_price"}
        if price is not None:
            priced_as = getattr(price, "model", None)
            covered.add(str(priced_as) if priced_as else row["id"])
            if priced_as and priced_as != row["id"]:
                entry["priced_as"] = priced_as  # D-701 follow-up: an Anthropic snapshot id priced by its alias
        models.append(entry)
    not_listed = []
    if price_book is not None and cache is not None:
        listed = {m["id"] for m in models}
        not_listed = [{"id": mid, "listed": False, "price_status": "priced"}
                      for mid in price_book.models_for(endpoint) if mid not in listed and mid not in covered]
    out: dict[str, Any] = {
        "format": CACHE_FORMAT, "endpoint": endpoint, "host": (cache or {}).get("host"),
        "fetched_at": (cache or {}).get("fetched_at"), "source": source,
        "stale": cache is None or age(cache, now) > STALE_AFTER,
        "responses": list((cache or {}).get("responses", ())), "models": models, "not_listed": not_listed,
    }
    if refresh_error is not None:
        out["refresh_error"] = refresh_error
    return out
