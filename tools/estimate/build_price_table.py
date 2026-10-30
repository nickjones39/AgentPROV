"""Build the shipped price table ``src/agentprov/estimate/data/prices.json`` (D-650, D-701):

    uv run python tools/estimate/build_price_table.py --openrouter SNAPSHOT.json --fetched YYYY-MM-DD

``SNAPSHOT.json`` is a saved OpenRouter ``/api/v1/models`` response (untrusted: parsed by ``parse_openrouter``,
through ``agentprov.ingest``; only ids and prices are kept, never names or descriptions). The direct-provider rows
come from ``tools/estimate/price_direct.toml``. The table records the snapshot's sha256 and date; the snapshot itself
is not committed. No network: fetching is a separate, confirmed step (``agentprov prices refresh --allow-network``
writes a snapshot of ids and prices only; a saved raw response comes from fetching the URL yourself).
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import tomllib
from pathlib import Path

from agentprov.estimate.prices import (
    OPENROUTER_URL,
    PRICES_FORMAT,
    SHIPPED,
    Price,
    PriceError,
    _decimal,
    parse_openrouter,
)

HERE = Path(__file__).resolve().parent


def direct_rows(path: Path) -> list[Price]:
    doc = tomllib.loads(path.read_text(encoding="utf-8"))
    out: list[Price] = []
    for provider in ("openai", "deepseek", "anthropic"):
        for block in doc.get(provider, []):
            as_of = dt.date.fromisoformat(block["as_of"])
            for row in block["rows"]:
                pin, pout = _decimal(row["input"], per_token=False), _decimal(row["output"], per_token=False)
                cached = None if row.get("cached_input") is None else _decimal(row["cached_input"], per_token=False)
                if pin is None or pout is None:
                    raise SystemExit(f"{provider} {row['model']}: a price is not a valid decimal")
                write = None if row.get("cache_write") is None else _decimal(row["cache_write"], per_token=False)
                out.append(Price(provider, row["model"], pin, pout, cached, block["source"], as_of, row.get("note", ""),
                                 write))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--openrouter", type=Path, help="a saved OpenRouter /api/v1/models response")
    ap.add_argument("--fetched", help="the snapshot's fetch date (UTC, YYYY-MM-DD)")
    ap.add_argument("--direct", type=Path, default=HERE / "price_direct.toml")
    ap.add_argument("--out", type=Path, default=SHIPPED)
    args = ap.parse_args(argv)
    rows = direct_rows(args.direct)
    header: dict[str, object] = {"format": PRICES_FORMAT, "direct": str(args.direct.name)}
    if args.openrouter is not None:
        if not args.fetched:
            ap.error("--openrouter needs --fetched")
        data = args.openrouter.read_bytes()
        fetched = dt.date.fromisoformat(args.fetched)
        try:
            routed = parse_openrouter(data, fetched=fetched)
        except PriceError as exc:
            print(f"build_price_table: {exc}", file=sys.stderr)
            return 1
        rows += routed
        header["openrouter"] = {"source": OPENROUTER_URL, "fetched": fetched.isoformat(),
                                "raw_sha256": hashlib.sha256(data).hexdigest(), "models": len(routed)}
    dates = sorted({r.as_of for r in rows})
    header["as_of"] = dates[-1].isoformat() if dates else None
    header["oldest"] = dates[0].isoformat() if dates else None
    doc = {**header, "rows": [r.to_json() for r in sorted(rows, key=lambda r: (r.provider, r.model))]}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    head = json.dumps(header, sort_keys=True, separators=(",", ":"))[:-1]  # one row per line keeps diffs readable
    lines = [json.dumps(r, sort_keys=True, separators=(",", ":")) for r in doc["rows"]]
    args.out.write_text(head + ',"rows":[\n' + ",\n".join(lines) + "\n]}\n", encoding="utf-8")
    print(f"build_price_table: {len(rows)} rows -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
