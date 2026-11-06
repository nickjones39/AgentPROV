"""D-1090: ``agentprov estimate``'s suggested caps (``quote.caps``): the quote's p90 calls and upper cost times
``1 + margin``, plus room for the cells that run at once and every preflight probe attempt at their worst case, priced
at the cap prices; the cost's p90 priced as the run counts spend (every input-side token at the cap input price); calls
rounded up to a whole call and USD up to the cent; none, with the reason, when nothing can be suggested."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from agentprov.cli.estimate import caps_line, suggested_caps
from agentprov.estimate.plan import CellBound
from agentprov.estimate.prices import Price

PRICE = Price("openrouter", "vendor/m", Decimal("2.5"), Decimal("10"), Decimal("1.25"), "test", dt.date(2026, 11, 1))
BOUND = CellBound(48, 1, 32_000, 4_096)


def _caps(*, units: int = 4, calls: float = 100.0, cost: str | None = "1.00", sources: dict[str, int] | None = None,
          bound: CellBound | None = BOUND, settled: int = 0, price: Any = PRICE, jobs: int = 1, margin: str = "20",
          real: bool = True, price_in: float | None = None, price_out: float | None = None,
          capped: str | None = None) -> dict[str, Any]:
    e = SimpleNamespace(units=units, calls_p90=calls, cost_p90=None if cost is None else Decimal(cost),
                        sources=sources if sources is not None else {"priors": units})
    plan = SimpleNamespace(cell_bound=bound, settled=settled)
    at_caps = capped if capped is not None else cost  # the quote's cost priced at the cap prices (the same here)
    return suggested_caps(e, plan, price, real=real, jobs=jobs, margin_pct=Decimal(margin), margin_from="default",
                          price_in=price_in, price_out=price_out,
                          cost_at_cap_prices=None if at_caps is None else Decimal(at_caps))


def test_the_caps_are_the_quote_plus_margin_plus_the_reserved_worst_case() -> None:
    c = _caps()
    # one call at the bound: 32,000 x 2.5 + 4,096 x 10 per million = $0.12096; a cell 48 of them, a probe attempt 1,
    # and the run sends up to PROBE_ATTEMPTS (3) probes while the verdict is unconfirmed, each charged step_calls
    call_usd = (Decimal(32_000) * Decimal("2.5") + Decimal(4_096) * 10) / 1_000_000
    assert c["available"] is True and c["reason"] is None
    assert c["max_calls"] == 120 + 48 + 3  # ceil(100 x 1.2) + one cell + the probe's three attempts
    assert Decimal(c["max_cost_usd"]) == (Decimal("1.20") + 51 * call_usd).quantize(Decimal("0.01"), "ROUND_CEILING")
    assert c["max_cost_usd"] == "7.37" and c["cell_usd"] == "5.81" and c["probe_usd"] == "0.37"
    assert c["probe_calls"] == 3
    assert (c["price_in"], c["price_out"], c["margin_pct"], c["reserved_cells"]) == ("2.5", "10", "20", 1)
    assert (c["calls_basis"], c["cost_basis"]) == ("calls_p90", "usd_p90")


def test_the_room_is_for_the_cells_that_run_at_once() -> None:
    assert _caps(jobs=3)["reserved_cells"] == 3 and _caps(jobs=3)["max_calls"] == 120 + 3 * 48 + 3
    assert _caps(jobs=8, units=2)["reserved_cells"] == 2  # never more cells than are due
    wide = _caps(bound=CellBound(384, 8, 32_000, 4_096))  # gateway_compat (AU-LIVE-1)
    assert wide["max_calls"] == 120 + 384 + 3 * 8 and wide["probe_calls"] == 24


def test_rounding_is_up_and_the_margin_and_prices_are_honoured() -> None:
    assert _caps(calls=100.01, margin="0")["max_calls"] == 101 + 51
    assert _caps(margin="50")["max_calls"] == 150 + 51
    typed = _caps(price_in=3.0, price_out=15.0)  # the cap prices the user typed (run's --price-in/--price-out)
    assert (typed["price_in"], typed["price_out"]) == ("3", "15") and typed["cell_usd"] == "7.56"
    write = Price("anthropic", "m", Decimal("3"), Decimal("15"), Decimal("0.3"), "t", dt.date(2026, 11, 1),
                  cache_write=Decimal("3.75"))
    assert _caps(price=write)["price_in"] == "3.75"  # the input side is the highest of input, cached and cache write


def test_no_suggestion_says_why() -> None:
    cases = {
        "a scripted run is not billed": _caps(real=False),
        "the model has no price": _caps(price=None),
        "no cell run is left": _caps(units=0),
        "only your default assumptions": _caps(sources={"default": 4}),
        "the run's per-cell bound is unknown: no call bound": _caps(bound=CellBound(refused="no call bound")),
    }
    for words, c in cases.items():
        assert c["available"] is False and words in c["reason"] and c["max_calls"] is None, words
        assert caps_line(c).startswith("Suggested caps: none (") and "yourself" in caps_line(c)
    assert _caps(cost=None)["available"] is False
    assert _caps(capped=None, cost="1.00")["available"] is True and _caps(cost=None, capped="1.00")["available"] is False
    assert _caps(sources={"default": 2, "priors": 2})["available"] is True  # partly recorded figures still fill


def test_the_text_line_names_the_figures_and_a_resumed_corpus() -> None:
    line = caps_line(_caps())
    assert line.startswith("Suggested caps: --max-calls 171 --max-cost-usd 7.37 --price-in 2.5 --price-out 10: ")
    assert "plus 20 %" in line and "1 cell(s) at their worst case (48 billed calls, $5.81 each)" in line
    assert "the preflight probe's attempts (3 billed calls, $0.37)" in line
    assert "settled" not in line and "settled unit(s)" in caps_line(_caps(settled=3))


def test_the_cost_base_is_priced_as_the_run_counts_spend() -> None:
    """The run counts every input-side token (input, cache read and cache write) at --price-in (Budget.charge), so the
    quote's cached-input discount and cache-write price would leave the cap below what the run counts: an input-heavy
    Anthropic loop (cache write 1.25 x input) ran about 20 % over the quote, so a run that spent what the quote says
    stopped at cap_reached. The base is the quote's tokens priced at the cap prices (cap_price), not its own figure."""
    from agentprov.cli.estimate import cap_price
    from agentprov.estimate.cost import CellStats, Quantiles, _call_cost

    anthropic = Price("anthropic", "m", Decimal("3"), Decimal("15"), Decimal("0.3"), "t", dt.date(2026, 11, 1),
                      cache_write=Decimal("3.75"))
    at_caps = cap_price(anthropic, None, None)
    assert (at_caps.input, at_caps.output, at_caps.cached_input, at_caps.cache_write) == (Decimal("3.75"),
                                                                                          Decimal("15"), None, None)
    stats = CellStats(calls=Quantiles(1, 1), tokens_in=Quantiles(1_000_000, 1_000_000),
                      tokens_cached=Quantiles(600_000, 600_000), tokens_out=Quantiles(0, 0), seconds=Quantiles(1, 1),
                      source="priors")
    assert _call_cost(stats, anthropic, "p90") == Decimal("1.38")  # 0.4 M at $3 + 0.6 M cached at $0.30
    assert _call_cost(stats, at_caps, "p90") == Decimal("3.75")  # what the run counts for the same tokens
    c = _caps(price=anthropic, cost="1.38", capped="3.75", margin="0", bound=CellBound(1, 1, 1, 1))
    assert Decimal(c["max_cost_usd"]) >= Decimal("3.75")  # a run that spends what the quote says can finish
    before = _caps(price=anthropic, cost="1.38", capped="1.38", margin="0", bound=CellBound(1, 1, 1, 1))
    assert Decimal(before["max_cost_usd"]) < Decimal("3.75")  # the base the quote's own figure gave
