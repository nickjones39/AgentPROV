"""``agentprov prices``: the model prices the estimate reads (D-701; D-650; reverse CLI parity D-700).

    agentprov prices list [--endpoint NAME] [--format text|json]
    agentprov prices get ENDPOINT MODEL [--format text|json]
    agentprov prices set ENDPOINT MODEL --input USD --output USD [--cached-input USD] [--cache-write USD] [--as-of DATE]
    agentprov prices unset ENDPOINT MODEL
    agentprov prices refresh --allow-network | --from-file RESPONSE.json [--fetched DATE]

Prices are USD per million tokens (:mod:`agentprov.estimate.prices`). An override wins over a refreshed OpenRouter
snapshot, which wins over the shipped table where it is newer; a local endpoint costs nothing per token. ``refresh``
reads one public URL (OpenRouter's model list, no key) and needs ``--allow-network`` (exit 4 without it); the
response is untrusted, parsed strictly, and only ids and prices are kept. ``--from-file`` imports a response saved
earlier instead (no network).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

from agentprov.cli.common import CliUsageError, CommandResult, Context, safe_text

LIST_FORMAT = "agentprov-prices-list/0.1"


def register(sub: Any, shared: argparse.ArgumentParser) -> None:
    p = sub.add_parser("prices", parents=[shared], help="list, set or refresh the model prices the estimate uses",
                       description=__doc__.splitlines()[0], allow_abbrev=False)
    p.set_defaults(command="prices", handler=run_prices, feedback=False)
    actions = p.add_subparsers(dest="prices_action", metavar="ACTION", required=True)
    ls = actions.add_parser("list", parents=[shared], help="the price sources and every priced model per endpoint",
                            allow_abbrev=False)
    ls.add_argument("--endpoint", metavar="NAME", help="only this endpoint of endpoints.toml")
    ls.add_argument("--format", choices=["text", "json"], default="text")
    g = actions.add_parser("get", parents=[shared], help="the price one estimate would use (nothing when unpriced)",
                           allow_abbrev=False)
    g.add_argument("endpoint", metavar="ENDPOINT")
    g.add_argument("model", metavar="MODEL")
    g.add_argument("--format", choices=["text", "json"], default="text")
    s = actions.add_parser("set", parents=[shared], help="store a per-model override (USD per million tokens)",
                           allow_abbrev=False)
    s.add_argument("endpoint", metavar="ENDPOINT")
    s.add_argument("model", metavar="MODEL")
    s.add_argument("--input", required=True, metavar="USD", help="input tokens (uncached)")
    s.add_argument("--output", required=True, metavar="USD", help="output tokens (reasoning included)")
    s.add_argument("--cached-input", metavar="USD", help="cache reads (default: the input price)")
    s.add_argument("--cache-write", metavar="USD", help="5-minute cache writes (default: the input price)")
    s.add_argument("--as-of", metavar="YYYY-MM-DD", help="the date of the price (default: today)")
    u = actions.add_parser("unset", parents=[shared], help="remove an override", allow_abbrev=False)
    u.add_argument("endpoint", metavar="ENDPOINT")
    u.add_argument("model", metavar="MODEL")
    r = actions.add_parser("refresh", parents=[shared],
                           help="fetch OpenRouter's model list into a dated snapshot (network; confirm first)",
                           allow_abbrev=False)
    source = r.add_mutually_exclusive_group()
    source.add_argument("--allow-network", action="store_true", help="required to fetch (one public URL, no key)")
    source.add_argument("--from-file", metavar="RESPONSE.json", help="import a saved /api/v1/models response instead")
    r.add_argument("--fetched", metavar="YYYY-MM-DD", help="with --from-file: the date it was fetched (default: today)")


def _payload(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"


def _date(value: str | None, what: str) -> dt.date | None:
    if value is None:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise CliUsageError(f"agentprov prices: {what} is not a date (YYYY-MM-DD)") from None


def endpoint_table() -> dict[str, Any]:
    """The endpoint registry (names, whether local); a seam for the tests."""
    from agentprov_capture.endpoints import load_endpoints

    return load_endpoints()


def local_endpoints() -> list[str]:
    return sorted(name for name, e in endpoint_table().items() if e.local)


def book(home: Path) -> Any:
    from agentprov.estimate.prices import PriceBook

    return PriceBook.load(home, local_endpoints=local_endpoints())


def _row(price: Any, today: dt.date) -> dict[str, Any]:
    from agentprov.estimate.prices import stale

    return {**price.to_json(), "stale": stale(price, today)}


def _listing(home: Path, only: str | None) -> dict[str, Any]:
    from agentprov.estimate.prices import STALE_DAYS, load_overrides

    endpoints = endpoint_table()
    if only is not None and only not in endpoints:
        raise CliUsageError(f"agentprov prices: unknown endpoint {safe_text(only, 40)!r} (endpoints.toml)")
    b = book(home)
    today = dt.date.today()
    stored = load_overrides(home)
    rows = []
    for name in sorted(endpoints):
        if only is not None and name != only:
            continue
        mine = {k.split(":", 1)[1] for k in stored if isinstance(k, str) and k.startswith(f"{name}:")}
        models = sorted(set(b.models_for(name)) | mine)
        local = bool(endpoints[name].local)
        priced = [] if local else [(m, p) for m in models if (p := b.lookup(name, m)) is not None]
        rows.append({"name": name, "local": local, "models": [{"id": m, **_row(p, today)} for m, p in priced]})
    header = b.shipped_header
    return {
        "format": LIST_FORMAT, "stale_days": STALE_DAYS,
        "shipped": {"rows": len(b.shipped), "as_of": header.get("as_of"), "oldest": header.get("oldest"),
                    "openrouter": header.get("openrouter")},
        "refreshed": {"rows": len(b.refreshed),
                      "as_of": b.refreshed_as_of.isoformat() if b.refreshed_as_of else None},
        "overrides": [{"key": p.model, **_row(p, today)} for p in sorted(b.overrides.values(), key=lambda p: p.model)],
        "overrides_ignored": sorted(set(stored) - set(b.overrides)),
        "endpoints": rows,
    }  # fmt: skip


def run_prices(ctx: Context) -> CommandResult:
    from agentprov.cli.live.envs import agentprov_home
    from agentprov.estimate import prices as P

    args = ctx.args
    home = agentprov_home(ctx.env)
    result = CommandResult()
    action = args.prices_action
    if action == "list":
        doc = _listing(home, args.endpoint)
        if args.format == "json":
            result.payload = _payload(doc)
        else:
            sh, rf = doc["shipped"], doc["refreshed"]
            result.output(f"shipped table: {sh['rows']} prices as of {sh['as_of']}")
            result.output(f"refreshed OpenRouter snapshot: {rf['rows']} prices as of {rf['as_of'] or 'none'}")
            result.output(f"overrides: {len(doc['overrides'])}")
            for e in doc["endpoints"]:
                if e["local"]:
                    result.output(f"  {e['name']}: local endpoint, no per-token cost")
                elif args.endpoint is None:
                    result.output(f"  {e['name']}: {len(e['models'])} priced model(s)")
                else:
                    for m in e["models"]:
                        result.output(f"  {safe_text(m['id'], 120)}  in {m['input']}  out {m['output']}  cached "
                                      f"{m['cached_input'] or '-'}  as of {m['as_of']}{'  STALE' if m['stale'] else ''}"
                                      f"  ({safe_text(m['source'], 120)})")
        for key in doc["overrides_ignored"]:
            result.notices.append(f"ignored stored override: {safe_text(str(key), 120)}")
        result.counters = {"endpoints": len(doc["endpoints"]), "overrides": len(doc["overrides"])}
    elif action == "get":
        if args.endpoint not in endpoint_table():
            raise CliUsageError(f"agentprov prices: unknown endpoint {safe_text(args.endpoint, 40)!r} (endpoints.toml)")
        price = book(home).lookup(args.endpoint, args.model)
        if args.format == "json":
            result.payload = _payload(None if price is None else _row(price, dt.date.today()))
        elif price is not None:  # the value is what was asked for: stdout, as settings get
            result.payload = (safe_text(f"input {price.input}, output {price.output}, cached input "
                                        f"{price.cached_input if price.cached_input is not None else '-'} USD per "
                                        f"million tokens; {price.source}, as of {price.as_of.isoformat()}", 600)
                              + "\n").encode("utf-8")
    elif action in ("set", "unset"):
        if args.endpoint not in endpoint_table():
            raise CliUsageError(f"agentprov prices: unknown endpoint {safe_text(args.endpoint, 40)!r} (endpoints.toml)")
        try:
            if action == "set":
                price = P.set_override(home, args.endpoint, args.model, input=args.input, output=args.output,
                                       cached_input=args.cached_input, cache_write=args.cache_write,
                                       as_of=_date(args.as_of, "--as-of"))
                result.info(f"prices: override {safe_text(price.model, 160)} stored")
            else:
                removed = P.unset_override(home, args.endpoint, args.model)
                result.info(f"prices: override {safe_text(args.endpoint + ':' + args.model, 160)} "
                            + ("removed" if removed else "was not set"))
        except P.PriceError as exc:
            raise CliUsageError(f"agentprov prices {action}: {exc}") from None
    elif action == "refresh":
        result.payload = None
        if args.from_file is not None:
            data = _read_response(Path(args.from_file))
            fetched = _date(args.fetched, "--fetched") or dt.datetime.now(dt.UTC).date()
        else:
            from agentprov.raw.fetch import NetworkRefusedError

            if args.fetched is not None:
                raise CliUsageError("agentprov prices refresh: --fetched goes with --from-file")
            if not args.allow_network:
                raise NetworkRefusedError("agentprov prices refresh reads OpenRouter's public model list: give "
                                          "--allow-network (or --from-file with a saved response)")
            data = P.fetch_openrouter(transport())
            fetched = dt.datetime.now(dt.UTC).date()
        path, n = P.import_response(home, data, fetched=fetched)
        result.output(f"prices: {n} OpenRouter prices as of {fetched.isoformat()} into {path.name}")
        result.counters = {"prices": n}
    return result


def transport() -> Any:
    """The HTTP transport of ``refresh`` (``UrllibTransport``); a seam for the tests, which never open a socket."""
    from agentprov.raw.fetch import UrllibTransport

    return UrllibTransport()


def _read_response(path: Path) -> bytes:
    from agentprov.estimate.prices import MAX_RESPONSE_BYTES

    try:
        with open(path, "rb") as fh:
            data = fh.read(MAX_RESPONSE_BYTES + 1)
    except OSError as exc:
        raise CliUsageError(f"agentprov prices refresh: --from-file cannot be read ({type(exc).__name__})") from None
    return data
